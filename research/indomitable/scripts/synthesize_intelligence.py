#!/usr/bin/env python3
"""
Stage 5: Intelligence Synthesis
Enriches differential analysis reports with industry context, peer data,
and comprehensive Claude-generated investment intelligence.

Usage:
    python synthesize_intelligence.py --all
    python synthesize_intelligence.py --ticker EQT
    python synthesize_intelligence.py --filing-id 5
"""

import sys
import os
import re
import json
import time as _time
from datetime import datetime, date
from psycopg2.extras import RealDictCursor
from config import connect_db, get_anthropic_client, parse_claude_json, MODEL
from external_data import get_industry_context, populate_company_news, populate_earnings_transcript, compute_consensus_summary, fetch_finnhub_earnings_calendar
from report_templates import generate_intelligence_html


# --- Report Mode Vocabulary ---
# Three modes driven by earnings calendar proximity + filing age
REPORT_MODE_VOCABULARY = {
    'pre_earnings': {
        'mode_label': 'PRE-EARNINGS BRIEF',
        'report_type': 'pre_earnings_brief',
        'assessment_instruction': (
            'You have NOT seen current-quarter results. '
            'Do NOT say the thesis is "intact" — that word is FORBIDDEN in this mode. '
            'Say "untested since {last_quarter}" or "awaiting validation from upcoming {next_quarter} results." '
            'Frame everything as "here is what to watch for."'
        ),
        'forbidden_words': ['intact'],
        'task_framing': 'IC PRE-EARNINGS BRIEF',
    },
    'earnings_review': {
        'mode_label': 'EARNINGS REVIEW',
        'report_type': 'earnings_review',
        'assessment_instruction': (
            'You have fresh earnings data. Render a VERDICT on the thesis. '
            'Use vocabulary like "intact," "under pressure," "strengthening," "weakening," or "breaking down." '
            'If thesis_review recommends revision, the assessment must NOT say "intact." '
            'If thesis_review says no revision needed (thesis already reflects the data), evaluate whether the data CONFIRMS or CHALLENGES the thesis predictions.'
        ),
        'forbidden_words': [],
        'task_framing': 'IC EARNINGS REVIEW',
    },
    'update': {
        'mode_label': 'UPDATE',
        'report_type': 'update',
        'assessment_instruction': (
            'No new earnings data since {last_earnings_date}. '
            'Say "no new information to challenge the thesis since {last_earnings_date}" '
            'rather than rendering a verdict.'
        ),
        'forbidden_words': [],
        'task_framing': 'IC UPDATE',
    },
}


def determine_report_mode(filing_date, earnings_dates, filing_age_days):
    """
    Determine report mode based on earnings calendar proximity and filing age.

    Args:
        filing_date: date object or string of the filing being analyzed
        earnings_dates: dict with 'next_earnings_date' and/or 'last_earnings_date' (date objects), or None
        filing_age_days: int, age of the filing in days

    Returns:
        dict with mode, mode_label, vocabulary, days_to_next, days_since_last, report_type
    """
    today = date.today()

    # Parse filing_date if string
    if isinstance(filing_date, str):
        try:
            filing_date = datetime.strptime(filing_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            filing_date = today

    days_to_next = None
    days_since_last = None

    if earnings_dates:
        next_ed = earnings_dates.get('next_earnings_date')
        last_ed = earnings_dates.get('last_earnings_date')

        if next_ed:
            if isinstance(next_ed, str):
                next_ed = date.fromisoformat(next_ed)
            days_to_next = (next_ed - today).days

        if last_ed:
            if isinstance(last_ed, str):
                last_ed = date.fromisoformat(last_ed)
            days_since_last = (today - last_ed).days

    # --- Mode determination with priority rule ---
    # Priority: earnings_review > pre_earnings > update
    # But earnings_review also requires fresh filing (≤7 days old)

    mode = 'update'  # default

    # Check earnings_review first (wins if both windows overlap)
    if days_since_last is not None and days_since_last <= 7:
        # Calendar says this could be earnings_review
        if filing_age_days <= 7:
            # Filing is fresh enough to actually contain earnings data
            mode = 'earnings_review'
        else:
            # Filing is old — can't review earnings we haven't seen
            mode = 'update'
    elif days_to_next is not None and 0 <= days_to_next <= 14:
        mode = 'pre_earnings'

    # Fallback: if no calendar data, use filing-age heuristic
    if not earnings_dates:
        if filing_age_days <= 7:
            mode = 'earnings_review'
        elif filing_age_days > 60:
            mode = 'pre_earnings'
        else:
            mode = 'update'

    vocab = REPORT_MODE_VOCABULARY[mode]

    # Format the assessment instruction with actual dates
    last_earnings_str = str(earnings_dates.get('last_earnings_date', 'unknown')) if earnings_dates else 'unknown'
    next_earnings_str = str(earnings_dates.get('next_earnings_date', 'unknown')) if earnings_dates else 'unknown'

    # Determine quarter labels
    # Earnings released in month M report on the PRIOR quarter:
    # Jan-Mar release → Q4 prior year, Apr-Jun → Q1, Jul-Sep → Q2, Oct-Dec → Q3
    def _reported_quarter(d):
        """Given an earnings release date, return the quarter being reported."""
        if isinstance(d, str):
            d = date.fromisoformat(d)
        q = ((d.month - 1) // 3)
        if q == 0:
            return f"Q4 {d.year - 1}"
        return f"Q{q} {d.year}"

    if earnings_dates and earnings_dates.get('next_earnings_date'):
        next_quarter = _reported_quarter(earnings_dates['next_earnings_date'])
    else:
        next_quarter = "upcoming quarter"

    if earnings_dates and earnings_dates.get('last_earnings_date'):
        last_quarter = _reported_quarter(earnings_dates['last_earnings_date'])
    else:
        last_quarter = "prior quarter"

    assessment = vocab['assessment_instruction'].format(
        last_earnings_date=last_earnings_str,
        next_quarter=next_quarter,
        last_quarter=last_quarter,
    )

    return {
        'mode': mode,
        'mode_label': vocab['mode_label'],
        'report_type': vocab['report_type'],
        'task_framing': vocab['task_framing'],
        'assessment_instruction': assessment,
        'forbidden_words': vocab['forbidden_words'],
        'days_to_next': days_to_next,
        'days_since_last': days_since_last,
        'next_earnings_date': next_earnings_str,
        'last_earnings_date': last_earnings_str,
        'filing_age_days': filing_age_days,
    }


def get_active_thesis(conn, company_id):
    """Fetch the active investment thesis for a company."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT * FROM company_theses
        WHERE company_id = %s AND thesis_type = 'bull' AND is_active = TRUE
        ORDER BY created_at DESC LIMIT 1
    """, (company_id,))
    row = cursor.fetchone()
    cursor.close()
    return row


def get_reports_needing_synthesis(conn, ticker=None, filing_id=None):
    """Find intelligence reports that need Stage 5 synthesis."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if filing_id:
        cursor.execute("""
            SELECT ir.*, f.filing_type, f.filing_date, f.accession_number, f.company_id,
                   c.ticker, c.company_name, c.industry_profile_id
            FROM intelligence_reports ir
            JOIN filings f ON ir.filing_id = f.id
            JOIN companies c ON f.company_id = c.id
            WHERE ir.filing_id = %s
            ORDER BY f.filing_date DESC
        """, (filing_id,))
    elif ticker:
        cursor.execute("""
            SELECT ir.*, f.filing_type, f.filing_date, f.accession_number, f.company_id,
                   c.ticker, c.company_name, c.industry_profile_id
            FROM intelligence_reports ir
            JOIN filings f ON ir.filing_id = f.id
            JOIN companies c ON f.company_id = c.id
            WHERE c.ticker = %s AND ir.operational_analysis IS NULL OR ir.operational_analysis = ''
            ORDER BY f.filing_date DESC
        """, (ticker,))
    else:
        cursor.execute("""
            SELECT ir.*, f.filing_type, f.filing_date, f.accession_number, f.company_id,
                   c.ticker, c.company_name, c.industry_profile_id
            FROM intelligence_reports ir
            JOIN filings f ON ir.filing_id = f.id
            JOIN companies c ON f.company_id = c.id
            WHERE ir.operational_analysis IS NULL OR ir.operational_analysis = ''
            ORDER BY f.filing_date DESC
        """)

    reports = cursor.fetchall()
    cursor.close()
    return reports


def get_supplementary_data(conn, company_id, filing_date, window_days=30):
    """Get press releases and other data sources near a filing date."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT source_type, title, published_date, content
        FROM data_sources
        WHERE company_id = %s
        AND published_date BETWEEN %s::date - interval '%s days' AND %s::date + interval '7 days'
        ORDER BY published_date DESC
        LIMIT 5
    """, (company_id, filing_date, window_days, filing_date))
    results = cursor.fetchall()
    cursor.close()
    return results


def get_peer_data(conn, company_id, industry_profile_id):
    """Get latest metrics from peer companies in the same industry."""
    if not industry_profile_id:
        return {}

    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT c.ticker, c.company_name,
               em.metric_name, em.metric_value, em.metric_unit, em.metric_period,
               f.filing_type, f.filing_date
        FROM companies c
        JOIN filings f ON f.company_id = c.id
        JOIN extracted_metrics em ON em.filing_id = f.id
        WHERE c.industry_profile_id = %s
        AND c.id != %s
        AND c.active = TRUE
        AND f.id = (
            SELECT f2.id FROM filings f2
            WHERE f2.company_id = c.id AND f2.processed = TRUE
            ORDER BY f2.filing_date DESC LIMIT 1
        )
        ORDER BY c.ticker, em.metric_name
    """, (industry_profile_id, company_id))

    rows = cursor.fetchall()
    cursor.close()

    # Group by ticker
    peers = {}
    for row in rows:
        t = row['ticker']
        if t not in peers:
            peers[t] = {
                'company_name': row['company_name'],
                'filing_type': row['filing_type'],
                'filing_date': str(row['filing_date']),
                'metrics': []
            }
        peers[t]['metrics'].append({
            'name': row['metric_name'],
            'value': float(row['metric_value']) if row['metric_value'] else None,
            'unit': row['metric_unit'],
            'period': row['metric_period']
        })

    return peers


def _numbers_schema_example(report_mode):
    """
    Return mode-aware schema example for numbers_that_matter.
    Field names stay the same (rendering code unchanged), but examples and
    descriptions change to match what each mode needs.
    """
    mode = report_mode['mode'] if report_mode else 'pre_earnings'

    if mode == 'earnings_review':
        return """\
  "numbers_that_matter": [
    {
      "metric": "e.g. Production Volume",
      "consensus_estimate": "Actual: 590 Bcfe vs est. 580 — beat by 1.7%",
      "why_it_matters": "Directly measures whether low-cost production thesis is scaling",
      "bullish_threshold": "Interpretation: Q4 annualized pace of 610 exceeds full-year 590, suggesting growth accelerating — thesis scaling assumption validated",
      "bearish_threshold": "Counter-interpretation: beat concentrated in acquired assets, not organic drilling — overstates core growth if integration is one-time"
    },
    {
      "metric": "e.g. Operating Cash Flow vs Capex",
      "consensus_estimate": "Actual: $888M OCF annualized vs $1.4B capex guidance = $512M funding gap",
      "why_it_matters": "Tests whether production economics self-fund the drilling program at current realized prices",
      "bullish_threshold": "Interpretation: 315 Bcf hedged at $3.21 locks ~$1.0B base revenue; forward curve at $4.36 implies ~$180M unhedged upside on remaining ~135 Bcf, narrowing gap to ~$330M — manageable with asset sale proceeds",
      "bearish_threshold": "Counter-interpretation: $512M gap at $3.21 realized means self-funding requires ~$3.80 across all production — 17% above current realized, so program depends on forward curve materializing"
    }
  ],"""
    elif mode == 'update':
        return """\
  "numbers_that_matter": [
    {
      "metric": "e.g. Production Volume",
      "consensus_estimate": "Last reported: 590 Bcfe (Q4 2025)",
      "why_it_matters": "Directly measures whether low-cost production thesis is scaling",
      "bullish_threshold": "If next report confirms >590 pace, scaling assumption holds",
      "bearish_threshold": "Sequential decline from 590 would signal integration drag"
    }
  ],"""
    else:  # pre_earnings (default)
        return """\
  "numbers_that_matter": [
    {
      "metric": "e.g. Production Volume",
      "consensus_estimate": "e.g. 580-600 Bcfe (or 'not available' if unknown)",
      "why_it_matters": "Directly measures whether low-cost production thesis is scaling",
      "bullish_threshold": "Above 600 Bcfe — capacity additions translating faster than modeled",
      "bearish_threshold": "Below 560 Bcfe — integration headwinds or geological limits"
    }
  ],"""


def build_synthesis_prompt(company, filing_info, differential, industry_profile, external_context, peer_data, supplementary, thesis=None, report_mode=None):
    """Build the IC briefing prompt for Claude with thesis-anchored framing and report mode."""

    prompt_context = industry_profile.get('prompt_context', '') if industry_profile else ''
    sector = industry_profile.get('sector', 'General') if industry_profile else 'General'

    # Build consensus summary string
    consensus_summary = compute_consensus_summary(external_context) if external_context else ''

    # Compute filing age for time-value-of-information
    today = datetime.now().date()
    try:
        filing_date_obj = datetime.strptime(str(filing_info['filing_date']), '%Y-%m-%d').date()
        filing_age_days = (today - filing_date_obj).days
    except (ValueError, TypeError):
        filing_age_days = 0

    # Build mode-driven context for the prompt
    if report_mode:
        mode = report_mode['mode']
        mode_label = report_mode['mode_label']
        task_framing = report_mode['task_framing']

        if mode == 'pre_earnings':
            days_to = report_mode.get('days_to_next')
            next_date = report_mode.get('next_earnings_date', 'unknown')
            age_context = (
                f"\nREPORT MODE: {mode_label} (earnings expected {next_date}, {days_to} days away)"
                f"\nFILING AGE: {filing_age_days} days old."
                f"\n{report_mode['assessment_instruction']}"
            )
            forbidden = report_mode.get('forbidden_words', [])
            if forbidden:
                forbidden_list = ', '.join('"' + w + '"' for w in forbidden)
                age_context += f"\nFORBIDDEN WORDS: {forbidden_list} — do NOT use these words anywhere in your response."
        elif mode == 'earnings_review':
            days_since = report_mode.get('days_since_last')
            last_date = report_mode.get('last_earnings_date', 'unknown')
            age_context = (
                f"\nREPORT MODE: {mode_label} (earnings released {last_date}, {days_since} days ago)"
                f"\nFILING AGE: {filing_age_days} days old."
                f"\n{report_mode['assessment_instruction']}"
            )
        else:  # update
            age_context = (
                f"\nREPORT MODE: {mode_label} (no earnings event nearby)"
                f"\nFILING AGE: {filing_age_days} days old."
                f"\n{report_mode['assessment_instruction']}"
            )

        reader_question = {
            'pre_earnings': '"Earnings are coming. What should I watch for? Is our thesis about to be tested?"',
            'earnings_review': '"We just got results. What did we learn? Is the thesis intact or does it need revision?"',
            'update': '"Nothing new is happening. Where do things stand?"',
        }[mode]
    else:
        task_framing = 'IC EARNINGS BRIEFING'
        reader_question = '"Should we add, hold, or trim? We get new data in days. What do I need to know?"'
        if filing_age_days > 60:
            age_context = (
                f"\nFILING AGE: {filing_age_days} days old. This filing is NOT recent news."
            )
        elif filing_age_days > 14:
            age_context = (
                f"\nFILING AGE: {filing_age_days} days old. Most analysts have likely reviewed this filing."
            )
        else:
            age_context = f"\nFILING AGE: {filing_age_days} days old. This is a recent filing."

    sections = []
    sections.append(f"""{prompt_context}

You are preparing a 2-page {task_framing} for an investment committee member. The reader's question: {reader_question}

Your job is NOT to summarize the filing. Your job is to {'prepare the reader for the upcoming earnings call — what numbers matter, what signals to listen for, and what would change the thesis' if not report_mode or report_mode['mode'] == 'pre_earnings' else 'deliver a clear verdict on the thesis based on the latest data' if report_mode and report_mode['mode'] == 'earnings_review' else 'summarize where things stand — no new earnings data to analyze'}.

TODAY'S DATE: {today.isoformat()}
COMPANY: {company['ticker']} — {company['company_name']}
FILING: {filing_info['filing_type']} dated {filing_info['filing_date']}{age_context}""")

    # Inject thesis FIRST — this is the anchoring framework
    if thesis:
        thesis_expired = False
        if thesis.get('expires_at'):
            try:
                exp = thesis['expires_at']
                if isinstance(exp, str):
                    exp = datetime.strptime(exp[:19], '%Y-%m-%d %H:%M:%S')
                if hasattr(exp, 'date') and exp.date() < today:
                    thesis_expired = True
            except (ValueError, TypeError):
                pass

        key_drivers = thesis.get('key_value_drivers', [])
        if isinstance(key_drivers, str):
            key_drivers = json.loads(key_drivers)
        uncertainties = thesis.get('key_uncertainties', [])
        if isinstance(uncertainties, str):
            uncertainties = json.loads(uncertainties)
        key_metrics = thesis.get('key_metrics', [])
        if isinstance(key_metrics, str):
            key_metrics = json.loads(key_metrics)

        expiry_note = " [THESIS EXPIRED — flag in output if thesis needs re-evaluation]" if thesis_expired else ""

        # Provenance: when the thesis was generated and from what filing
        thesis_created = thesis.get('created_at', '')
        if hasattr(thesis_created, 'strftime'):
            thesis_created_str = thesis_created.strftime('%Y-%m-%d')
        else:
            thesis_created_str = str(thesis_created)[:10] if thesis_created else 'unknown'
        src_type = thesis.get('_source_filing_type', '')
        src_date = thesis.get('_source_filing_date', '')
        if hasattr(src_date, 'strftime'):
            src_date = src_date.strftime('%Y-%m-%d')
        provenance = f"Generated {thesis_created_str}"
        if src_type and src_date:
            provenance += f" from {src_type} ({src_date})"

        # Build financial claims section if available
        financial_claims = thesis.get('financial_claims', {})
        if isinstance(financial_claims, str):
            try:
                financial_claims = json.loads(financial_claims)
            except (json.JSONDecodeError, TypeError):
                financial_claims = {}

        claims_section = ""
        if financial_claims:
            claims_lines = []
            for name, data in sorted(financial_claims.items()):
                if isinstance(data, dict):
                    if 'low' in data and 'high' in data:
                        claims_lines.append(f"  {name}: {data['low']}-{data['high']} {data.get('unit', '')} (period: {data.get('period', 'N/A')}, source: {data.get('source', 'N/A')})")
                    elif 'value' in data:
                        extra = ''
                        if data.get('price'):
                            extra = f", price: {data['price']}"
                        if data.get('basis'):
                            extra += f", basis: {data['basis']}"
                        if data.get('baseline'):
                            extra += f", baseline: {data['baseline']}"
                        claims_lines.append(f"  {name}: {data['value']} {data.get('unit', '')} (period: {data.get('period', 'N/A')}{extra}, source: {data.get('source', 'N/A')})")
            claims_section = f"""

STRUCTURED FINANCIAL CLAIMS (AUTHORITATIVE — use these exact numbers):
These numbers were computed/validated by the thesis pipeline. They are the GROUND TRUTH for this analysis.
Do NOT recompute these values. Use them directly. If the filing data contradicts a claim, note the discrepancy
explicitly ("Thesis claims $X; filing shows $Y"), but do NOT silently substitute a different number.

{chr(10).join(claims_lines)}"""

        sections.append(f"""
--- INVESTMENT THESIS (anchor all analysis against this){expiry_note} ---
Provenance: {provenance}
Summary: {thesis.get('thesis_summary', '')}

Value Drivers:
{chr(10).join(f'  - {d}' for d in key_drivers)}

Key Uncertainties (two-way — could go better or worse):
{chr(10).join(f'  - {u}' for u in uncertainties)}

Key Metrics to Track:
{chr(10).join(f'  - {m}' for m in key_metrics)}
{claims_section}""")

    # Inject consensus summary prominently
    if consensus_summary:
        sections.append(f"""
--- WALL STREET CONSENSUS ---
{consensus_summary}""")

    # Differential analysis data
    diff_data = {
        'executive_summary': differential.get('executive_summary', ''),
        'key_insights': differential.get('key_insights', []),
        'financial_analysis': differential.get('financial_analysis', ''),
        'strategic_assessment': differential.get('strategic_assessment', ''),
        'risks_opportunities': differential.get('risks_opportunities', ''),
    }
    for key in diff_data:
        if isinstance(diff_data[key], str) and diff_data[key]:
            try:
                diff_data[key] = json.loads(diff_data[key])
            except (json.JSONDecodeError, TypeError):
                pass

    sections.append(f"""
--- FILING DATA (differential analysis — changes vs previous filing) ---
{json.dumps(diff_data, indent=2, default=str)}""")

    if external_context:
        sections.append(f"""
--- CURRENT MARKET CONTEXT ---
{json.dumps(external_context, indent=2, default=str)}""")

    if peer_data:
        sections.append(f"""
--- PEER COMPARISON DATA ---
{json.dumps(peer_data, indent=2, default=str)}""")

    if supplementary:
        supp_list = []
        for s in supplementary:
            if s['source_type'] == 'earnings_press_release':
                max_len = 12000  # Full financials matter
            elif s['source_type'] == 'earnings_transcript':
                max_len = 2000
            else:
                max_len = 500
            supp_list.append({
                'type': s['source_type'], 'title': s['title'], 'date': str(s['published_date']),
                'content': s['content'][:max_len] if s['content'] else ''
            })
        sections.append(f"""
--- SUPPLEMENTARY DATA (press releases, news, earnings transcripts) ---
{json.dumps(supp_list, indent=2, default=str)}""")

    sections.append("""
Generate an IC earnings briefing. Return as JSON with this exact structure:

{
  "briefing_type": "earnings_briefing|contrarian_alert",
  "briefing_type_reasoning": "why this briefing type was chosen",

  "where_we_stand": {
    "thesis_assessment": "Is the thesis intact, strengthening, or weakening based on latest data? 2-3 sentences.",
    "street_consensus_summary": "Ratings distribution, price target, key estimate — factual summary",
    "valuation_snapshot": "Current price vs target, forward P/E context, how it compares to peers"
  },

""" + _numbers_schema_example(report_mode) + """

  "signal_map": {
    "accelerating": [
      {
        "signal": "What this means for the thesis — directional interpretation",
        "evidence": "Direct quote or specific data point: 'Q4 production averaged 29 MMcf/day' (press release)",
        "source": "filing_data|supplementary_data|external_context|peer_data"
      }
    ],
    "stalling": [{"signal": "...", "evidence": "...", "source": "..."}],
    "inflecting": [{"signal": "...", "evidence": "...", "source": "..."}]
  },

  "risk_watchlist": [
    {
      "item": "Regulatory enforcement actions",
      "what_to_listen_for": "Does management quantify financial exposure or brush it off?",
      "signal_if_mentioned": "bearish — materializing regulatory cost",
      "signal_if_absent": "neutral — confirms priced-in treatment"
    }
  ],

  "thesis_review": {
    "revision_recommended": false,
    "trigger_type": null,
    "evidence": "Specific filing content or external context that triggered this recommendation, or null",
    "suggested_changes": {
      "add_value_drivers": [],
      "remove_value_drivers": [],
      "add_uncertainties": [],
      "remove_uncertainties": [],
      "add_metrics": [],
      "remove_metrics": [],
      "thesis_summary_note": "How the summary should evolve, or null"
    }
  },

  "reference_analysis": {
    "financial_summary": "2-3 sentences on financial position from filing",
    "operational_summary": "2-3 sentences on operations from filing",
    "strategic_summary": "2-3 sentences on strategy from filing",
    "peer_comparison": "2-3 sentences on relative positioning vs peers"
  },

  "urgency_indicators": {
    "material_change_detected": false,
    "contrarian_signal": false,
    "contrarian_thesis": "required if contrarian_signal is true — the specific thesis the street is missing",
    "reasoning": "string"
  }
}

THESIS REVIEW — COMPARISON-BASED EVALUATION:
The thesis_review is a COMPARISON between what the thesis says and what this filing says. It is NOT a detection of change in the filing.

CRITICAL RULE: Read the thesis text above carefully. If the thesis ALREADY states the key facts from this filing (e.g., the thesis says "$1.4-1.5B capex" and the filing says "$1.4-1.5B capex"), then revision_recommended MUST be false. The filing may frame something as a change from prior periods — that is irrelevant. The only question is: does the THESIS text match the CURRENT reality shown in this filing?

STEP-BY-STEP PROCESS:
1. List the 3-5 most material facts from this filing (capex, production, pricing, cash flow, strategic shifts)
2. For each fact, check: does the thesis summary, value drivers, or uncertainties already state this number or reflect this reality?
3. Only if the thesis CONTRADICTS or OMITS a material fact should you recommend revision
4. Note the thesis provenance above — if the thesis was generated recently, it likely already incorporates this data

Apply this test: "If I read ONLY the thesis text (not the filing), would I have an INCORRECT picture of where this company stands today?"

Trigger types (only recommend revision if the thesis text CONTRADICTS or OMITS one of these):

1. new_value_driver: The filing reveals a material value source that the thesis does NOT mention at all. Not "the filing discusses X" — "the thesis is MISSING X." Evidence bar: management quantifies revenue/volume from a new source not referenced anywhere in the thesis.

2. value_driver_invalidated: A value driver listed in the thesis is no longer operative based on this filing. Evidence bar: the thesis claims X but the filing shows X is no longer true.

3. capital_allocation_pivot: The thesis states a capex, cash flow, or capital return assumption that CONTRADICTS this filing. Evidence bar: the thesis says "$X capex" but the filing says a materially different number, OR the thesis assumes FCF positive but the filing shows negative. CRITICAL: If the thesis already states the correct capex number, this is NOT a trigger — even if the filing frames it as a change from prior periods.

4. structural_cost_shift: The thesis states cost or margin assumptions that CONTRADICT this filing. Evidence bar: the thesis claims breakeven at $X but the filing shows a materially different breakeven.

5. regulatory_regime_change: The thesis does not reflect a regulatory change shown in this filing. Evidence bar: consent decree, material settlement, new framework not mentioned in thesis.

6. magnitude_escalation: An uncertainty listed in the thesis dramatically underestimates the stakes based on this filing. Evidence bar: the thesis frames something as minor but the filing shows it is now material.

What is NOT a trigger: anything the thesis already reflects accurately, quarterly beat/miss, commodity price swings, management tone, the filing framing something as "new" or "increased" when the thesis already has the updated numbers.

If no thesis exists, set revision_recommended to true with trigger_type "new_value_driver" and evidence "No thesis exists."
""")

    # Signal map evidence instructions (all modes)
    sections.append("""
SIGNAL MAP — EVIDENCE REQUIRED: Each signal entry must be a JSON object with "signal", "evidence", and "source" fields. The "evidence" field must contain a direct quote or specific number from the data sections above. The "source" field must be one of: "filing_data", "supplementary_data", "external_context", "peer_data". If you cannot cite evidence for a signal, do not include it.

CROSS-CHECK: Every number in signal_map must be consistent with numbers_that_matter. If numbers_that_matter reports a metric at X, signal_map must not claim a different value for the same metric.
""")

    # Mode-specific instructions injected AFTER the schema but BEFORE guidelines
    if report_mode and report_mode['mode'] == 'earnings_review':
        sections.append("""
EARNINGS REVIEW — MODE-SPECIFIC INSTRUCTIONS:
- SIGNAL MAP: Report what management ACTUALLY said or what the filing data ACTUALLY shows. Every signal must be grounded in specific data from this filing or press release. Do NOT describe hypothetical bullish/bearish scenarios — describe what was communicated and categorize it. "Accelerating" means management said or the data shows something positive. "Stalling" means they said or the data shows something concerning. "Inflecting" means something new emerged. Every entry must cite actual data from this filing, press release, or transcript. No hypothetical scenarios — those belong in risk_watchlist.
- NUMBERS THAT MATTER: The "consensus_estimate" column is now "Result vs Est." — put the ACTUAL reported number and how it compares to prior estimates or guidance. If you do not have the actual result from the filing data, do NOT include that metric.
- NUMBERS THAT MATTER — FIELD SEMANTICS (earnings_review mode):
  - "bullish_threshold" (displayed under column header "What This Means"): INTERPRET the actual result. This is NOT a hypothetical threshold. Connect the reported number to the thesis — what does this result tell us about whether the thesis is working? Flag quarter-over-quarter trends (e.g., Q4 pace vs full-year average). A tautology like "Consistent >X rates" when the result IS X is WRONG — instead explain what X means for the thesis. Do NOT prefix the value with "What This Means:" — just write the interpretation directly.
  - "bearish_threshold" (displayed under column header "Risk If..."): What RISK or counter-interpretation does this result introduce? Not a hypothetical downside threshold — a specific analytical concern raised by the actual data (e.g., "beat concentrated in acquired assets, not organic drilling — overstates core growth"). Do NOT prefix the value with "Risk If:" — just write the risk directly.
- PRICE ECONOMICS: You have actual reported numbers (OCF, capex, realized price) AND forward curve data. Use them together. "Hedge protection working effectively" or "risk if prices insufficient" is NOT analysis — compute the actual cash flow coverage ratio and forward curve exposure. Connect hedge book volume + realized price + forward curve + capex into a quantitative picture.
""")
    elif report_mode and report_mode['mode'] == 'pre_earnings':
        sections.append("""
PRE-EARNINGS — MODE-SPECIFIC INSTRUCTIONS:
- SIGNAL MAP: Describe what management WOULD say on the upcoming call that would be bullish, bearish, or a new signal. These are forward-looking — things to listen for. Forward-looking signals are acceptable, but any historical numbers cited must have evidence from the data above.
- NUMBERS THAT MATTER: Include consensus estimates where available. If no estimate exists for a metric, you may still include it if the metric itself is critical to the thesis — but label the estimate honestly.
- PRICE THRESHOLDS: When the thesis depends on commodity prices, set thresholds using actual hedge book and forward curve data, not round numbers. "Watch for gas prices above $X" is tautological — use hedge book coverage and capex economics to set meaningful thresholds.
""")

    sections.append("""
Guidelines:
- THESIS-ANCHORED: Frame everything against the investment thesis. The reader knows the thesis — tell them whether it's working.
- USE STRUCTURED FINANCIAL CLAIMS: If STRUCTURED FINANCIAL CLAIMS are provided above, use those exact numbers in your analysis. They are the authoritative source. Do NOT recompute funding gaps, breakeven prices, or other derived metrics — use the provided values directly.
- INTERNAL COHERENCE: The thesis_assessment and thesis_review MUST tell the same story. If thesis_review says revision_recommended: true, the assessment must explain what the thesis gets wrong. If thesis_review says revision_recommended: false (thesis already reflects the data), the assessment should evaluate whether the thesis is WORKING — is the data confirming or challenging the thesis's predictions? Do NOT say "thesis needs revision" when the thesis already has the right numbers. Do NOT say "thesis intact" when the data contradicts it.
- NUMBERS THAT MATTER: Pick 3-5 metrics that will most directly tell the IC member whether the thesis is intact. Include consensus estimates where available. Set thresholds that are directionally meaningful — not arbitrary. CRITICAL: Only include a metric if you have an actual number to put in the consensus_estimate field. Do NOT include metrics with "not available" as the estimate — an IC member does not want a half-empty table. If you only have data for 2 metrics, return 2 excellent metrics. Quality over quantity.
- SIGNAL MAP: For each key uncertainty in the thesis, describe what management would say on the call that would be bullish, bearish, or a new signal. Be DIRECTIONAL, not prescriptive — say "this would be bullish" not "you should buy."
- FACTUAL ACCURACY: Every number you cite must come from the filing data, external context, or supplementary data provided above. Do NOT fabricate, round up, or infer numbers that aren't in the data. If a well delivered 29 MMcf/day, say 29 — not 32. An IC member will check.
- RISK WATCHLIST: 3-5 items to monitor. Not headline risks — "also listen for" items. Include interpretation guidance for whether it's mentioned or not.
- THESIS REVIEW: Evaluate BOTH the filing content AND the external market context injected above. An uncertainty may not have changed in the filing, but external developments may have changed the stakes.
- FORWARD CURVE HONESTY: Present commodity data factually. If futures show contango, note the contract months — do not narrativize seasonal patterns as structural trends.
- PRICE-GROUNDED ANALYSIS: When you have hedge book data, realized prices, forward curve, and capex/cash flow data, you MUST connect them quantitatively. Saying "hedge protection working effectively" or "risk if prices insufficient" is a TAUTOLOGY for a commodity company — it says nothing an IC member doesn't already know. Use the STRUCTURED FINANCIAL CLAIMS above (funding_gap, hedge_coverage_pct, breakeven_price) as the basis for your analysis. Present them as given facts and build your interpretation around them. BAD: "Hedge protection enables capital deployment confidence despite price uncertainty." GOOD: "$[funding_gap] gap at [OCF] vs [capex]. [hedge_volume] hedged (~[hedge_coverage_pct]% of production) locks base cash flow. Forward curve at [price] implies ~$[X]M unhedged upside. Self-funding requires ~$[breakeven_price] realized across full production."
- REFERENCE ANALYSIS: Keep each summary to 2-3 sentences. The detailed filing analysis is reference material, not the briefing itself.
- DO NOT PARROT MANAGEMENT: When management says "signals confidence" but the numbers show negative free cash flow and escalating spend, say what the numbers say. An IC member needs your honest read, not the press release rewritten.
- BREVITY: Every section should be information-dense and concise. An IC member is reading this in 3 minutes before a meeting.
- Be specific with numbers and percentages — never vague
- If data is insufficient for a section, say so explicitly

Return ONLY valid JSON, no other text.""")

    return '\n'.join(sections)


def compute_consensus_strength(external_context):
    """
    Compute analyst consensus strength from 0.0 (no consensus) to 1.0 (unanimous).
    Based on the distribution of buy/hold/sell ratings.
    """
    analyst_data = external_context.get('analyst_data', {})
    recs = analyst_data.get('recommendations', {})
    if not recs:
        return 0.0

    sb = recs.get('strong_buy', 0)
    b = recs.get('buy', 0)
    h = recs.get('hold', 0)
    s = recs.get('sell', 0)
    ss = recs.get('strong_sell', 0)
    total = sb + b + h + s + ss

    if total == 0:
        return 0.0

    # Weighted score: strong_buy=2, buy=1, hold=0, sell=-1, strong_sell=-2
    # Normalize to 0-1 where 1.0 = all strong buy, 0.0 = all strong sell
    weighted = (sb * 2 + b * 1 + h * 0 + s * -1 + ss * -2) / total
    # Map from [-2, 2] to [0, 1]
    strength = (weighted + 2) / 4
    return round(strength, 3)


def compute_urgency(synthesis, filing_type, watchlist_priority='standard', external_context=None, filing_date=None, report_mode=None):
    """
    Urgency scoring for IC briefing schema with earnings-calendar-driven modes.

    Scores based on urgency_indicators, filing type, filing age, and report mode.
    Report mode drives report_type and controls whether age dampener applies.

    Returns: (urgency_level, report_type, urgency_detail_dict)
    """
    external_context = external_context or {}

    # --- Filing age computation ---
    today = datetime.now().date()
    filing_age_days = 0
    if filing_date:
        try:
            fd = datetime.strptime(str(filing_date), '%Y-%m-%d').date()
            filing_age_days = (today - fd).days
        except (ValueError, TypeError):
            pass

    mode = report_mode['mode'] if report_mode else None

    # --- Phase 1: Raw significance ---
    score = 0
    detail = {'phase1_raw': 0, 'phase2_adjusted': 0, 'dampener': 1.0, 'filing_age_days': filing_age_days}
    if mode:
        detail['report_mode'] = mode

    urgency_ind = synthesis.get('urgency_indicators', {})
    if urgency_ind.get('material_change_detected'):
        score += 15
        detail['material_change'] = True

    has_contrarian_thesis = bool(urgency_ind.get('contrarian_signal') and urgency_ind.get('contrarian_thesis'))
    detail['has_contrarian_thesis'] = has_contrarian_thesis
    if has_contrarian_thesis:
        score += 30

    if filing_type == '8-K':
        score += 15
    elif filing_type in ('10-Q', '10-K'):
        score += 5

    if watchlist_priority == 'primary':
        score += 5

    detail['phase1_raw'] = score

    # --- Phase 2: Consensus calibration + filing age ---
    consensus_strength = compute_consensus_strength(external_context)
    detail['consensus_strength'] = consensus_strength

    # Determine report type from mode (mode-driven) or Claude's suggestion (legacy)
    if mode:
        report_type = report_mode['report_type']  # pre_earnings_brief / earnings_review / update
    else:
        report_type = synthesis.get('briefing_type', 'earnings_briefing')
        if report_type not in ('earnings_briefing', 'contrarian_alert'):
            report_type = 'earnings_briefing'

    # Contrarian alert overrides any mode
    if has_contrarian_thesis:
        # In pre_earnings or earnings_review: contrarian_alert is NOT downgraded by filing age
        # In update mode: contrarian is subject to age dampener (handled below)
        if mode in ('pre_earnings', 'earnings_review'):
            report_type = 'contrarian_alert'
            detail['contrarian_override'] = f'contrarian_alert in {mode} mode — no age downgrade'
        elif mode == 'update':
            # Contrarian in update mode — will be age-dampened below
            report_type = 'contrarian_alert'
        else:
            # Legacy (no mode) — validate contrarian
            report_type = 'contrarian_alert'

    # Validate contrarian_alert: must have an actual thesis
    if report_type == 'contrarian_alert' and not has_contrarian_thesis:
        report_type = report_mode['report_type'] if report_mode else 'earnings_briefing'
        detail['report_type_downgraded'] = True

    # --- Filing age dampener ---
    # Pre-earnings and earnings_review: skip age dampener entirely
    # Update mode (and legacy no-mode): apply age dampener as before
    if mode in ('pre_earnings', 'earnings_review'):
        # No age dampener — fresh context around earnings event
        detail['age_dampener_skipped'] = f'mode={mode}, no age dampener applied'
    else:
        # Update mode or legacy: apply age dampener
        if filing_age_days > 60:
            # In update mode, also downgrade contrarian (old data = old contrarian signal)
            if report_type == 'contrarian_alert' and mode == 'update':
                report_type = 'update'
                detail['report_type_age_override'] = f'contrarian_alert downgraded in update mode: filing is {filing_age_days} days old'
            elif report_type == 'contrarian_alert' and not mode:
                report_type = 'earnings_briefing'
                detail['report_type_age_override'] = f'contrarian_alert downgraded: filing is {filing_age_days} days old'

            age_dampener = max(0.2, 1.0 - (filing_age_days / 150))
            score = int(score * age_dampener)
            detail['age_dampener'] = round(age_dampener, 3)
        elif filing_age_days > 14:
            age_dampener = max(0.5, 1.0 - (filing_age_days / 120))
            score = int(score * age_dampener)
            detail['age_dampener'] = round(age_dampener, 3)

    # Consensus dampener for non-contrarian briefings
    if not has_contrarian_thesis and consensus_strength > 0.6:
        dampener = 1.0 - (consensus_strength * 0.5)
        score = int(score * dampener)
        detail['consensus_dampener'] = round(dampener, 3)

    detail['phase2_adjusted'] = score

    # Classify urgency
    if score >= 50:
        urgency = 'immediate'
    elif score >= 25:
        urgency = 'daily_digest'
    else:
        urgency = 'weekly_rollup'

    detail['urgency_level'] = urgency
    detail['report_type'] = report_type

    return urgency, report_type, detail


def save_synthesis(conn, report_id, synthesis, urgency, report_type, urgency_detail, html, external_context, peer_data, company_id, report_mode=None, validation_log=None, review_notes=None):
    """Update the intelligence_reports row with synthesis results (new IC briefing schema)."""
    cursor = conn.cursor()

    # Map new schema fields into existing DB columns
    # where_we_stand → executive_summary (thesis assessment)
    where_we_stand = synthesis.get('where_we_stand', {})
    exec_summary = where_we_stand.get('thesis_assessment', '')

    # numbers_that_matter + signal_map → key_insights JSONB
    briefing_data = {
        'numbers_that_matter': synthesis.get('numbers_that_matter', []),
        'signal_map': synthesis.get('signal_map', {}),
        'risk_watchlist': synthesis.get('risk_watchlist', []),
    }

    # reference_analysis fields → existing text columns
    ref = synthesis.get('reference_analysis', {})

    cursor.execute("""
        UPDATE intelligence_reports SET
            executive_summary = %s,
            key_insights = %s,
            financial_analysis = %s,
            operational_analysis = %s,
            strategic_assessment = %s,
            risks_opportunities = %s,
            peer_comparison = %s,
            actionable_takeaways = %s,
            full_report_html = %s,
            materiality = %s,
            urgency = %s,
            report_type = %s,
            company_id = %s,
            industry_context = %s,
            peer_data = %s,
            generation_metadata = %s
        WHERE id = %s
    """, (
        exec_summary,
        json.dumps(briefing_data),
        json.dumps(ref.get('financial_summary', '')),
        json.dumps(ref.get('operational_summary', '')),
        json.dumps(ref.get('strategic_summary', '')),
        json.dumps(synthesis.get('risk_watchlist', [])),
        json.dumps(ref.get('peer_comparison', '')),
        json.dumps(synthesis.get('where_we_stand', {})),
        html,
        compute_materiality(synthesis),
        urgency,
        report_type,
        company_id,
        json.dumps(external_context, default=str),
        json.dumps(peer_data, default=str),
        json.dumps({
            'model': MODEL,
            'timestamp': datetime.now().isoformat(),
            'report_type': report_type,
            'report_mode': report_mode.get('mode') if report_mode else None,
            'report_mode_detail': report_mode if report_mode else None,
            'urgency_detail': urgency_detail,
            'briefing_type': synthesis.get('briefing_type', report_type),
            'thesis_review': synthesis.get('thesis_review'),
            'review_notes': review_notes or [],
            'validation_log': validation_log or [],
        }, default=str),
        report_id
    ))

    conn.commit()
    cursor.close()


def compute_materiality(synthesis):
    """Derive materiality from urgency indicators and briefing content."""
    urgency_ind = synthesis.get('urgency_indicators', {})
    if urgency_ind.get('material_change_detected') or urgency_ind.get('contrarian_signal'):
        return 'high'
    numbers = synthesis.get('numbers_that_matter', [])
    if len(numbers) >= 3:
        return 'medium'
    return 'low'


def validate_signal_map(synthesis, report_mode=None):
    """
    Validate signal_map entries for evidence consistency.
    - Converts legacy bare strings to structured entries (marked unverified).
    - Checks that numbers in 'signal' appear in 'evidence'.
    - Cross-references against numbers_that_matter.
    - Adds 'verified' boolean to each entry.
    Returns (modified_synthesis, validation_log).
    """
    signal_map = synthesis.get('signal_map', {})
    validation_log = []

    # Build reference numbers from numbers_that_matter
    numbers_data = {}
    for n in synthesis.get('numbers_that_matter', []):
        est = str(n.get('consensus_estimate', ''))
        nums = re.findall(r'[\d,.]+', est)
        if nums:
            numbers_data[n.get('metric', '').lower()] = nums

    for category in ('accelerating', 'stalling', 'inflecting'):
        entries = signal_map.get(category, [])
        validated = []
        for entry in entries:
            if isinstance(entry, str):
                # Legacy bare string — can't validate, mark unverified
                validated.append({
                    'signal': entry, 'evidence': '', 'source': 'unknown', 'verified': False
                })
                validation_log.append(f"LEGACY: bare string in {category}, no evidence")
                continue

            signal_text = entry.get('signal', '')
            evidence_text = entry.get('evidence', '')

            # Extract numbers from signal and evidence
            signal_nums = set(re.findall(r'[\d,.]+', signal_text))
            evidence_nums = set(re.findall(r'[\d,.]+', evidence_text))

            # Check: numbers in signal should appear in evidence
            signal_only = signal_nums - evidence_nums
            verified = True
            if signal_only and evidence_nums:
                # Signal contains numbers not in its own evidence
                validation_log.append(
                    f"MISMATCH in {category}: signal has {signal_only} not in evidence. "
                    f"Signal: '{signal_text[:80]}' | Evidence: '{evidence_text[:80]}'"
                )
                verified = False

            entry['verified'] = verified
            validated.append(entry)

        signal_map[category] = validated

    synthesis['signal_map'] = signal_map
    return synthesis, validation_log


def validate_numbers_that_matter(synthesis, report_mode=None):
    """
    Validate numbers_that_matter entries for internal consistency.
    Flags entries where subsidiary fields contain numbers suspiciously close to
    (but different from) the consensus_estimate.

    In earnings_review mode, bullish_threshold and bearish_threshold are interpretive
    fields containing derived economics (breakevens, coverage ratios) — so the
    suspiciously-close check only applies to why_it_matters.

    Adds 'verified' boolean to each entry.
    Returns (modified_synthesis, validation_log).
    """
    mode = report_mode['mode'] if report_mode else None
    numbers = synthesis.get('numbers_that_matter', [])
    validation_log = []

    for entry in numbers:
        metric = entry.get('metric', '')
        estimate = entry.get('consensus_estimate', '')
        verified = True

        estimate_nums = re.findall(r'[\d,.]+', estimate)
        if not estimate_nums:
            entry['verified'] = True
            continue

        # In earnings_review, threshold fields contain derived economics (breakevens,
        # coverage ratios) that intentionally differ from the estimate — skip them.
        if mode == 'earnings_review':
            fields_to_check = ('why_it_matters',)
        else:
            fields_to_check = ('bullish_threshold', 'bearish_threshold', 'why_it_matters')

        for field_name in fields_to_check:
            field_val = entry.get(field_name, '')
            if not field_val:
                continue
            field_nums = re.findall(r'[\d,.]+', field_val)

            for fn in field_nums:
                if fn in estimate_nums:
                    continue  # Exact match — fine
                for en in estimate_nums:
                    # Check if numbers are suspiciously close (within 25%)
                    try:
                        a, b = float(fn.replace(',', '')), float(en.replace(',', ''))
                        if a > 0 and b > 0 and 1.0 < max(a, b) / min(a, b) <= 1.25:
                            validation_log.append(
                                f"MISMATCH in numbers_that_matter '{metric}' {field_name}: "
                                f"'{fn}' close to but differs from estimate '{en}'. "
                                f"Estimate: '{estimate[:80]}' | {field_name}: '{field_val[:80]}'"
                            )
                            verified = False
                    except (ValueError, AttributeError, ZeroDivisionError):
                        pass

        entry['verified'] = verified

    synthesis['numbers_that_matter'] = numbers
    return synthesis, validation_log


def _build_review_checklist(report_mode):
    """Build a mode-aware review checklist for the synthesis review pass."""
    mode = report_mode['mode'] if report_mode else 'pre_earnings'

    checklist = """REVIEW CHECKLIST — check the synthesis JSON against the source data:

1. FACTUAL ACCURACY: Every number in the synthesis must trace to the source data provided.
   - Check signal_map: every number in "signal" must appear in "evidence"
   - Check numbers_that_matter: consensus_estimate must match source data
   - If you find a fabricated number (not in any source), fix it or remove the entry

2. CROSS-REFERENCING: signal_map numbers must be consistent with numbers_that_matter.
   - If numbers_that_matter says metric X = 29, signal_map must not say 32 for the same metric

3. COMPLETENESS: Are important trends visible in the data but missing from the analysis?
   - Quarter-over-quarter changes (e.g., Q4 rate vs full-year average)
   - Year-over-year comparisons present in the source data
   - Divergences between management narrative and actual numbers
"""

    if mode == 'earnings_review':
        checklist += """
4. ANALYTICAL QUALITY (earnings_review mode):
   - "bullish_threshold" fields must INTERPRET the actual result, not set hypothetical thresholds
   - Flag TAUTOLOGIES: if the result is X and the interpretation just says "consistent >X rates", that is wrong — rewrite to explain what X means for the thesis
   - "bearish_threshold" fields must present a RISK or counter-interpretation of the result, not a hypothetical downside number
   - Surface Q-over-Q trends: if Q4 pace differs meaningfully from full-year average, that should appear in either numbers_that_matter interpretation or signal_map
   - The "consensus_estimate" column should show the ACTUAL result vs estimate, not a forward-looking estimate

5. PRICE-CONDITIONAL TAUTOLOGIES:
   - Scan ALL numbers_that_matter and signal_map entries for price-conditional language
   - Flag phrases like: "hedge protection working effectively", "if prices sustain current levels",
     "risk if realization insufficient", "confidence despite price uncertainty", "if gas pricing holds"
   - These are TAUTOLOGIES for a commodity company — every commodity company benefits from higher prices
   - For each flagged entry, REWRITE using the specific economics from the data:
     * What is the actual OCF vs capex gap?
     * What % of production is hedged, at what price?
     * What does the forward curve imply for unhedged volumes?
     * At what price does the company self-fund?
   - Use the MARKET DATA provided below to validate and compute price-grounded corrections
"""
    elif mode == 'pre_earnings':
        checklist += """
4. ANALYTICAL QUALITY (pre_earnings mode):
   - Thresholds should be meaningful relative to estimates, not arbitrary round numbers
   - Signal map entries should be forward-looking (what to listen for), not historical claims
   - Any historical number cited must have evidence from source data

5. PRICE-CONDITIONAL TAUTOLOGIES:
   - Flag generic price-conditional statements: "watch for prices above $X", "bullish if gas prices recover"
   - Rewrite using hedge book + forward curve data: what specific price level changes the economics?
   - Use the MARKET DATA provided below if available
"""
    else:  # update
        checklist += """
4. ANALYTICAL QUALITY (update mode):
   - Thresholds should reference the most recent reported numbers
   - Analysis should acknowledge no new earnings data — don't overstate freshness
   - Forward-looking statements should be clearly conditional
"""

    return checklist


def _extract_review_notes(review_text):
    """Extract review notes from the Claude review response text."""
    # Look for review notes that Claude may embed in various formats
    notes = []

    # Check for a REVIEW_NOTES section
    if 'REVIEW_NOTES' in review_text or 'review_notes' in review_text:
        # Try to find notes between markers
        for marker in ['REVIEW_NOTES:', 'review_notes:', 'Review Notes:']:
            if marker in review_text:
                after = review_text.split(marker, 1)[1]
                # Take until next JSON or end
                end_markers = ['```', '{"', '\n{']
                for em in end_markers:
                    if em in after:
                        after = after.split(em, 1)[0]
                for line in after.strip().split('\n'):
                    line = line.strip().lstrip('-').lstrip('*').strip()
                    if line:
                        notes.append(line)
                break

    return notes


def _extract_pricing_context(external_context):
    """
    Extract pricing-relevant fields from external_context for the review pass.
    Returns a compact string with spot price, forward curve, and stock quote.
    """
    if not external_context:
        return ""

    parts = []

    # Spot price
    spot = external_context.get('henry_hub_spot')
    if spot and isinstance(spot, dict) and spot.get('price'):
        parts.append(f"{spot.get('display_name', 'Henry Hub Spot')}: ${spot['price']}/MMBtu ({spot.get('date', '')})")

    # WTI crude
    wti = external_context.get('wti_crude')
    if wti and isinstance(wti, dict) and wti.get('value'):
        parts.append(f"{wti.get('display_name', 'WTI Crude')}: ${wti['value']}/barrel ({wti.get('date', '')})")

    # Forward curve
    curve = external_context.get('forward_curve')
    if curve and isinstance(curve, dict):
        curve_parts = []
        for tenor in ('3_month', '6_month', '12_month', '18_month', '24_month'):
            data = curve.get(tenor)
            if isinstance(data, dict) and data.get('price'):
                curve_parts.append(f"{tenor.replace('_', ' ')}: ${data['price']}")
        if curve_parts:
            parts.append(f"Forward curve: {' | '.join(curve_parts)}")

    # Curve shape
    shape = external_context.get('curve_shape')
    if shape:
        parts.append(f"Curve shape: {shape}")

    # Stock quote
    quote = external_context.get('stock_quote')
    if quote and isinstance(quote, dict) and quote.get('current_price'):
        parts.append(f"Stock: ${quote['current_price']}")

    if not parts:
        return ""

    return "MARKET DATA (for price-grounding validation):\n" + "\n".join(f"  - {p}" for p in parts)


def review_synthesis(client, synthesis, supplementary, report_mode, external_context=None, thesis=None):
    """
    Review pass: Claude checks its own synthesis against source data.
    Replaces the correction-prompt approach with holistic analytical review.

    Returns (reviewed_synthesis, review_notes).
    """
    checklist = _build_review_checklist(report_mode)

    # Build source data summary for cross-referencing
    source_summary = ""
    if supplementary:
        for s in supplementary:
            if s['source_type'] == 'earnings_press_release':
                max_len = 12000
            elif s['source_type'] == 'earnings_transcript':
                max_len = 2000
            else:
                max_len = 500
            content = s['content'][:max_len] if s['content'] else ''
            source_summary += f"\n--- {s['source_type']}: {s['title']} ({s['published_date']}) ---\n{content}\n"

    # Add pricing context for price-grounding validation
    pricing_context = _extract_pricing_context(external_context)
    if pricing_context:
        source_summary += f"\n{pricing_context}\n"

    # NOTE: Thesis number consistency is now handled by validate_thesis_consistency() in Python.
    # The review pass focuses on what LLMs are good at: analytical quality, tautology detection,
    # source attribution, and interpretive coherence. Arithmetic is Python's job.

    review_prompt = f"""You are reviewing a synthesis JSON that you previously generated for an IC briefing. Your task is to check analytical quality and fix any issues.

{checklist}

NOTE: Number consistency between thesis and synthesis is validated separately by a deterministic check. You do NOT need to verify arithmetic or cross-check specific dollar amounts against the thesis. Focus on analytical quality, tautology detection, source attribution, and interpretive coherence.

SOURCE DATA (ground truth — these contain the actual numbers):
{source_summary if source_summary else '(No supplementary source data available)'}

SYNTHESIS TO REVIEW:
```json
{json.dumps(synthesis, indent=2, default=str)}
```

INSTRUCTIONS:
1. Check every item on the checklist above
2. Fix any issues you find directly in the JSON
3. After the JSON, add a REVIEW_NOTES: section listing what you changed and why (or "No changes needed" if clean)

Return the corrected full synthesis JSON followed by review notes. Format:
```json
{{...corrected synthesis...}}
```

REVIEW_NOTES:
- description of each change made, or "No changes needed"

Return ONLY the JSON block and review notes, no other text."""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            messages=[{"role": "user", "content": review_prompt}]
        )
        response_text = response.content[0].text

        # Extract review notes before parsing JSON
        review_notes = _extract_review_notes(response_text)

        # Parse the corrected JSON
        reviewed = parse_claude_json(response_text)
        if reviewed and isinstance(reviewed, dict):
            return reviewed, review_notes
        else:
            # JSON parsing failed — return original with note
            return synthesis, ["Review pass returned unparseable JSON — keeping original"]

    except Exception as e:
        return synthesis, [f"Review pass failed: {e}"]


def validate_thesis_consistency(synthesis, thesis):
    """
    Deterministic check: synthesis numbers must match thesis financial_claims.
    Returns list of error strings. Empty list = consistent.

    This replaces the LLM-based consistency check. Python checks arithmetic;
    Claude checks analytical quality.
    """
    errors = []
    if not thesis:
        return errors

    claims = thesis.get('financial_claims', {})
    if isinstance(claims, str):
        try:
            claims = json.loads(claims)
        except (json.JSONDecodeError, TypeError):
            claims = {}
    if not claims:
        return errors

    # Flatten synthesis text for number checking
    synthesis_text = json.dumps(synthesis, default=str)

    # Helper: extract all numbers from text (handles $1,400, 540-640, 3.49, etc.)
    def extract_numbers(text):
        """Extract numeric values from text, handling commas and decimals."""
        raw = re.findall(r'[\d,]+\.?\d*', text)
        nums = set()
        for r in raw:
            try:
                nums.add(float(r.replace(',', '')))
            except ValueError:
                pass
        return nums

    # For key claims, check that the number appears in the synthesis
    # We check the main value fields — not exact text matching, but number presence
    key_claims = {}
    for name, data in claims.items():
        if not isinstance(data, dict):
            continue
        if data.get('source') == 'derived' and name in ('funding_gap', 'capex_increase_pct', 'hedge_coverage_pct', 'breakeven_price'):
            # Derived claims are the most critical to check
            if 'low' in data and 'high' in data:
                key_claims[name] = {'low': data['low'], 'high': data['high'], 'type': 'range'}
            elif 'value' in data:
                key_claims[name] = {'value': data['value'], 'type': 'single'}

    # Check funding_gap specifically — this is the claim most likely to be wrong
    funding_gap = claims.get('funding_gap', {})
    if funding_gap and isinstance(funding_gap, dict):
        gap_low = funding_gap.get('low')
        gap_high = funding_gap.get('high')
        if gap_low is not None and gap_high is not None:
            # Extract all numbers from synthesis for cross-check
            synth_nums = extract_numbers(synthesis_text)

            # Check that if synthesis mentions "funding gap" it uses our numbers
            # Look in where_we_stand and numbers_that_matter
            where = synthesis.get('where_we_stand', {})
            assessment = where.get('thesis_assessment', '')
            numbers_that_matter = synthesis.get('numbers_that_matter', [])

            gap_text_areas = [assessment]
            for n in numbers_that_matter:
                for field in ('consensus_estimate', 'bullish_threshold', 'bearish_threshold', 'why_it_matters'):
                    gap_text_areas.append(str(n.get(field, '')))

            # Also check signal_map
            for cat in ('accelerating', 'stalling', 'inflecting'):
                for entry in synthesis.get('signal_map', {}).get(cat, []):
                    if isinstance(entry, dict):
                        gap_text_areas.append(str(entry.get('signal', '')))

            combined_text = ' '.join(gap_text_areas).lower()

            # If synthesis mentions "funding gap" or "gap", check the numbers
            if 'funding gap' in combined_text or 'gap' in combined_text:
                gap_nums = extract_numbers(combined_text)
                # Check that either gap_low or gap_high appears in the text near "gap"
                gap_found = False
                for n in gap_nums:
                    if abs(n - gap_low) < 5 or abs(n - gap_high) < 5:
                        gap_found = True
                        break
                if not gap_found and gap_nums:
                    # Check if any synthesis gap number is wildly different from our computed gap
                    for n in gap_nums:
                        if 100 < n < 5000:  # plausible M range
                            if abs(n - gap_low) > 50 and abs(n - gap_high) > 50:
                                errors.append(
                                    f"FUNDING_GAP_MISMATCH: Thesis claims ${gap_low}-${gap_high}M "
                                    f"(capex minus OCF), but synthesis appears to use ${n:.0f}M. "
                                    f"The number must match."
                                )

    return errors


def process_report(conn, client, report, industry_profile, external_context):
    """Process a single intelligence report through Stage 5 synthesis."""
    ticker = report['ticker']
    filing_type = report['filing_type']
    filing_date = report['filing_date']

    print(f"\n{'=' * 70}")
    print(f"Synthesizing: {ticker} {filing_type} — {filing_date}")
    print(f"Report ID: {report['id']}")
    print(f"{'=' * 70}")

    company = {'ticker': ticker, 'company_name': report['company_name']}
    filing_info = {
        'filing_type': filing_type,
        'filing_date': str(filing_date),
        'accession_number': report['accession_number']
    }

    # Get peer data
    print("  → Fetching peer data...")
    peer_data = get_peer_data(conn, report['company_id'], report['industry_profile_id'])
    if peer_data:
        print(f"    ✓ Found data for {len(peer_data)} peers: {', '.join(peer_data.keys())}")
    else:
        print("    — No peer data available")

    # Populate recent news (Finnhub → data_sources)
    print("  → Fetching recent news...")
    news_count = populate_company_news(conn, report['company_id'], ticker)
    if news_count:
        print(f"    ✓ Added {news_count} new articles")
    else:
        print("    — No new articles")

    # Populate earnings transcript (FMP → data_sources)
    print("  → Fetching earnings transcript...")
    if populate_earnings_transcript(conn, report['company_id'], ticker, filing_date=filing_date):
        print("    ✓ New transcript stored")
    else:
        print("    — Transcript already cached or unavailable")

    # Get supplementary data
    print("  → Checking supplementary data...")
    supplementary = get_supplementary_data(conn, report['company_id'], filing_date)
    if supplementary:
        print(f"    ✓ Found {len(supplementary)} supplementary items")
    else:
        print("    — No supplementary data")

    # Fetch earnings calendar for mode determination
    print("  → Fetching earnings calendar...")
    _time.sleep(1)  # Finnhub rate limit
    earnings_dates = fetch_finnhub_earnings_calendar(ticker)

    # Compute filing age
    today = datetime.now().date()
    try:
        filing_date_obj = datetime.strptime(str(filing_date), '%Y-%m-%d').date()
        filing_age_days = (today - filing_date_obj).days
    except (ValueError, TypeError):
        filing_age_days = 0

    # Determine report mode
    report_mode = determine_report_mode(filing_date, earnings_dates, filing_age_days)
    mode = report_mode['mode']
    print(f"  → Report mode: {report_mode['mode_label']} (mode={mode})")
    if report_mode.get('days_to_next') is not None:
        print(f"    Next earnings: {report_mode['next_earnings_date']} ({report_mode['days_to_next']} days)")
    if report_mode.get('days_since_last') is not None:
        print(f"    Last earnings: {report_mode['last_earnings_date']} ({report_mode['days_since_last']} days ago)")
    print(f"    Filing age: {filing_age_days} days")
    if not earnings_dates:
        print(f"    ⚠ No calendar data — using filing-age heuristic")

    # Fetch investment thesis
    print("  → Fetching investment thesis...")
    thesis = get_active_thesis(conn, report['company_id'])
    if thesis:
        expired = ''
        if thesis.get('expires_at') and thesis['expires_at'].date() < datetime.now().date():
            expired = ' [EXPIRED]'
        print(f"    ✓ Active thesis found (created {thesis['created_at']}){expired}")
        # Enrich thesis with source filing info for report provenance
        source_ids = thesis.get('source_filing_ids')
        if isinstance(source_ids, str):
            try:
                source_ids = json.loads(source_ids)
            except (json.JSONDecodeError, TypeError):
                source_ids = []
        if source_ids:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT filing_type, filing_date FROM filings WHERE id = %s
            """, (source_ids[0],))
            src_filing = cursor.fetchone()
            cursor.close()
            if src_filing:
                thesis['_source_filing_type'] = src_filing['filing_type']
                thesis['_source_filing_date'] = src_filing['filing_date']
    else:
        print("    — No thesis found (run generate_thesis.py first for best results)")

    # Build prompt
    print("  → Building synthesis prompt...")
    prompt = build_synthesis_prompt(
        company, filing_info, report, industry_profile,
        external_context, peer_data, supplementary, thesis=thesis,
        report_mode=report_mode
    )

    # Call Claude
    print("  → Calling Claude for synthesis...")
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}]
        )
        synthesis = parse_claude_json(response.content[0].text)
        if not synthesis:
            print("  ✗ Failed to parse Claude response")
            return False
        print("  ✓ Synthesis complete")
    except Exception as e:
        print(f"  ✗ Claude API error: {e}")
        return False

    # Review pass: Claude checks its own synthesis against source data
    print("  → Review pass (analytical quality, tautology, source attribution)...")
    synthesis, review_notes = review_synthesis(client, synthesis, supplementary, report_mode, external_context=external_context, thesis=thesis)
    if review_notes and review_notes != ["No changes needed"]:
        print(f"    ✓ Review complete — {len(review_notes)} note(s):")
        for note in review_notes[:5]:
            print(f"      - {note[:120]}")
    else:
        print("    ✓ Review complete — no changes needed")

    # Deterministic thesis consistency validation (Python checks arithmetic)
    print("  → Validating thesis consistency (deterministic)...")
    consistency_errors = validate_thesis_consistency(synthesis, thesis)
    if consistency_errors:
        print(f"    ⚠ {len(consistency_errors)} consistency error(s) detected:")
        for err in consistency_errors:
            print(f"      ✗ {err}")
        print(f"    Note: these are logged but not blocking in this version")
    else:
        if thesis and thesis.get('financial_claims'):
            print("    ✓ Synthesis numbers consistent with thesis financial_claims")
        else:
            print("    — No financial_claims to validate against")

    # Validate signal_map (safety net — log only, no correction prompts)
    print("  → Validating signal_map (safety net)...")
    validation_log = list(consistency_errors)  # Start with thesis consistency errors
    synthesis, signal_log = validate_signal_map(synthesis, report_mode=report_mode)
    validation_log.extend(signal_log)
    signal_issues = [e for e in signal_log if e.startswith('MISMATCH')]
    if signal_issues:
        print(f"    ⚠ {len(signal_issues)} issue(s) flagged (review pass should have caught these):")
        for entry in signal_issues:
            print(f"      - {entry}")
    elif signal_log:
        print(f"    ⚠ {len(signal_log)} non-critical issue(s):")
        for entry in signal_log:
            print(f"      - {entry}")
    else:
        print("    ✓ All signals verified")

    # Validate numbers_that_matter (safety net — log only, no correction prompts)
    print("  → Validating numbers_that_matter (safety net)...")
    synthesis, ntm_log = validate_numbers_that_matter(synthesis, report_mode=report_mode)
    ntm_issues = [e for e in ntm_log if e.startswith('MISMATCH')]
    if ntm_issues:
        print(f"    ⚠ {len(ntm_issues)} issue(s) flagged (review pass should have caught these):")
        for entry in ntm_issues:
            print(f"      - {entry}")
    else:
        print("    ✓ All numbers verified")
    validation_log.extend(ntm_log)

    # Compute urgency (consensus-calibrated, mode-aware)
    urgency, report_type, urgency_detail = compute_urgency(
        synthesis, filing_type, report.get('watchlist_priority', 'standard'),
        external_context=external_context, filing_date=str(filing_date),
        report_mode=report_mode
    )
    print(f"  → Report type: {report_type}")
    print(f"  → Urgency: {urgency} (score: {urgency_detail.get('phase2_adjusted', '?')}, "
          f"consensus: {urgency_detail.get('consensus_strength', '?')}, "
          f"dampener: {urgency_detail.get('dampener', 1.0)})")

    # Generate HTML
    print("  → Generating HTML report...")
    html = generate_intelligence_html(company, filing_info, synthesis, external_context, urgency,
                                      report_type=report_type, urgency_detail=urgency_detail,
                                      thesis=thesis, report_mode=report_mode)

    # Save
    print("  → Saving to database...")
    save_synthesis(conn, report['id'], synthesis, urgency, report_type, urgency_detail, html,
                   external_context, peer_data, report['company_id'], report_mode=report_mode,
                   validation_log=validation_log, review_notes=review_notes)
    print(f"  ✓ Report {report['id']} updated")

    # Display summary
    print(f"\n  Report Mode: {report_mode['mode_label']}")
    print(f"  Report Type: {report_type}")
    where = synthesis.get('where_we_stand', {})
    print(f"  Thesis Assessment: {where.get('thesis_assessment', 'N/A')[:200]}")
    numbers = synthesis.get('numbers_that_matter', [])
    print(f"  Numbers That Matter: {len(numbers)}")
    for n in numbers[:4]:
        print(f"    - {n.get('metric', '?')}: {n.get('consensus_estimate', 'N/A')}")
    signal_map = synthesis.get('signal_map', {})
    for cat in ('accelerating', 'stalling', 'inflecting'):
        signals = signal_map.get(cat, [])
        if signals:
            print(f"  {cat.title()}: {len(signals)} signals")

    # Thesis review warning
    thesis_review = synthesis.get('thesis_review', {})
    if thesis_review.get('revision_recommended'):
        trigger = thesis_review.get('trigger_type', 'unknown')
        evidence = thesis_review.get('evidence', '')[:200]
        print(f"\n  {'⚠' * 3}  THESIS REVIEW RECOMMENDED  {'⚠' * 3}")
        print(f"  Trigger: {trigger}")
        print(f"  Evidence: {evidence}")
        suggested = thesis_review.get('suggested_changes', {})
        if suggested:
            for key in ('add_value_drivers', 'remove_value_drivers', 'add_uncertainties',
                       'remove_uncertainties', 'add_metrics', 'remove_metrics'):
                items = suggested.get(key, [])
                if items:
                    print(f"  {key}: {items}")
            note = suggested.get('thesis_summary_note')
            if note:
                print(f"  Summary note: {note}")
        print(f"  Run: generate_thesis.py --ticker {ticker} --refresh")

    return True


def main():
    print("=" * 70)
    print("STAGE 5: INTELLIGENCE SYNTHESIS")
    print("=" * 70)

    # Parse arguments
    ticker_arg = None
    filing_id_arg = None
    for i, arg in enumerate(sys.argv):
        if arg == '--ticker' and i + 1 < len(sys.argv):
            ticker_arg = sys.argv[i + 1].upper()
        elif arg == '--filing-id' and i + 1 < len(sys.argv):
            filing_id_arg = int(sys.argv[i + 1])
        elif arg == '--all':
            pass  # default behavior

    # Initialize
    client = get_anthropic_client()
    if not client:
        return

    conn = connect_db()
    if not conn:
        return
    print("✓ Connected to database")

    # Get reports needing synthesis
    print("\nFinding reports needing synthesis...")
    reports = get_reports_needing_synthesis(conn, ticker=ticker_arg, filing_id=filing_id_arg)

    if not reports:
        print("✓ No reports need synthesis (all already processed)")
        conn.close()
        return

    print(f"✓ Found {len(reports)} reports to synthesize")

    # Fetch external context once (shared across all reports for same industry)
    profiles_cache = {}
    context_cache = {}

    success_count = 0

    for report in reports:
        profile_id = report.get('industry_profile_id')

        # Cache industry profile
        if profile_id and profile_id not in profiles_cache:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM industry_profiles WHERE id = %s", (profile_id,))
            profiles_cache[profile_id] = cursor.fetchone()
            cursor.close()

        industry_profile = profiles_cache.get(profile_id)

        # Cache external context per industry
        if profile_id and profile_id not in context_cache:
            print(f"\n  → Fetching external market context for {industry_profile['industry_name'] if industry_profile else 'unknown'}...")
            context_cache[profile_id] = get_industry_context(conn, industry_profile, company_ticker=report['ticker'])
            if context_cache[profile_id]:
                print(f"    ✓ Got market data: {', '.join(context_cache[profile_id].keys())}")
            else:
                print("    — No external data available")

        external_context = context_cache.get(profile_id, {})

        if process_report(conn, client, report, industry_profile, external_context):
            success_count += 1

    # Summary
    print(f"\n{'=' * 70}")
    print(f"SYNTHESIS COMPLETE")
    print(f"{'=' * 70}")
    print(f"Reports Synthesized: {success_count}/{len(reports)}")
    print(f"{'=' * 70}")

    conn.close()


if __name__ == "__main__":
    main()
