#!/usr/bin/env python3
"""
Stage 4: Differential Analysis
Compare filings over time to identify changes and trends
"""

import os
import json
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import anthropic

# Configuration
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'sec_filings'),
    'user': os.getenv('POSTGRES_USER', 'sec_user'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

# Anthropic API
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

MODEL = "claude-sonnet-4-20250514"

def connect_db():
    """Connect to PostgreSQL"""
    try:
        return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return None

def get_comparable_filings(conn, ticker):
    """Get pairs of filings to compare (YoY for 10-K/10-Q)"""
    cursor = conn.cursor()
    
    # Get 10-K filings for YoY comparison
    cursor.execute("""
        SELECT f.id, f.filing_type, f.filing_date, f.accession_number
        FROM filings f
        JOIN companies c ON f.company_id = c.id
        WHERE c.ticker = %s 
        AND f.filing_type = '10-K'
        AND f.processed = TRUE
        ORDER BY f.filing_date DESC
    """, (ticker,))
    
    annual_filings = cursor.fetchall()
    
    # Get 10-Q filings by quarter for YoY comparison
    cursor.execute("""
        SELECT f.id, f.filing_type, f.filing_date, f.accession_number,
               EXTRACT(QUARTER FROM f.filing_date) as quarter,
               EXTRACT(YEAR FROM f.filing_date) as year
        FROM filings f
        JOIN companies c ON f.company_id = c.id
        WHERE c.ticker = %s 
        AND f.filing_type = '10-Q'
        AND f.processed = TRUE
        ORDER BY f.filing_date DESC
    """, (ticker,))
    
    quarterly_filings = cursor.fetchall()
    cursor.close()
    
    # Create comparison pairs
    comparison_pairs = []
    
    # YoY 10-K comparisons
    for i in range(len(annual_filings) - 1):
        comparison_pairs.append({
            'type': '10-K YoY',
            'current': annual_filings[i],
            'previous': annual_filings[i + 1],
            'comparison': 'Year-over-Year'
        })
    
    # YoY 10-Q comparisons (same quarter, different year)
    quarters = {}
    for filing in quarterly_filings:
        q = filing['quarter']
        y = filing['year']
        if q not in quarters:
            quarters[q] = []
        quarters[q].append(filing)
    
    for quarter, filings in quarters.items():
        filings_sorted = sorted(filings, key=lambda x: x['year'], reverse=True)
        for i in range(len(filings_sorted) - 1):
            comparison_pairs.append({
                'type': f'10-Q Q{int(quarter)} YoY',
                'current': filings_sorted[i],
                'previous': filings_sorted[i + 1],
                'comparison': 'Year-over-Year'
            })
    
    return comparison_pairs

def get_filing_metrics(conn, filing_id):
    """Get all metrics for a filing"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT metric_name, metric_value, metric_unit, metric_period, extraction_confidence
        FROM extracted_metrics
        WHERE filing_id = %s
        ORDER BY metric_name
    """, (filing_id,))
    metrics = cursor.fetchall()
    cursor.close()
    return metrics

def get_filing_risks(conn, filing_id):
    """Get risk factors for a filing"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT risk_category, risk_description, materiality, change_type
        FROM risk_factors
        WHERE filing_id = %s
        ORDER BY materiality DESC
    """, (filing_id,))
    risks = cursor.fetchall()
    cursor.close()
    return risks

def get_filing_statements(conn, filing_id):
    """Get forward-looking statements for a filing"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT statement_category, statement_text, timeframe, confidence_level, 
               quantitative_value, value_unit
        FROM forward_statements
        WHERE filing_id = %s
        ORDER BY statement_category
    """, (filing_id,))
    statements = cursor.fetchall()
    cursor.close()
    return statements

def analyze_metric_changes(current_metrics, previous_metrics):
    """Compare metrics between two filings"""
    
    # Convert to dicts for easier comparison
    current_dict = {m['metric_name']: m for m in current_metrics}
    previous_dict = {m['metric_name']: m for m in previous_metrics}
    
    changes = {
        'new_metrics': [],
        'removed_metrics': [],
        'changed_metrics': [],
        'unchanged_metrics': []
    }
    
    # Find new, removed, and changed metrics
    for name, current in current_dict.items():
        if name not in previous_dict:
            changes['new_metrics'].append(current)
        else:
            previous = previous_dict[name]
            # Convert Decimal to float for comparison
            current_val = float(current['metric_value']) if current['metric_value'] is not None else None
            previous_val = float(previous['metric_value']) if previous['metric_value'] is not None else None
            
            if current_val != previous_val:
                pct_change = None
                if previous_val and previous_val != 0:
                    pct_change = ((current_val - previous_val) / abs(previous_val)) * 100
                
                changes['changed_metrics'].append({
                    'name': name,
                    'current_value': current_val,
                    'previous_value': previous_val,
                    'change': current_val - previous_val if current_val and previous_val else None,
                    'pct_change': round(pct_change, 2) if pct_change else None,
                    'unit': current['metric_unit']
                })
            else:
                changes['unchanged_metrics'].append(name)
    
    for name in previous_dict:
        if name not in current_dict:
            changes['removed_metrics'].append(previous_dict[name])
    
    return changes

def generate_differential_report(conn, comparison):
    """Generate differential analysis report using Claude"""
    
    current_filing = comparison['current']
    previous_filing = comparison['previous']
    
    print(f"\n{'='*70}")
    print(f"Differential Analysis: {comparison['type']}")
    print(f"Current:  {current_filing['filing_date']} ({current_filing['accession_number']})")
    print(f"Previous: {previous_filing['filing_date']} ({previous_filing['accession_number']})")
    print(f"{'='*70}")
    
    # Get data for both filings
    current_metrics = get_filing_metrics(conn, current_filing['id'])
    previous_metrics = get_filing_metrics(conn, previous_filing['id'])
    
    current_risks = get_filing_risks(conn, current_filing['id'])
    previous_risks = get_filing_risks(conn, previous_filing['id'])
    
    current_statements = get_filing_statements(conn, current_filing['id'])
    previous_statements = get_filing_statements(conn, previous_filing['id'])
    
    print(f"\nData Summary:")
    print(f"  Current:  {len(current_metrics)} metrics, {len(current_risks)} risks, {len(current_statements)} statements")
    print(f"  Previous: {len(previous_metrics)} metrics, {len(previous_risks)} risks, {len(previous_statements)} statements")
    
    # Analyze metric changes
    metric_changes = analyze_metric_changes(current_metrics, previous_metrics)
    
    print(f"\nMetric Changes:")
    print(f"  New: {len(metric_changes['new_metrics'])}")
    print(f"  Removed: {len(metric_changes['removed_metrics'])}")
    print(f"  Changed: {len(metric_changes['changed_metrics'])}")
    print(f"  Unchanged: {len(metric_changes['unchanged_metrics'])}")
    
    # Prepare data for Claude
    analysis_data = {
        'comparison_type': comparison['type'],
        'current_date': str(current_filing['filing_date']),
        'previous_date': str(previous_filing['filing_date']),
        'metric_changes': {
            'changed': metric_changes['changed_metrics'][:20],  # Top 20 changes
            'new': [m['metric_name'] for m in metric_changes['new_metrics']],
            'removed': [m['metric_name'] for m in metric_changes['removed_metrics']]
        },
        'current_risks': [{'category': r['risk_category'], 'materiality': r['materiality'], 
                          'description': r['risk_description'][:200]} for r in current_risks],
        'previous_risks': [{'category': r['risk_category'], 'materiality': r['materiality'],
                           'description': r['risk_description'][:200]} for r in previous_risks],
        'current_statements': [{'category': s['statement_category'], 'timeframe': s['timeframe'],
                               'statement': s['statement_text'][:200]} for s in current_statements],
        'previous_statements': [{'category': s['statement_category'], 'timeframe': s['timeframe'],
                                'statement': s['statement_text'][:200]} for s in previous_statements]
    }
    
    # Call Claude for differential analysis
    print("\n→ Generating differential analysis with Claude...")
    
    # Look up company name
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.company_name FROM companies c
        JOIN filings f ON f.company_id = c.id
        WHERE f.id = %s
    """, (current_filing['id'],))
    company_row = cursor.fetchone()
    company_name = company_row['company_name'] if company_row else 'Unknown Company'
    cursor.close()

    prompt = f"""You are analyzing SEC filings for {company_name} to identify material changes.

COMPARISON TYPE: {comparison['type']}
CURRENT FILING: {current_filing['filing_date']}
PREVIOUS FILING: {previous_filing['filing_date']}

FINANCIAL METRIC CHANGES:
{json.dumps(analysis_data['metric_changes'], indent=2)}

CURRENT RISK FACTORS:
{json.dumps(analysis_data['current_risks'], indent=2)}

PREVIOUS RISK FACTORS:
{json.dumps(analysis_data['previous_risks'], indent=2)}

CURRENT FORWARD STATEMENTS:
{json.dumps(analysis_data['current_statements'], indent=2)}

PREVIOUS FORWARD STATEMENTS:
{json.dumps(analysis_data['previous_statements'], indent=2)}

Provide a comprehensive differential analysis in JSON format:

{{
  "executive_summary": "2-3 sentence summary of the most important changes",
  "key_changes": [
    {{
      "category": "string (Financial, Operational, Risk, Strategic)",
      "finding": "string (concise description of change)",
      "materiality": "string (High, Medium, Low)",
      "direction": "string (Positive, Negative, Neutral)"
    }}
  ],
  "financial_analysis": {{
    "revenue_trend": "string",
    "profitability_trend": "string",
    "cash_flow_trend": "string",
    "notable_changes": ["list of specific metric changes"]
  }},
  "risk_assessment": {{
    "new_risks": ["list of new risk categories"],
    "elevated_risks": ["risks that increased in severity"],
    "mitigated_risks": ["risks that decreased or were removed"],
    "overall_risk_direction": "string (Increasing, Stable, Decreasing)"
  }},
  "strategic_shifts": {{
    "guidance_changes": ["changes in forward guidance"],
    "capital_allocation_changes": ["changes in capex, debt, etc."],
    "operational_changes": ["production, drilling, etc."]
  }},
  "red_flags": ["concerning trends or unexpected changes"],
  "opportunities": ["positive developments or improvements"],
  "materiality_score": "string (1-10, where 10 is most material)"
}}

Focus on:
- Material changes (>10% for metrics)
- New or removed risks
- Guidance updates
- Strategic direction changes
- Unexpected items

Return ONLY valid JSON, no other text."""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        result_text = response.content[0].text.strip()
        
        # Remove markdown code blocks if present
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        analysis = json.loads(result_text)
        
        print("✓ Differential analysis complete")
        
        return analysis
    
    except Exception as e:
        print(f"✗ Error in differential analysis: {e}")
        return None

def save_differential_report(conn, current_filing_id, previous_filing_id, analysis):
    """Save differential analysis to intelligence_reports table"""
    
    cursor = conn.cursor()
    
    # Prepare report data
    executive_summary = analysis.get('executive_summary', '')
    key_insights = json.dumps(analysis.get('key_changes', []))
    financial_analysis = json.dumps(analysis.get('financial_analysis', {}))
    risk_assessment = json.dumps(analysis.get('risk_assessment', {}))
    strategic_assessment = json.dumps(analysis.get('strategic_shifts', {}))
    risks_opportunities = json.dumps({
        'red_flags': analysis.get('red_flags', []),
        'opportunities': analysis.get('opportunities', [])
    })
    materiality = 'high' if int(analysis.get('materiality_score', 5)) >= 7 else 'medium' if int(analysis.get('materiality_score', 5)) >= 4 else 'low'
    
    # Generate HTML report
    full_report_html = f"""
    <html>
    <head><title>Differential Analysis Report</title></head>
    <body>
    <h1>Differential Analysis</h1>
    <h2>Executive Summary</h2>
    <p>{executive_summary}</p>
    
    <h2>Key Changes</h2>
    <ul>
    {''.join([f'<li><strong>{c.get("category")}</strong>: {c.get("finding")} (Materiality: {c.get("materiality")}, Direction: {c.get("direction")})</li>' for c in analysis.get('key_changes', [])])}
    </ul>
    
    <h2>Financial Analysis</h2>
    <pre>{json.dumps(analysis.get('financial_analysis', {}), indent=2)}</pre>
    
    <h2>Risk Assessment</h2>
    <pre>{json.dumps(analysis.get('risk_assessment', {}), indent=2)}</pre>
    
    <h2>Strategic Shifts</h2>
    <pre>{json.dumps(analysis.get('strategic_shifts', {}), indent=2)}</pre>
    
    <h2>Red Flags</h2>
    <ul>
    {''.join([f'<li>{flag}</li>' for flag in analysis.get('red_flags', [])])}
    </ul>
    
    <h2>Opportunities</h2>
    <ul>
    {''.join([f'<li>{opp}</li>' for opp in analysis.get('opportunities', [])])}
    </ul>
    </body>
    </html>
    """
    
    # Insert report
    cursor.execute("""
        INSERT INTO intelligence_reports 
        (filing_id, executive_summary, key_insights, financial_analysis, 
         operational_analysis, strategic_assessment, risks_opportunities, 
         full_report_html, materiality, urgency)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        current_filing_id,
        executive_summary,
        key_insights,
        financial_analysis,
        '',  # operational_analysis (could extract from strategic_shifts)
        strategic_assessment,
        risks_opportunities,
        full_report_html,
        materiality,
        'standard'
    ))
    
    report_id = cursor.fetchone()['id']
    conn.commit()
    cursor.close()
    
    return report_id

def display_analysis_summary(analysis):
    """Display analysis summary to console"""
    
    print(f"\n{'='*70}")
    print("DIFFERENTIAL ANALYSIS RESULTS")
    print(f"{'='*70}")
    
    print(f"\n📊 Executive Summary:")
    print(f"  {analysis.get('executive_summary', 'N/A')}")
    
    print(f"\n🔍 Key Changes ({len(analysis.get('key_changes', []))}):")
    for change in analysis.get('key_changes', [])[:5]:  # Top 5
        print(f"  [{change.get('materiality')}] {change.get('category')}: {change.get('finding')}")
    
    print(f"\n⚠️  Red Flags ({len(analysis.get('red_flags', []))}):")
    for flag in analysis.get('red_flags', []):
        print(f"  - {flag}")
    
    print(f"\n✅ Opportunities ({len(analysis.get('opportunities', []))}):")
    for opp in analysis.get('opportunities', []):
        print(f"  - {opp}")
    
    print(f"\n📈 Materiality Score: {analysis.get('materiality_score', 'N/A')}/10")
    print(f"{'='*70}")

def main():
    """Main execution"""
    print("="*70)
    print("STAGE 4: DIFFERENTIAL ANALYSIS")
    print("="*70)
    
    # Check API key
    if not ANTHROPIC_API_KEY:
        print("\n✗ Error: ANTHROPIC_API_KEY not set")
        return
    
    # Connect to database
    print("\nConnecting to database...")
    conn = connect_db()
    if not conn:
        return
    print("✓ Connected")
    
    # Determine which tickers to process
    import sys
    ticker_arg = None
    for i, arg in enumerate(sys.argv):
        if arg == '--ticker' and i + 1 < len(sys.argv):
            ticker_arg = sys.argv[i + 1]

    if ticker_arg:
        tickers = [ticker_arg]
    else:
        # Default: all active primary companies
        from psycopg2.extras import RealDictCursor as RDC
        cur = conn.cursor()
        cur.execute("SELECT ticker FROM companies WHERE active = TRUE AND watchlist_priority = 'primary' ORDER BY ticker")
        tickers = [row['ticker'] for row in cur.fetchall()]
        cur.close()
        if not tickers:
            tickers = ['EQT']  # fallback

    # Get comparable filings
    print("\nIdentifying comparable filings...")
    comparisons = []
    for t in tickers:
        comparisons.extend(get_comparable_filings(conn, t))
    
    if not comparisons:
        print("✓ No comparable filings found (need at least 2 filings of same type)")
        conn.close()
        return
    
    print(f"✓ Found {len(comparisons)} filing comparisons to analyze\n")
    
    # Process each comparison
    reports_generated = 0
    
    for comparison in comparisons:
        analysis = generate_differential_report(conn, comparison)
        
        if analysis:
            # Save to database
            report_id = save_differential_report(
                conn,
                comparison['current']['id'],
                comparison['previous']['id'],
                analysis
            )
            
            # Display summary
            display_analysis_summary(analysis)
            
            reports_generated += 1
            print(f"\n✓ Report saved (ID: {report_id})")
    
    # Summary
    print(f"\n{'='*70}")
    print(f"DIFFERENTIAL ANALYSIS COMPLETE")
    print(f"{'='*70}")
    print(f"Reports Generated: {reports_generated}")
    print(f"{'='*70}")
    
    conn.close()

if __name__ == "__main__":
    main()
