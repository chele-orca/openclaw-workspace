#!/usr/bin/env python3
"""
Stage 3: Structured Data Extraction with Claude
Extract financial metrics, risk factors, and forward-looking statements
"""

import os
import json
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values
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

# Claude model
MODEL = "claude-sonnet-4-20250514"

def connect_db():
    """Connect to PostgreSQL"""
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return None

def get_filing_info(conn, filing_id):
    """Get filing metadata"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.filing_type, f.filing_date, f.accession_number, c.company_name
        FROM filings f
        JOIN companies c ON f.company_id = c.id
        WHERE f.id = %s
    """, (filing_id,))
    result = cursor.fetchone()
    cursor.close()
    return result

def get_chunks_for_extraction(conn, filing_id, section_name):
    """Get chunks for a specific section"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, content, token_count
        FROM chunks
        WHERE filing_id = %s AND section_name = %s
        ORDER BY chunk_index
    """, (filing_id, section_name))
    results = cursor.fetchall()
    cursor.close()
    return results

def extract_financial_metrics(company_name, filing_type, filing_date, content):
    """Use Claude to extract financial metrics from content"""
    
    prompt = f"""You are a financial analyst extracting structured data from SEC filings.

Company: {company_name}
Filing Type: {filing_type}
Filing Date: {filing_date}

Extract financial and operational metrics from this section. Focus on quantitative data.

Section Content:
{content}

Return a JSON object with this structure:
{{
  "metrics": [
    {{
      "metric_name": "string (e.g., 'Revenue', 'Net Income', 'Production Volume')",
      "metric_value": number (numeric value only),
      "metric_unit": "string (e.g., 'USD millions', 'Bcf', 'MMBtu')",
      "metric_period": "string (e.g., 'Q3 2025', 'FY 2024', 'YTD 2025')",
      "confidence": number (0.0 to 1.0, how confident you are in this extraction)
    }}
  ]
}}

Guidelines:
- Only extract metrics that are explicitly stated with numbers
- For natural gas companies, focus on: production volumes, reserves, hedging positions, revenue, income, cash flow, capex, debt
- If no clear metrics found, return empty array
- Be conservative - only include data you're confident about
- Convert all values to consistent units where possible

Return ONLY valid JSON, no other text."""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse response
        result_text = response.content[0].text.strip()
        
        # Remove markdown code blocks if present
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        result = json.loads(result_text)
        return result.get('metrics', [])
    
    except Exception as e:
        print(f"    ✗ Error in Claude API call: {e}")
        return []

def extract_risk_factors(company_name, filing_type, filing_date, content, previous_risks=None):
    """Use Claude to analyze risk factors"""
    
    previous_context = ""
    if previous_risks:
        previous_context = f"\n\nPrevious filing's risk factors for comparison:\n{json.dumps(previous_risks, indent=2)}"
    
    prompt = f"""You are a financial analyst analyzing risk factors in SEC filings.

Company: {company_name}
Filing Type: {filing_type}
Filing Date: {filing_date}

Analyze the risk factors section and identify key risks.{previous_context}

Risk Factors Content:
{content}

Return a JSON object with this structure:
{{
  "risks": [
    {{
      "risk_category": "string (e.g., 'Market Risk', 'Operational Risk', 'Regulatory Risk')",
      "risk_description": "string (concise summary of the risk)",
      "change_type": "string ('new', 'modified', 'unchanged', or 'removed' if comparing to previous)",
      "materiality": "string ('high', 'medium', 'low')"
    }}
  ]
}}

Guidelines:
- Identify 3-7 most material risks
- Categorize each risk appropriately
- If previous risks provided, identify what changed
- Focus on business-specific risks, not generic boilerplate
- Assess materiality based on emphasis and detail in the filing

Return ONLY valid JSON, no other text."""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        result_text = response.content[0].text.strip()
        
        # Remove markdown code blocks if present
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        result = json.loads(result_text)
        return result.get('risks', [])
    
    except Exception as e:
        print(f"    ✗ Error in Claude API call: {e}")
        return []

def extract_forward_statements(company_name, filing_type, filing_date, content):
    """Use Claude to extract forward-looking statements and guidance"""
    
    prompt = f"""You are a financial analyst extracting forward-looking statements from SEC filings.

Company: {company_name}
Filing Type: {filing_type}
Filing Date: {filing_date}

Extract forward-looking statements, guidance, and strategic plans from this content.

MD&A Content:
{content}

Return a JSON object with this structure:
{{
  "statements": [
    {{
      "category": "string (e.g., 'production_guidance', 'capex_plan', 'debt_reduction', 'strategic_initiative')",
      "statement": "string (the forward-looking statement)",
      "timeframe": "string (when this applies, e.g., '2025', 'Q1 2026', 'next 3 years')",
      "quantitative_value": number or null (if statement includes specific target),
      "value_unit": "string or null (unit for quantitative value)",
      "confidence": "string ('high', 'medium', 'low' - based on language certainty)"
    }}
  ]
}}

Guidelines:
- Focus on actionable guidance and specific plans
- Look for: production targets, capital expenditure plans, debt targets, M&A intentions, strategic initiatives
- Note the certainty of language (e.g., "will" vs "may" vs "exploring")
- Extract specific numbers where provided
- Ignore generic or vague statements

Return ONLY valid JSON, no other text."""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        result_text = response.content[0].text.strip()
        
        # Remove markdown code blocks if present
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        result = json.loads(result_text)
        return result.get('statements', [])
    
    except Exception as e:
        print(f"    ✗ Error in Claude API call: {e}")
        return []

def save_metrics_to_db(conn, filing_id, metrics, section_name):
    """Save extracted metrics to database"""
    if not metrics:
        return 0
    
    cursor = conn.cursor()
    
    records = [
        (
            filing_id,
            m['metric_name'],
            m.get('metric_value'),
            m.get('metric_unit'),
            m.get('metric_period'),
            section_name,
            m.get('confidence', 0.8)
        )
        for m in metrics
    ]
    
    insert_query = """
        INSERT INTO extracted_metrics 
        (filing_id, metric_name, metric_value, metric_unit, metric_period, section_name, extraction_confidence)
        VALUES %s
    """
    
    execute_values(cursor, insert_query, records)
    conn.commit()
    cursor.close()
    
    return len(records)

def save_risks_to_db(conn, filing_id, risks, previous_filing_id=None):
    """Save risk factors to database"""
    if not risks:
        return 0
    
    cursor = conn.cursor()
    
    records = [
        (
            filing_id,
            r.get('risk_category'),
            r['risk_description'],
            r.get('change_type', 'unchanged'),
            r.get('materiality', 'medium'),
            previous_filing_id
        )
        for r in risks
    ]
    
    insert_query = """
        INSERT INTO risk_factors 
        (filing_id, risk_category, risk_description, change_type, materiality, previous_filing_id)
        VALUES %s
    """
    
    execute_values(cursor, insert_query, records)
    conn.commit()
    cursor.close()
    
    return len(records)

def save_forward_statements_to_db(conn, filing_id, statements):
    """Save forward-looking statements to database"""
    if not statements:
        return 0
    
    cursor = conn.cursor()
    
    records = [
        (
            filing_id,
            s.get('category'),
            s['statement'],
            s.get('timeframe'),
            s.get('confidence', 'medium'),
            s.get('quantitative_value'),
            s.get('value_unit')
        )
        for s in statements
    ]
    
    insert_query = """
        INSERT INTO forward_statements 
        (filing_id, statement_category, statement_text, timeframe, confidence_level, quantitative_value, value_unit)
        VALUES %s
    """
    
    execute_values(cursor, insert_query, records)
    conn.commit()
    cursor.close()
    
    return len(records)

def process_filing_for_extraction(conn, filing_id):
    """Process a single filing through all extraction steps"""
    
    # Get filing info
    filing_info = get_filing_info(conn, filing_id)
    if not filing_info:
        print(f"✗ Filing {filing_id} not found")
        return
    
    filing_type, filing_date, accession_number, company_name = filing_info
    
    print(f"\n{'='*70}")
    print(f"Extracting from: {filing_type} - {filing_date} ({company_name})")
    print(f"Accession: {accession_number}")
    print(f"{'='*70}")
    
    total_metrics = 0
    total_risks = 0
    total_statements = 0
    
    # 1. Extract Financial Metrics (from Financial Statements and MD&A)
    print("\n→ Extracting Financial Metrics...")
    for section in ['Item 8: Financial Statements', 'Item 7: MD&A', 'Item 2: MD&A', 'Item 1: Financial Statements']:
        chunks = get_chunks_for_extraction(conn, filing_id, section)
        if chunks:
            print(f"  Processing: {section} ({len(chunks)} chunks)")
            for chunk_id, content, token_count in chunks:
                metrics = extract_financial_metrics(company_name, filing_type, filing_date, content)
                if metrics:
                    saved = save_metrics_to_db(conn, filing_id, metrics, section)
                    total_metrics += saved
                    print(f"    ✓ Extracted {saved} metrics")
    
    print(f"  ✓ Total metrics extracted: {total_metrics}")
    
    # 2. Extract Risk Factors
    print("\n→ Analyzing Risk Factors...")
    chunks = get_chunks_for_extraction(conn, filing_id, 'Item 1A: Risk Factors')
    if chunks:
        print(f"  Processing: Item 1A: Risk Factors ({len(chunks)} chunks)")
        # Combine all chunks for risk analysis
        combined_content = "\n\n".join([content for _, content, _ in chunks])
        
        # TODO: Get previous filing's risks for comparison
        risks = extract_risk_factors(company_name, filing_type, filing_date, combined_content)
        if risks:
            saved = save_risks_to_db(conn, filing_id, risks)
            total_risks += saved
            print(f"    ✓ Extracted {saved} risk factors")
    
    print(f"  ✓ Total risks extracted: {total_risks}")
    
    # 3. Extract Forward-Looking Statements (from MD&A)
    print("\n→ Extracting Forward-Looking Statements...")
    for section in ['Item 7: MD&A', 'Item 2: MD&A']:
        chunks = get_chunks_for_extraction(conn, filing_id, section)
        if chunks:
            print(f"  Processing: {section} ({len(chunks)} chunks)")
            # Combine chunks for forward statement analysis
            combined_content = "\n\n".join([content for _, content, _ in chunks])
            
            statements = extract_forward_statements(company_name, filing_type, filing_date, combined_content)
            if statements:
                saved = save_forward_statements_to_db(conn, filing_id, statements)
                total_statements += saved
                print(f"    ✓ Extracted {saved} forward-looking statements")
    
    print(f"  ✓ Total forward statements extracted: {total_statements}")
    
    print(f"\n{'='*70}")
    print(f"Extraction Summary for {filing_type}:")
    print(f"  - Metrics: {total_metrics}")
    print(f"  - Risks: {total_risks}")
    print(f"  - Forward Statements: {total_statements}")
    print(f"{'='*70}")

def get_processed_filings(conn):
    """Get filings that have been chunked but not yet extracted"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT f.id, f.filing_type, f.filing_date
        FROM filings f
        WHERE f.processed = TRUE
        AND f.id IN (SELECT DISTINCT filing_id FROM chunks)
        ORDER BY f.filing_date ASC
    """)
    results = cursor.fetchall()
    cursor.close()
    return results

def generate_extraction_summary(conn):
    """Generate summary of extraction results"""
    cursor = conn.cursor()
    
    print("\n" + "="*70)
    print("EXTRACTION SUMMARY")
    print("="*70)
    
    # Metrics by filing
    cursor.execute("""
        SELECT f.filing_type, f.filing_date, COUNT(m.id) as metric_count
        FROM filings f
        LEFT JOIN extracted_metrics m ON f.id = m.filing_id
        WHERE f.id IN (SELECT DISTINCT filing_id FROM chunks)
        GROUP BY f.id, f.filing_type, f.filing_date
        ORDER BY f.filing_date DESC
    """)
    
    print("\nMetrics Extracted by Filing:")
    print("-"*70)
    for filing_type, filing_date, count in cursor.fetchall():
        print(f"  {filing_type:10s} {filing_date} : {count:3d} metrics")
    
    # Overall totals
    cursor.execute("SELECT COUNT(*) FROM extracted_metrics")
    total_metrics = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM risk_factors")
    total_risks = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM forward_statements")
    total_statements = cursor.fetchone()[0]
    
    print("-"*70)
    print(f"  Total Metrics:            {total_metrics}")
    print(f"  Total Risk Factors:       {total_risks}")
    print(f"  Total Forward Statements: {total_statements}")
    print("="*70)
    
    cursor.close()

def main():
    """Main execution"""
    print("="*70)
    print("STAGE 3: STRUCTURED DATA EXTRACTION WITH CLAUDE")
    print("="*70)
    
    # Check API key
    if not ANTHROPIC_API_KEY:
        print("\n✗ Error: ANTHROPIC_API_KEY not set in environment")
        print("  Add to your .env file or set as environment variable")
        return
    
    # Connect to database
    print("\nConnecting to database...")
    conn = connect_db()
    if not conn:
        return
    print("✓ Connected")
    
    # Get filings to process
    print("\nFetching processed filings...")
    filings = get_processed_filings(conn)
    
    if not filings:
        print("✓ No processed filings found")
        print("  Run process_filings.py first")
        conn.close()
        return
    
    print(f"✓ Found {len(filings)} filings ready for extraction\n")
    
    # Process each filing
    for filing_id, filing_type, filing_date in filings:
        process_filing_for_extraction(conn, filing_id)
    
    # Generate summary
    generate_extraction_summary(conn)
    
    # Close connection
    conn.close()
    print("\n✓ Extraction complete")

if __name__ == "__main__":
    main()