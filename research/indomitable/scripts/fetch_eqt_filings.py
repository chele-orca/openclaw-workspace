#!/usr/bin/env python3
"""
Fetch EQT Corporation SEC filings from the last 14 months
and generate a summary report by filing type.

SEC EDGAR Compliance:
- User-Agent with contact email (required)
- Rate limit: 10 requests/second (we only make 1 request)
- Proper CIK padding to 10 digits
"""

import requests
import json
from datetime import datetime, timedelta
from collections import Counter

# Configuration
SEC_API_BASE = "https://data.sec.gov"
USER_AGENT = "MacMini Analysis tbjohnston@gmail.com"
EQT_CIK = "0000033213"  # EQT Corporation (already padded to 10 digits)

# Calculate date range: last 26 months
end_date = datetime.now()
start_date = end_date - timedelta(days=26*30)  # Approximate 26 months

def fetch_eqt_filings():
    """Fetch EQT filings from SEC EDGAR API"""
    print(f"Fetching EQT SEC filings from {start_date.date()} to {end_date.date()}...")
    print(f"Using CIK: {EQT_CIK}\n")
    
    # Construct API URL
    url = f"{SEC_API_BASE}/submissions/CIK{EQT_CIK}.json"
    
    # Required headers for SEC compliance
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Host": "data.sec.gov"
    }
    
    try:
        # Make request to SEC API
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        print("✓ Successfully fetched data from SEC API\n")
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error fetching data from SEC API: {e}")
        return None

def filter_filings(data):
    """Filter filings from last 14 months"""
    # Extract recent filings data
    recent_filings = data.get('filings', {}).get('recent', {})
    
    # Get filing data arrays
    filing_dates = recent_filings.get('filingDate', [])
    form_types = recent_filings.get('form', [])
    accession_numbers = recent_filings.get('accessionNumber', [])
    primary_documents = recent_filings.get('primaryDocument', [])
    primary_doc_descriptions = recent_filings.get('primaryDocDescription', [])
    
    # Filter filings within date range
    filtered_filings = []
    for i in range(len(filing_dates)):
        filing_date = datetime.strptime(filing_dates[i], '%Y-%m-%d')
        if start_date <= filing_date <= end_date:
            filtered_filings.append({
                'filingDate': filing_dates[i],
                'form': form_types[i],
                'accessionNumber': accession_numbers[i],
                'primaryDocument': primary_documents[i],
                'primaryDocDescription': primary_doc_descriptions[i] if i < len(primary_doc_descriptions) else ''
            })
    
    print(f"✓ Filtered {len(filtered_filings)} filings from last 14 months\n")
    return filtered_filings

def save_raw_json(data, filtered_filings):
    """Save raw JSON data to file"""
    output_data = {
        'metadata': {
            'company': data.get('name'),
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
    
    # Save to file
    output_path = '/home/sec-data/eqt_filings_26mo.json'
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"✓ Saved raw JSON to {output_path}\n")
    return output_data

def generate_summary(output_data):
    """Generate and display summary report"""
    metadata = output_data['metadata']
    filings = output_data['filings']
    
    # Count filings by type
    form_counts = Counter([f['form'] for f in filings])
    
    # Display summary
    print("=" * 70)
    print("EQT CORPORATION SEC FILINGS SUMMARY")
    print("=" * 70)
    print(f"Company:          {metadata['company']}")
    print(f"CIK:              {metadata['cik']}")
    print(f"SIC:              {metadata['sic']} - {metadata['sicDescription']}")
    print(f"State of Inc:     {metadata['stateOfIncorporation']}")
    print(f"Fiscal Year End:  {metadata['fiscalYearEnd']}")
    print(f"Date Range:       {metadata['date_range']['start']} to {metadata['date_range']['end']}")
    print(f"Total Filings:    {metadata['total_filings']}")
    print("=" * 70)
    print("\nFILINGS BY TYPE:")
    print("-" * 70)
    
    # Sort by count (descending) then by form type
    for form_type, count in sorted(form_counts.items(), key=lambda x: (-x[1], x[0])):
        percentage = (count / metadata['total_filings']) * 100
        print(f"  {form_type:20s} : {count:3d} filings ({percentage:5.1f}%)")
    
    print("=" * 70)
    
    # Save summary to text file
    summary_path = '/home/sec-data/eqt_filings_summary.txt'
    with open(summary_path, 'w') as f:
        f.write("=" * 70 + "\n")
        f.write("EQT CORPORATION SEC FILINGS SUMMARY\n")
        f.write("=" * 70 + "\n")
        f.write(f"Company:          {metadata['company']}\n")
        f.write(f"CIK:              {metadata['cik']}\n")
        f.write(f"SIC:              {metadata['sic']} - {metadata['sicDescription']}\n")
        f.write(f"State of Inc:     {metadata['stateOfIncorporation']}\n")
        f.write(f"Fiscal Year End:  {metadata['fiscalYearEnd']}\n")
        f.write(f"Date Range:       {metadata['date_range']['start']} to {metadata['date_range']['end']}\n")
        f.write(f"Total Filings:    {metadata['total_filings']}\n")
        f.write("=" * 70 + "\n")
        f.write("\nFILINGS BY TYPE:\n")
        f.write("-" * 70 + "\n")
        for form_type, count in sorted(form_counts.items(), key=lambda x: (-x[1], x[0])):
            percentage = (count / metadata['total_filings']) * 100
            f.write(f"  {form_type:20s} : {count:3d} filings ({percentage:5.1f}%)\n")
        f.write("=" * 70 + "\n")
    
    print(f"\n✓ Saved summary report to {summary_path}\n")

def main():
    """Main execution function"""
    # Step 1: Fetch data from SEC API
    data = fetch_eqt_filings()
    if not data:
        print("Failed to fetch data. Exiting.")
        return
    
    # Step 2: Filter filings from last 14 months
    filtered_filings = filter_filings(data)
    
    # Step 3: Save raw JSON
    output_data = save_raw_json(data, filtered_filings)
    
    # Step 4: Generate and display summary
    generate_summary(output_data)

if __name__ == "__main__":
    main()
