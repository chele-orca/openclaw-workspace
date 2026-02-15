#!/usr/bin/env python3
"""
Fetch SEC filings metadata for any company from EDGAR API.
Generalized from the original fetch_eqt_filings.py.

Usage:
    python fetch_filings.py --ticker EQT
    python fetch_filings.py --all

SEC EDGAR Compliance:
- User-Agent with contact email (required)
- Rate limit: 10 requests/second (we only make 1 request per company)
- Proper CIK padding to 10 digits
"""

import sys
import os
import requests
import json
from datetime import datetime, timedelta
from collections import Counter
from pathlib import Path
from config import connect_db

# Project root: parent of scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Configuration
SEC_API_BASE = "https://data.sec.gov"
USER_AGENT = "MacMini Analysis tbjohnston@gmail.com"

# Date range: last 26 months
end_date = datetime.now()
start_date = end_date - timedelta(days=26 * 30)


def fetch_company_filings(cik, company_name):
    """Fetch filings from SEC EDGAR API for a given CIK."""
    padded_cik = cik.zfill(10)
    print(f"Fetching {company_name} SEC filings from {start_date.date()} to {end_date.date()}...")
    print(f"Using CIK: {padded_cik}\n")

    url = f"{SEC_API_BASE}/submissions/CIK{padded_cik}.json"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Host": "data.sec.gov"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        print("✓ Successfully fetched data from SEC API\n")
        return data
    except requests.exceptions.RequestException as e:
        print(f"✗ Error fetching data from SEC API: {e}")
        return None


def filter_filings(data):
    """Filter filings within date range."""
    recent_filings = data.get('filings', {}).get('recent', {})

    filing_dates = recent_filings.get('filingDate', [])
    form_types = recent_filings.get('form', [])
    accession_numbers = recent_filings.get('accessionNumber', [])
    primary_documents = recent_filings.get('primaryDocument', [])
    primary_doc_descriptions = recent_filings.get('primaryDocDescription', [])

    filtered = []
    for i in range(len(filing_dates)):
        filing_date = datetime.strptime(filing_dates[i], '%Y-%m-%d')
        if start_date <= filing_date <= end_date:
            filtered.append({
                'filingDate': filing_dates[i],
                'form': form_types[i],
                'accessionNumber': accession_numbers[i],
                'primaryDocument': primary_documents[i],
                'primaryDocDescription': primary_doc_descriptions[i] if i < len(primary_doc_descriptions) else ''
            })

    print(f"✓ Filtered {len(filtered)} filings within date range\n")
    return filtered


def save_json(data, filtered_filings, ticker):
    """Save filings metadata to JSON file."""
    output_data = {
        'metadata': {
            'company': data.get('name'),
            'ticker': ticker,
            'cik': data.get('cik'),
            'sic': data.get('sic'),
            'sicDescription': data.get('sicDescription'),
            'ein': data.get('ein'),
            'stateOfIncorporation': data.get('stateOfIncorporation'),
            'fiscalYearEnd': data.get('fiscalYearEnd'),
            'query_date': end_date.strftime('%Y-%m-%d'),
            'date_range': {
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d')
            },
            'total_filings': len(filtered_filings)
        },
        'filings': filtered_filings
    }

    output_path = str(PROJECT_ROOT / 'sec-data' / f'{ticker.lower()}_filings_26mo.json')
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"✓ Saved to {output_path}\n")
    return output_data


def print_summary(output_data, ticker):
    """Print filing summary."""
    metadata = output_data['metadata']
    filings = output_data['filings']
    form_counts = Counter([f['form'] for f in filings])

    print("=" * 70)
    print(f"{ticker} SEC FILINGS SUMMARY")
    print("=" * 70)
    print(f"Company:          {metadata['company']}")
    print(f"CIK:              {metadata['cik']}")
    print(f"SIC:              {metadata['sic']} - {metadata['sicDescription']}")
    print(f"Date Range:       {metadata['date_range']['start']} to {metadata['date_range']['end']}")
    print(f"Total Filings:    {metadata['total_filings']}")
    print("-" * 70)
    for form_type, count in sorted(form_counts.items(), key=lambda x: (-x[1], x[0])):
        pct = (count / metadata['total_filings']) * 100
        print(f"  {form_type:20s} : {count:3d} filings ({pct:5.1f}%)")
    print("=" * 70)


def process_company(ticker, cik, company_name):
    """Run the full fetch pipeline for one company."""
    data = fetch_company_filings(cik, company_name)
    if not data:
        return

    filtered = filter_filings(data)
    output_data = save_json(data, filtered, ticker)
    print_summary(output_data, ticker)


def main():
    ticker_arg = None
    fetch_all = False

    for i, arg in enumerate(sys.argv):
        if arg == '--ticker' and i + 1 < len(sys.argv):
            ticker_arg = sys.argv[i + 1].upper()
        elif arg == '--all':
            fetch_all = True

    conn = connect_db()
    if not conn:
        return

    from psycopg2.extras import RealDictCursor
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if fetch_all:
        cursor.execute("SELECT ticker, cik, company_name FROM companies WHERE active = TRUE ORDER BY ticker")
        companies = cursor.fetchall()
    elif ticker_arg:
        cursor.execute("SELECT ticker, cik, company_name FROM companies WHERE ticker = %s", (ticker_arg,))
        companies = cursor.fetchall()
        if not companies:
            print(f"✗ Company with ticker '{ticker_arg}' not found in database")
            conn.close()
            return
    else:
        print("Usage: python fetch_filings.py --ticker TICKER | --all")
        conn.close()
        return

    cursor.close()
    conn.close()

    for company in companies:
        print(f"\n{'=' * 70}")
        process_company(company['ticker'], company['cik'], company['company_name'])


if __name__ == "__main__":
    main()
