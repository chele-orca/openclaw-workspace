#!/usr/bin/env python3
"""
Monitor active theses against new data.

Runs after new filings or external data arrives. Tests hypotheses,
checks kill criteria, updates management scorecard. Calls Claude
ONLY when something changed.

Silence is the default. No output = nothing changed.

Usage:
    python monitor.py --ticker CRK              # monitor specific company
    python monitor.py --all                      # monitor all active theses
    python monitor.py --ticker CRK --filing-id 72  # check specific new filing
"""

import sys
import json
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor
from config import connect_db, get_anthropic_client, parse_claude_json, MODEL
from financial_model import EPModel


def get_active_theses(conn, company_id=None):
    """Get all active (approved) theses, optionally for one company."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    if company_id:
        cursor.execute("""
            SELECT it.*, c.ticker, c.company_name, c.industry_profile_id
            FROM investment_theses it
            JOIN companies c ON c.id = it.company_id
            WHERE it.company_id = %s AND it.is_active = TRUE AND it.is_draft = FALSE
        """, (company_id,))
    else:
        cursor.execute("""
            SELECT it.*, c.ticker, c.company_name, c.industry_profile_id
            FROM investment_theses it
            JOIN companies c ON c.id = it.company_id
            WHERE it.is_active = TRUE AND it.is_draft = FALSE
        """)
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_kill_criteria(conn, thesis_id):
    """Get untriggered kill criteria for a thesis."""
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
    """Get active hypotheses for a thesis."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT * FROM hypotheses
        WHERE thesis_id = %s AND status = 'active'
        ORDER BY id
    """, (thesis_id,))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_pending_scorecard(conn, company_id):
    """Get management promises still pending verification."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT * FROM management_scorecard
        WHERE company_id = %s AND assessment = 'pending'
        ORDER BY promise_date
    """, (company_id,))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_latest_guidance(conn, company_id):
    """Get the most recent guidance for each metric (for revision detection)."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT DISTINCT ON (metric_name)
            id, metric_name, guidance_value_low, guidance_value_high,
            guidance_unit, guidance_period, source_date
        FROM guidance_history
        WHERE company_id = %s AND superseded_by IS NULL
        ORDER BY metric_name, source_date DESC
    """, (company_id,))
    rows = cursor.fetchall()
    cursor.close()
    return {r['metric_name']: r for r in rows}


def check_guidance_revisions(conn, company_id, forward_stmts, filing_id, filing_date):
    """Compare new forward_statements to prior guidance. Insert revisions if changed.
    Returns list of alert messages for significant revisions."""
    alerts = []

    prior_guidance = get_latest_guidance(conn, company_id)

    # Map forward_statement categories to guidance metric names
    category_to_metric = {
        'capital_expenditure': 'capex_guidance',
        'capex': 'capex_guidance',
        'production': 'production_guidance',
        'production_guidance': 'production_guidance',
        'debt_reduction': 'debt_reduction_target',
        'debt': 'debt_reduction_target',
        'rig_count': 'rig_count_guidance',
    }

    cursor = conn.cursor()

    for stmt in forward_stmts:
        category = (stmt.get('statement_category') or '').lower().replace(' ', '_')
        metric_name = category_to_metric.get(category)
        if not metric_name:
            # Try a broader match
            for key, val in category_to_metric.items():
                if key in category:
                    metric_name = val
                    break
        if not metric_name:
            continue

        # Parse quantitative value
        quant = stmt.get('quantitative_value')
        if quant is None:
            continue

        # Determine low/high from the quantitative value
        new_low = float(quant)
        new_high = float(quant)
        unit = stmt.get('value_unit', '')
        period = stmt.get('timeframe', '')

        # Check against prior guidance
        prior = prior_guidance.get(metric_name)
        revision_pct = None
        superseded_id = None

        if prior:
            prior_mid = float(prior['guidance_value_low'] or 0)
            if prior.get('guidance_value_high'):
                prior_mid = (float(prior['guidance_value_low']) + float(prior['guidance_value_high'])) / 2
            new_mid = (new_low + new_high) / 2

            if prior_mid > 0:
                revision_pct = round(((new_mid - prior_mid) / prior_mid) * 100, 2)

            # Only record if there's a meaningful change (>2%)
            if revision_pct is not None and abs(revision_pct) < 2:
                continue

            superseded_id = prior['id']

        # Insert new guidance history entry
        cursor.execute("""
            INSERT INTO guidance_history
                (company_id, metric_name, guidance_value_low, guidance_value_high,
                 guidance_unit, guidance_period, source_filing_id, source_date,
                 revision_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            company_id, metric_name, new_low, new_high,
            unit, period, filing_id, filing_date, revision_pct
        ))
        new_id = cursor.fetchone()[0]

        # Link superseded entry
        if superseded_id:
            cursor.execute("""
                UPDATE guidance_history SET superseded_by = %s WHERE id = %s
            """, (new_id, superseded_id))

        conn.commit()

        # Alert on significant revisions (>15%)
        if revision_pct is not None and abs(revision_pct) > 15:
            direction = 'increased' if revision_pct > 0 else 'decreased'
            msg = (f"GUIDANCE REVISION: {metric_name} {direction} {abs(revision_pct):.1f}% "
                   f"(was {prior['guidance_value_low']}-{prior.get('guidance_value_high', prior['guidance_value_low'])} "
                   f"{prior.get('guidance_unit', '')}, now {new_low}-{new_high} {unit})")
            alerts.append(('GUIDANCE', msg))

    cursor.close()
    return alerts


def get_new_data_since(conn, company_id, since):
    """Get new filings and data sources since a given datetime."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # New filings
    cursor.execute("""
        SELECT f.id, f.filing_type, f.filing_date, f.accession_number
        FROM filings f
        WHERE f.company_id = %s AND f.processed = TRUE AND f.created_at > %s
        ORDER BY f.filing_date DESC
    """, (company_id, since))
    new_filings = cursor.fetchall()

    # New extracted metrics
    cursor.execute("""
        SELECT em.metric_name, em.metric_value, em.metric_unit, em.metric_period,
               f.filing_type, f.filing_date
        FROM extracted_metrics em
        JOIN filings f ON f.id = em.filing_id
        WHERE f.company_id = %s AND em.created_at > %s
        ORDER BY em.metric_name
    """, (company_id, since))
    new_metrics = cursor.fetchall()

    # New data sources
    cursor.execute("""
        SELECT source_type, title, published_date
        FROM data_sources
        WHERE company_id = %s AND created_at > %s
        ORDER BY published_date DESC
    """, (company_id, since))
    new_sources = cursor.fetchall()

    cursor.close()
    return new_filings, new_metrics, new_sources


def get_filing_metrics(conn, filing_id):
    """Get extracted metrics for a specific filing."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT metric_name, metric_value, metric_unit, metric_period
        FROM extracted_metrics WHERE filing_id = %s
    """, (filing_id,))
    rows = cursor.fetchall()
    cursor.close()
    return {r['metric_name']: float(r['metric_value']) if r['metric_value'] else None for r in rows}


def check_kill_criteria(model, criteria, actuals):
    """Check kill criteria using the financial model."""
    return model.check_kill_criteria(criteria, actuals)


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


def update_scorecard(conn, scorecard_entry_id, actual_value, actual_unit, filing_id, assessment):
    """Update a management scorecard entry with actuals."""
    cursor = conn.cursor()

    # Compute delta
    cursor.execute("SELECT promise_value_low, promise_value_high FROM management_scorecard WHERE id = %s",
                   (scorecard_entry_id,))
    row = cursor.fetchone()
    delta_pct = None
    if row and actual_value:
        low, high = row[0], row[1]
        if low and high:
            midpoint = (float(low) + float(high)) / 2
            if midpoint > 0:
                delta_pct = round(((float(actual_value) - midpoint) / midpoint) * 100, 2)

    cursor.execute("""
        UPDATE management_scorecard
        SET actual_value = %s, actual_unit = %s, actual_date = CURRENT_DATE,
            result_filing_id = %s, delta_pct = %s, assessment = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (actual_value, actual_unit, filing_id, delta_pct, assessment, scorecard_entry_id))
    conn.commit()
    cursor.close()


def log_evidence(conn, hypothesis_id, direction, evidence, source_type, source_id, source_date):
    """Log evidence for/against a hypothesis."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hypothesis_evidence
            (hypothesis_id, direction, evidence, source_type, source_id, source_date)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (hypothesis_id, direction, evidence, source_type, source_id, source_date))
    conn.commit()
    cursor.close()


def update_hypothesis_status(conn, hypothesis_id, new_status, new_confidence):
    """Update hypothesis status and confidence."""
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE hypotheses
        SET status = %s, confidence = %s, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (new_status, new_confidence, hypothesis_id))
    conn.commit()
    cursor.close()


def log_decision(conn, company_id, thesis_id, decision_type, decision_text, rationale, snapshot=None):
    """Log a decision to the decision log."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO decision_log
            (company_id, thesis_id, decision_type, decision_text, rationale, information_snapshot)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (company_id, thesis_id, decision_type, decision_text, rationale,
          json.dumps(snapshot) if snapshot else None))
    conn.commit()
    cursor.close()


def interpret_evidence(client, thesis, hypotheses, new_metrics, new_filings, new_sources):
    """Call Claude to interpret new evidence against hypotheses. Only called when data changed."""
    if not hypotheses:
        return []

    # Build context
    hypo_list = []
    for h in hypotheses:
        hypo_list.append({
            'id': h['id'],
            'hypothesis': h['hypothesis'],
            'counter_hypothesis': h['counter_hypothesis'],
            'confirming_evidence': h.get('confirming_evidence'),
            'disproving_evidence': h.get('disproving_evidence'),
            'current_confidence': float(h.get('confidence', 50)),
        })

    new_data = {
        'new_metrics': [dict(m) for m in new_metrics] if new_metrics else [],
        'new_filings': [{'type': f['filing_type'], 'date': str(f['filing_date'])} for f in new_filings],
        'new_sources': [{'type': s['source_type'], 'title': s['title'],
                         'date': str(s['published_date'])} for s in new_sources],
    }

    prompt = f"""You are evaluating new data against active investment hypotheses for {thesis['ticker']}.

THESIS: {thesis['thesis_summary']}

ACTIVE HYPOTHESES:
{json.dumps(hypo_list, indent=2, default=str)}

NEW DATA:
{json.dumps(new_data, indent=2, default=str)}

For each hypothesis, determine if the new data provides evidence FOR or AGAINST it.
Only include hypotheses where the new data is RELEVANT. Skip hypotheses where the data is irrelevant.

Return JSON:
{{
  "updates": [
    {{
      "hypothesis_id": 1,
      "direction": "for",
      "evidence": "One sentence describing what the data shows",
      "new_status": "strengthened",
      "new_confidence": 65.0
    }}
  ],
  "summary": "One sentence overall interpretation"
}}

RULES:
- direction: "for" or "against"
- new_status: "active" (unchanged), "strengthened", "weakened", "disproved"
- new_confidence: 0-100, must change by at least 5 points to justify a status change
- If NO hypotheses are affected, return {{"updates": [], "summary": "No relevant evidence"}}
- Be conservative. Most data doesn't change hypothesis status.

Return ONLY valid JSON."""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        result = parse_claude_json(response.content[0].text)
        return result.get('updates', []) if result else []
    except Exception as e:
        print(f"  ✗ Claude API error interpreting evidence: {e}")
        return []


def check_scorecard_against_actuals(pending_scorecard, actuals):
    """Check if any pending management promises now have actual results."""
    matches = []
    for entry in pending_scorecard:
        metric = entry.get('promise_metric')
        if metric and metric in actuals:
            actual_val = actuals[metric]
            low = float(entry['promise_value_low']) if entry.get('promise_value_low') else None
            high = float(entry['promise_value_high']) if entry.get('promise_value_high') else None

            if low is not None and high is not None:
                if actual_val >= low and actual_val <= high:
                    assessment = 'delivered'
                elif actual_val > high:
                    assessment = 'exceeded'
                else:
                    assessment = 'missed'
            elif low is not None:
                assessment = 'delivered' if actual_val >= low else 'missed'
            else:
                assessment = 'delivered'

            matches.append({
                'scorecard_id': entry['id'],
                'promise_text': entry['promise_text'],
                'actual_value': actual_val,
                'actual_unit': entry.get('promise_unit'),
                'assessment': assessment,
            })
    return matches


def monitor_thesis(conn, client, thesis, filing_id=None):
    """Monitor a single thesis. Returns list of alert messages."""
    ticker = thesis['ticker']
    company_id = thesis['company_id']
    thesis_id = thesis['id']
    alerts = []

    # Determine lookback period
    last_check = thesis.get('updated_at') or thesis.get('created_at')
    if not last_check:
        last_check = datetime.now() - timedelta(days=7)

    # Get new data
    if filing_id:
        # Specific filing
        new_filings = [{'id': filing_id, 'filing_type': 'manual', 'filing_date': datetime.now().date()}]
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT f.id, f.filing_type, f.filing_date, f.accession_number
            FROM filings f WHERE f.id = %s
        """, (filing_id,))
        f = cursor.fetchone()
        cursor.close()
        if f:
            new_filings = [f]
        new_metrics_rows = []
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT em.metric_name, em.metric_value, em.metric_unit, em.metric_period
            FROM extracted_metrics em WHERE em.filing_id = %s
        """, (filing_id,))
        new_metrics_rows = cursor.fetchall()
        cursor.close()
        new_sources = []
    else:
        new_filings, new_metrics_rows, new_sources = get_new_data_since(conn, company_id, last_check)

    # If nothing new, stay silent
    if not new_filings and not new_metrics_rows and not new_sources:
        return alerts

    print(f"\n  [{ticker}] New data detected:")
    if new_filings:
        print(f"    {len(new_filings)} new filing(s)")
    if new_metrics_rows:
        print(f"    {len(new_metrics_rows)} new metric(s)")
    if new_sources:
        print(f"    {len(new_sources)} new data source(s)")

    # Build actuals dict from metrics
    actuals = {}
    for m in new_metrics_rows:
        if m['metric_value'] is not None:
            actuals[m['metric_name']] = float(m['metric_value'])

    # Also get actuals from specific filing if provided
    if filing_id and filing_id not in [f['id'] for f in new_filings if isinstance(f, dict) and 'id' in f]:
        filing_actuals = get_filing_metrics(conn, filing_id)
        actuals.update(filing_actuals)
    elif new_filings:
        for f in new_filings:
            fid = f['id'] if isinstance(f, dict) else f
            filing_actuals = get_filing_metrics(conn, fid)
            actuals.update(filing_actuals)

    # Set up financial model
    claims = thesis.get('financial_claims', {})
    if isinstance(claims, str):
        claims = json.loads(claims)
    model_params = EPModel.params_from_claims(claims)
    model = EPModel(model_params)

    # 1. CHECK KILL CRITERIA
    criteria = get_kill_criteria(conn, thesis_id)
    if criteria and actuals:
        kill_results = check_kill_criteria(model, criteria, actuals)
        for kr in kill_results:
            if kr['triggered']:
                msg = (f"KILL CRITERION TRIGGERED: {kr['criterion']} "
                       f"(actual {kr['metric_name']}={kr['actual_value']} "
                       f"{kr['threshold_operator']} {kr['threshold_value']})")
                alerts.append(('KILL', msg))
                print(f"    🚨 {msg}")

                update_kill_criterion(conn, kr['criterion_id'],
                                      f"Actual {kr['metric_name']}={kr['actual_value']}")
                log_decision(conn, company_id, thesis_id, 'kill_triggered',
                             msg, f"Threshold breached: {kr['metric_name']}")

    # 2. CHECK MANAGEMENT SCORECARD
    pending_scorecard = get_pending_scorecard(conn, company_id)
    if pending_scorecard and actuals:
        scorecard_matches = check_scorecard_against_actuals(pending_scorecard, actuals)
        for sm in scorecard_matches:
            source_fid = new_filings[0]['id'] if new_filings else None
            update_scorecard(conn, sm['scorecard_id'], sm['actual_value'],
                             sm['actual_unit'], source_fid, sm['assessment'])
            status_icon = '✓' if sm['assessment'] == 'delivered' else '⚠' if sm['assessment'] == 'exceeded' else '✗'
            msg = f"Scorecard: {sm['promise_text']} → {sm['assessment'].upper()} (actual: {sm['actual_value']})"
            alerts.append(('SCORECARD', msg))
            print(f"    {status_icon} {msg}")

    # 3. CHECK GUIDANCE REVISIONS
    if new_filings:
        for f in new_filings:
            fid = f['id'] if isinstance(f, dict) else f
            fdate = f.get('filing_date', datetime.now().date()) if isinstance(f, dict) else datetime.now().date()
            # Get forward statements from the new filing
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT statement_category, statement_text, quantitative_value,
                       value_unit, timeframe, confidence_level
                FROM forward_statements WHERE filing_id = %s
            """, (fid,))
            new_fwd_stmts = cursor.fetchall()
            cursor.close()

            if new_fwd_stmts:
                guidance_alerts = check_guidance_revisions(
                    conn, company_id, new_fwd_stmts, fid, fdate)
                for alert_type, msg in guidance_alerts:
                    alerts.append((alert_type, msg))
                    print(f"    ⚠ {msg}")
                    log_decision(conn, company_id, thesis_id, 'guidance_revision',
                                 msg, 'Guidance changed significantly from prior')

    # 4. TEST HYPOTHESES (Claude interprets)
    hypotheses = get_hypotheses(conn, thesis_id)
    if hypotheses and (new_metrics_rows or new_filings or new_sources):
        evidence_updates = interpret_evidence(client, thesis, hypotheses,
                                              new_metrics_rows, new_filings, new_sources)
        for update in evidence_updates:
            hypo_id = update.get('hypothesis_id')
            if not hypo_id:
                continue

            direction = update.get('direction', 'for')
            evidence_text = update.get('evidence', '')
            new_status = update.get('new_status', 'active')
            new_confidence = update.get('new_confidence', 50)

            # Log evidence
            source_id = new_filings[0]['id'] if new_filings else None
            source_date = new_filings[0]['filing_date'] if new_filings else datetime.now().date()
            log_evidence(conn, hypo_id, direction, evidence_text,
                         'filing', source_id, source_date)

            # Update hypothesis if status changed
            if new_status != 'active':
                update_hypothesis_status(conn, hypo_id, new_status, new_confidence)
                icon = '↑' if new_status == 'strengthened' else '↓' if new_status in ('weakened', 'disproved') else '→'
                msg = f"Hypothesis #{hypo_id} {icon} {new_status.upper()} ({new_confidence}%): {evidence_text}"
                alerts.append(('HYPOTHESIS', msg))
                print(f"    {icon} {msg}")
            else:
                print(f"    → Evidence logged for hypothesis #{hypo_id}: {evidence_text}")

    # Update thesis timestamp
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE investment_theses SET updated_at = CURRENT_TIMESTAMP WHERE id = %s
    """, (thesis_id,))
    conn.commit()
    cursor.close()

    return alerts


def main():
    print("=" * 70)
    print("THESIS MONITOR")
    print("=" * 70)

    # Parse arguments
    ticker = None
    all_mode = False
    filing_id = None
    for i, arg in enumerate(sys.argv):
        if arg == '--ticker' and i + 1 < len(sys.argv):
            ticker = sys.argv[i + 1].upper()
        elif arg == '--all':
            all_mode = True
        elif arg == '--filing-id' and i + 1 < len(sys.argv):
            filing_id = int(sys.argv[i + 1])

    if not ticker and not all_mode:
        print("Usage: python monitor.py --ticker CRK [--filing-id 72]")
        print("       python monitor.py --all")
        sys.exit(1)

    # Initialize
    client = get_anthropic_client()
    if not client:
        return

    conn = connect_db()
    if not conn:
        return
    print("  Connected to database")

    # Get company if ticker specified
    company_id = None
    if ticker:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT id FROM companies WHERE ticker = %s", (ticker,))
        row = cursor.fetchone()
        cursor.close()
        if not row:
            print(f"  ✗ Company {ticker} not found")
            conn.close()
            return
        company_id = row['id']

    # Get active theses
    theses = get_active_theses(conn, company_id)
    if not theses:
        print("  No active (approved) theses to monitor.")
        print("  Create one with: python init_thesis.py --ticker CRK")
        print("  Then approve with: python approve_thesis.py --thesis-id N")
        conn.close()
        return

    print(f"  Monitoring {len(theses)} active thesis(es)")

    # Monitor each thesis
    total_alerts = []
    for thesis in theses:
        alerts = monitor_thesis(conn, client, thesis, filing_id)
        total_alerts.extend(alerts)

    # Summary
    if total_alerts:
        print(f"\n{'=' * 70}")
        print(f"MONITOR SUMMARY: {len(total_alerts)} alert(s)")
        print(f"{'=' * 70}")
        kills = [a for a in total_alerts if a[0] == 'KILL']
        if kills:
            print(f"\n  🚨 KILL CRITERIA TRIGGERED: {len(kills)}")
            for _, msg in kills:
                print(f"    {msg}")
        hypos = [a for a in total_alerts if a[0] == 'HYPOTHESIS']
        if hypos:
            print(f"\n  HYPOTHESIS UPDATES: {len(hypos)}")
            for _, msg in hypos:
                print(f"    {msg}")
        scores = [a for a in total_alerts if a[0] == 'SCORECARD']
        if scores:
            print(f"\n  SCORECARD UPDATES: {len(scores)}")
            for _, msg in scores:
                print(f"    {msg}")
        guidance = [a for a in total_alerts if a[0] == 'GUIDANCE']
        if guidance:
            print(f"\n  GUIDANCE REVISIONS: {len(guidance)}")
            for _, msg in guidance:
                print(f"    {msg}")
    else:
        print(f"\n  — No changes detected. Silence is the default.")

    conn.close()


if __name__ == "__main__":
    main()
