#!/usr/bin/env python3
"""
Approve a draft investment thesis.

Reviews the draft, displays it for human confirmation, then sets
is_active=TRUE, is_draft=FALSE. Deactivates any prior active thesis.

Usage:
    python approve_thesis.py --thesis-id 5
    python approve_thesis.py --thesis-id 5 --list     # list all drafts
"""

import sys
import json
from psycopg2.extras import RealDictCursor
from config import connect_db


def list_drafts(conn):
    """List all draft theses awaiting approval."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT it.id, c.ticker, c.company_name, it.position_type,
               LEFT(it.thesis_summary, 120) as summary,
               it.confidence_bull, it.confidence_base, it.confidence_bear,
               it.created_at
        FROM investment_theses it
        JOIN companies c ON c.id = it.company_id
        WHERE it.is_draft = TRUE
        ORDER BY it.created_at DESC
    """)
    drafts = cursor.fetchall()
    cursor.close()

    if not drafts:
        print("  No draft theses awaiting approval.")
        return

    print(f"\n  {'ID':>4}  {'Ticker':<6}  {'Position':<6}  {'Bull%':>5}  {'Created':<20}  Summary")
    print(f"  {'—'*4}  {'—'*6}  {'—'*6}  {'—'*5}  {'—'*20}  {'—'*50}")
    for d in drafts:
        print(f"  {d['id']:>4}  {d['ticker']:<6}  {d['position_type']:<6}  "
              f"{d['confidence_bull']:>5}  {str(d['created_at'])[:19]:<20}  "
              f"{d['summary']}...")


def get_thesis_detail(conn, thesis_id):
    """Get full thesis detail including kill criteria, hypotheses, scorecard."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Thesis
    cursor.execute("""
        SELECT it.*, c.ticker, c.company_name
        FROM investment_theses it
        JOIN companies c ON c.id = it.company_id
        WHERE it.id = %s
    """, (thesis_id,))
    thesis = cursor.fetchone()
    if not thesis:
        cursor.close()
        return None, None, None, None

    # Kill criteria
    cursor.execute("""
        SELECT * FROM kill_criteria WHERE thesis_id = %s ORDER BY id
    """, (thesis_id,))
    kill = cursor.fetchall()

    # Hypotheses
    cursor.execute("""
        SELECT * FROM hypotheses WHERE thesis_id = %s ORDER BY id
    """, (thesis_id,))
    hypos = cursor.fetchall()

    # Management scorecard entries for this company
    cursor.execute("""
        SELECT * FROM management_scorecard
        WHERE company_id = %s
        ORDER BY promise_date DESC
    """, (thesis['company_id'],))
    scorecard = cursor.fetchall()

    cursor.close()
    return thesis, kill, hypos, scorecard


def display_thesis(thesis, kill_criteria, hypotheses, scorecard):
    """Display full thesis for review."""
    ticker = thesis['ticker']

    print(f"\n{'=' * 70}")
    print(f"THESIS REVIEW — {ticker} ({thesis['company_name']})")
    print(f"ID: {thesis['id']}  |  Status: {'DRAFT' if thesis['is_draft'] else 'ACTIVE'}  |  Created: {thesis['created_at']}")
    print(f"{'=' * 70}")

    position = thesis['position_type'].upper()
    position_labels = {
        'OWN': 'OWN (hinge resolves favorably, we have edge)',
        'PASS': 'PASS (economics may work, no edge on hinge)',
        'AVOID': 'AVOID (hinge unlikely to resolve favorably)',
        'SELL': 'SELL (thesis broken, exit position)',
    }
    print(f"\nPosition: {position_labels.get(position, position)}")
    print(f"\nThesis:\n  {thesis['thesis_summary']}")

    print(f"\n--- VARIANT PERCEPTION ---")
    print(f"Market View:\n  {thesis['market_view']}")
    print(f"\nOur View:\n  {thesis['our_view']}")
    print(f"\nVariant Edge:\n  {thesis['variant_edge']}")

    print(f"\n--- PRE-MORTEM ---")
    print(f"  {thesis.get('pre_mortem', 'N/A')}")

    print(f"\n--- MANAGEMENT CREDIBILITY ---")
    print(f"  {thesis.get('management_credibility', 'N/A')}")

    print(f"\n--- CONFIDENCE ---")
    print(f"  Bull: {thesis['confidence_bull']}%  |  "
          f"Base: {thesis['confidence_base']}%  |  "
          f"Bear: {thesis['confidence_bear']}%")
    total = (thesis['confidence_bull'] or 0) + (thesis['confidence_base'] or 0) + (thesis['confidence_bear'] or 0)
    if abs(total - 100) > 1:
        print(f"  ⚠ Probabilities sum to {total}%, not 100%")

    print(f"\n--- CATALYST ---")
    print(f"  {thesis.get('catalyst_description', 'N/A')}")
    print(f"  Deadline: {thesis.get('catalyst_deadline', 'N/A')}")
    print(f"  Review:   {thesis.get('review_date', 'N/A')}")

    print(f"\n--- KILL CRITERIA ({len(kill_criteria)}) ---")
    for i, kc in enumerate(kill_criteria, 1):
        auto = ""
        if kc.get('metric_name'):
            auto = f" [AUTO: {kc['metric_name']} {kc.get('threshold_operator', '')} {kc.get('threshold_value', '')} {kc.get('threshold_unit', '')}]"
        print(f"  {i}. {kc['criterion']}{auto}")

    print(f"\n--- HYPOTHESES ({len(hypotheses)}) ---")
    for i, h in enumerate(hypotheses, 1):
        print(f"  {i}. {h['hypothesis']}")
        print(f"     Counter: {h['counter_hypothesis']}")
        print(f"     Confirm: {h.get('confirming_evidence', 'N/A')}")
        print(f"     Disprove: {h.get('disproving_evidence', 'N/A')}")
        print(f"     Confidence: {h.get('confidence', 50)}%")
        print()

    # Financial claims
    claims = thesis.get('financial_claims', {})
    if isinstance(claims, str):
        claims = json.loads(claims)
    if claims:
        print(f"--- FINANCIAL CLAIMS ({len(claims)}) ---")
        for name, data in sorted(claims.items()):
            if isinstance(data, dict):
                if 'low' in data and 'high' in data:
                    print(f"  - {name}: {data['low']}-{data['high']} {data.get('unit', '')} [{data.get('source', '')}]")
                elif 'value' in data:
                    print(f"  - {name}: {data['value']} {data.get('unit', '')} [{data.get('source', '')}]")

    # Management scorecard
    if scorecard:
        print(f"\n--- MANAGEMENT SCORECARD ({len(scorecard)} promises) ---")
        for ms in scorecard:
            status = ms.get('assessment', 'pending').upper()
            low = ms.get('promise_value_low', '?')
            high = ms.get('promise_value_high', '?')
            unit = ms.get('promise_unit', '')
            actual = ms.get('actual_value')
            actual_str = f" → Actual: {actual} {ms.get('actual_unit', '')}" if actual else ""
            print(f"  [{status}] {ms['promise_text']} [{low}-{high} {unit}]{actual_str}")


def approve_thesis(conn, thesis_id):
    """Approve a draft thesis: set active, deactivate prior."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get thesis to find company_id
    cursor.execute("SELECT company_id FROM investment_theses WHERE id = %s", (thesis_id,))
    row = cursor.fetchone()
    if not row:
        print(f"  ✗ Thesis {thesis_id} not found")
        cursor.close()
        return False

    company_id = row['company_id']

    # Deactivate any existing active thesis for this company
    cursor.execute("""
        UPDATE investment_theses
        SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
        WHERE company_id = %s AND is_active = TRUE AND id != %s
    """, (company_id, thesis_id))
    deactivated = cursor.rowcount

    # Activate the draft
    cursor.execute("""
        UPDATE investment_theses
        SET is_active = TRUE, is_draft = FALSE,
            approved_by = 'human', updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (thesis_id,))

    # Log the decision
    cursor.execute("""
        INSERT INTO decision_log
            (company_id, thesis_id, decision_type, decision_text, rationale)
        VALUES (%s, %s, 'thesis_approved', 'Thesis approved by human review', 'Manual approval via approve_thesis.py')
    """, (company_id, thesis_id))

    conn.commit()
    cursor.close()

    if deactivated:
        print(f"  ✓ Deactivated {deactivated} prior thesis(es)")
    print(f"  ✓ Thesis {thesis_id} approved and activated")
    return True


def main():
    print("=" * 70)
    print("THESIS APPROVAL")
    print("=" * 70)

    # Parse arguments
    thesis_id = None
    list_mode = False
    for i, arg in enumerate(sys.argv):
        if arg == '--thesis-id' and i + 1 < len(sys.argv):
            thesis_id = int(sys.argv[i + 1])
        elif arg == '--list':
            list_mode = True

    conn = connect_db()
    if not conn:
        return
    print("  Connected to database")

    if list_mode or (not thesis_id):
        list_drafts(conn)
        if not thesis_id:
            print("\n  Usage: python approve_thesis.py --thesis-id N")
        conn.close()
        return

    # Get and display thesis
    thesis, kill, hypos, scorecard = get_thesis_detail(conn, thesis_id)
    if not thesis:
        print(f"  ✗ Thesis {thesis_id} not found")
        conn.close()
        return

    if not thesis['is_draft']:
        print(f"  ⚠ Thesis {thesis_id} is already approved (is_draft=FALSE)")
        conn.close()
        return

    display_thesis(thesis, kill, hypos, scorecard)

    # Confirm
    print(f"\n  Approve this thesis? (y/n): ", end='', flush=True)
    answer = input().strip().lower()

    if answer in ('y', 'yes'):
        approve_thesis(conn, thesis_id)
    else:
        print("  — Thesis remains as draft")

    conn.close()


if __name__ == "__main__":
    main()
