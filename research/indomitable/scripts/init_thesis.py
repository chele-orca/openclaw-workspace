#!/usr/bin/env python3
"""
Initialize an investment thesis for a company.

Replaces generate_thesis.py with the new investment process:
- Assembles all available data (filings, metrics, external context, consensus)
- Runs financial model to compute derived metrics
- Calls Claude to draft thesis with variant perception, kill criteria,
  hypotheses, pre-mortem, financial claims, and model parameters
- Saves as DRAFT (is_draft=TRUE, is_active=FALSE) — human must approve

Usage:
    python init_thesis.py --ticker CRK
    python init_thesis.py --ticker CRK --refresh   # regenerate from existing thesis
"""

import sys
import json
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor
from config import connect_db, get_anthropic_client, parse_claude_json, MODEL
from external_data import get_industry_context
from financial_model import EPModel


def get_latest_filings(conn, company_id, limit=3):
    """Get the most recent processed filings with extracted data."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT f.*, ir.executive_summary, ir.financial_analysis,
               ir.operational_analysis, ir.strategic_assessment,
               ir.risks_opportunities
        FROM filings f
        LEFT JOIN intelligence_reports ir ON ir.filing_id = f.id
        WHERE f.company_id = %s AND f.filing_type IN ('10-K', '10-Q') AND f.processed = TRUE
        ORDER BY f.filing_date DESC LIMIT %s
    """, (company_id, limit))
    rows = cursor.fetchall()
    cursor.close()
    return rows


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


def get_forward_statements(conn, filing_id):
    """Get forward-looking statements / guidance from a filing."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT statement_category, statement_text, quantitative_value,
               value_unit, timeframe, confidence_level
        FROM forward_statements WHERE filing_id = %s
        ORDER BY statement_category
    """, (filing_id,))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_supplementary_data(conn, company_id, days_back=90):
    """Get recent press releases, news, and transcripts."""
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


def get_supplementary_metrics(conn, company_id, days_back=90):
    """Get extracted metrics from supplementary sources (earnings releases, etc.)."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT em.metric_name, em.metric_value, em.metric_unit, em.metric_period,
               em.section_name, ds.source_type, ds.title, ds.published_date
        FROM extracted_metrics em
        JOIN data_sources ds ON ds.id = em.data_source_id
        WHERE ds.company_id = %s
        AND ds.published_date >= CURRENT_DATE - interval '%s days'
        ORDER BY ds.published_date DESC, em.section_name, em.metric_name
    """, (company_id, days_back))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_guidance_history(conn, company_id):
    """Get guidance revision history for credibility assessment."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT gh.metric_name, gh.guidance_value_low, gh.guidance_value_high,
               gh.guidance_unit, gh.guidance_period, gh.source_date,
               gh.revision_pct, gh.revision_reason,
               gh.superseded_by IS NOT NULL AS was_revised
        FROM guidance_history gh
        WHERE gh.company_id = %s
        ORDER BY gh.metric_name, gh.source_date
    """, (company_id,))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_existing_thesis(conn, company_id):
    """Get the active investment thesis if one exists (from new table)."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT * FROM investment_theses
        WHERE company_id = %s AND is_active = TRUE
        ORDER BY created_at DESC LIMIT 1
    """, (company_id,))
    row = cursor.fetchone()
    cursor.close()
    if row:
        return row

    # Fall back to old company_theses table for migration
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT * FROM company_theses
        WHERE company_id = %s AND is_active = TRUE
        ORDER BY created_at DESC LIMIT 1
    """, (company_id,))
    row = cursor.fetchone()
    cursor.close()
    return row


def get_peer_data(conn, industry_profile_id, exclude_company_id):
    """Get peer company metrics for context."""
    if not industry_profile_id:
        return []
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT c.ticker, c.company_name, ct.thesis_summary, ct.financial_claims
        FROM companies c
        LEFT JOIN company_theses ct ON ct.company_id = c.id AND ct.is_active = TRUE
        WHERE c.industry_profile_id = %s AND c.id != %s AND c.active = TRUE
    """, (industry_profile_id, exclude_company_id))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_consensus_estimates(conn, ticker):
    """Fetch analyst consensus estimates from external sources."""
    from external_data import (fetch_stockanalysis_estimates,
                                fetch_fmp_analyst_estimates, fetch_fmp_price_target)
    estimates = {}

    # StockAnalysis (free, scraping)
    try:
        sa = fetch_stockanalysis_estimates(ticker)
        if sa:
            estimates['stockanalysis'] = sa
    except Exception as e:
        print(f"  ⚠ StockAnalysis estimates: {e}")

    # FMP estimates
    try:
        fmp = fetch_fmp_analyst_estimates(ticker)
        if fmp:
            estimates['fmp_estimates'] = fmp
    except Exception as e:
        print(f"  ⚠ FMP estimates: {e}")

    # FMP price target
    try:
        pt = fetch_fmp_price_target(ticker)
        if pt:
            estimates['price_target'] = pt
    except Exception as e:
        print(f"  ⚠ FMP price target: {e}")

    return estimates


def build_thesis_prompt(company, filings, metrics_by_filing, forward_stmts,
                        industry_profile, external_context, model_summary,
                        consensus, peer_data, supplementary, supplementary_metrics=None,
                        previous_thesis=None, guidance_history=None):
    """Build the Claude prompt for thesis initialization."""
    sector = industry_profile.get('sector', 'General') if industry_profile else 'General'
    prompt_context = industry_profile.get('prompt_context', '') if industry_profile else ''
    ticker = company['ticker']

    sections = []
    sections.append(f"""{prompt_context}

You are a senior {sector} equity analyst initializing an investment thesis for {ticker} ({company['company_name']}).

Your task: Draft a COMPLETE investment thesis package that will be reviewed by a human portfolio manager before activation.

=== MACRO-FIRST RULE ===
Before analyzing ANY company-specific data, you MUST address the macro/sector question:
- What is the supply/demand outlook for this company's primary commodity or market?
- At current prices, does the macro environment support this business model?
- If the answer is "no" or "unclear," the thesis position should be PASS or AVOID unless you can articulate a specific, quantified reason why conditions will change.

Do NOT dive into well productivity, hedge books, or operational details until you have answered the macro question.

COMPANY: {ticker} — {company['company_name']}""")

    # Filings data
    for filing in filings:
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
--- FILING: {filing['filing_type']} dated {filing['filing_date']} ---
{json.dumps(filing_data, indent=2, default=str)}""")

    # Metrics
    for filing in filings:
        m = metrics_by_filing.get(filing['id'], [])
        if m:
            metrics_list = [{'name': x['metric_name'], 'value': str(x['metric_value']),
                            'unit': x['metric_unit'], 'period': x['metric_period']} for x in m]
            sections.append(f"""
--- EXTRACTED METRICS ({filing['filing_type']} {filing['filing_date']}) ---
{json.dumps(metrics_list, indent=2, default=str)}""")

    # Forward statements / guidance
    if forward_stmts:
        stmts_list = [{'category': s['statement_category'], 'statement': s['statement_text'],
                       'quantitative_value': s.get('quantitative_value'),
                       'unit': s.get('value_unit'), 'timeframe': s.get('timeframe'),
                       'confidence': s.get('confidence_level')}
                      for s in forward_stmts]
        sections.append(f"""
--- MANAGEMENT GUIDANCE / FORWARD STATEMENTS ---
{json.dumps(stmts_list, indent=2, default=str)}""")

    # Financial model output
    if model_summary:
        sections.append(f"""
--- FINANCIAL MODEL OUTPUT (computed by Python, DO NOT recompute) ---
These are deterministic calculations from our model. Reference them but do not recalculate.
{json.dumps(model_summary, indent=2, default=str)}""")

    # Market context
    if external_context:
        sections.append(f"""
--- CURRENT MARKET CONTEXT ---
{json.dumps(external_context, indent=2, default=str)}""")

    # Consensus estimates
    if consensus:
        sections.append(f"""
--- ANALYST CONSENSUS ESTIMATES ---
{json.dumps(consensus, indent=2, default=str)}""")

    # Peer data
    if peer_data:
        peer_list = []
        for p in peer_data:
            claims = p.get('financial_claims', {})
            if isinstance(claims, str):
                try:
                    claims = json.loads(claims)
                except (json.JSONDecodeError, TypeError):
                    claims = {}
            peer_list.append({
                'ticker': p['ticker'],
                'name': p['company_name'],
                'thesis': p.get('thesis_summary', 'N/A'),
                'claims': claims,
            })
        sections.append(f"""
--- PEER COMPANIES ---
{json.dumps(peer_list, indent=2, default=str)}""")

    # Supplementary metrics (extracted from earnings releases, etc.)
    if supplementary_metrics:
        # Group by source
        by_source = {}
        for m in supplementary_metrics:
            key = f"{m.get('source_type', '')} — {m.get('title', '')} ({m.get('published_date', '')})"
            by_source.setdefault(key, []).append({
                'name': m['metric_name'],
                'value': str(m['metric_value']),
                'unit': m['metric_unit'],
                'period': m['metric_period'],
                'section': m.get('section_name', ''),
            })
        sections.append(f"""
--- SUPPLEMENTARY SOURCE METRICS (extracted from earnings releases, press releases) ---
These are pre-extracted structured metrics. Use these as authoritative financial data.
{json.dumps(by_source, indent=2, default=str)}""")
    elif supplementary:
        # Fallback: raw text if no extracted metrics available
        supp_list = []
        for s in supplementary:
            content = s.get('content', '')
            max_len = 4000
            supp_list.append({
                'type': s['source_type'],
                'title': s.get('title', ''),
                'date': str(s.get('published_date', '')),
                'content': content[:max_len] if content else '',
            })
        sections.append(f"""
--- SUPPLEMENTARY DATA (press releases, news — raw text, not yet extracted) ---
{json.dumps(supp_list, indent=2, default=str)}""")

    # Guidance revision history for credibility assessment
    if guidance_history:
        # Group by metric for readability
        by_metric = {}
        for g in guidance_history:
            key = g['metric_name']
            by_metric.setdefault(key, []).append({
                'date': str(g['source_date']),
                'low': float(g['guidance_value_low']) if g['guidance_value_low'] else None,
                'high': float(g['guidance_value_high']) if g['guidance_value_high'] else None,
                'unit': g['guidance_unit'],
                'period': g['guidance_period'],
                'revision_pct': float(g['revision_pct']) if g['revision_pct'] else None,
                'reason': g['revision_reason'],
                'was_revised': g['was_revised'],
            })
        sections.append(f"""
--- GUIDANCE REVISION HISTORY ---
This shows how management guidance has changed over time. Use this to assess credibility.
{json.dumps(by_metric, indent=2, default=str)}""")

    # Previous thesis for continuity on --refresh
    if previous_thesis:
        prev_summary = previous_thesis.get('thesis_summary', '')
        sections.append(f"""
--- PREVIOUS THESIS (evolve, don't discard without reason) ---
Summary: {prev_summary}
Market View: {previous_thesis.get('market_view', 'N/A')}
Our View: {previous_thesis.get('our_view', 'N/A')}
Variant Edge: {previous_thesis.get('variant_edge', 'N/A')}

INSTRUCTIONS: Evolve this thesis based on the latest data. Preserve what remains valid.""")

    sections.append("""
Generate a COMPLETE investment thesis package. Return as JSON with this exact structure:

{
  "position_type": "own|pass|avoid|sell",
  "thesis_summary": "See THESIS STRUCTURE below for required 3-part content.",

  "market_view": "What consensus believes about this company. Be specific about the consensus narrative.",
  "our_view": "What we believe differently. Must be a genuine variant — not just 'we're more bullish'.",
  "variant_edge": "Why we think market is wrong. What information or analysis do we have that others don't weight properly?",

  "pre_mortem": "It's 12 months later and we lost 30%. Write the story of what happened. Be specific with scenarios.",

  "management_credibility": "1-2 sentence honest assessment of management credibility based on guidance history, promise delivery, and narrative consistency.",

  "confidence_bull": 50.0,
  "confidence_base": 30.0,
  "confidence_bear": 20.0,

  "catalyst_description": "What event or development will cause market to reprice toward our view?",
  "catalyst_deadline": "2026-12-31",
  "review_date": "2026-06-30",

  "kill_criteria": [
    {
      "criterion": "Human-readable exit condition",
      "metric_name": "capex_guidance",
      "threshold_value": 1500,
      "threshold_operator": ">",
      "threshold_unit": "M"
    }
  ],

  "hypotheses": [
    {
      "hypothesis": "Testable statement about the company or sector",
      "counter_hypothesis": "What must be true if we're wrong",
      "confirming_evidence": "What data would confirm this hypothesis",
      "disproving_evidence": "What data would disprove this hypothesis",
      "confidence": 60.0
    }
  ],

  "management_promises": [
    {
      "promise_text": "Exact quote or paraphrase of management commitment",
      "promise_metric": "capex_guidance",
      "promise_value_low": 1400,
      "promise_value_high": 1500,
      "promise_unit": "M",
      "promise_date": "2025-10-30"
    }
  ],

  "financial_claims": {
    "capex_guidance": {"low": 1400, "high": 1500, "unit": "M", "period": "2026", "source": "10-K"},
    "operating_cash_flow": {"value": 861, "unit": "M", "period": "FY2025", "source": "10-K"},
    "production_volume": {"value": 590, "unit": "Bcfe", "period": "FY2025", "source": "10-K"},
    "hedge_volume": {"value": 315, "unit": "Bcf", "price": 3.49, "period": "2026", "source": "10-K"},
    "realized_price": {"value": 2.87, "unit": "$/Mcfe", "period": "FY2025", "source": "10-K"},
    "operating_cost_per_unit": {"value": 0.77, "unit": "$/Mcfe", "period": "FY2025", "source": "10-K"},
    "net_debt": {"value": 2785, "unit": "M", "period": "2025-12-31", "source": "earnings_release"},
    "interest_expense": {"value": 222.8, "unit": "M", "period": "FY2025", "source": "earnings_release"},
    "total_long_term_debt": {"value": 2809, "unit": "M", "period": "2025-12-31", "source": "earnings_release"},
    "credit_facility_available": {"value": 500, "unit": "M", "period": "2025-12-31", "source": "10-K"}
  },

  "model_parameters": {
    "production_growth_assumption": "flat to +2% YoY",
    "price_sensitivity_note": "$0.50/Mcf swing = ~$67M revenue on unhedged volumes",
    "key_model_inputs_to_watch": ["realized_price", "capex_actual", "production_volume"]
  }
}

=== POSITION TYPE RULES (CRITICAL) ===

Choose ONE of these position types based on the data:
- "own"  — The hinge resolves favorably AND we have a differentiated view on why. The economics work at current or near-term achievable prices.
- "pass" — Economics may work but we have no edge on the hinge variable. We cannot articulate why we know better than the market.
- "avoid" — The hinge is unlikely to resolve favorably. The economics do not work at current prices and there is no clear catalyst for change.
- "sell" — We own this but the hinge has changed or the thesis is broken. Time to exit.

CRITICAL RULE: If your own numbers show the thesis doesn't work at current prices (e.g., breakeven price > strip price, funding gap requires prices well above strip) and you cannot articulate a specific, quantified reason why prices will change, the position MUST be "pass" or "avoid", NOT "own". Do not assume commodity prices will rise without evidence. Be honest.

=== THESIS STRUCTURE (CRITICAL — 3 PARTS) ===

The thesis_summary MUST follow this exact 3-part structure:

**Part 1 — WHAT IT IS (first paragraph):**
Plain-English company description. A reader unfamiliar with the company understands the business after this paragraph.
   - BAD: "CRK's Western Haynesville wells deliver 33 MMcf/day" (jargon, no context)
   - GOOD: "Comstock Resources is a pure-play natural gas producer in Louisiana's Haynesville Shale, one of the lowest-cost US gas basins with direct pipeline access to Gulf Coast LNG export terminals."

**Part 2 — THE CONTEXT (second paragraph):**
Macro/sector environment that determines the playing field. For a commodity producer: supply/demand outlook for the commodity. This MUST be quantified, not vague.
   - Address the industry-level demand/supply balance BEFORE company specifics
   - Use the industry profile prompt_context for sector-level framing
   - Quantify demand drivers (e.g., "even 50-100 GW of AI data center demand = ~10% of US gas production; 200+ GW of renewables expected to offset")
   - State the key price question: "At what gas price does supply growth = demand growth?"
   - Reference the current strip price and whether it supports the thesis
   - BAD: "Natural gas demand is growing due to AI data centers" (vague, unquantified)
   - GOOD: "US natural gas demand is structurally supported by LNG exports (14 Bcf/d, growing to 20+ Bcf/d by 2028) and data center power needs, but Permian associated gas growth (~8 Bcf/d) offsets much of the incremental demand. The 12-month strip at $3.79 reflects a balanced market; self-funding E&P operations requires $5+ pricing that the strip does not support."

**Part 3 — THE HINGE (third paragraph):**
The single variable that determines whether this investment works. MUST name the hinge explicitly, state the condition AND our view on probability.
   - Identify the ONE variable that matters most
   - State the specific threshold (e.g., "$5.41 realized pricing")
   - State whether we think the threshold will be met and why/why not
   - Connect back to the position type
   - BAD: "Gas prices need to rise for this to work"
   - GOOD: "Self-funding requires $5.41 realized gas pricing, 43% above the current $3.79 strip. We see no catalyst to close that gap in the next 12 months — LNG export capacity additions are priced in, data center demand growth is offset by Permian associated gas, and Haynesville producers are collectively adding supply. Position: AVOID."

=== FUNDING ANALYSIS (REQUIRED when funding_gap > 0) ===

When the company has a funding gap (capex > OCF), the thesis MUST address:
1. How is the gap funded TODAY? (revolver draws, asset sales, bond issuance, equity?)
2. What is the interest cost? ($X annual interest at ~Y% implied rate on $Z total debt)
3. What happens at debt maturity? Can they refinance at current economics?
4. What happens if capital markets tighten? (capex gets cut -> production decline -> thesis breaks)

A company that cannot self-fund its capex is at the mercy of capital markets.
This is a key risk that must be addressed explicitly in the thesis, not buried.

Reference the FINANCIAL MODEL OUTPUT values for interest_coverage, debt_service_capacity, and funding_gap_coverage if available.

financial_claims MUST include: interest_expense, total_long_term_debt, and credit_facility_available when this data is present in the filings.

=== MANAGEMENT CREDIBILITY (REQUIRED) ===

Review the guidance_history data (if provided). For each major metric (capex, production, debt):
1. How has guidance changed over the last 2-3 filings?
2. What direction are revisions trending? (consistently up? consistently down?)
3. Did management explain the change, or did they quietly revise?
4. Are current actions consistent with stated strategy?

Specific patterns to flag:
- Promising debt reduction while increasing capex
- Raising capex guidance without explaining what changed
- Selling assets to "reduce debt" while spending more than proceeds on new drilling
- Increasing rig count in a weak pricing environment

The management_credibility field should be a 1-2 sentence honest assessment.
If no guidance_history is available, assess based on current filing data and any apparent contradictions between stated strategy and financial actions.

=== INTELLIGIBILITY GUIDELINES ===

Write for a reader who follows markets broadly but does NOT follow this specific company:
- First mention of any geographic area (e.g. "Western Haynesville", "Shelby Trough") must include a parenthetical explanation: "(CRK's newest high-productivity drilling area in NW Louisiana)"
- Use consistent names — if an asset was sold, call it the same thing every time. Don't switch between "East Texas" and "Shelby Trough" without explaining they're the same.
- Include key derived ratios in the narrative — don't just state raw numbers:
  * Hedge coverage: "315 Bcf hedged out of 450 Bcf production (70% covered)"
  * Leverage: "Net debt of $2.8B = 3.2x OCF"
  * OCF coverage: "OCF funds 59% of planned capex"
  * Interest coverage: "OCF covers interest expense X.Xx"
- Walk through the cash flow bridge: Revenue -> Operating costs -> OCF -> Interest -> Capex -> Funding gap -> How the gap gets filled (asset sales, debt, equity?)

=== PRICING RULES ===

When referencing forward gas pricing, use the 12-month STRIP AVERAGE (weighted average across the full curve), NOT the single highest monthly contract.
The data includes strip_averages with strip_12m, strip_24m, winter_strip, and summer_strip.
- BAD: "$4.35 12-month forward pricing" (this is the Feb 2027 winter peak, not representative)
- GOOD: "$3.70 12-month strip average (summer $3.37, winter $3.98)" (honest representation of expected pricing)
If the thesis depends on prices above the strip, say so explicitly.

=== OTHER REQUIREMENTS ===

- kill_criteria: 3-5 explicit exit conditions. Each MUST have a metric_name, threshold_value, and threshold_operator so Python can check automatically.
- hypotheses: 3-5 testable hypotheses. Each MUST have a counter_hypothesis (what if we're wrong?).
- management_promises: Extract every quantitative commitment from filings/guidance (capex, production, debt targets, etc.)
- financial_claims: Include EVERY specific number your thesis references. MUST include net_debt, production_volume, realized_price, interest_expense, total_long_term_debt.
- model_parameters: Notes about what drives the model — not numbers (those are in financial_claims).

VARIANT PERCEPTION:
The variant perception is THE most important part. It must answer: "What does the market believe, what do we believe, and why is the market wrong?"
BAD market_view: "Market thinks the company is okay" (vague)
GOOD market_view: "Market prices CRK as a leveraged nat gas play with execution risk on the Haynesville expansion, reflected in 3.5x EV/EBITDA vs peer avg of 4.5x"

Return ONLY valid JSON, no other text.""")

    return '\n'.join(sections)


def save_draft_thesis(conn, company_id, thesis_data, filing_ids, model_used):
    """Save thesis as a DRAFT in investment_theses table. Returns thesis_id."""
    cursor = conn.cursor()

    # Parse dates
    catalyst_deadline = thesis_data.get('catalyst_deadline')
    review_date = thesis_data.get('review_date')

    cursor.execute("""
        INSERT INTO investment_theses
            (company_id, position_type, thesis_summary,
             market_view, our_view, variant_edge, pre_mortem,
             management_credibility,
             confidence_bull, confidence_base, confidence_bear,
             catalyst_description, catalyst_deadline, review_date,
             financial_claims, model_parameters,
             source_filing_ids, generated_by, model_used,
             is_active, is_draft, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                'claude', %s, FALSE, TRUE, %s)
        RETURNING id
    """, (
        company_id,
        thesis_data.get('position_type', 'own'),
        thesis_data['thesis_summary'],
        thesis_data['market_view'],
        thesis_data['our_view'],
        thesis_data['variant_edge'],
        thesis_data.get('pre_mortem'),
        thesis_data.get('management_credibility'),
        thesis_data.get('confidence_bull', 50.0),
        thesis_data.get('confidence_base', 30.0),
        thesis_data.get('confidence_bear', 20.0),
        thesis_data.get('catalyst_description'),
        catalyst_deadline,
        review_date,
        json.dumps(thesis_data.get('financial_claims', {})),
        json.dumps(thesis_data.get('model_parameters', {})),
        json.dumps(filing_ids),
        model_used,
        datetime.now() + timedelta(days=365),
    ))
    thesis_id = cursor.fetchone()[0]

    # Save kill criteria
    for kc in thesis_data.get('kill_criteria', []):
        cursor.execute("""
            INSERT INTO kill_criteria
                (thesis_id, criterion, metric_name, threshold_value,
                 threshold_operator, threshold_unit)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            thesis_id,
            kc['criterion'],
            kc.get('metric_name'),
            kc.get('threshold_value'),
            kc.get('threshold_operator'),
            kc.get('threshold_unit'),
        ))

    # Save hypotheses
    for h in thesis_data.get('hypotheses', []):
        cursor.execute("""
            INSERT INTO hypotheses
                (company_id, thesis_id, hypothesis, counter_hypothesis,
                 confirming_evidence, disproving_evidence, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            company_id,
            thesis_id,
            h['hypothesis'],
            h['counter_hypothesis'],
            h.get('confirming_evidence'),
            h.get('disproving_evidence'),
            h.get('confidence', 50.0),
        ))

    # Save management promises to scorecard
    for mp in thesis_data.get('management_promises', []):
        source_filing_id = filing_ids[0] if filing_ids else None
        cursor.execute("""
            INSERT INTO management_scorecard
                (company_id, promise_date, promise_text, promise_metric,
                 promise_value_low, promise_value_high, promise_unit,
                 source_filing_id, assessment)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """, (
            company_id,
            mp.get('promise_date', datetime.now().date()),
            mp['promise_text'],
            mp.get('promise_metric'),
            mp.get('promise_value_low'),
            mp.get('promise_value_high'),
            mp.get('promise_unit'),
            source_filing_id,
        ))

    # Log the decision
    cursor.execute("""
        INSERT INTO decision_log
            (company_id, thesis_id, decision_type, decision_text, rationale,
             information_snapshot)
        VALUES (%s, %s, 'thesis_created', %s, %s, %s)
    """, (
        company_id,
        thesis_id,
        f"Draft thesis created for {thesis_data.get('position_type', 'own')} position",
        thesis_data.get('variant_edge', ''),
        json.dumps({
            'confidence': {
                'bull': thesis_data.get('confidence_bull'),
                'base': thesis_data.get('confidence_base'),
                'bear': thesis_data.get('confidence_bear'),
            },
            'kill_criteria_count': len(thesis_data.get('kill_criteria', [])),
            'hypotheses_count': len(thesis_data.get('hypotheses', [])),
        }),
    ))

    conn.commit()
    cursor.close()
    return thesis_id


def display_draft(thesis_data, model_summary, thesis_id):
    """Display the draft thesis for human review."""
    print(f"\n{'=' * 70}")
    print(f"DRAFT INVESTMENT THESIS (ID: {thesis_id})")
    print(f"{'=' * 70}")
    print(f"\nPosition: {thesis_data.get('position_type', 'own').upper()}")
    print(f"\nThesis: {thesis_data['thesis_summary']}")

    print(f"\n--- VARIANT PERCEPTION ---")
    print(f"Market View: {thesis_data['market_view']}")
    print(f"Our View:    {thesis_data['our_view']}")
    print(f"Edge:        {thesis_data['variant_edge']}")

    print(f"\n--- PRE-MORTEM ---")
    print(f"{thesis_data.get('pre_mortem', 'N/A')}")

    print(f"\n--- MANAGEMENT CREDIBILITY ---")
    print(f"{thesis_data.get('management_credibility', 'N/A')}")

    print(f"\n--- CONFIDENCE ---")
    print(f"Bull: {thesis_data.get('confidence_bull', 50)}%  |  "
          f"Base: {thesis_data.get('confidence_base', 30)}%  |  "
          f"Bear: {thesis_data.get('confidence_bear', 20)}%")

    print(f"\n--- CATALYST ---")
    print(f"Description: {thesis_data.get('catalyst_description', 'N/A')}")
    print(f"Deadline:    {thesis_data.get('catalyst_deadline', 'N/A')}")
    print(f"Review Date: {thesis_data.get('review_date', 'N/A')}")

    print(f"\n--- KILL CRITERIA ---")
    for i, kc in enumerate(thesis_data.get('kill_criteria', []), 1):
        auto = ""
        if kc.get('metric_name'):
            auto = f" [AUTO: {kc['metric_name']} {kc.get('threshold_operator', '')} {kc.get('threshold_value', '')} {kc.get('threshold_unit', '')}]"
        print(f"  {i}. {kc['criterion']}{auto}")

    print(f"\n--- HYPOTHESES ---")
    for i, h in enumerate(thesis_data.get('hypotheses', []), 1):
        print(f"  {i}. {h['hypothesis']}")
        print(f"     Counter: {h['counter_hypothesis']}")
        print(f"     Confirm: {h.get('confirming_evidence', 'N/A')}")
        print(f"     Disprove: {h.get('disproving_evidence', 'N/A')}")
        print(f"     Confidence: {h.get('confidence', 50)}%")
        print()

    print(f"--- MANAGEMENT PROMISES ---")
    for mp in thesis_data.get('management_promises', []):
        low = mp.get('promise_value_low', '?')
        high = mp.get('promise_value_high', '?')
        unit = mp.get('promise_unit', '')
        print(f"  - {mp['promise_text']} [{low}-{high} {unit}]")

    # Financial claims
    claims = thesis_data.get('financial_claims', {})
    if claims:
        print(f"\n--- FINANCIAL CLAIMS ({len(claims)} items) ---")
        for name, data in sorted(claims.items()):
            if isinstance(data, dict):
                if 'low' in data and 'high' in data:
                    print(f"  - {name}: {data['low']}-{data['high']} {data.get('unit', '')} [{data.get('source', '')}]")
                elif 'value' in data:
                    print(f"  - {name}: {data['value']} {data.get('unit', '')} [{data.get('source', '')}]")

    # Model summary
    if model_summary:
        print(f"\n--- MODEL OUTPUT (Python-computed) ---")
        for key, val in model_summary.items():
            if val is not None:
                print(f"  - {key}: {val}")

    print(f"\n{'=' * 70}")
    print(f"This thesis is saved as DRAFT (ID: {thesis_id}).")
    print(f"To approve: python approve_thesis.py --thesis-id {thesis_id}")
    print(f"{'=' * 70}")


def main():
    print("=" * 70)
    print("INVESTMENT THESIS INITIALIZATION")
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
        print("Usage: python init_thesis.py --ticker CRK [--refresh]")
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
        print(f"  ✗ Company {ticker} not found in database")
        conn.close()
        return

    print(f"  Company: {company['ticker']} — {company['company_name']}")

    # Check for existing thesis
    existing = get_existing_thesis(conn, company['id'])
    if existing and not refresh:
        src = 'investment_theses' if 'market_view' in dict(existing) else 'company_theses'
        print(f"\n  Active thesis already exists in {src} (created {existing['created_at']})")
        print(f"  Summary: {existing.get('thesis_summary', '')[:200]}...")
        print(f"\n  Use --refresh to create a new draft from existing thesis")
        conn.close()
        return

    # Get filings
    print("\n  Gathering data...")
    filings = get_latest_filings(conn, company['id'])
    if not filings:
        print("  ✗ No processed 10-K or 10-Q found")
        conn.close()
        return
    print(f"  ✓ {len(filings)} recent filings found")

    # Get metrics per filing
    metrics_by_filing = {}
    total_metrics = 0
    for f in filings:
        m = get_filing_metrics(conn, f['id'])
        metrics_by_filing[f['id']] = m
        total_metrics += len(m)
    print(f"  ✓ {total_metrics} extracted metrics")

    # Get forward statements from latest filing
    forward_stmts = get_forward_statements(conn, filings[0]['id'])
    if forward_stmts:
        print(f"  ✓ {len(forward_stmts)} forward statements")

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

    # Get consensus estimates
    print("  Fetching consensus estimates...")
    consensus = get_consensus_estimates(conn, ticker)
    if consensus:
        print(f"  ✓ Consensus from {len(consensus)} sources")
    else:
        print("  — No consensus estimates available")

    # Get peer data
    peer_data = get_peer_data(conn, company.get('industry_profile_id'), company['id'])
    if peer_data:
        print(f"  ✓ {len(peer_data)} peer companies")

    # Get supplementary data
    supplementary = get_supplementary_data(conn, company['id'])
    if supplementary:
        print(f"  ✓ {len(supplementary)} supplementary sources")

    # Get extracted metrics from supplementary sources
    supp_metrics = get_supplementary_metrics(conn, company['id'])
    if supp_metrics:
        print(f"  ✓ {len(supp_metrics)} pre-extracted supplementary metrics")
    else:
        print("  — No extracted supplementary metrics (run extract_supplementary.py first)")

    # Get guidance revision history for credibility assessment
    guidance_hist = get_guidance_history(conn, company['id'])
    if guidance_hist:
        print(f"  ✓ {len(guidance_hist)} guidance history entries")
    else:
        print("  — No guidance history (will be populated from future filings)")

    # Run financial model with whatever claims we have
    print("\n  Running financial model...")
    existing_claims = {}
    if existing and existing.get('financial_claims'):
        c = existing['financial_claims']
        existing_claims = json.loads(c) if isinstance(c, str) else c

    model_params = EPModel.params_from_claims(existing_claims, external_context)
    model = EPModel(model_params)
    model_summary = {k: v for k, v in model.summary().items() if v is not None}
    if model_summary:
        print(f"  ✓ Model computed {len(model_summary)} values")
    else:
        print("  — Insufficient data for model (will populate from Claude's claims)")

    # Build prompt and call Claude
    print("\n  Generating thesis draft with Claude...")
    previous_thesis = existing if refresh else None
    prompt = build_thesis_prompt(
        company, filings, metrics_by_filing, forward_stmts,
        profile, external_context, model_summary,
        consensus, peer_data, supplementary,
        supplementary_metrics=supp_metrics, previous_thesis=previous_thesis,
        guidance_history=guidance_hist
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}]
        )
        thesis_data = parse_claude_json(response.content[0].text)
        if not thesis_data:
            print("  ✗ Failed to parse Claude response")
            conn.close()
            return
    except Exception as e:
        print(f"  ✗ Claude API error: {e}")
        conn.close()
        return

    # Validate required fields
    required = ['thesis_summary', 'market_view', 'our_view', 'variant_edge']
    for field in required:
        if field not in thesis_data:
            print(f"  ✗ Missing required field: {field}")
            conn.close()
            return

    # Run financial model with Claude's claims to compute derived metrics
    claims = thesis_data.get('financial_claims', {})
    if claims:
        print("\n  Computing derived financial claims...")
        model_params = EPModel.params_from_claims(claims, external_context)
        model = EPModel(model_params)
        claims_before = set(claims.keys())
        claims = model.compute_derived_claims(claims)
        thesis_data['financial_claims'] = claims
        claims_after = set(claims.keys())
        derived = claims_after - claims_before
        if derived:
            print(f"  ✓ Derived: {', '.join(sorted(derived))}")
        else:
            print(f"  ✓ No additional derivations needed")
        model_summary = {k: v for k, v in model.summary().items() if v is not None}
    else:
        print("\n  ⚠ Claude did not produce financial_claims")

    # Save as draft
    filing_ids = [f['id'] for f in filings]
    thesis_id = save_draft_thesis(conn, company['id'], thesis_data, filing_ids, MODEL)
    print(f"\n  ✓ Draft thesis saved (ID: {thesis_id})")

    # Display
    display_draft(thesis_data, model_summary, thesis_id)

    conn.close()


if __name__ == "__main__":
    main()
