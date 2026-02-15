#!/usr/bin/env python3
"""
Shared configuration and utilities for the SEC filings analysis pipeline.
"""

import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
import anthropic

# Database configuration
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'sec_filings'),
    'user': os.getenv('POSTGRES_USER', 'sec_user'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

# Anthropic API
MODEL = "claude-sonnet-4-20250514"


def connect_db(use_dict_cursor=False):
    """Connect to PostgreSQL database."""
    try:
        kwargs = dict(DB_CONFIG)
        if use_dict_cursor:
            kwargs['cursor_factory'] = RealDictCursor
        return psycopg2.connect(**kwargs)
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return None


def get_anthropic_client():
    """Get an Anthropic API client."""
    api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key:
        print("✗ ANTHROPIC_API_KEY not set")
        return None
    return anthropic.Anthropic(api_key=api_key)


def strip_markdown_json(text):
    """Strip markdown code block wrappers from JSON responses."""
    text = text.strip()
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
        text = text.strip()
    return text


def parse_claude_json(text):
    """Parse JSON from a Claude response, handling markdown wrappers and trailing text."""
    try:
        cleaned = strip_markdown_json(text)
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to extract just the first JSON object by finding matching braces
        cleaned = strip_markdown_json(text)
        depth = 0
        start = None
        for i, ch in enumerate(cleaned):
            if ch == '{':
                if start is None:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        return json.loads(cleaned[start:i + 1])
                    except json.JSONDecodeError:
                        pass
                    break
        print(f"  ✗ JSON parse error: could not extract valid JSON")
        return None


def get_company_by_ticker(conn, ticker):
    """Get company info by ticker symbol."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM companies WHERE ticker = %s", (ticker,))
    result = cursor.fetchone()
    cursor.close()
    return result


def get_active_companies(conn, priority=None):
    """Get all active companies, optionally filtered by watchlist priority."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    if priority:
        cursor.execute(
            "SELECT * FROM companies WHERE active = TRUE AND watchlist_priority = %s ORDER BY ticker",
            (priority,)
        )
    else:
        cursor.execute("SELECT * FROM companies WHERE active = TRUE ORDER BY ticker")
    results = cursor.fetchall()
    cursor.close()
    return results


def get_industry_profile(conn, industry_profile_id):
    """Get industry profile by ID."""
    if not industry_profile_id:
        return None
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM industry_profiles WHERE id = %s", (industry_profile_id,))
    result = cursor.fetchone()
    cursor.close()
    return result
