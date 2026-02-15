#!/usr/bin/env python3
"""
Report viewer: display and export intelligence reports.

Usage:
    python view_reports.py --latest
    python view_reports.py --ticker EQT
    python view_reports.py --id 3
    python view_reports.py --html 3        # writes HTML to stdout
    python view_reports.py --list          # list all reports
"""

import sys
import json
from psycopg2.extras import RealDictCursor
from config import connect_db


def list_reports(conn):
    """List all intelligence reports."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT ir.id, c.ticker, f.filing_type, f.filing_date,
               ir.materiality, ir.urgency, ir.report_delivered,
               LEFT(ir.executive_summary, 80) as summary_preview
        FROM intelligence_reports ir
        JOIN filings f ON ir.filing_id = f.id
        JOIN companies c ON f.company_id = c.id
        ORDER BY f.filing_date DESC
    """)
    reports = cursor.fetchall()
    cursor.close()
    return reports


def get_report(conn, report_id=None, ticker=None, latest=False):
    """Get a specific report or the latest."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if report_id:
        cursor.execute("""
            SELECT ir.*, c.ticker, c.company_name, f.filing_type, f.filing_date, f.accession_number
            FROM intelligence_reports ir
            JOIN filings f ON ir.filing_id = f.id
            JOIN companies c ON f.company_id = c.id
            WHERE ir.id = %s
        """, (report_id,))
    elif ticker:
        cursor.execute("""
            SELECT ir.*, c.ticker, c.company_name, f.filing_type, f.filing_date, f.accession_number
            FROM intelligence_reports ir
            JOIN filings f ON ir.filing_id = f.id
            JOIN companies c ON f.company_id = c.id
            WHERE c.ticker = %s
            ORDER BY f.filing_date DESC
        """, (ticker.upper(),))
    elif latest:
        cursor.execute("""
            SELECT ir.*, c.ticker, c.company_name, f.filing_type, f.filing_date, f.accession_number
            FROM intelligence_reports ir
            JOIN filings f ON ir.filing_id = f.id
            JOIN companies c ON f.company_id = c.id
            ORDER BY ir.created_at DESC
            LIMIT 1
        """)

    reports = cursor.fetchall()
    cursor.close()
    return reports


def display_report(report):
    """Display a report in formatted text."""
    print(f"\n{'=' * 70}")
    print(f"  {report['ticker']} — {report['filing_type']} Intelligence Report")
    print(f"  Filed: {report['filing_date']}  |  Report ID: {report['id']}")
    print(f"  Materiality: {report.get('materiality', 'N/A')}  |  Urgency: {report.get('urgency', 'N/A')}")
    print(f"{'=' * 70}")

    # Executive Summary
    summary = report.get('executive_summary', '')
    if summary:
        print(f"\n  EXECUTIVE SUMMARY")
        print(f"  {'-' * 50}")
        for line in _wrap(summary, 66):
            print(f"  {line}")

    # Key Insights
    insights = report.get('key_insights')
    if insights:
        if isinstance(insights, str):
            try:
                insights = json.loads(insights)
            except (json.JSONDecodeError, TypeError):
                insights = []
        if insights:
            print(f"\n  KEY INSIGHTS")
            print(f"  {'-' * 50}")
            for i in insights:
                if isinstance(i, dict):
                    mat = i.get('materiality', '?')
                    direction = i.get('direction', '?')
                    print(f"  [{mat:6s}] [{direction:8s}] {i.get('insight', i.get('finding', ''))}")
                else:
                    print(f"  - {i}")

    # Financial Analysis
    _print_json_section(report, 'financial_analysis', 'FINANCIAL ANALYSIS')
    _print_json_section(report, 'operational_analysis', 'OPERATIONAL ANALYSIS')
    _print_json_section(report, 'strategic_assessment', 'STRATEGIC ASSESSMENT')

    # Risks & Opportunities
    ro = report.get('risks_opportunities')
    if ro:
        if isinstance(ro, str):
            try:
                ro = json.loads(ro)
            except (json.JSONDecodeError, TypeError):
                ro = {}
        if isinstance(ro, dict):
            print(f"\n  RISKS & OPPORTUNITIES")
            print(f"  {'-' * 50}")
            for key in ['red_flags', 'upside_scenarios', 'downside_scenarios', 'key_monitoring_items']:
                items = ro.get(key, [])
                if items:
                    print(f"  {key.replace('_', ' ').title()}:")
                    for item in items:
                        print(f"    - {item}")

    # Actionable Takeaways
    _print_json_section(report, 'actionable_takeaways', 'ACTIONABLE TAKEAWAYS')

    # Peer Comparison
    _print_json_section(report, 'peer_comparison', 'PEER COMPARISON')

    print(f"\n{'=' * 70}\n")


def _print_json_section(report, field, title):
    """Print a JSON field as formatted text."""
    data = report.get(field)
    if not data or data == '' or data == '{}':
        return

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return

    if not data:
        return

    print(f"\n  {title}")
    print(f"  {'-' * 50}")

    if isinstance(data, dict):
        for key, val in data.items():
            label = key.replace('_', ' ').title()
            if isinstance(val, list):
                print(f"  {label}:")
                for item in val:
                    print(f"    - {item}")
            elif val:
                for line in _wrap(f"{label}: {val}", 66):
                    print(f"  {line}")
    elif isinstance(data, list):
        for item in data:
            print(f"  - {item}")


def _wrap(text, width):
    """Simple word wrap."""
    words = text.split()
    lines = []
    current = ''
    for word in words:
        if current and len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return lines or ['']


def main():
    mode = None
    value = None

    for i, arg in enumerate(sys.argv):
        if arg == '--latest':
            mode = 'latest'
        elif arg == '--list':
            mode = 'list'
        elif arg == '--ticker' and i + 1 < len(sys.argv):
            mode = 'ticker'
            value = sys.argv[i + 1]
        elif arg == '--id' and i + 1 < len(sys.argv):
            mode = 'id'
            value = int(sys.argv[i + 1])
        elif arg == '--html' and i + 1 < len(sys.argv):
            mode = 'html'
            value = int(sys.argv[i + 1])

    if not mode:
        print("Usage: python view_reports.py --latest | --list | --ticker EQT | --id N | --html N")
        return

    conn = connect_db()
    if not conn:
        return

    if mode == 'list':
        reports = list_reports(conn)
        if not reports:
            print("No reports found.")
        else:
            print(f"\n{'ID':>4s}  {'Ticker':6s}  {'Type':5s}  {'Date':12s}  {'Mat':6s}  {'Urgency':14s}  {'Summary'}")
            print(f"{'-' * 80}")
            for r in reports:
                delivered = '✓' if r['report_delivered'] else ' '
                preview = (r['summary_preview'] or '')[:50]
                print(f"{r['id']:4d}  {r['ticker']:6s}  {r['filing_type']:5s}  {str(r['filing_date']):12s}  {(r['materiality'] or '?'):6s}  {(r['urgency'] or '?'):14s}  {preview}")
        conn.close()
        return

    if mode == 'html':
        reports = get_report(conn, report_id=value)
        if reports and reports[0].get('full_report_html'):
            print(reports[0]['full_report_html'])
        else:
            print("No HTML report found.", file=sys.stderr)
        conn.close()
        return

    if mode == 'latest':
        reports = get_report(conn, latest=True)
    elif mode == 'ticker':
        reports = get_report(conn, ticker=value)
    elif mode == 'id':
        reports = get_report(conn, report_id=value)

    if not reports:
        print("No reports found.")
    else:
        for report in reports:
            display_report(report)

    conn.close()


if __name__ == "__main__":
    main()
