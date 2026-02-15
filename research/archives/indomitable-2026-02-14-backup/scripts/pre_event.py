#!/usr/bin/env python3
"""
Generate pre-event expectations brief.

Runs financial model to generate quantitative expectations for upcoming
earnings or filing. Fetches street consensus. Compares our expectations
to consensus. Stores in expectations table. Outputs structured brief.

Usage:
    python pre_event.py --ticker CRK --period "Q4 2025"
    python pre_event.py --ticker CRK --period "Q4 2025" --event-date 2026-02-28
"""

import sys
import json
from datetime import datetime
from psycopg2.extras import RealDictCursor
from config import connect_db, get_anthropic_client, parse_claude_json, MODEL
from financial_model import EPModel
from external_data import get_industry_context


def get_active_thesis(conn, company_id):
    """Get the active investment thesis for a company."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT it.*, c.ticker, c.company_name, c.industry_profile_id
        FROM investment_theses it
        JOIN companies c ON c.id = it.company_id
        WHERE it.company_id = %s AND it.is_active = TRUE AND it.is_draft = FALSE
        ORDER BY it.created_at DESC LIMIT 1
    """, (company_id,))
    row = cursor.fetchone()
    cursor.close()
    return row


def get_hypotheses(conn, thesis_id):
    """Get active hypotheses for a thesis."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT * FROM hypotheses
        WHERE thesis_id = %s AND status IN ('active', 'strengthened')
        ORDER BY id
    """, (thesis_id,))
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


def get_consensus_estimates(ticker):
    """Fetch analyst consensus from external sources."""
    from external_data import fetch_stockanalysis_estimates, fetch_fmp_analyst_estimates
    estimates = {}

    try:
        sa = fetch_stockanalysis_estimates(ticker)
        if sa:
            estimates['stockanalysis'] = sa
    except Exception as e:
        print(f"  ⚠ StockAnalysis: {e}")

    try:
        fmp = fetch_fmp_analyst_estimates(ticker)
        if fmp:
            estimates['fmp'] = fmp
    except Exception as e:
        print(f"  ⚠ FMP estimates: {e}")

    return estimates


def save_expectations(conn, company_id, thesis_id, period, event_type, event_date,
                      expectations, consensus_map):
    """Save expectations to database and publish them."""
    cursor = conn.cursor()
    now = datetime.now()

    for exp in expectations:
        metric = exp['metric_name']
        consensus = consensus_map.get(metric, {})

        cursor.execute("""
            INSERT INTO expectations
                (company_id, thesis_id, period, event_type, event_date,
                 metric_name, expected_low, expected_mid, expected_high, expected_unit,
                 assumption_basis, consensus_value, consensus_source, our_vs_consensus,
                 published, published_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
        """, (
            company_id, thesis_id, period, event_type, event_date,
            metric,
            exp.get('expected_low'), exp.get('expected_mid'), exp.get('expected_high'),
            exp.get('expected_unit'),
            exp.get('assumption_basis'),
            consensus.get('value'), consensus.get('source'),
            exp.get('our_vs_consensus'),
            now,
        ))

    conn.commit()
    cursor.close()


def add_claude_rationale(client, ticker, thesis, expectations, consensus, hypotheses, kill_criteria):
    """Have Claude write assumption_basis and our_vs_consensus for each expectation."""
    if not expectations:
        return expectations

    prompt = f"""You are writing the rationale for pre-earnings expectations for {ticker}.

THESIS: {thesis['thesis_summary']}

EXPECTATIONS (from our quantitative model):
{json.dumps(expectations, indent=2, default=str)}

CONSENSUS ESTIMATES:
{json.dumps(consensus, indent=2, default=str)}

ACTIVE HYPOTHESES:
{json.dumps([{{'id': h['id'], 'hypothesis': h['hypothesis'], 'confidence': float(h['confidence'])}} for h in hypotheses], indent=2, default=str)}

KILL CRITERIA:
{json.dumps([{{'criterion': k['criterion'], 'metric': k.get('metric_name'), 'threshold': k.get('threshold_value'), 'operator': k.get('threshold_operator')}} for k in kill_criteria], indent=2, default=str)}

For each expectation, add:
1. "assumption_basis" - ONE sentence explaining why we expect this range
2. "our_vs_consensus" - ONE sentence on how/why we differ from street (only if we differ)
3. "hypothesis_tested" - which hypothesis ID this expectation tests (if any)

Also identify:
- Which hypotheses this earnings will test
- Which kill criteria are in play

Return JSON:
{{
  "expectations": [
    {{
      "metric_name": "revenue",
      "assumption_basis": "450 Bcf production at $3.20-3.50 realized",
      "our_vs_consensus": "We're 3% above street on revenue due to higher realized price assumption",
      "hypothesis_tested": 3
    }}
  ],
  "hypotheses_tested": [
    {{
      "hypothesis_id": 1,
      "test_description": "Western Haynesville well performance — confirm if >30 MMcf/day avg"
    }}
  ],
  "kill_criteria_in_play": [
    {{
      "criterion": "Capex > $400M quarterly",
      "significance": "Would imply >$1.5B annual, triggering exit"
    }}
  ]
}}

Return ONLY valid JSON."""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        result = parse_claude_json(response.content[0].text)
        if result:
            # Merge rationale back into expectations
            rationale_map = {e['metric_name']: e for e in result.get('expectations', [])}
            for exp in expectations:
                r = rationale_map.get(exp['metric_name'], {})
                exp['assumption_basis'] = r.get('assumption_basis', exp.get('assumption_basis', ''))
                exp['our_vs_consensus'] = r.get('our_vs_consensus', '')
            return expectations, result.get('hypotheses_tested', []), result.get('kill_criteria_in_play', [])
    except Exception as e:
        print(f"  ⚠ Claude rationale: {e}")

    return expectations, [], []


def format_brief(ticker, period, event_date, expectations, consensus_map,
                 hypotheses_tested, kill_criteria_in_play):
    """Format the pre-event brief for display."""
    lines = []
    lines.append(f"\n{'=' * 70}")
    lines.append(f"{ticker} {period} — Pre-Earnings Expectations")
    lines.append(f"Published: {datetime.now().strftime('%Y-%m-%d')}")
    if event_date:
        lines.append(f"Expected Event: {event_date}")
    lines.append(f"{'=' * 70}")

    lines.append(f"\nEXPECTATIONS:")
    for exp in expectations:
        metric = exp['metric_name']
        low = exp.get('expected_low', '?')
        mid = exp.get('expected_mid', '?')
        high = exp.get('expected_high', '?')
        unit = exp.get('expected_unit', '')

        # Format consensus comparison
        cons = consensus_map.get(metric, {})
        cons_str = f"Street: ${cons['value']}{unit}" if cons.get('value') else "Street: N/A"

        basis = exp.get('assumption_basis', '')
        lines.append(f"  {metric:<25} ${low}-${high}{unit}  ({cons_str})  — {basis}")

        vs = exp.get('our_vs_consensus', '')
        if vs:
            lines.append(f"  {'':25} ↳ {vs}")

    if hypotheses_tested:
        lines.append(f"\nHYPOTHESES BEING TESTED:")
        for ht in hypotheses_tested:
            lines.append(f"  {ht.get('hypothesis_id', '?')}. {ht.get('test_description', '')}")

    if kill_criteria_in_play:
        lines.append(f"\nKILL CRITERIA IN PLAY:")
        for kc in kill_criteria_in_play:
            lines.append(f"  - {kc.get('criterion', '')} → {kc.get('significance', '')}")

    lines.append(f"\n{'=' * 70}")
    return '\n'.join(lines)


def main():
    print("=" * 70)
    print("PRE-EVENT EXPECTATIONS")
    print("=" * 70)

    # Parse arguments
    ticker = None
    period = None
    event_date = None
    for i, arg in enumerate(sys.argv):
        if arg == '--ticker' and i + 1 < len(sys.argv):
            ticker = sys.argv[i + 1].upper()
        elif arg == '--period' and i + 1 < len(sys.argv):
            period = sys.argv[i + 1]
        elif arg == '--event-date' and i + 1 < len(sys.argv):
            event_date = sys.argv[i + 1]

    if not ticker or not period:
        print("Usage: python pre_event.py --ticker CRK --period 'Q4 2025' [--event-date 2026-02-28]")
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

    # Get active thesis
    thesis = get_active_thesis(conn, company['id'])
    if not thesis:
        print(f"  ✗ No active thesis for {ticker}")
        print(f"  Create one with: python init_thesis.py --ticker {ticker}")
        conn.close()
        return

    print(f"  ✓ Active thesis (ID: {thesis['id']})")

    # Get hypotheses and kill criteria
    hypotheses = get_hypotheses(conn, thesis['id'])
    kill_criteria = get_kill_criteria(conn, thesis['id'])
    print(f"  ✓ {len(hypotheses)} active hypotheses, {len(kill_criteria)} kill criteria")

    # Build financial model from thesis claims
    claims = thesis.get('financial_claims', {})
    if isinstance(claims, str):
        claims = json.loads(claims)

    # Get external context for forward curve
    profile = None
    if company.get('industry_profile_id'):
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM industry_profiles WHERE id = %s", (company['industry_profile_id'],))
        profile = cursor.fetchone()
        cursor.close()

    print("  Fetching market context...")
    external_context = get_industry_context(conn, profile, company_ticker=ticker) if profile else {}

    # Run model
    print("  Running financial model...")
    model_params = EPModel.params_from_claims(claims, external_context)
    model = EPModel(model_params)
    expectations = model.generate_expectations(period)

    if not expectations:
        print("  ✗ Insufficient data to generate expectations")
        print("  Ensure thesis has financial_claims with production, pricing, capex data")
        conn.close()
        return

    print(f"  ✓ {len(expectations)} expectations generated")

    # Get consensus
    print("  Fetching consensus estimates...")
    consensus_raw = get_consensus_estimates(ticker)

    # Build consensus map: metric_name -> {value, source}
    consensus_map = {}
    if consensus_raw:
        # Parse StockAnalysis estimates
        sa = consensus_raw.get('stockanalysis', {})
        if sa:
            rev_est = sa.get('revenue_estimates', [])
            for est in rev_est:
                if period.lower().replace(' ', '') in str(est.get('period', '')).lower().replace(' ', ''):
                    consensus_map['revenue'] = {
                        'value': est.get('consensus'),
                        'source': 'StockAnalysis',
                    }
            eps_est = sa.get('eps_estimates', [])
            for est in eps_est:
                if period.lower().replace(' ', '') in str(est.get('period', '')).lower().replace(' ', ''):
                    consensus_map['eps'] = {
                        'value': est.get('consensus'),
                        'source': 'StockAnalysis',
                    }

    # Add Claude rationale
    print("  Adding rationale...")
    expectations, hypos_tested, kill_in_play = add_claude_rationale(
        client, ticker, thesis, expectations, consensus_raw, hypotheses, kill_criteria
    )

    # Save to database
    save_expectations(conn, company['id'], thesis['id'], period, 'earnings',
                      event_date, expectations, consensus_map)
    print(f"  ✓ Expectations published to database")

    # Log decision
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO decision_log
            (company_id, thesis_id, decision_type, decision_text, rationale,
             information_snapshot)
        VALUES (%s, %s, 'expectations_published', %s, %s, %s)
    """, (
        company['id'], thesis['id'],
        f"Pre-event expectations published for {period}",
        f"{len(expectations)} metrics, {len(hypos_tested)} hypotheses being tested",
        json.dumps({'expectations_count': len(expectations),
                    'consensus_sources': list(consensus_raw.keys())}),
    ))
    conn.commit()
    cursor.close()

    # Display brief
    brief = format_brief(ticker, period, event_date, expectations, consensus_map,
                         hypos_tested, kill_in_play)
    print(brief)

    conn.close()


if __name__ == "__main__":
    main()
