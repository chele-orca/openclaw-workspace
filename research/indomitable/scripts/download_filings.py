#!/usr/bin/env python3
"""
Download SEC filings and populate PostgreSQL database
Focuses on strategic subset: 10-Ks, 10-Qs, and recent 8-Ks
"""

import json
import os
import sys
import time
import argparse
import requests
from datetime import datetime
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_values

# Project root: parent of scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Configuration
SEC_BASE_URL = "https://www.sec.gov/Archives/edgar/data"
USER_AGENT = "MacMini Analysis tbjohnston@gmail.com"
FILINGS_BASE_DIR = str(PROJECT_ROOT / "filings")

# PostgreSQL connection
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'sec_filings'),
    'user': os.getenv('POSTGRES_USER', 'sec_user'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

# Strategic filing types to download
PRIORITY_FILING_TYPES = ['10-K', '10-Q', '8-K']

def connect_db():
    """Connect to PostgreSQL database"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return None

def find_filings_json(ticker=None):
    """Find the filings JSON file for a ticker"""
    data_dir = str(PROJECT_ROOT / "sec-data")
    if ticker:
        # Look for ticker-specific file
        pattern = f"{ticker.lower()}_filings_"
        for f in sorted(os.listdir(data_dir), reverse=True):
            if f.startswith(pattern) and f.endswith('.json'):
                return os.path.join(data_dir, f)
    # Fallback: find any filings JSON
    for f in sorted(os.listdir(data_dir), reverse=True):
        if f.endswith('_filings_26mo.json'):
            return os.path.join(data_dir, f)
    return None

def load_filings_data(json_path):
    """Load the filings JSON data"""
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        print(f"✓ Loaded {len(data['filings'])} filings from {os.path.basename(json_path)}")
        return data
    except Exception as e:
        print(f"✗ Error loading filings data: {e}")
        return None

def filter_strategic_filings(filings):
    """Filter filings to strategic subset"""
    strategic = []
    
    # Get all 10-Ks and 10-Qs
    for filing in filings:
        if filing['form'] in ['10-K', '10-Q']:
            strategic.append(filing)
    
    # Get recent 8-Ks (last 10)
    eight_ks = [f for f in filings if f['form'] == '8-K']
    eight_ks.sort(key=lambda x: x['filingDate'], reverse=True)
    strategic.extend(eight_ks[:10])
    
    # Sort by date
    strategic.sort(key=lambda x: x['filingDate'])
    
    print(f"\n✓ Strategic subset selected:")
    print(f"  - 10-Ks: {len([f for f in strategic if f['form'] == '10-K'])}")
    print(f"  - 10-Qs: {len([f for f in strategic if f['form'] == '10-Q'])}")
    print(f"  - 8-Ks: {len([f for f in strategic if f['form'] == '8-K'])}")
    print(f"  - Total: {len(strategic)} filings\n")
    
    return strategic

def construct_filing_url(cik, accession_number, primary_document):
    """Construct the SEC EDGAR URL for a filing"""
    # Remove hyphens from accession number for the path
    acc_no_path = accession_number.replace('-', '')
    
    # URL format: https://www.sec.gov/Archives/edgar/data/{CIK}/{ACC_NO}/{PRIMARY_DOC}
    url = f"{SEC_BASE_URL}/{cik}/{acc_no_path}/{primary_document}"
    
    return url

def download_filing(url, local_path):
    """Download a filing from SEC EDGAR"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Host": "www.sec.gov"
    }
    
    try:
        # Respect SEC rate limit (10 requests/second)
        time.sleep(0.15)  # ~6-7 requests per second to be safe
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Save to file
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, 'wb') as f:
            f.write(response.content)
        
        return True, len(response.content)
    
    except Exception as e:
        print(f"    ✗ Download failed: {e}")
        return False, 0

def insert_filings_to_db(conn, filings_data, strategic_filings):
    """Insert filing metadata into PostgreSQL"""
    cursor = conn.cursor()
    
    # Get company_id from filings data
    ticker = filings_data['metadata'].get('ticker', 'EQT')
    cursor.execute("SELECT id FROM companies WHERE ticker = %s", (ticker,))
    row = cursor.fetchone()
    if not row:
        # Fallback: try matching by CIK
        cik = filings_data['metadata']['cik']
        cursor.execute("SELECT id FROM companies WHERE cik = %s", (cik,))
        row = cursor.fetchone()
    if not row:
        print(f"  ✗ Company not found for ticker={ticker}")
        cursor.close()
        return 0
    company_id = row[0]
    
    # Prepare data for batch insert
    filing_records = []
    for filing in strategic_filings:
        filing_records.append((
            company_id,
            filings_data['metadata']['cik'],
            filing['form'],
            filing['filingDate'],
            filing['accessionNumber'],
            filing['primaryDocument'],
            filing.get('primaryDocDescription', ''),
            None,  # file_url - will be set during download
            None,  # local_path - will be set during download
            False,  # downloaded
            False,  # processed
        ))
    
    # Insert filings (on conflict do nothing to avoid duplicates)
    insert_query = """
        INSERT INTO filings 
        (company_id, cik, filing_type, filing_date, accession_number, 
         primary_document, primary_doc_description, file_url, local_path, 
         downloaded, processed)
        VALUES %s
        ON CONFLICT (accession_number) DO NOTHING
        RETURNING id, accession_number
    """
    
    execute_values(cursor, insert_query, filing_records)
    inserted = cursor.fetchall()
    conn.commit()
    
    print(f"✓ Inserted {len(inserted)} new filings into database")
    cursor.close()
    
    return len(inserted)

def download_and_update_filings(conn, cik, ticker="EQT"):
    """Download filings and update database"""
    cursor = conn.cursor()

    # Get filings that haven't been downloaded yet
    cursor.execute("""
        SELECT id, filing_type, filing_date, accession_number, primary_document
        FROM filings
        WHERE downloaded = FALSE AND cik = %s
        ORDER BY filing_date DESC
    """, (cik,))

    pending = cursor.fetchall()

    if not pending:
        print("✓ All strategic filings already downloaded")
        cursor.close()
        return

    print(f"\nDownloading {len(pending)} filings...\n")

    downloaded_count = 0
    total_bytes = 0

    for filing_id, filing_type, filing_date, accession_number, primary_document in pending:
        # Construct paths
        year = filing_date.year
        filing_dir = f"{FILINGS_BASE_DIR}/{ticker.upper()}/{year}/{filing_type}"
        local_path = f"{filing_dir}/{accession_number.replace('-', '')}.html"
        file_url = construct_filing_url(cik, accession_number, primary_document)
        
        print(f"  {filing_type} - {filing_date} ({accession_number})")
        print(f"    URL: {file_url}")
        
        # Download
        success, file_size = download_filing(file_url, local_path)
        
        if success:
            downloaded_count += 1
            total_bytes += file_size
            
            # Update database
            cursor.execute("""
                UPDATE filings
                SET file_url = %s,
                    local_path = %s,
                    downloaded = TRUE,
                    download_date = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (file_url, local_path, filing_id))
            conn.commit()
            
            print(f"    ✓ Downloaded ({file_size:,} bytes) → {local_path}\n")
        else:
            print()
    
    cursor.close()
    
    print("=" * 70)
    print(f"Download Summary:")
    print(f"  - Files downloaded: {downloaded_count}/{len(pending)}")
    print(f"  - Total size: {total_bytes:,} bytes ({total_bytes/1024/1024:.2f} MB)")
    print("=" * 70)

def generate_summary(conn):
    """Generate summary of database contents"""
    cursor = conn.cursor()
    
    print("\n" + "=" * 70)
    print("DATABASE SUMMARY")
    print("=" * 70)
    
    # Total filings by type
    cursor.execute("""
        SELECT filing_type, COUNT(*), 
               SUM(CASE WHEN downloaded THEN 1 ELSE 0 END) as downloaded
        FROM filings
        GROUP BY filing_type
        ORDER BY COUNT(*) DESC
    """)
    
    print("\nFilings in Database:")
    print("-" * 70)
    for filing_type, total, downloaded in cursor.fetchall():
        print(f"  {filing_type:15s} : {total:2d} total, {downloaded:2d} downloaded")
    
    # Overall stats
    cursor.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN downloaded THEN 1 ELSE 0 END) as downloaded,
               SUM(CASE WHEN processed THEN 1 ELSE 0 END) as processed
        FROM filings
    """)
    
    total, downloaded, processed = cursor.fetchone()
    
    print("-" * 70)
    print(f"  Total:          {total}")
    print(f"  Downloaded:     {downloaded}")
    print(f"  Processed:      {processed}")
    print("=" * 70)
    
    cursor.close()

def main():
    """Main execution"""
    parser = argparse.ArgumentParser(description='Download SEC filings and populate database')
    parser.add_argument('--ticker', type=str, help='Ticker symbol (auto-detects from JSON if not provided)')
    args = parser.parse_args()

    print("=" * 70)
    print("SEC FILINGS DOWNLOADER & DATABASE POPULATOR")
    print("=" * 70)
    print()

    # Find and load filings data
    json_path = find_filings_json(args.ticker)
    if not json_path:
        print(f"✗ No filings JSON found for ticker={args.ticker}")
        return

    data = load_filings_data(json_path)
    if not data:
        return

    ticker = data['metadata'].get('ticker', args.ticker or 'EQT')

    # Filter to strategic subset
    strategic = filter_strategic_filings(data['filings'])

    # Connect to database
    print("Connecting to PostgreSQL...")
    conn = connect_db()
    if not conn:
        return

    print("✓ Connected to database\n")

    # Insert filings metadata
    print("Inserting filings metadata into database...")
    inserted = insert_filings_to_db(conn, data, strategic)
    print()

    # Download filings
    download_and_update_filings(conn, data['metadata']['cik'], ticker)

    # Generate summary
    generate_summary(conn)

    # Close connection
    conn.close()
    print("\n✓ Database connection closed")

if __name__ == "__main__":
    main()
