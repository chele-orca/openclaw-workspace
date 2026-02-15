#!/usr/bin/env python3
"""
Extract structured metrics from supplementary data sources (earnings releases,
press releases, transcripts).

Processes data_sources entries and stores extracted metrics in extracted_metrics
table (via data_source_id). This ensures the thesis prompt gets structured
numbers instead of raw text.

Usage:
    python extract_supplementary.py --ticker CRK                  # all unprocessed sources
    python extract_supplementary.py --ticker CRK --source-id 170  # specific source
    python extract_supplementary.py --all                         # all companies
"""

import sys
import json
from psycopg2.extras import RealDictCursor, execute_values
from config import connect_db, get_anthropic_client, parse_claude_json, MODEL


def get_unprocessed_sources(conn, company_id=None, source_id=None):
    """Get data sources that haven't been extracted yet."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if source_id:
        cursor.execute("""
            SELECT ds.*, c.ticker, c.company_name
            FROM data_sources ds
            JOIN companies c ON c.id = ds.company_id
            WHERE ds.id = %s
        """, (source_id,))
    elif company_id:
        cursor.execute("""
            SELECT ds.*, c.ticker, c.company_name
            FROM data_sources ds
            JOIN companies c ON c.id = ds.company_id
            WHERE ds.company_id = %s
            AND ds.source_type IN ('earnings_press_release', 'earnings_transcript', 'press_release')
            AND ds.content IS NOT NULL
            AND ds.id NOT IN (SELECT DISTINCT data_source_id FROM extracted_metrics WHERE data_source_id IS NOT NULL)
            ORDER BY ds.published_date DESC
        """, (company_id,))
    else:
        cursor.execute("""
            SELECT ds.*, c.ticker, c.company_name
            FROM data_sources ds
            JOIN companies c ON c.id = ds.company_id
            WHERE ds.source_type IN ('earnings_press_release', 'earnings_transcript', 'press_release')
            AND ds.content IS NOT NULL
            AND ds.id NOT IN (SELECT DISTINCT data_source_id FROM extracted_metrics WHERE data_source_id IS NOT NULL)
            ORDER BY ds.published_date DESC
        """)

    rows = cursor.fetchall()
    cursor.close()
    return rows


def build_extraction_prompt(source, ticker, company_name):
    """Build Claude prompt for extracting metrics from a supplementary source."""
    source_type = source['source_type']
    content = source['content'] or ''

    prompt = f"""You are a financial analyst extracting structured data from a {source_type.replace('_', ' ')} for {ticker} ({company_name}).

Source: {source.get('title', source_type)}
Date: {source.get('published_date', 'unknown')}

Content:
{content}

Extract ALL quantitative financial and operational metrics. Be thorough — capture everything with a number.

Return JSON:
{{
  "metrics": [
    {{
      "metric_name": "descriptive_snake_case_name",
      "metric_value": 1234.5,
      "metric_unit": "M|B|Bcf|Bcfe|$/Mcf|$/MMBtu|%|x|rigs|wells|feet",
      "metric_period": "Q4 2025|FY2025|2026E",
      "section": "balance_sheet|income_statement|cash_flow|operations|guidance|reserves",
      "confidence": 0.95
    }}
  ]
}}

EXTRACTION RULES:
1. Use consistent metric_name conventions:
   - Balance sheet: total_debt, cash_and_equivalents, net_debt, total_assets, total_equity, shares_outstanding
   - Income: total_revenue, natural_gas_revenue, oil_revenue, operating_income, net_income, ebitda, adjusted_ebitda
   - Cash flow: operating_cash_flow, capital_expenditures, midstream_capex, free_cash_flow, acquisitions, divestitures
   - Operations: production_volume, oil_production, gas_production, realized_gas_price, realized_oil_price, operating_cost_per_unit, loe_per_unit
   - Guidance: capex_guidance, production_guidance, debt_reduction_target
   - Reserves: proved_reserves, reserve_replacement_ratio, pv10_value
   - Hedging: hedge_volume, hedge_price, hedge_period
   - Valuation: shares_outstanding, book_value_per_share
   - Per-share: eps_basic, eps_diluted, adjusted_eps
   - Debt instruments: interest_expense, credit_facility_available, credit_facility_total, debt_maturity_next, total_long_term_debt, weighted_avg_interest_rate

2. Units: "M" = millions of dollars, "B" = billions, "Bcf" = billion cubic feet, etc.
   - Convert "(in thousands)" to M by dividing by 1000
   - If table says "$2,809,066 thousands", record as 2809.066 M

3. Period: Use the specific period the metric applies to. For balance sheet items, use the date (e.g., "2025-12-31"). For flow items, use the period (e.g., "Q4 2025" or "FY2025").

4. Extract BOTH current period AND prior period comparatives when available.

5. For guidance/forward-looking items, append "_guidance" and use the forward period.

6. Compute net_debt = total_debt - cash_and_equivalents if both are available.

7. DEBT INSTRUMENTS (critical for financing risk analysis):
   - interest_expense: annual interest cost on all debt (M)
   - credit_facility_available: available/undrawn capacity on revolving credit facility (M)
   - credit_facility_total: total revolving credit facility size (M)
   - debt_maturity_next: nearest significant debt maturity amount and year
   - total_long_term_debt: gross long-term debt (M)
   - weighted_avg_interest_rate: weighted average interest rate across all debt (%)
   Look for these in balance sheet footnotes, debt schedule tables, and liquidity discussion sections.

Return ONLY valid JSON."""

    return prompt


def save_metrics(conn, data_source_id, metrics):
    """Save extracted metrics to database."""
    if not metrics:
        return 0

    cursor = conn.cursor()
    records = []
    for m in metrics:
        name = m.get('metric_name', '')
        value = m.get('metric_value')
        if not name or value is None:
            continue
        records.append((
            None,  # filing_id
            data_source_id,
            name,
            value,
            m.get('metric_unit', ''),
            m.get('metric_period', ''),
            m.get('section', 'supplementary'),
            m.get('confidence', 0.8),
        ))

    if not records:
        return 0

    execute_values(cursor, """
        INSERT INTO extracted_metrics
            (filing_id, data_source_id, metric_name, metric_value, metric_unit,
             metric_period, section_name, extraction_confidence)
        VALUES %s
    """, records)

    conn.commit()
    cursor.close()
    return len(records)


def extract_source(conn, client, source):
    """Extract metrics from a single supplementary source."""
    ticker = source['ticker']
    company_name = source['company_name']
    source_type = source['source_type']
    title = source.get('title', source_type)
    content = source.get('content', '')

    if not content or len(content) < 100:
        print(f"    — Skipping {title}: insufficient content ({len(content)} chars)")
        return 0

    print(f"    Extracting from: {title} ({len(content)} chars)")

    prompt = build_extraction_prompt(source, ticker, company_name)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text
        result = parse_claude_json(raw)
        if not result:
            print(f"    ✗ Failed to parse Claude response ({len(raw)} chars)")
            print(f"    First 200 chars: {raw[:200]}")
            return 0

        metrics = result.get('metrics', [])
        if not metrics:
            print(f"    — No metrics extracted")
            return 0

        count = save_metrics(conn, source['id'], metrics)
        print(f"    ✓ {count} metrics extracted")
        return count

    except Exception as e:
        print(f"    ✗ Extraction error: {e}")
        return 0


def main():
    print("=" * 70)
    print("SUPPLEMENTARY SOURCE EXTRACTION")
    print("=" * 70)

    # Parse arguments
    ticker = None
    source_id = None
    all_mode = False
    for i, arg in enumerate(sys.argv):
        if arg == '--ticker' and i + 1 < len(sys.argv):
            ticker = sys.argv[i + 1].upper()
        elif arg == '--source-id' and i + 1 < len(sys.argv):
            source_id = int(sys.argv[i + 1])
        elif arg == '--all':
            all_mode = True

    if not ticker and not all_mode and not source_id:
        print("Usage: python extract_supplementary.py --ticker CRK")
        print("       python extract_supplementary.py --ticker CRK --source-id 170")
        print("       python extract_supplementary.py --all")
        sys.exit(1)

    # Initialize
    client = get_anthropic_client()
    if not client:
        return

    conn = connect_db()
    if not conn:
        return
    print("  Connected to database")

    # Get company ID if ticker specified
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

    # Get sources to process
    sources = get_unprocessed_sources(conn, company_id, source_id)
    if not sources:
        print("  No unprocessed supplementary sources found.")
        conn.close()
        return

    print(f"  Found {len(sources)} source(s) to extract")

    # Process each source
    total_metrics = 0
    for source in sources:
        total_metrics += extract_source(conn, client, source)

    print(f"\n{'=' * 70}")
    print(f"  Total: {total_metrics} metrics extracted from {len(sources)} source(s)")
    print(f"{'=' * 70}")

    conn.close()


if __name__ == "__main__":
    main()
