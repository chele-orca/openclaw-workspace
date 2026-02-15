#!/usr/bin/env python3
"""
Stage 2: Document Processing & Chunking
Parse HTML SEC filings, extract key sections, and chunk for Claude analysis
"""

import os
import re
import json
from pathlib import Path
from bs4 import BeautifulSoup
import psycopg2
from psycopg2.extras import execute_values
import tiktoken

# Configuration
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'sec_filings'),
    'user': os.getenv('POSTGRES_USER', 'sec_user'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

# Token counting (using tiktoken for Claude)
encoding = tiktoken.get_encoding("cl100k_base")  # Claude uses similar to GPT-4

# Section patterns for different filing types
SECTION_PATTERNS = {
    '10-K': [
        (r'ITEM\s+1\b[^A]', 'Item 1: Business'),
        (r'ITEM\s+1A', 'Item 1A: Risk Factors'),
        (r'ITEM\s+7\b[^A]', 'Item 7: MD&A'),
        (r'ITEM\s+8\b', 'Item 8: Financial Statements'),
        (r'ITEM\s+9A', 'Item 9A: Controls and Procedures'),
    ],
    '10-Q': [
        (r'ITEM\s+1\b[^A]', 'Item 1: Financial Statements'),
        (r'ITEM\s+2\b', 'Item 2: MD&A'),
        (r'ITEM\s+3\b', 'Item 3: Quantitative and Qualitative Disclosures'),
        (r'ITEM\s+4\b', 'Item 4: Controls and Procedures'),
    ],
    '8-K': [
        (r'ITEM\s+1\.01', 'Item 1.01: Entry into Material Agreement'),
        (r'ITEM\s+2\.02', 'Item 2.02: Results of Operations'),
        (r'ITEM\s+5\.02', 'Item 5.02: Departure/Election of Directors'),
        (r'ITEM\s+7\.01', 'Item 7.01: Regulation FD Disclosure'),
        (r'ITEM\s+8\.01', 'Item 8.01: Other Events'),
        (r'ITEM\s+9\.01', 'Item 9.01: Financial Statements and Exhibits'),
    ]
}

def connect_db():
    """Connect to PostgreSQL"""
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return None

def count_tokens(text):
    """Count tokens using tiktoken"""
    return len(encoding.encode(text))

def clean_html(html_content):
    """Parse and clean HTML content"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style elements
    for element in soup(['script', 'style', 'meta', 'link']):
        element.decompose()
    
    # Get text
    text = soup.get_text()
    
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = '\n'.join(chunk for chunk in chunks if chunk)
    
    return text

def extract_sections(text, filing_type):
    """Extract sections based on filing type"""
    sections = {}
    
    # Get patterns for this filing type
    patterns = SECTION_PATTERNS.get(filing_type, [])
    
    if not patterns:
        # For unknown types, return full text as single section
        return {'Full Document': text}
    
    # Find all section positions
    section_positions = []
    for pattern, section_name in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            section_positions.append((match.start(), section_name))
    
    # Sort by position
    section_positions.sort(key=lambda x: x[0])
    
    # Extract text for each section
    for i, (start_pos, section_name) in enumerate(section_positions):
        # Determine end position (start of next section or end of document)
        if i < len(section_positions) - 1:
            end_pos = section_positions[i + 1][0]
        else:
            end_pos = len(text)
        
        section_text = text[start_pos:end_pos].strip()
        
        # Only include if substantial content
        if len(section_text) > 100:
            sections[section_name] = section_text
    
    # If no sections found, return full text
    if not sections:
        sections['Full Document'] = text
    
    return sections

def chunk_text(text, section_name, max_tokens=8000, overlap_tokens=200):
    """
    Split text into chunks with token limits
    Preserves paragraph boundaries where possible
    """
    # Split into paragraphs
    paragraphs = text.split('\n\n')
    
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for para in paragraphs:
        para_tokens = count_tokens(para)
        
        # If single paragraph exceeds max, split it
        if para_tokens > max_tokens:
            # Save current chunk if exists
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_tokens = 0
            
            # Split large paragraph by sentences
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sentence in sentences:
                sentence_tokens = count_tokens(sentence)
                if current_tokens + sentence_tokens > max_tokens:
                    if current_chunk:
                        chunks.append('\n\n'.join(current_chunk))
                    current_chunk = [sentence]
                    current_tokens = sentence_tokens
                else:
                    current_chunk.append(sentence)
                    current_tokens += sentence_tokens
        
        # Normal paragraph processing
        elif current_tokens + para_tokens > max_tokens:
            # Save current chunk and start new one
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_tokens = para_tokens
        else:
            current_chunk.append(para)
            current_tokens += para_tokens
    
    # Add final chunk
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    
    return chunks

def process_filing(filing_id, filing_type, local_path):
    """Process a single filing"""
    print(f"\n{'='*70}")
    print(f"Processing: {filing_type} (ID: {filing_id})")
    print(f"Path: {local_path}")
    print(f"{'='*70}")
    
    # Read HTML file
    try:
        with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
            html_content = f.read()
    except Exception as e:
        print(f"✗ Failed to read file: {e}")
        return None
    
    # Clean HTML
    print("  → Cleaning HTML...")
    text = clean_html(html_content)
    total_tokens = count_tokens(text)
    print(f"  ✓ Extracted {len(text):,} characters ({total_tokens:,} tokens)")
    
    # Extract sections
    print(f"  → Extracting sections for {filing_type}...")
    sections = extract_sections(text, filing_type)
    print(f"  ✓ Found {len(sections)} sections")
    
    # Process each section
    all_chunks = []
    for section_name, section_text in sections.items():
        section_tokens = count_tokens(section_text)
        print(f"\n  Section: {section_name}")
        print(f"    Tokens: {section_tokens:,}")
        
        # Chunk if needed
        if section_tokens > 8000:
            chunks = chunk_text(section_text, section_name)
            print(f"    Split into {len(chunks)} chunks")
        else:
            chunks = [section_text]
            print(f"    Single chunk (under 8k tokens)")
        
        # Store chunk data
        for idx, chunk in enumerate(chunks):
            all_chunks.append({
                'filing_id': filing_id,
                'section_name': section_name,
                'chunk_index': idx,
                'content': chunk,
                'token_count': count_tokens(chunk)
            })
    
    print(f"\n  ✓ Total chunks created: {len(all_chunks)}")
    return all_chunks

def save_chunks_to_db(conn, chunks):
    """Save chunks to database"""
    if not chunks:
        return 0
    
    cursor = conn.cursor()
    
    # Prepare data for batch insert
    chunk_records = [
        (
            chunk['filing_id'],
            chunk['section_name'],
            chunk['chunk_index'],
            chunk['content'],
            chunk['token_count']
        )
        for chunk in chunks
    ]
    
    # Insert chunks
    insert_query = """
        INSERT INTO chunks (filing_id, section_name, chunk_index, content, token_count)
        VALUES %s
    """
    
    execute_values(cursor, insert_query, chunk_records)
    conn.commit()
    
    cursor.close()
    return len(chunk_records)

def mark_filing_processed(conn, filing_id):
    """Mark filing as processed in database"""
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE filings
        SET processed = TRUE,
            process_date = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (filing_id,))
    conn.commit()
    cursor.close()

def get_unprocessed_filings(conn):
    """Get list of downloaded but unprocessed filings"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, filing_type, filing_date, accession_number, local_path
        FROM filings
        WHERE downloaded = TRUE AND processed = FALSE
        ORDER BY filing_date ASC
    """)
    results = cursor.fetchall()
    cursor.close()
    return results

def generate_processing_summary(conn):
    """Generate summary of processing results"""
    cursor = conn.cursor()
    
    print("\n" + "="*70)
    print("PROCESSING SUMMARY")
    print("="*70)
    
    # Filings processed
    cursor.execute("""
        SELECT filing_type, 
               COUNT(*) as total,
               SUM(CASE WHEN processed THEN 1 ELSE 0 END) as processed
        FROM filings
        WHERE downloaded = TRUE
        GROUP BY filing_type
        ORDER BY filing_type
    """)
    
    print("\nFilings Processed:")
    print("-"*70)
    for filing_type, total, processed in cursor.fetchall():
        print(f"  {filing_type:15s} : {processed}/{total} processed")
    
    # Chunks created
    cursor.execute("""
        SELECT f.filing_type, COUNT(c.id) as chunk_count, SUM(c.token_count) as total_tokens
        FROM filings f
        JOIN chunks c ON f.id = c.filing_id
        GROUP BY f.filing_type
        ORDER BY f.filing_type
    """)
    
    print("\nChunks Created:")
    print("-"*70)
    results = cursor.fetchall()
    if results:
        for filing_type, chunk_count, total_tokens in results:
            print(f"  {filing_type:15s} : {chunk_count:4d} chunks, {total_tokens:,} tokens")
    else:
        print("  No chunks created yet")
    
    # Overall stats
    cursor.execute("""
        SELECT COUNT(*) as total_chunks, SUM(token_count) as total_tokens
        FROM chunks
    """)
    
    total_chunks, total_tokens = cursor.fetchone()
    
    print("-"*70)
    print(f"  Total Chunks:   {total_chunks or 0}")
    print(f"  Total Tokens:   {total_tokens or 0:,}")
    print("="*70)
    
    cursor.close()

def main():
    """Main execution"""
    print("="*70)
    print("STAGE 2: SEC FILING DOCUMENT PROCESSOR")
    print("="*70)
    
    # Connect to database
    print("\nConnecting to database...")
    conn = connect_db()
    if not conn:
        return
    print("✓ Connected")
    
    # Get unprocessed filings
    print("\nFetching unprocessed filings...")
    filings = get_unprocessed_filings(conn)
    
    if not filings:
        print("✓ No unprocessed filings found")
        generate_processing_summary(conn)
        conn.close()
        return
    
    print(f"✓ Found {len(filings)} filings to process\n")
    
    # Process each filing
    processed_count = 0
    total_chunks = 0
    
    for filing_id, filing_type, filing_date, accession_number, local_path in filings:
        # Process filing
        chunks = process_filing(filing_id, filing_type, local_path)
        
        if chunks:
            # Save to database
            saved = save_chunks_to_db(conn, chunks)
            total_chunks += saved
            
            # Mark as processed
            mark_filing_processed(conn, filing_id)
            
            processed_count += 1
            print(f"  ✓ Saved {saved} chunks to database")
            print(f"  ✓ Marked filing as processed")
    
    # Generate summary
    generate_processing_summary(conn)
    
    # Close connection
    conn.close()
    print("\n✓ Processing complete")

if __name__ == "__main__":
    main()
