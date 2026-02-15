#!/usr/bin/env python3
"""
Stage 6: Delivery Tracking
Tracks report delivery readiness and logs what would be sent.
Email delivery is deferred — this script manages urgency classification
and delivery status tracking.

Usage:
    python deliver_reports.py                 # show pending deliveries
    python deliver_reports.py --mark-ready    # compute urgency for unclassified reports
"""

import sys
import json
from psycopg2.extras import RealDictCursor
from config import connect_db


def get_pending_reports(conn):
    """Get reports that haven't been delivered."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT ir.id, ir.urgency, ir.materiality, ir.report_delivered,
               ir.executive_summary, ir.created_at, ir.report_type,
               c.ticker, c.company_name,
               f.filing_type, f.filing_date
        FROM intelligence_reports ir
        JOIN filings f ON ir.filing_id = f.id
        JOIN companies c ON f.company_id = c.id
        WHERE ir.report_delivered = FALSE
        ORDER BY
            CASE ir.urgency
                WHEN 'immediate' THEN 1
                WHEN 'daily_digest' THEN 2
                WHEN 'weekly_rollup' THEN 3
                ELSE 4
            END,
            f.filing_date DESC
    """)
    reports = cursor.fetchall()
    cursor.close()
    return reports


def format_subject_line(report):
    """Generate what the email subject line would be."""
    ticker = report['ticker']
    filing_type = report['filing_type']
    report_type = report.get('report_type', 'filing_update')
    summary = (report.get('executive_summary') or '')[:60]

    prefixes = {
        'contrarian_alert': '[CONTRARIAN ALERT] ',
        'pre_earnings_brief': '[PRE-EARNINGS BRIEF] ',
        'earnings_review': '[EARNINGS REVIEW] ',
        'update': '[UPDATE] ',
        'earnings_briefing': '[EARNINGS BRIEFING] ',
        'filing_update': '',
    }
    prefix = prefixes.get(report_type, '')
    return f"{prefix}{ticker} {filing_type} — {summary}"


def display_delivery_summary(reports):
    """Display what would be delivered."""
    if not reports:
        print("\n✓ No pending deliveries. All reports have been delivered (or none exist).\n")
        return

    # Group by urgency
    immediate = [r for r in reports if r.get('urgency') == 'immediate']
    daily = [r for r in reports if r.get('urgency') == 'daily_digest']
    weekly = [r for r in reports if r.get('urgency') == 'weekly_rollup']
    other = [r for r in reports if r.get('urgency') not in ('immediate', 'daily_digest', 'weekly_rollup')]

    print(f"\n{'=' * 70}")
    print("DELIVERY STATUS")
    print(f"{'=' * 70}")
    print(f"Total Pending: {len(reports)}")
    print(f"  Immediate:    {len(immediate)}")
    print(f"  Daily Digest: {len(daily)}")
    print(f"  Weekly Rollup:{len(weekly)}")
    if other:
        print(f"  Unclassified: {len(other)}")
    print(f"{'=' * 70}")

    if immediate:
        print("\n🔴 IMMEDIATE (would send now):")
        for r in immediate:
            subject = format_subject_line(r)
            print(f"  Report #{r['id']}: {subject}")

    if daily:
        print("\n🟠 DAILY DIGEST:")
        for r in daily:
            print(f"  Report #{r['id']}: {r['ticker']} {r['filing_type']} ({r['filing_date']})")

    if weekly:
        print("\n🔵 WEEKLY ROLLUP:")
        for r in weekly:
            print(f"  Report #{r['id']}: {r['ticker']} {r['filing_type']} ({r['filing_date']})")

    if other:
        print("\n⚪ UNCLASSIFIED (need synthesis first):")
        for r in other:
            print(f"  Report #{r['id']}: {r['ticker']} {r['filing_type']} ({r['filing_date']}) — urgency: {r.get('urgency', 'none')}")

    print(f"\n{'=' * 70}")
    print("Email delivery is not yet configured.")
    print("Run 'python view_reports.py --html N > report.html' to export individual reports.")
    print(f"{'=' * 70}\n")


def main():
    print("=" * 70)
    print("STAGE 6: DELIVERY TRACKING")
    print("=" * 70)

    conn = connect_db()
    if not conn:
        return
    print("✓ Connected")

    reports = get_pending_reports(conn)
    display_delivery_summary(reports)

    conn.close()


if __name__ == "__main__":
    main()
