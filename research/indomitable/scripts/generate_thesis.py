#!/usr/bin/env python3
"""
Generate investment thesis for a company using Claude.

Reads the most recent 10-K (preferred) or 10-Q filing, industry profile,
and market context to produce a structured investment thesis stored in
the company_theses table.

Usage:
    python generate_thesis.py --ticker EQT
    python generate_thesis.py --ticker EQT --refresh   # regenerate active thesis
"""

import sys
import json
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor
from config import connect_db, get_anthropic_client, parse_claude_json, MODEL
from external_data import get_industry_context


def get_latest_filing(conn, company_id, prefer_10k=True):
    """Get the most recent 10-K or 10-Q filing with extracted metrics and differential analysis."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Prefer 10-K for thesis generation (annual = fuller picture)
    if prefer_10k:
        cursor.execute("""
            SELECT f.*, ir.executive_summary, ir.financial_analysis,
                   ir.operational_analysis, ir.strategic_assessment,
                   ir.risks_opportunities
            FROM filings f
            LEFT JOIN intelligence_reports ir ON ir.filing_id = f.id
            WHERE f.company_id = %s AND f.filing_type = '10-K' AND f.processed = TRUE
            ORDER BY f.filing_date DESC LIMIT 1
        """, (company_id,))
        row = cursor.fetchone()
        if row:
            cursor.close()
            return row

    # Fall back to most recent 10-Q or 10-K
    cursor.execute("""
        SELECT f.*, ir.executive_summary, ir.financial_analysis,
               ir.operational_analysis, ir.strategic_assessment,
               ir.risks_opportunities
        FROM filings f
        LEFT JOIN intelligence_reports ir ON ir.filing_id = f.id
        WHERE f.company_id = %s AND f.filing_type IN ('10-K', '10-Q') AND f.processed = TRUE
        ORDER BY f.filing_date DESC LIMIT 1
    """, (company_id,))
    row = cursor.fetchone()
    cursor.close()
    return row


def get_filing_metrics(conn, filing_id):
    """Get extracted metrics for a filing."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT metric_name, metric_value, metric_unit, metric_period
        FROM extracted_metrics WHERE filing_id = %s
        ORDER BY metric_name
    """, (filing_id,))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_latest_thesis_review(conn, company_id):
    """Get the most recent thesis_review recommendations from intelligence reports."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT ir.generation_metadata, ir.created_at, f.filing_type, f.filing_date
        FROM intelligence_reports ir
        JOIN filings f ON ir.filing_id = f.id
        WHERE f.company_id = %s
        AND ir.generation_metadata IS NOT NULL
        AND ir.generation_metadata->'thesis_review' IS NOT NULL
        AND (ir.generation_metadata->'thesis_review'->>'revision_recommended')::boolean = TRUE
        ORDER BY ir.created_at DESC
        LIMIT 1
    """, (company_id,))
    row = cursor.fetchone()
    cursor.close()
    if not row:
        return None
    metadata = row['generation_metadata']
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    review = metadata.get('thesis_review', {})
    review['_source_filing_type'] = row['filing_type']
    review['_source_filing_date'] = str(row['filing_date'])
    review['_report_date'] = str(row['created_at'])
    return review


def get_supplementary_data_for_thesis(conn, company_id, days_back=60):
    """Get recent press releases, news, and transcripts for thesis refresh context."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT source_type, title, published_date, content
        FROM data_sources
        WHERE company_id = %s
        AND published_date >= CURRENT_DATE - interval '%s days'
        ORDER BY published_date DESC
        LIMIT 5
    """, (company_id, days_back))
    results = cursor.fetchall()
    cursor.close()
    return results


def get_active_thesis(conn, company_id, thesis_type='bull'):
    """Check if an active thesis already exists."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT * FROM company_theses
        WHERE company_id = %s AND thesis_type = %s AND is_active = TRUE
    """, (company_id, thesis_type))
    row = cursor.fetchone()
    cursor.close()
    return row


def build_thesis_prompt(company, filing, metrics, industry_profile, external_context,
                        previous_thesis=None, thesis_review=None, supplementary=None):
    """Build the Claude prompt for thesis generation."""
    sector = industry_profile.get('sector', 'General') if industry_profile else 'General'
    prompt_context = industry_profile.get('prompt_context', '') if industry_profile else ''

    sections = []
    sections.append(f"""{prompt_context}

You are a senior {sector} equity analyst generating a core investment thesis for {company['ticker']} ({company['company_name']}).

Your task: Identify the core investment thesis — what creates value for this company, what are the key uncertainties where consensus could be wrong in either direction, and what 5-6 metrics most directly measure whether the thesis is working.

COMPANY: {company['ticker']} — {company['company_name']}
FILING: {filing['filing_type']} dated {filing['filing_date']}""")

    # Inject previous thesis for continuity on --refresh
    if previous_thesis:
        prev_drivers = previous_thesis.get('key_value_drivers', [])
        if isinstance(prev_drivers, str):
            prev_drivers = json.loads(prev_drivers)
        prev_uncertainties = previous_thesis.get('key_uncertainties', [])
        if isinstance(prev_uncertainties, str):
            prev_uncertainties = json.loads(prev_uncertainties)
        prev_metrics = previous_thesis.get('key_metrics', [])
        if isinstance(prev_metrics, str):
            prev_metrics = json.loads(prev_metrics)

        sections.append(f"""
--- PREVIOUS THESIS (evolve, don't discard without reason) ---
Summary: {previous_thesis.get('thesis_summary', '')}

Value Drivers:
{chr(10).join(f'  - {d}' for d in prev_drivers)}

Key Uncertainties:
{chr(10).join(f'  - {u}' for u in prev_uncertainties)}

Key Metrics:
{chr(10).join(f'  - {m}' for m in prev_metrics)}

INSTRUCTIONS: Evolve this thesis based on the latest filing and market context. Add new themes that have emerged, remove themes that are no longer relevant, but preserve existing themes that remain valid. Do NOT discard the previous thesis wholesale — build on it.""")

    # Synthesis feedback (thesis review recommendations from latest intelligence report)
    if thesis_review:
        suggested = thesis_review.get('suggested_changes', {})
        feedback_lines = []
        feedback_lines.append(f"Trigger: {thesis_review.get('trigger_type', 'unknown')}")
        feedback_lines.append(f"Evidence: {thesis_review.get('evidence', '')}")
        if suggested:
            for key, label in [('add_value_drivers', 'ADD driver'),
                               ('remove_value_drivers', 'REMOVE driver'),
                               ('add_uncertainties', 'ADD uncertainty'),
                               ('remove_uncertainties', 'REMOVE uncertainty'),
                               ('add_metrics', 'ADD metric'),
                               ('remove_metrics', 'REMOVE metric')]:
                for item in suggested.get(key, []):
                    feedback_lines.append(f"  {label}: {item}")
            note = suggested.get('thesis_summary_note')
            if note:
                feedback_lines.append(f"  Summary revision: {note}")

        sections.append(f"""
--- SYNTHESIS FEEDBACK (from latest intelligence report, {thesis_review.get('_source_filing_type', '')} {thesis_review.get('_source_filing_date', '')}) ---
The most recent synthesis identified issues with the current thesis and recommended specific changes.
You MUST address each recommendation below — either incorporate it or explain why it's not warranted.

{chr(10).join(feedback_lines)}""")

    # Supplementary data (press releases, transcripts, news)
    if supplementary:
        supp_list = []
        for s in supplementary:
            content = s.get('content', '')
            if s['source_type'] == 'earnings_press_release':
                max_len = 8000
            elif s['source_type'] == 'earnings_transcript':
                max_len = 2000
            else:
                max_len = 500
            supp_list.append({
                'type': s['source_type'],
                'title': s.get('title', ''),
                'date': str(s.get('published_date', '')),
                'content': content[:max_len] if content else '',
            })
        sections.append(f"""
--- SUPPLEMENTARY DATA (press releases, news, earnings transcripts) ---
This data provides recent context beyond the primary filing. Use it to update capex guidance, production targets, or other forward-looking statements.
{json.dumps(supp_list, indent=2, default=str)}""")

    # Filing analysis data
    filing_data = {}
    for key in ['executive_summary', 'financial_analysis', 'operational_analysis',
                'strategic_assessment', 'risks_opportunities']:
        val = filing.get(key, '')
        if val:
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
            filing_data[key] = val

    if filing_data:
        sections.append(f"""
--- FILING ANALYSIS ---
{json.dumps(filing_data, indent=2, default=str)}""")

    # Metrics
    if metrics:
        metrics_list = [{'name': m['metric_name'], 'value': str(m['metric_value']),
                        'unit': m['metric_unit'], 'period': m['metric_period']} for m in metrics]
        sections.append(f"""
--- EXTRACTED METRICS ---
{json.dumps(metrics_list, indent=2, default=str)}""")

    # Market context
    if external_context:
        sections.append(f"""
--- CURRENT MARKET CONTEXT ---
{json.dumps(external_context, indent=2, default=str)}""")

    sections.append("""
Generate a structured investment thesis. Return as JSON with this exact structure:

{
  "thesis_summary": "2-3 sentence bull thesis — what creates value and why this stock could outperform. Must be PRICE-GROUNDED (see guidelines below).",
  "key_value_drivers": ["3-5 specific value drivers, each quantified with actual data from the filing"],
  "key_uncertainties": ["4-6 uncertainties where consensus could be wrong in either direction, quantitatively framed where data exists"],
  "key_metrics": ["5-6 specific metrics that most directly measure whether the thesis is working. Use exact names where possible, e.g. 'realized_price_per_mcfe', 'production_volume_bcfe', 'free_cash_flow', 'ROIC', 'net_debt_to_ebitda'"],
  "financial_claims": {
    "capex_guidance": {"low": 1400, "high": 1500, "unit": "M", "period": "2026", "source": "10-K or press release"},
    "operating_cash_flow": {"value": 861, "unit": "M", "period": "FY2025", "source": "10-K"},
    "production_volume": {"value": 590, "unit": "Bcfe", "period": "FY2025", "source": "10-K"},
    "hedge_volume": {"value": 315, "unit": "Bcf", "price": 3.49, "period": "2026", "source": "10-K"},
    "realized_price": {"value": 2.87, "unit": "$/Mcfe", "period": "FY2025", "source": "10-K"},
    "breakeven_price": {"value": 3.80, "unit": "$/Mcf", "basis": "self-funding at capex guidance", "source": "derived"}
  }
}

FINANCIAL_CLAIMS INSTRUCTIONS:
The financial_claims object captures the KEY NUMBERS your thesis depends on. These are stored as structured data and injected into downstream analysis to guarantee number consistency.
- Include EVERY specific dollar amount, volume, price, or percentage your thesis_summary and value_drivers reference
- Use the field names shown above where applicable; add additional fields as needed (e.g., "net_debt", "ebitda", "dividend_yield")
- Each claim MUST have a "source" field indicating where the number comes from (filing type, press release, or "derived" for computed values)
- For range values, use "low" and "high" fields. For single values, use "value"
- Units: "M" = millions, "B" = billions, "Bcf" = billion cubic feet, "Bcfe" = billion cubic feet equivalent, etc.
- If a number is a forward estimate/guidance, note the period (e.g., "2026", "FY2026")
- Do NOT include numbers you aren't confident about — only include claims grounded in the source data

Guidelines:

PRICE-GROUNDED ANALYSIS (CRITICAL):
When the filing provides hedge book data, forward curve prices, capex guidance, or breakeven economics, you MUST connect them into a coherent economic picture. The thesis summary must answer: "At what price does this company's strategy work, and what does the data say about whether that price is achievable?"

BAD thesis_summary: "Company is positioned to generate superior returns if natural gas prices recover from current $3.25/MMBtu levels."
WHY BAD: This is a tautology — "stock goes up if prices go up" applies to every gas producer and adds zero analytical value.

GOOD thesis_summary: "$861M operating cash flow against $1.4-1.5B capex program creates $540-640M funding gap; 315 Bcf hedged at $3.27/MMBtu locks base cash flow but self-funding requires ~$3.80 realized pricing, achievable at forward curve of $4.35 but leaving thin margin for operational misses."
WHY GOOD: Uses actual operating cash flow (not a derived metric) as the baseline, so the funding gap arithmetic is verifiable. Connects OCF → capex → gap → hedge coverage → breakeven → forward curve.

FUNDING GAP METHODOLOGY: When computing a funding gap, ALWAYS use operating cash flow as the baseline — not hedge revenue, not a derived figure. The synthesis will present your numbers alongside actual OCF data in the same document. If you write "$X gap" the reader will check it against OCF minus capex. The arithmetic must work.

ANTI-TAUTOLOGY RULE FOR VALUE DRIVERS:
Each value driver must be specific and quantified with actual data. Do NOT write generic statements.
BAD driver: "Hedge protection provides stability and downside protection"
GOOD driver: "315 Bcf hedged at $3.27/MMBtu through 2026 covers 70% of planned production, locking floor revenue of ~$1.0B"
BAD driver: "Low-cost operations support margins"
GOOD driver: "Haynesville wells at $0.95/Mcfe LOE vs peer average $1.20, providing $0.25/Mcfe structural advantage on 1.2 Tcfe base"

QUANTITATIVELY FRAMED UNCERTAINTIES:
Where the filing provides data, uncertainties must include the specific numbers at stake.
BAD: "Natural gas price volatility could impact results"
GOOD: "Unhedged 30% of production (~135 Bcf) exposed to spot; $0.50/MMBtu swing = ~$67M revenue impact, difference between FCF positive and funding gap"

OTHER GUIDELINES:
- The thesis should be SPECIFIC to this company's competitive position, not generic sector commentary
- Key uncertainties should be TWO-WAY (could go better or worse than expected), not just downside risks
- Key metrics should be measurable and trackable quarter over quarter

Return ONLY valid JSON, no other text.""")

    return '\n'.join(sections)


def compute_derived_claims(claims):
    """
    Compute derived financial metrics from structured claims.

    Python does the arithmetic. Claude interprets the numbers.
    This ensures funding_gap, capex_increase_pct, etc. are consistent
    across all pipeline stages.

    Modifies claims in-place and returns it.
    """
    if not claims:
        return claims

    # --- Funding gap: capex - operating_cash_flow ---
    capex = claims.get('capex_guidance', {})
    ocf = claims.get('operating_cash_flow', {})
    if capex and ocf:
        ocf_val = ocf.get('value')
        capex_low = capex.get('low') or capex.get('value')
        capex_high = capex.get('high') or capex.get('value')
        if ocf_val is not None and capex_low is not None:
            gap_low = round(capex_low - ocf_val)
            gap_high = round((capex_high or capex_low) - ocf_val)
            claims['funding_gap'] = {
                'low': min(gap_low, gap_high),
                'high': max(gap_low, gap_high),
                'unit': 'M',
                'methodology': 'capex_guidance minus operating_cash_flow',
                'source': 'derived',
            }

    # --- Capex increase percentage (vs prior if available) ---
    prior_capex = claims.get('prior_capex', {})
    if capex and prior_capex:
        prior_val = prior_capex.get('value') or prior_capex.get('high')
        capex_mid = capex.get('value') or (
            ((capex.get('low', 0) + capex.get('high', 0)) / 2) if capex.get('low') else None
        )
        if prior_val and capex_mid and prior_val > 0:
            pct = round(((capex_mid - prior_val) / prior_val) * 100, 1)
            claims['capex_increase_pct'] = {
                'value': pct,
                'unit': '%',
                'baseline': f"{prior_val}M ({prior_capex.get('period', 'prior')})",
                'source': 'derived',
            }

    # --- Hedge coverage percentage ---
    hedge = claims.get('hedge_volume', {})
    production = claims.get('production_volume', {})
    if hedge and production:
        hedge_vol = hedge.get('value')
        prod_vol = production.get('value')
        if hedge_vol and prod_vol and prod_vol > 0:
            coverage = round((hedge_vol / prod_vol) * 100, 1)
            claims['hedge_coverage_pct'] = {
                'value': coverage,
                'unit': '%',
                'source': 'derived',
            }

    # --- Breakeven self-funding price (if OCF, capex, and production available) ---
    # breakeven = capex / production (simplified: price at which revenue = capex)
    # Only compute if not already provided by Claude
    if 'breakeven_price' not in claims:
        if capex and ocf and production:
            capex_mid = capex.get('value') or (
                ((capex.get('low', 0) + capex.get('high', 0)) / 2) if capex.get('low') else None
            )
            prod_vol = production.get('value')
            ocf_val = ocf.get('value')
            realized = claims.get('realized_price', {}).get('value')
            if capex_mid and prod_vol and ocf_val and realized and prod_vol > 0 and realized > 0:
                # revenue_at_realized = prod_vol * realized (in same units as OCF)
                # We want price P such that (P/realized) * OCF = capex
                # => P = capex * realized / OCF
                breakeven = round(capex_mid * realized / ocf_val, 2)
                claims['breakeven_price'] = {
                    'value': breakeven,
                    'unit': claims.get('realized_price', {}).get('unit', '$/Mcfe'),
                    'basis': 'self-funding at capex guidance',
                    'source': 'derived',
                }

    return claims


def save_thesis(conn, company_id, thesis, filing_id, model):
    """Save thesis to company_theses table, deactivating any existing active thesis."""
    cursor = conn.cursor()

    # Remove old inactive theses, then deactivate current active thesis
    cursor.execute("""
        DELETE FROM company_theses
        WHERE company_id = %s AND thesis_type = 'bull' AND is_active = FALSE
    """, (company_id,))
    cursor.execute("""
        UPDATE company_theses SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
        WHERE company_id = %s AND thesis_type = 'bull' AND is_active = TRUE
    """, (company_id,))

    # Insert new thesis
    expires_at = datetime.now() + timedelta(days=365)
    financial_claims = thesis.get('financial_claims', {})
    cursor.execute("""
        INSERT INTO company_theses
            (company_id, thesis_type, thesis_summary, key_value_drivers,
             key_uncertainties, key_metrics, financial_claims, source_filing_ids,
             generated_by, model_used, expires_at, is_active)
        VALUES (%s, 'bull', %s, %s, %s, %s, %s, %s, 'claude', %s, %s, TRUE)
        RETURNING id
    """, (
        company_id,
        thesis['thesis_summary'],
        json.dumps(thesis['key_value_drivers']),
        json.dumps(thesis['key_uncertainties']),
        json.dumps(thesis['key_metrics']),
        json.dumps(financial_claims),
        json.dumps([filing_id]),
        model,
        expires_at,
    ))

    thesis_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    return thesis_id


def main():
    print("=" * 70)
    print("INVESTMENT THESIS GENERATOR")
    print("=" * 70)

    # Parse arguments
    ticker = None
    refresh = False
    for i, arg in enumerate(sys.argv):
        if arg == '--ticker' and i + 1 < len(sys.argv):
            ticker = sys.argv[i + 1].upper()
        elif arg == '--refresh':
            refresh = True

    if not ticker:
        print("Usage: python generate_thesis.py --ticker EQT [--refresh]")
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
        print(f"  Company {ticker} not found in database")
        conn.close()
        return

    print(f"  Company: {company['ticker']} — {company['company_name']}")

    # Check for existing thesis
    existing = get_active_thesis(conn, company['id'])
    if existing and not refresh:
        print(f"\n  Active thesis already exists (created {existing['created_at']})")
        print(f"  Expires: {existing['expires_at']}")
        print(f"  Summary: {existing['thesis_summary'][:200]}...")
        print(f"\n  Use --refresh to regenerate")
        conn.close()
        return

    # Get filing
    print("\n  Finding best filing for thesis generation...")
    filing = get_latest_filing(conn, company['id'])
    if not filing:
        print("  No processed 10-K or 10-Q found")
        conn.close()
        return
    print(f"  Using: {filing['filing_type']} dated {filing['filing_date']}")

    # Get metrics
    metrics = get_filing_metrics(conn, filing['id'])
    print(f"  Extracted metrics: {len(metrics)}")

    # Get industry profile
    profile = None
    if company.get('industry_profile_id'):
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM industry_profiles WHERE id = %s", (company['industry_profile_id'],))
        profile = cursor.fetchone()
        cursor.close()

    # Get external context
    print("  Fetching market context...")
    external_context = get_industry_context(conn, profile, company_ticker=ticker) if profile else {}

    # On refresh, fetch thesis review recommendations and supplementary data
    thesis_review = None
    supplementary = None
    if refresh:
        print("  Fetching thesis review recommendations...")
        thesis_review = get_latest_thesis_review(conn, company['id'])
        if thesis_review:
            print(f"    ✓ Found review: {thesis_review.get('trigger_type', '?')} from {thesis_review.get('_source_filing_date', '?')}")
        else:
            print("    — No thesis review recommendations found")

        print("  Fetching supplementary data (press releases, news)...")
        supplementary = get_supplementary_data_for_thesis(conn, company['id'])
        if supplementary:
            print(f"    ✓ {len(supplementary)} supplementary sources found")
        else:
            print("    — No recent supplementary data")

    # Build prompt and call Claude
    print("\n  Generating thesis with Claude...")
    previous_thesis = existing if (refresh and existing) else None
    if previous_thesis:
        print("  Evolving from previous thesis (--refresh mode)")
    prompt = build_thesis_prompt(company, filing, metrics, profile, external_context,
                                 previous_thesis=previous_thesis,
                                 thesis_review=thesis_review,
                                 supplementary=supplementary)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        thesis = parse_claude_json(response.content[0].text)
        if not thesis:
            print("  Failed to parse Claude response")
            conn.close()
            return
    except Exception as e:
        print(f"  Claude API error: {e}")
        conn.close()
        return

    # Validate required fields
    required = ['thesis_summary', 'key_value_drivers', 'key_uncertainties', 'key_metrics']
    for field in required:
        if field not in thesis:
            print(f"  Missing required field: {field}")
            conn.close()
            return

    # Compute derived financial claims (Python does the arithmetic)
    if thesis.get('financial_claims'):
        print("\n  Computing derived financial claims...")
        claims_before = set(thesis['financial_claims'].keys())
        thesis['financial_claims'] = compute_derived_claims(thesis['financial_claims'])
        claims_after = set(thesis['financial_claims'].keys())
        derived = claims_after - claims_before
        if derived:
            print(f"  ✓ Derived: {', '.join(sorted(derived))}")
        else:
            print(f"  ✓ No additional derivations needed")
    else:
        print("\n  ⚠ Claude did not produce financial_claims — thesis will lack structured claims")

    # Save
    thesis_id = save_thesis(conn, company['id'], thesis, filing['id'], MODEL)
    print(f"\n  Thesis saved (ID: {thesis_id})")

    # Display
    print(f"\n{'=' * 70}")
    print(f"INVESTMENT THESIS: {ticker}")
    print(f"{'=' * 70}")
    print(f"\nSummary: {thesis['thesis_summary']}")
    print(f"\nValue Drivers:")
    for d in thesis['key_value_drivers']:
        print(f"  - {d}")
    print(f"\nKey Uncertainties:")
    for u in thesis['key_uncertainties']:
        print(f"  - {u}")
    print(f"\nKey Metrics:")
    for m in thesis['key_metrics']:
        print(f"  - {m}")

    # Display financial claims
    claims = thesis.get('financial_claims', {})
    if claims:
        print(f"\nFinancial Claims ({len(claims)} items):")
        for name, data in sorted(claims.items()):
            if isinstance(data, dict):
                if 'low' in data and 'high' in data:
                    print(f"  - {name}: {data['low']}-{data['high']} {data.get('unit', '')} [{data.get('source', '')}]")
                elif 'value' in data:
                    print(f"  - {name}: {data['value']} {data.get('unit', '')} [{data.get('source', '')}]")

    conn.close()
    print(f"\n  Done")


if __name__ == "__main__":
    main()
