#!/usr/bin/env python3
"""
HTML report templates for IC Decision Briefs.
Uses inline CSS for Gmail compatibility.
Report types: earnings_briefing, contrarian_alert
"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo


# Report type visual identity
REPORT_TYPE_STYLES = {
    'contrarian_alert': {
        'bg': '#dc3545', 'text': '#ffffff',
        'label': 'CONTRARIAN ALERT',
        'subtitle': 'Filing diverges from analyst consensus',
    },
    'pre_earnings_brief': {
        'bg': '#0d6efd', 'text': '#ffffff',
        'label': 'PRE-EARNINGS BRIEF',
        'subtitle': 'Earnings expected {earnings_date}',
    },
    'earnings_review': {
        'bg': '#198754', 'text': '#ffffff',
        'label': 'EARNINGS REVIEW',
        'subtitle': 'Earnings released {earnings_date}',
    },
    'update': {
        'bg': '#6c757d', 'text': '#ffffff',
        'label': 'UPDATE',
        'subtitle': 'IC Decision Brief',
    },
    # Legacy types (backwards compatibility)
    'earnings_briefing': {
        'bg': '#0d6efd', 'text': '#ffffff',
        'label': 'EARNINGS BRIEFING',
        'subtitle': 'IC Decision Brief',
    },
    'filing_update': {
        'bg': '#6c757d', 'text': '#ffffff',
        'label': 'FILING UPDATE',
        'subtitle': 'Confirms consensus view',
    },
}

# Mode-aware table column headers for Numbers That Matter
NUMBERS_TABLE_HEADERS = {
    'pre_earnings': {
        'col2': 'Consensus Estimate',
        'col3': 'Bullish If...',
        'col4': 'Bearish If...',
    },
    'earnings_review': {
        'col2': 'Result vs Est.',
        'col3': 'What This Means',
        'col4': 'Risk If...',
    },
    'update': {
        'col2': 'Last Reported',
        'col3': 'Watch For',
        'col4': 'Risk Factor',
    },
}

# Mode-aware Signal Map intro text
SIGNAL_MAP_INTROS = {
    'pre_earnings': 'What to listen for on the call:',
    'earnings_review': 'What management signaled:',
    'update': 'Key signals to monitor:',
}

URGENCY_BADGES = {
    'immediate': {'bg': '#dc3545', 'label': 'DELIVER NOW'},
    'daily_digest': {'bg': '#fd7e14', 'label': 'DAILY DIGEST'},
    'weekly_rollup': {'bg': '#6c757d', 'label': 'WEEKLY'},
}

SIGNAL_COLORS = {
    'accelerating': '#28a745',
    'stalling': '#fd7e14',
    'inflecting': '#0d6efd',
}


def _section_html(title, content):
    """Wrap a section with consistent styling."""
    return f"""
    <tr><td style="padding: 20px 30px 10px;">
        <h2 style="margin: 0 0 10px; font-size: 18px; color: #333; border-bottom: 2px solid #eee; padding-bottom: 8px;">{title}</h2>
        {content}
    </td></tr>"""


def _muted_section_html(title, content):
    """Wrap a section with muted reference appendix styling."""
    return f"""
    <tr><td style="padding: 15px 30px 10px; background: #f8f9fa;">
        <h3 style="margin: 0 0 8px; font-size: 14px; color: #888; text-transform: uppercase; letter-spacing: 0.5px;">{title}</h3>
        <div style="color: #666; font-size: 13px; line-height: 1.5;">{content}</div>
    </td></tr>"""


def _bullet_list(items, color='#444'):
    """Generate a bulleted list from a list of strings."""
    if not items:
        return '<p style="color: #999; margin: 5px 0;">None identified</p>'
    return '<ul style="margin: 5px 0; padding-left: 20px;">' + \
        ''.join(f'<li style="margin: 4px 0; color: {color}; line-height: 1.5;">{item}</li>' for item in items) + \
        '</ul>'


def _json_field(data, key, default='N/A'):
    """Safely extract a field from data that may be JSON string or dict."""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return default
    if isinstance(data, dict):
        return data.get(key, default)
    return default


def _render_header(ticker, company_name, filing_type, filing_date, timestamp, report_type, urgency, report_mode=None):
    """Render the report header with report-type-driven color and urgency badge."""
    rt_style = REPORT_TYPE_STYLES.get(report_type, REPORT_TYPE_STYLES.get('earnings_briefing', REPORT_TYPE_STYLES['update']))
    urgency_badge = URGENCY_BADGES.get(urgency, URGENCY_BADGES['weekly_rollup'])

    # Format subtitle with earnings date if available
    subtitle = rt_style['subtitle']
    if report_mode:
        if report_mode.get('mode') == 'pre_earnings' and report_mode.get('next_earnings_date'):
            subtitle = subtitle.format(earnings_date=report_mode['next_earnings_date'])
        elif report_mode.get('mode') == 'earnings_review' and report_mode.get('last_earnings_date'):
            subtitle = subtitle.format(earnings_date=report_mode['last_earnings_date'])
        else:
            subtitle = subtitle.replace('{earnings_date}', '')
    else:
        subtitle = subtitle.replace('{earnings_date}', '')

    return f"""
    <tr><td style="background: {rt_style['bg']}; color: {rt_style['text']}; padding: 20px 30px;">
        <table style="width: 100%;"><tr>
            <td>
                <p style="margin: 0 0 4px; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; opacity: 0.9;">{rt_style['label']}</p>
                <h1 style="margin: 0; font-size: 22px;">{ticker} — {company_name}</h1>
                <p style="margin: 5px 0 0; font-size: 14px; opacity: 0.9;">{subtitle} | {filing_type} ({filing_date})</p>
                <p style="margin: 3px 0 0; font-size: 13px; opacity: 0.75;">Prepared {timestamp}</p>
            </td>
            <td style="text-align: right; vertical-align: top;">
                <span style="background: {urgency_badge['bg']}; color: #fff; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;">{urgency_badge['label']}</span>
            </td>
        </tr></table>
    </td></tr>"""


def _render_thesis_review_banner(synthesis):
    """Render an amber thesis review banner when revision is recommended."""
    thesis_review = synthesis.get('thesis_review', {})
    if not thesis_review.get('revision_recommended'):
        return ''

    trigger = thesis_review.get('trigger_type', 'unknown')
    evidence = thesis_review.get('evidence', '')
    suggested = thesis_review.get('suggested_changes', {})

    # Trigger type display labels
    trigger_labels = {
        'new_value_driver': 'New Value Driver Emerging',
        'value_driver_invalidated': 'Value Driver Invalidated',
        'capital_allocation_pivot': 'Capital Allocation Pivot',
        'structural_cost_shift': 'Structural Cost/Margin Shift',
        'regulatory_regime_change': 'Regulatory Regime Change',
        'magnitude_escalation': 'Magnitude Escalation',
    }
    trigger_label = trigger_labels.get(trigger, trigger.replace('_', ' ').title())

    # Build suggested changes bullets
    changes_html = ''
    if suggested:
        bullets = []
        for key, label in [('add_value_drivers', 'Add driver'),
                           ('remove_value_drivers', 'Remove driver'),
                           ('add_uncertainties', 'Add uncertainty'),
                           ('remove_uncertainties', 'Remove uncertainty'),
                           ('add_metrics', 'Add metric'),
                           ('remove_metrics', 'Remove metric')]:
            for item in suggested.get(key, []):
                bullets.append(f'<li style="margin: 3px 0; font-size: 13px; color: #856404;">{label}: {item}</li>')
        note = suggested.get('thesis_summary_note')
        if note:
            bullets.append(f'<li style="margin: 3px 0; font-size: 13px; color: #856404;">Summary: {note}</li>')
        if bullets:
            changes_html = f'<ul style="margin: 8px 0 0; padding-left: 20px;">{"".join(bullets)}</ul>'

    return f"""
    <tr><td style="padding: 15px 30px;">
        <div style="border: 2px solid #ffc107; background: #fff8e1; padding: 15px 20px; border-radius: 6px;">
            <p style="margin: 0 0 6px; font-size: 13px; font-weight: bold; color: #856404; text-transform: uppercase; letter-spacing: 0.5px;">&#9888; Thesis Review Recommended — {trigger_label}</p>
            <p style="margin: 0; font-size: 14px; color: #333; line-height: 1.5;">{evidence}</p>
            {changes_html}
        </div>
    </td></tr>"""


def _render_contrarian_callout(synthesis):
    """Render contrarian thesis callout box for contrarian_alert reports."""
    urgency_ind = synthesis.get('urgency_indicators', {})
    contrarian_thesis = urgency_ind.get('contrarian_thesis', '')
    if not contrarian_thesis:
        return ''
    return f"""
    <tr><td style="padding: 15px 30px;">
        <div style="border: 2px solid #dc3545; background: #fff5f5; padding: 15px 20px; border-radius: 6px;">
            <p style="margin: 0 0 6px; font-size: 13px; font-weight: bold; color: #dc3545; text-transform: uppercase; letter-spacing: 0.5px;">Contrarian Thesis</p>
            <p style="margin: 0; font-size: 15px; color: #333; line-height: 1.5;">{contrarian_thesis}</p>
        </div>
    </td></tr>"""


def _render_where_we_stand(synthesis, thesis=None):
    """Render the 'Where We Stand' section."""
    where = synthesis.get('where_we_stand', {})

    html = ''

    # Investment thesis from stored data
    if thesis:
        key_drivers = thesis.get('key_value_drivers', [])
        if isinstance(key_drivers, str):
            try:
                key_drivers = json.loads(key_drivers)
            except (json.JSONDecodeError, TypeError):
                key_drivers = []
        uncertainties = thesis.get('key_uncertainties', [])
        if isinstance(uncertainties, str):
            try:
                uncertainties = json.loads(uncertainties)
            except (json.JSONDecodeError, TypeError):
                uncertainties = []

        # Determine if revision is recommended (for staleness indicator)
        thesis_review = synthesis.get('thesis_review', {})
        revision_recommended = thesis_review.get('revision_recommended', False)

        # Visual styling: amber border when stale, blue when current
        if revision_recommended:
            border_color = '#ffc107'
            bg_color = '#fffbf0'
            stale_tag = ' <span style="background: #ffc107; color: #856404; font-size: 10px; padding: 2px 6px; border-radius: 3px; margin-left: 8px; vertical-align: middle;">UPDATE RECOMMENDED</span>'
        else:
            border_color = '#0d6efd'
            bg_color = '#f0f4ff'
            stale_tag = ''

        # Provenance line: when generated and from what filing
        provenance_parts = []
        created_at = thesis.get('created_at')
        if created_at:
            if hasattr(created_at, 'strftime'):
                provenance_parts.append(f"Generated {created_at.strftime('%Y-%m-%d')}")
            else:
                provenance_parts.append(f"Generated {str(created_at)[:10]}")
        src_type = thesis.get('_source_filing_type')
        src_date = thesis.get('_source_filing_date')
        if src_type and src_date:
            if hasattr(src_date, 'strftime'):
                src_date_str = src_date.strftime('%Y-%m-%d')
            else:
                src_date_str = str(src_date)[:10]
            provenance_parts.append(f"from {src_type} ({src_date_str})")
        provenance_line = ''
        if provenance_parts:
            provenance_line = f'<p style="margin: 6px 0 0; font-size: 11px; color: #999;">{" ".join(provenance_parts)}</p>'

        html += f"""
        <div style="background: {bg_color}; border-left: 3px solid {border_color}; padding: 12px 16px; margin: 5px 0 15px; border-radius: 0 4px 4px 0;">
            <p style="margin: 0 0 4px; font-size: 13px; font-weight: bold; color: {border_color}; text-transform: uppercase; letter-spacing: 0.5px;">Investment Thesis{stale_tag}</p>
            <p style="margin: 0 0 8px; color: #333; line-height: 1.5;">{thesis.get('thesis_summary', '')}</p>
            <p style="margin: 0; font-size: 12px; color: #666;">Key uncertainties: {' | '.join(u[:60] for u in uncertainties[:4])}</p>
            {provenance_line}
        </div>"""

    # Thesis assessment from Claude
    assessment = where.get('thesis_assessment', '')
    if assessment:
        html += f'<p style="margin: 10px 0; font-size: 15px; line-height: 1.6; color: #333;"><strong>Thesis Assessment:</strong> {assessment}</p>'

    # Street consensus
    street = where.get('street_consensus_summary', '')
    if street:
        html += f'<p style="margin: 8px 0; color: #444;"><strong>Street Consensus:</strong> {street}</p>'

    # Valuation snapshot
    valuation = where.get('valuation_snapshot', '')
    if valuation:
        html += f'<p style="margin: 8px 0; color: #444;"><strong>Valuation:</strong> {valuation}</p>'

    if not html:
        html = '<p style="color: #999;">Not available.</p>'

    return _section_html('Where We Stand', html)


def _render_numbers_that_matter(synthesis, report_mode=None):
    """Render the 'Numbers That Matter' table with mode-aware column headers."""
    numbers = synthesis.get('numbers_that_matter', [])
    if not numbers:
        return _section_html('Numbers That Matter', '<p style="color: #999;">Not available.</p>')

    # Mode-aware column headers
    mode = report_mode.get('mode') if report_mode else None
    headers = NUMBERS_TABLE_HEADERS.get(mode, NUMBERS_TABLE_HEADERS['pre_earnings'])

    rows = ''
    for n in numbers:
        metric_label = n.get('metric', '')
        verified = n.get('verified', True)
        if not verified:
            metric_label += ' <span style="color: #dc3545; font-size: 11px; font-weight: bold;">[unverified]</span>'
        rows += f"""
        <tr>
            <td style="padding: 8px 10px; border-bottom: 1px solid #eee; font-weight: bold; color: #333;">{metric_label}</td>
            <td style="padding: 8px 10px; border-bottom: 1px solid #eee; text-align: center; color: #333;">{n.get('consensus_estimate', 'N/A')}</td>
            <td style="padding: 8px 10px; border-bottom: 1px solid #eee; color: #28a745; font-size: 13px;">{n.get('bullish_threshold', '')}</td>
            <td style="padding: 8px 10px; border-bottom: 1px solid #eee; color: #dc3545; font-size: 13px;">{n.get('bearish_threshold', '')}</td>
        </tr>"""

    table_html = f"""
    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        <tr style="background: #f8f9fa;">
            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Metric</th>
            <th style="padding: 10px; text-align: center; border-bottom: 2px solid #dee2e6; width: 140px;">{headers['col2']}</th>
            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">{headers['col3']}</th>
            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">{headers['col4']}</th>
        </tr>
        {rows}
    </table>"""

    # Add "why it matters" detail below the table
    detail_html = ''
    for n in numbers:
        why = n.get('why_it_matters', '')
        if why:
            detail_html += f'<p style="margin: 3px 0; font-size: 12px; color: #666;"><strong>{n.get("metric", "")}:</strong> {why}</p>'
    if detail_html:
        table_html += f'<div style="margin-top: 10px; padding: 8px 12px; background: #f8f9fa; border-radius: 4px;">{detail_html}</div>'

    return _section_html('Numbers That Matter', table_html)


def _render_signal_map(synthesis, report_mode=None):
    """Render the 'Signal Map' section with mode-aware intro.

    Handles both structured entries (dict with signal/evidence/source/verified)
    and legacy bare strings for backwards compatibility.
    """
    signal_map = synthesis.get('signal_map', {})
    if not signal_map:
        return _section_html('Signal Map', '<p style="color: #999;">Not available.</p>')

    mode = report_mode.get('mode') if report_mode else None
    intro = SIGNAL_MAP_INTROS.get(mode, SIGNAL_MAP_INTROS['pre_earnings'])
    html = f'<p style="margin: 0 0 10px; font-size: 13px; color: #666;">{intro}</p>'

    for category, color in SIGNAL_COLORS.items():
        signals = signal_map.get(category, [])
        if signals:
            label = category.title()
            icon = {'accelerating': '&#9650;', 'stalling': '&#9644;', 'inflecting': '&#9733;'}.get(category, '')
            html += f'<p style="margin: 10px 0 4px; font-weight: bold; color: {color};">{icon} {label}</p>'

            html += '<ul style="margin: 5px 0; padding-left: 20px;">'
            for entry in signals:
                if isinstance(entry, str):
                    # Legacy bare string
                    html += f'<li style="margin: 4px 0; color: {color}; line-height: 1.5;">{entry}</li>'
                elif isinstance(entry, dict):
                    signal = entry.get('signal', '')
                    evidence = entry.get('evidence', '')
                    verified = entry.get('verified', True)
                    unverified_tag = ' <span style="color: #dc3545; font-size: 11px; font-weight: bold;">[unverified]</span>' if not verified else ''
                    html += f'<li style="margin: 4px 0; color: {color}; line-height: 1.5;">{signal}{unverified_tag}'
                    if evidence:
                        html += f'<br><span style="font-size: 12px; color: #888; font-style: italic;">Evidence: {evidence}</span>'
                    html += '</li>'
            html += '</ul>'

    return _section_html('Signal Map', html)


def _render_risk_watchlist(synthesis):
    """Render the 'Risk Watchlist' section with muted checklist styling."""
    watchlist = synthesis.get('risk_watchlist', [])
    if not watchlist:
        return ''

    rows = ''
    for item in watchlist:
        rows += f"""
        <tr>
            <td style="padding: 6px 10px; border-bottom: 1px solid #eee; vertical-align: top;">
                <span style="color: #888; margin-right: 4px;">&#9744;</span>
                <strong style="color: #555;">{item.get('item', '')}</strong>
            </td>
            <td style="padding: 6px 10px; border-bottom: 1px solid #eee; color: #666; font-size: 13px; vertical-align: top;">
                {item.get('what_to_listen_for', '')}
            </td>
        </tr>
        <tr>
            <td colspan="2" style="padding: 2px 10px 8px 30px; font-size: 12px;">
                <span style="color: #dc3545;">If mentioned:</span> <span style="color: #666;">{item.get('signal_if_mentioned', '')}</span>
                &nbsp;&nbsp;|&nbsp;&nbsp;
                <span style="color: #28a745;">If absent:</span> <span style="color: #666;">{item.get('signal_if_absent', '')}</span>
            </td>
        </tr>"""

    html = f"""
    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        {rows}
    </table>"""

    return _section_html('Risk Watchlist', html)


def _render_market_context(external_context, timestamp):
    """Render market context data for the reference appendix."""
    if not external_context:
        return '<p style="color: #999;">No market data available.</p>'

    html = ''
    for ctx_key, ctx_data in external_context.items():
        if ctx_key == 'curve_shape':
            continue
        elif ctx_key == 'stock_quote':
            if isinstance(ctx_data, dict) and ctx_data.get('current_price'):
                price = float(ctx_data['current_price'])
                change = float(ctx_data.get('change', 0))
                change_pct = float(ctx_data.get('change_pct', 0))
                high = float(ctx_data.get('high', 0))
                low = float(ctx_data.get('low', 0))
                color = '#28a745' if change >= 0 else '#dc3545'
                arrow = '&#9650;' if change >= 0 else '&#9660;'
                sign = '+' if change >= 0 else ''
                html += f'<p style="margin: 3px 0;"><strong>Stock:</strong> ${price:.2f} {arrow} {sign}{change:.2f} ({sign}{change_pct:.1f}%) | Range: ${low:.2f} — ${high:.2f}</p>'
        elif ctx_key == 'analyst_data':
            if isinstance(ctx_data, dict):
                recs = ctx_data.get('recommendations', {})
                if recs:
                    total = recs.get('strong_buy', 0) + recs.get('buy', 0) + recs.get('hold', 0) + recs.get('sell', 0) + recs.get('strong_sell', 0)
                    html += f'<p style="margin: 3px 0;"><strong>Analysts ({total}):</strong> {recs.get("strong_buy", 0)} SB / {recs.get("buy", 0)} B / {recs.get("hold", 0)} H / {recs.get("sell", 0)} S / {recs.get("strong_sell", 0)} SS</p>'
        elif ctx_key == 'price_target':
            if isinstance(ctx_data, dict) and ctx_data.get('target_consensus'):
                consensus = ctx_data['target_consensus']
                low_t = ctx_data.get('target_low')
                high_t = ctx_data.get('target_high')
                source = ctx_data.get('source', '')
                range_str = f' (${low_t} — ${high_t})' if low_t and high_t else ''
                html += f'<p style="margin: 3px 0;"><strong>Price Target:</strong> ${consensus:.2f}{range_str} [{source}]</p>'
        elif ctx_key == 'consensus_estimates':
            if isinstance(ctx_data, dict):
                eps_ests = ctx_data.get('eps_estimates', [])
                rev_ests = ctx_data.get('revenue_estimates', [])
                source = ctx_data.get('source', '')
                if eps_ests:
                    next_q = eps_ests[0]
                    eps_val = next_q.get('eps_avg')
                    if eps_val is not None:
                        html += f'<p style="margin: 3px 0;"><strong>EPS Est:</strong> ${eps_val:.2f}'
                        if next_q.get('eps_low') is not None and next_q.get('eps_high') is not None:
                            html += f' (${next_q["eps_low"]:.2f} — ${next_q["eps_high"]:.2f})'
                        html += f' [{source}]</p>'
                if rev_ests:
                    next_q = rev_ests[0]
                    rev_val = next_q.get('revenue_avg')
                    if rev_val is not None:
                        if rev_val >= 1e9:
                            rev_str = f'${rev_val/1e9:.2f}B'
                        else:
                            rev_str = f'${rev_val/1e6:.0f}M'
                        html += f'<p style="margin: 3px 0;"><strong>Rev Est:</strong> {rev_str} [{source}]</p>'
        elif ctx_key == 'forward_curve':
            if isinstance(ctx_data, dict):
                curve_parts = []
                for tenor, data in ctx_data.items():
                    if data:
                        label = tenor.replace('_', ' ')
                        curve_parts.append(f'{label}: ${data.get("price", "N/A")}')
                if curve_parts:
                    html += f'<p style="margin: 3px 0;"><strong>Nat Gas Futures:</strong> {" | ".join(curve_parts)}</p>'
                    shape = external_context.get('curve_shape', '')
                    if shape:
                        html += f'<p style="margin: 3px 0;"><strong>Curve:</strong> {shape.title()}</p>'
        elif ctx_key == 'analyst_grades':
            if isinstance(ctx_data, dict) and ctx_data.get('grades'):
                grades = ctx_data['grades'][:3]
                grade_strs = [f'{g.get("firm", "")} → {g.get("new_grade", "")} ({g.get("date", "")})' for g in grades]
                html += f'<p style="margin: 3px 0;"><strong>Recent Grades:</strong> {" | ".join(grade_strs)}</p>'
        elif ctx_key == 'insider_activity':
            if isinstance(ctx_data, dict):
                count = ctx_data.get('count', 0)
                days = ctx_data.get('days_back', 90)
                html += f'<p style="margin: 3px 0;"><strong>Insider Activity:</strong> {count} Form 4s in {days}d</p>'
        elif isinstance(ctx_data, dict):
            display = ctx_data.get('display_name', ctx_key.replace('_', ' ').title())
            value = ctx_data.get('price', ctx_data.get('value', 'N/A'))
            unit = ctx_data.get('unit', '')
            ctx_date = ctx_data.get('date', '')
            if unit and unit.startswith('$/'):
                html += f'<p style="margin: 3px 0;"><strong>{display}:</strong> ${value}{unit[1:]} ({ctx_date})</p>'
            elif unit:
                html += f'<p style="margin: 3px 0;"><strong>{display}:</strong> {value} {unit} ({ctx_date})</p>'
            else:
                html += f'<p style="margin: 3px 0;"><strong>{display}:</strong> {value} ({ctx_date})</p>'

    return html or '<p style="color: #999;">No market data available.</p>'


def generate_intelligence_html(company, filing_info, synthesis, external_context, urgency='standard',
                               report_type='earnings_briefing', urgency_detail=None, thesis=None, report_mode=None):
    """
    Generate an IC Decision Brief HTML report.

    Args:
        company: dict with ticker, company_name
        filing_info: dict with filing_type, filing_date, accession_number
        synthesis: dict with IC briefing fields (from Claude)
        external_context: dict with market data
        urgency: string urgency level
        report_type: 'contrarian_alert', 'pre_earnings_brief', 'earnings_review', 'update', or legacy types
        urgency_detail: dict with scoring breakdown (optional)
        thesis: dict from company_theses table (optional)
        report_mode: dict from determine_report_mode() (optional)
    """
    ticker = company.get('ticker', '???')
    company_name = company.get('company_name', 'Unknown')
    filing_type = filing_info.get('filing_type', '')
    filing_date = filing_info.get('filing_date', '')
    accession = filing_info.get('accession_number', '')

    pacific = datetime.now(ZoneInfo('America/Los_Angeles'))
    tz_label = 'PDT' if pacific.dst() else 'PST'
    timestamp = f"{pacific.strftime('%Y-%m-%d %H:%M')} {tz_label}"

    # --- Build sections ---
    body_parts = []

    # 1. Header
    body_parts.append(_render_header(ticker, company_name, filing_type, filing_date, timestamp, report_type, urgency, report_mode=report_mode))

    # 2. Thesis review banner (amber, high visibility — before everything else)
    thesis_banner = _render_thesis_review_banner(synthesis)
    if thesis_banner:
        body_parts.append(thesis_banner)

    # 3. Contrarian callout (only for contrarian_alert)
    if report_type == 'contrarian_alert':
        callout = _render_contrarian_callout(synthesis)
        if callout:
            body_parts.append(callout)

    # === PAGE 1: WHERE WE STAND ===
    body_parts.append(_render_where_we_stand(synthesis, thesis=thesis))

    # === PAGE 2: WHAT TO LISTEN FOR ===
    body_parts.append(_render_numbers_that_matter(synthesis, report_mode=report_mode))
    body_parts.append(_render_signal_map(synthesis, report_mode=report_mode))
    body_parts.append(_render_risk_watchlist(synthesis))

    # === REFERENCE APPENDIX ===
    ref = synthesis.get('reference_analysis', {})
    appendix_divider = """
    <tr><td style="padding: 20px 30px 5px;">
        <hr style="border: none; border-top: 3px solid #dee2e6; margin: 0;">
        <p style="margin: 8px 0 0; font-size: 12px; color: #999; text-transform: uppercase; letter-spacing: 1px;">Reference Appendix</p>
    </td></tr>"""
    body_parts.append(appendix_divider)

    # Reference analysis summaries
    for key, label in [('financial_summary', 'Financial'), ('operational_summary', 'Operational'),
                       ('strategic_summary', 'Strategic'), ('peer_comparison', 'Peer Comparison')]:
        val = ref.get(key, '')
        if val:
            body_parts.append(_muted_section_html(label, f'<p style="margin: 0;">{val}</p>'))

    # Market context
    market_html = _render_market_context(external_context, timestamp)
    body_parts.append(_muted_section_html(f'Market Data ({timestamp})', market_html))

    # Footer
    body_parts.append(f"""
    <tr><td style="padding: 15px 30px; background: #f0f0f0; border-top: 1px solid #ddd;">
        <p style="margin: 0; font-size: 11px; color: #999;">
            Generated {timestamp} | Source: {filing_type} {filing_date} ({accession}) | Powered by Claude
        </p>
    </td></tr>""")

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{ticker} IC Decision Brief</title></head>
<body style="margin: 0; padding: 0; font-family: Arial, Helvetica, sans-serif; background: #f5f5f5;">
<table style="width: 100%; max-width: 700px; margin: 0 auto; background: #ffffff;" cellpadding="0" cellspacing="0">
    {''.join(body_parts)}
</table>
</body>
</html>"""

    return html
