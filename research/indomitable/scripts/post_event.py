#!/usr/bin/env python3
"""
Post-event scoring: compare actuals to expectations.

After an earnings filing arrives, extracts actuals, scores each expectation,
checks kill criteria, updates management scorecard, and outputs a scorecard.
Claude interprets the overall thesis impact.

Usage:
    python post_event.py --ticker CRK --filing-id 72
    python post_event.py --ticker CRK --filing-id 72 --period "Q4 2025"
"""

import sys
import json
from datetime import datetime
from psycopg2.extras import RealDictCursor
from config import connect_db, get_anthropic_client, parse_claude_json, MODEL
from financial_model import EPModel


def get_active_thesis(conn, company_id):
    """Get the active investment thesis."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT it.*, c.ticker, c.company_name
        FROM investment_theses it
        JOIN companies c ON c.id = it.company_id
        WHERE it.company_id = %s AND it.is_active = TRUE AND it.is_draft = FALSE
        ORDER BY it.created_at DESC LIMIT 1
    """, (company_id,))
    row = cursor.fetchone()
    cursor.close()
    return row


def get_published_expectations(conn, company_id, period=None):
    """Get published expectations, optionally for a specific period."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    if period:
        cursor.execute("""
            SELECT * FROM expectations
            WHERE company_id = %s AND period = %s AND published = TRUE
            ORDER BY metric_name
        """, (company_id, period))
    else:
        cursor.execute("""
            SELECT * FROM expectations
            WHERE company_id = %s AND published = TRUE
            AND id NOT IN (SELECT expectation_id FROM expectation_results)
            ORDER BY period DESC, metric_name
        """, (company_id,))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_filing_metrics(conn, filing_id):
    """Get extracted metrics from a filing as a dict."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT metric_name, metric_value, metric_unit, metric_period
        FROM extracted_metrics WHERE filing_id = %s
    """, (filing_id,))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_kill_criteria(conn, thesis_id):
    """Get untriggered kill criteria."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT * FROM kill_criteria
        WHERE thesis_id = %s AND triggered = FALSE
        ORDER BY id
    """, (thesis_id,))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_hypotheses(conn, thesis_id):
    """Get active hypotheses."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT * FROM hypotheses
        WHERE thesis_id = %s AND status IN ('active', 'strengthened', 'weakened')
        ORDER BY id
    """, (thesis_id,))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_pending_scorecard(conn, company_id):
    """Get pending management promises."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT * FROM management_scorecard
        WHERE company_id = %s AND assessment = 'pending'
        ORDER BY promise_date
    """, (company_id,))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def build_actuals_from_metrics(metrics_rows):
    """Build actuals dict from extracted metrics, mapping common metric names."""
    actuals = {}
    for m in metrics_rows:
        name = m['metric_name']
        val = m['metric_value']
        if val is not None:
            actuals[name] = float(val)

    # Map common alternate names to canonical names
    mappings = {
        'total_revenue': 'revenue',
        'net_revenue': 'revenue',
        'total_operating_revenue': 'revenue',
        'capital_expenditures': 'capex',
        'capital_expenditure': 'capex',
        'capex_total': 'capex',
        'cash_from_operations': 'operating_cash_flow',
        'net_cash_from_operating': 'operating_cash_flow',
        'ocf': 'operating_cash_flow',
        'total_production': 'production_volume',
        'net_production': 'production_volume',
    }
    for alt, canonical in mappings.items():
        if alt in actuals and canonical not in actuals:
            actuals[canonical] = actuals[alt]

    return actuals


def score_expectations(model, expectations, actuals):
    """Score actuals against expectations using the financial model."""
    exp_list = [
        {
            'metric_name': e['metric_name'],
            'expected_low': float(e['expected_low']) if e.get('expected_low') else None,
            'expected_mid': float(e['expected_mid']) if e.get('expected_mid') else None,
            'expected_high': float(e['expected_high']) if e.get('expected_high') else None,
        }
        for e in expectations
    ]
    return model.score_actuals(exp_list, actuals)


def save_results(conn, expectations, results, filing_id, interpretation):
    """Save expectation results to database."""
    cursor = conn.cursor()

    # Build results lookup
    results_map = {r['metric_name']: r for r in results}

    for exp in expectations:
        r = results_map.get(exp['metric_name'])
        if not r:
            continue

        cursor.execute("""
            INSERT INTO expectation_results
                (expectation_id, actual_value, actual_unit, source_filing_id,
                 vs_our_expectation_pct, thesis_impact, interpretation)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            exp['id'],
            r.get('actual_value'),
            exp.get('expected_unit'),
            filing_id,
            r.get('vs_expected_pct'),
            r.get('thesis_impact'),
            interpretation,
        ))

    conn.commit()
    cursor.close()


def update_scorecard(conn, entry_id, actual_value, actual_unit, filing_id, assessment, delta_pct):
    """Update management scorecard entry."""
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE management_scorecard
        SET actual_value = %s, actual_unit = %s, actual_date = CURRENT_DATE,
            result_filing_id = %s, assessment = %s, delta_pct = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (actual_value, actual_unit, filing_id, assessment, delta_pct, entry_id))
    conn.commit()
    cursor.close()


def update_kill_criterion(conn, criterion_id, evidence):
    """Mark a kill criterion as triggered."""
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE kill_criteria
        SET triggered = TRUE, triggered_date = CURRENT_DATE, triggered_evidence = %s
        WHERE id = %s
    """, (evidence, criterion_id))
    conn.commit()
    cursor.close()


def interpret_results(client, ticker, thesis, scored_results, kill_results,
                      scorecard_results, hypotheses):
    """Call Claude to interpret the overall earnings result."""
    prompt = f"""You are interpreting {ticker}'s earnings results against our investment thesis.

THESIS: {thesis['thesis_summary']}
VARIANT EDGE: {thesis.get('variant_edge', 'N/A')}
Current Confidence: Bull {thesis.get('confidence_bull')}% | Base {thesis.get('confidence_base')}% | Bear {thesis.get('confidence_bear')}%

EXPECTATIONS vs ACTUALS:
{json.dumps(scored_results, indent=2, default=str)}

KILL CRITERIA CHECKS:
{json.dumps(kill_results, indent=2, default=str)}

MANAGEMENT SCORECARD:
{json.dumps(scorecard_results, indent=2, default=str)}

ACTIVE HYPOTHESES:
{json.dumps([{{'id': h['id'], 'hypothesis': h['hypothesis'], 'confidence': float(h['confidence'])}} for h in hypotheses], indent=2, default=str)}

Provide your interpretation. Return JSON:
{{
  "overall_assessment": "One paragraph: what does this mean for our thesis?",
  "thesis_impact": "confirms / challenges / neutral / breaks",
  "confidence_suggestion": {{
    "bull": 55.0,
    "base": 30.0,
    "bear": 15.0,
    "rationale": "Why confidence changed"
  }},
  "hypothesis_updates": [
    {{
      "hypothesis_id": 1,
      "direction": "for",
      "evidence": "What the data showed",
      "new_status": "strengthened",
      "new_confidence": 70.0
    }}
  ]
}}

RULES:
- Be honest about misses. Don't rationalize away bad results.
- Only suggest confidence changes when results clearly warrant it.
- thesis_impact: "confirms" = within range, "challenges" = outside range on key metrics, "breaks" = kill criteria triggered
- Hypothesis updates only for hypotheses actually testable with this data.

Return ONLY valid JSON."""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        return parse_claude_json(response.content[0].text)
    except Exception as e:
        print(f"  ✗ Claude interpretation error: {e}")
        return None


def format_scorecard(ticker, period, scored_results, kill_results,
                     scorecard_results, interpretation):
    """Format the post-event scorecard for display."""
    lines = []
    lines.append(f"\n{'=' * 70}")
    lines.append(f"{ticker} {period} — Earnings Scorecard")
    lines.append(f"Scored: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"{'=' * 70}")

    # Expectations vs actuals
    lines.append(f"\nEXPECTATIONS vs ACTUALS:")
    for r in scored_results:
        metric = r['metric_name']
        low = r.get('expected_low', '?')
        high = r.get('expected_high', '?')
        actual = r.get('actual_value', '?')
        within = r.get('within_range', False)
        pct = r.get('vs_expected_pct')

        icon = '✓' if within else '⚠' if pct and abs(pct) <= 15 else '✗'
        pct_str = f" ({pct:+.1f}%)" if pct else ""
        lines.append(f"  {icon} {metric:<25} Expected {low}-{high} → Actual {actual}{pct_str}")

    # Kill criteria
    kills_triggered = [k for k in kill_results if k.get('triggered')]
    kills_safe = [k for k in kill_results if not k.get('triggered') and k.get('actual_value') is not None]
    if kill_results:
        lines.append(f"\nKILL CRITERIA:")
        for k in kills_triggered:
            lines.append(f"  🚨 TRIGGERED: {k['criterion']} (actual: {k['actual_value']})")
        for k in kills_safe:
            lines.append(f"  ✓ NOT triggered: {k['criterion']} (actual: {k.get('actual_value', 'N/A')})")

    # Scorecard
    if scorecard_results:
        lines.append(f"\nMANAGEMENT SCORECARD:")
        for s in scorecard_results:
            icon = '✓' if s['assessment'] == 'delivered' else '⚠' if s['assessment'] == 'exceeded' else '✗'
            lines.append(f"  {icon} {s['promise_text']} → {s['assessment'].upper()} (actual: {s.get('actual_value', 'N/A')})")

    # Interpretation
    if interpretation:
        lines.append(f"\nTHESIS IMPACT: {interpretation.get('thesis_impact', 'N/A').upper()}")
        lines.append(f"\n{interpretation.get('overall_assessment', '')}")

        conf = interpretation.get('confidence_suggestion', {})
        if conf:
            lines.append(f"\nCONFIDENCE SUGGESTION:")
            lines.append(f"  Bull: {conf.get('bull', '?')}%  |  Base: {conf.get('base', '?')}%  |  Bear: {conf.get('bear', '?')}%")
            lines.append(f"  Rationale: {conf.get('rationale', 'N/A')}")

        hypo_updates = interpretation.get('hypothesis_updates', [])
        if hypo_updates:
            lines.append(f"\nHYPOTHESIS UPDATES:")
            for hu in hypo_updates:
                icon = '↑' if hu.get('new_status') == 'strengthened' else '↓'
                lines.append(f"  {icon} #{hu.get('hypothesis_id')}: {hu.get('new_status', '').upper()} "
                              f"({hu.get('new_confidence', '?')}%) — {hu.get('evidence', '')}")

    lines.append(f"\n{'=' * 70}")
    return '\n'.join(lines)


def main():
    print("=" * 70)
    print("POST-EVENT SCORING")
    print("=" * 70)

    # Parse arguments
    ticker = None
    filing_id = None
    period = None
    for i, arg in enumerate(sys.argv):
        if arg == '--ticker' and i + 1 < len(sys.argv):
            ticker = sys.argv[i + 1].upper()
        elif arg == '--filing-id' and i + 1 < len(sys.argv):
            filing_id = int(sys.argv[i + 1])
        elif arg == '--period' and i + 1 < len(sys.argv):
            period = sys.argv[i + 1]

    if not ticker or not filing_id:
        print("Usage: python post_event.py --ticker CRK --filing-id 72 [--period 'Q4 2025']")
        sys.exit(1)

    # Initialize
    client = get_anthropic_client()
    if not client:
        return

    conn = connect_db()
    if not conn:
        return
    print("  Connected to database")

    # Get company
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM companies WHERE ticker = %s", (ticker,))
    company = cursor.fetchone()
    cursor.close()

    if not company:
        print(f"  ✗ Company {ticker} not found")
        conn.close()
        return

    # Verify filing exists
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM filings WHERE id = %s", (filing_id,))
    filing = cursor.fetchone()
    cursor.close()
    if not filing:
        print(f"  ✗ Filing {filing_id} not found")
        conn.close()
        return
    print(f"  ✓ Filing: {filing['filing_type']} dated {filing['filing_date']}")

    # Get active thesis
    thesis = get_active_thesis(conn, company['id'])
    if not thesis:
        print(f"  ✗ No active thesis for {ticker}")
        conn.close()
        return
    print(f"  ✓ Active thesis (ID: {thesis['id']})")

    # Get expectations
    expectations = get_published_expectations(conn, company['id'], period)
    if not expectations:
        print(f"  ⚠ No published expectations found{' for ' + period if period else ''}")
        print(f"  Generate them first with: python pre_event.py --ticker {ticker} --period 'Q4 2025'")
        conn.close()
        return
    if not period:
        period = expectations[0]['period']
    print(f"  ✓ {len(expectations)} expectations for {period}")

    # Get actuals from filing
    metrics_rows = get_filing_metrics(conn, filing_id)
    actuals = build_actuals_from_metrics(metrics_rows)
    print(f"  ✓ {len(actuals)} actual metrics from filing")

    if not actuals:
        print("  ✗ No metrics extracted from this filing")
        print("  Run extraction first: python extract_data.py --filing-id " + str(filing_id))
        conn.close()
        return

    # Set up financial model
    claims = thesis.get('financial_claims', {})
    if isinstance(claims, str):
        claims = json.loads(claims)
    model_params = EPModel.params_from_claims(claims)
    model = EPModel(model_params)

    # Score expectations
    print("  Scoring expectations vs actuals...")
    scored_results = score_expectations(model, expectations, actuals)
    matched = len(scored_results)
    total = len(expectations)
    print(f"  ✓ {matched}/{total} expectations matched with actuals")

    # Check kill criteria
    kill_criteria = get_kill_criteria(conn, thesis['id'])
    kill_results = model.check_kill_criteria(kill_criteria, actuals)
    kills_triggered = [k for k in kill_results if k.get('triggered')]
    if kills_triggered:
        print(f"  🚨 {len(kills_triggered)} KILL CRITERIA TRIGGERED")
        for k in kills_triggered:
            update_kill_criterion(conn, k['criterion_id'],
                                  f"Post-event: actual {k['metric_name']}={k['actual_value']}")

    # Check management scorecard
    pending = get_pending_scorecard(conn, company['id'])
    scorecard_results = []
    for entry in pending:
        metric = entry.get('promise_metric')
        if metric and metric in actuals:
            actual_val = actuals[metric]
            low = float(entry['promise_value_low']) if entry.get('promise_value_low') else None
            high = float(entry['promise_value_high']) if entry.get('promise_value_high') else None

            if low is not None and high is not None:
                midpoint = (low + high) / 2
                delta_pct = round(((actual_val - midpoint) / midpoint) * 100, 2) if midpoint > 0 else None
                if actual_val >= low and actual_val <= high:
                    assessment = 'delivered'
                elif actual_val > high:
                    assessment = 'exceeded'
                else:
                    assessment = 'missed'
            else:
                delta_pct = None
                assessment = 'delivered'

            update_scorecard(conn, entry['id'], actual_val, entry.get('promise_unit'),
                             filing_id, assessment, delta_pct)
            scorecard_results.append({
                'promise_text': entry['promise_text'],
                'promise_low': low,
                'promise_high': high,
                'actual_value': actual_val,
                'assessment': assessment,
                'delta_pct': delta_pct,
            })

    if scorecard_results:
        print(f"  ✓ {len(scorecard_results)} scorecard entries updated")

    # Get hypotheses for interpretation
    hypotheses = get_hypotheses(conn, thesis['id'])

    # Claude interprets overall result
    print("  Getting Claude's interpretation...")
    interpretation = interpret_results(client, ticker, thesis, scored_results,
                                       kill_results, scorecard_results, hypotheses)

    # Save results
    interp_text = interpretation.get('overall_assessment', '') if interpretation else ''
    save_results(conn, expectations, scored_results, filing_id, interp_text)

    # Apply hypothesis updates from interpretation
    if interpretation:
        for hu in interpretation.get('hypothesis_updates', []):
            hypo_id = hu.get('hypothesis_id')
            if not hypo_id:
                continue
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE hypotheses SET status = %s, confidence = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (hu.get('new_status', 'active'), hu.get('new_confidence', 50), hypo_id))
            conn.commit()
            cursor.close()

            # Log evidence
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO hypothesis_evidence
                    (hypothesis_id, direction, evidence, source_type, source_id, source_date)
                VALUES (%s, %s, %s, 'filing', %s, %s)
            """, (hypo_id, hu.get('direction', 'for'), hu.get('evidence', ''),
                  filing_id, filing['filing_date']))
            conn.commit()
            cursor.close()

    # Log decision
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO decision_log
            (company_id, thesis_id, decision_type, decision_text, rationale,
             information_snapshot)
        VALUES (%s, %s, 'post_event_scored', %s, %s, %s)
    """, (
        company['id'], thesis['id'],
        f"Post-event scoring for {period} from filing {filing_id}",
        interpretation.get('overall_assessment', '') if interpretation else '',
        json.dumps({
            'expectations_scored': len(scored_results),
            'kills_triggered': len(kills_triggered),
            'scorecard_updates': len(scorecard_results),
            'thesis_impact': interpretation.get('thesis_impact') if interpretation else None,
        }),
    ))
    conn.commit()
    cursor.close()

    # Display scorecard
    scorecard_text = format_scorecard(ticker, period, scored_results, kill_results,
                                      scorecard_results, interpretation)
    print(scorecard_text)

    conn.close()


if __name__ == "__main__":
    main()
