#!/usr/bin/env python3
"""
External data fetching module for industry context.
Fetches market data from EIA, Yahoo Finance, FRED, Finnhub, FMP APIs.
Scrapes earnings call transcripts from Motley Fool as FMP fallback.
Caches results in the external_context_cache table.
"""

import os
import re
import json
import time
import requests
from datetime import datetime, date, timedelta
from bs4 import BeautifulSoup
from config import connect_db

# API keys
EIA_API_KEY = os.getenv('EIA_API_KEY', '')
FRED_API_KEY = os.getenv('FRED_API_KEY', '')
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY', '')
FMP_API_KEY = os.getenv('FMP_API_KEY', '')

# NYMEX month codes for natural gas futures
MONTH_CODES = {
    1: 'F', 2: 'G', 3: 'H', 4: 'J', 5: 'K', 6: 'M',
    7: 'N', 8: 'Q', 9: 'U', 10: 'V', 11: 'X', 12: 'Z'
}


def get_nymex_ticker(months_out):
    """Generate NYMEX natural gas futures ticker for N months out."""
    now = datetime.now()
    target_month = now.month + months_out
    target_year = now.year + (target_month - 1) // 12
    target_month = ((target_month - 1) % 12) + 1
    code = MONTH_CODES[target_month]
    year_suffix = str(target_year)[-2:]
    return f"NG{code}{year_suffix}.NYM"


def fetch_eia_spot(api_key=None):
    """
    Fetch Henry Hub natural gas spot price from EIA API v2.
    Same endpoint as the n8n pricing workflow.
    """
    key = api_key or EIA_API_KEY
    if not key:
        print("  ✗ EIA_API_KEY not set")
        return None

    url = "https://api.eia.gov/v2/natural-gas/pri/fut/data/"
    params = {
        'frequency': 'daily',
        'data[0]': 'value',
        'facets[series][]': 'RNGWHHD',
        'sort[0][column]': 'period',
        'sort[0][direction]': 'desc',
        'length': '1',
        'api_key': key
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        spot = data['response']['data'][0]
        return {
            'price': float(spot['value']),
            'date': spot['period'],
            'series': spot['series']
        }
    except Exception as e:
        print(f"  ✗ EIA spot fetch failed: {e}")
        return None


def fetch_yahoo_futures(months_out_list=None):
    """
    Fetch NYMEX natural gas futures from Yahoo Finance.
    Same API as the n8n pricing workflow.
    """
    if months_out_list is None:
        months_out_list = [1, 2, 3, 6, 9, 12, 15, 18, 24]

    import time

    results = {}
    for i, months in enumerate(months_out_list):
        if i > 0:
            time.sleep(1)  # Rate limit: 1 request/sec for Yahoo Finance
        ticker = get_nymex_ticker(months)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

        try:
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            response.raise_for_status()
            data = response.json()
            meta = data['chart']['result'][0]['meta']
            results[f"{months}_month"] = {
                'price': meta['regularMarketPrice'],
                'contract': meta['symbol']
            }
        except Exception as e:
            print(f"  ✗ Yahoo Finance fetch failed for {ticker}: {e}")
            results[f"{months}_month"] = None

    return results


def compute_strip_average(futures: dict) -> dict:
    """
    Compute calendar strip averages from futures curve data.

    Returns dict with:
      strip_12m: average price across next 12 months of curve
      strip_24m: average price across next 24 months
      summer_strip: average of non-winter months (Apr-Oct)
      winter_strip: average of winter months (Nov-Mar)
      curve_points: sorted list of (months_out, price) for charting
    """
    # Extract valid price points
    points = []
    for key, val in futures.items():
        if val and isinstance(val, dict) and val.get('price'):
            months = int(key.split('_')[0])
            points.append((months, val['price']))

    if not points:
        return {}

    points.sort()

    # Weighted strip averages (weight by interval width between points)
    def weighted_avg(pts, max_months):
        filtered = [(m, p) for m, p in pts if m <= max_months]
        if not filtered:
            return None
        if len(filtered) == 1:
            return filtered[0][1]
        # Trapezoidal weighting: each point represents the interval to the next
        total_weight = 0
        total_value = 0
        for i in range(len(filtered)):
            if i == 0:
                weight = (filtered[1][0] - filtered[0][0]) / 2 if len(filtered) > 1 else 1
            elif i == len(filtered) - 1:
                weight = (filtered[-1][0] - filtered[-2][0]) / 2
            else:
                weight = (filtered[i+1][0] - filtered[i-1][0]) / 2
            total_weight += weight
            total_value += filtered[i][1] * weight
        return round(total_value / total_weight, 2) if total_weight > 0 else None

    result = {
        'strip_12m': weighted_avg(points, 12),
        'strip_24m': weighted_avg(points, 24),
        'curve_points': points,
    }

    # Simple average of all points as fallback
    all_prices = [p for _, p in points]
    result['simple_avg'] = round(sum(all_prices) / len(all_prices), 2)

    # Winter vs summer (approximate by month offset from now)
    from datetime import datetime
    current_month = datetime.now().month
    winter_prices = []
    summer_prices = []
    for months_out, price in points:
        target_month = ((current_month - 1 + months_out) % 12) + 1
        if target_month in (11, 12, 1, 2, 3):  # Nov-Mar
            winter_prices.append(price)
        else:  # Apr-Oct
            summer_prices.append(price)

    if winter_prices:
        result['winter_strip'] = round(sum(winter_prices) / len(winter_prices), 2)
    if summer_prices:
        result['summer_strip'] = round(sum(summer_prices) / len(summer_prices), 2)

    return result


def fetch_fred_data(series_id, api_key=None):
    """Fetch latest value from FRED API."""
    key = api_key or FRED_API_KEY
    if not key:
        print("  ✗ FRED_API_KEY not set")
        return None

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        'series_id': series_id,
        'api_key': key,
        'file_type': 'json',
        'sort_order': 'desc',
        'limit': 5
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        # Find first non-missing observation
        for obs in data.get('observations', []):
            if obs['value'] != '.':
                return {
                    'value': float(obs['value']),
                    'date': obs['date']
                }
        return None
    except Exception as e:
        print(f"  ✗ FRED fetch failed for {series_id}: {e}")
        return None


def cache_value(conn, source_api, series_id, data_date, value, unit):
    """Cache a fetched value in external_context_cache."""
    # Normalize partial dates (e.g., "2025-11" → "2025-11-01")
    if isinstance(data_date, str) and len(data_date) == 7:
        data_date = f"{data_date}-01"
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO external_context_cache (source_api, series_id, data_date, value, unit)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (source_api, series_id, data_date) DO UPDATE SET value = %s, fetched_at = CURRENT_TIMESTAMP
    """, (source_api, series_id, data_date, value, unit, value))
    conn.commit()
    cursor.close()


def get_cached_value(conn, source_api, series_id, data_date=None):
    """Get cached value, defaulting to most recent if no date specified."""
    cursor = conn.cursor()
    if data_date:
        cursor.execute("""
            SELECT value, unit, data_date FROM external_context_cache
            WHERE source_api = %s AND series_id = %s AND data_date = %s
        """, (source_api, series_id, data_date))
    else:
        cursor.execute("""
            SELECT value, unit, data_date FROM external_context_cache
            WHERE source_api = %s AND series_id = %s
            ORDER BY data_date DESC LIMIT 1
        """, (source_api, series_id))
    result = cursor.fetchone()
    cursor.close()
    return result


def fetch_eia_data(endpoint, facets, api_key=None, frequency='daily'):
    """
    Fetch data from any EIA API v2 endpoint.

    Args:
        endpoint: EIA API v2 path, e.g., '/v2/natural-gas/pri/fut/data/'
        facets: dict of facet filters, e.g., {'series': ['RNGWHHD']}
        api_key: optional override
        frequency: 'daily', 'weekly', 'monthly', 'annual'
    """
    key = api_key or EIA_API_KEY
    if not key:
        print("  ✗ EIA_API_KEY not set")
        return None

    url = f"https://api.eia.gov{endpoint}"
    params = {
        'frequency': frequency,
        'data[0]': 'value',
        'sort[0][column]': 'period',
        'sort[0][direction]': 'desc',
        'length': '1',
        'api_key': key
    }
    for facet_name, facet_values in facets.items():
        if isinstance(facet_values, list):
            for val in facet_values:
                params[f'facets[{facet_name}][]'] = val
        else:
            params[f'facets[{facet_name}][]'] = facet_values

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        record = data['response']['data'][0]
        return {
            'value': float(record['value']),
            'date': record['period'],
            'series': record.get('series', record.get('series-description', ''))
        }
    except Exception as e:
        print(f"  ✗ EIA fetch failed for {endpoint}: {e}")
        return None


def fetch_finnhub_quote(ticker, api_key=None):
    """Fetch current stock quote from Finnhub."""
    key = api_key or FINNHUB_API_KEY
    if not key:
        print("  ✗ FINNHUB_API_KEY not set")
        return None

    url = "https://finnhub.io/api/v1/quote"
    params = {'symbol': ticker, 'token': key}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get('c', 0) == 0:
            print(f"  ✗ Finnhub quote: no data for {ticker}")
            return None
        return {
            'current_price': data['c'],
            'change': round(data['d'], 2),
            'change_pct': round(data['dp'], 2),
            'high': data['h'],
            'low': data['l'],
            'open': data['o'],
            'prev_close': data['pc'],
        }
    except Exception as e:
        print(f"  ✗ Finnhub quote failed for {ticker}: {e}")
        return None


def fetch_finnhub_recommendations(ticker, api_key=None):
    """Fetch analyst recommendation trends from Finnhub."""
    key = api_key or FINNHUB_API_KEY
    if not key:
        return None

    url = "https://finnhub.io/api/v1/stock/recommendation"
    params = {'symbol': ticker, 'token': key}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not data:
            return None
        latest = data[0]  # Most recent period
        return {
            'period': latest.get('period', ''),
            'buy': latest.get('buy', 0),
            'hold': latest.get('hold', 0),
            'sell': latest.get('sell', 0),
            'strong_buy': latest.get('strongBuy', 0),
            'strong_sell': latest.get('strongSell', 0),
        }
    except Exception as e:
        print(f"  ✗ Finnhub recommendations failed for {ticker}: {e}")
        return None


def fetch_finnhub_price_target(ticker, api_key=None):
    """Fetch analyst price target consensus from Finnhub (requires premium plan)."""
    key = api_key or FINNHUB_API_KEY
    if not key:
        return None

    url = "https://finnhub.io/api/v1/stock/price-target"
    params = {'symbol': ticker, 'token': key}

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 403:
            # Price target endpoint requires premium — skip silently
            return None
        response.raise_for_status()
        data = response.json()
        if not data.get('targetMedian'):
            return None
        return {
            'target_high': data.get('targetHigh'),
            'target_low': data.get('targetLow'),
            'target_median': data.get('targetMedian'),
            'target_mean': data.get('targetMean'),
            'num_analysts': data.get('lastUpdated', ''),
        }
    except Exception as e:
        print(f"  ✗ Finnhub price target failed for {ticker}: {e}")
        return None


def fetch_finnhub_earnings_calendar(ticker, api_key=None):
    """
    Fetch earnings calendar dates from Finnhub.
    Returns dict with next_earnings_date, last_earnings_date as date objects, or None.
    Uses external_context_cache with 24h validity (dates stored as YYYYMMDD integers).
    """
    key = api_key or FINNHUB_API_KEY
    if not key:
        print("  ✗ FINNHUB_API_KEY not set")
        return None

    # Check cache first (24h validity)
    conn = None
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT series_id, value FROM external_context_cache
                WHERE source_api = 'finnhub_earnings'
                AND series_id IN (%s, %s)
                AND fetched_at > NOW() - INTERVAL '24 hours'
            """, (f'{ticker}_next_earnings', f'{ticker}_last_earnings'))
            cached = {row[0]: int(row[1]) for row in cursor.fetchall()}
            cursor.close()

            if f'{ticker}_next_earnings' in cached or f'{ticker}_last_earnings' in cached:
                result = {}
                for suffix, key_name in [('next_earnings', 'next_earnings_date'), ('last_earnings', 'last_earnings_date')]:
                    val = cached.get(f'{ticker}_{suffix}')
                    if val:
                        s = str(val)
                        result[key_name] = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
                if result:
                    print(f"  ✓ Earnings calendar (cached): {result}")
                    conn.close()
                    return result
    except Exception as e:
        print(f"  ✗ Earnings calendar cache check failed: {e}")

    # Fetch from Finnhub
    from_date = (date.today() - timedelta(days=90)).isoformat()
    to_date = (date.today() + timedelta(days=90)).isoformat()

    url = "https://finnhub.io/api/v1/calendar/earnings"
    params = {'symbol': ticker, 'from': from_date, 'to': to_date, 'token': key}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        earnings = data.get('earningsCalendar', [])
        if not earnings:
            print(f"  — Finnhub earnings calendar: no data for {ticker}")
            if conn:
                conn.close()
            return None

        today = date.today()
        past_dates = []
        future_dates = []

        for entry in earnings:
            raw = entry.get('date', '')
            if not raw:
                continue
            try:
                d = date.fromisoformat(raw)
                if d <= today:
                    past_dates.append(d)
                else:
                    future_dates.append(d)
            except ValueError:
                continue

        result = {}
        if future_dates:
            result['next_earnings_date'] = min(future_dates)
        if past_dates:
            result['last_earnings_date'] = max(past_dates)

        if not result:
            print(f"  — Finnhub earnings calendar: no parseable dates for {ticker}")
            if conn:
                conn.close()
            return None

        # Cache results
        if conn:
            try:
                today_str = today.isoformat()
                for suffix, key_name in [('next_earnings', 'next_earnings_date'), ('last_earnings', 'last_earnings_date')]:
                    d = result.get(key_name)
                    if d:
                        int_val = int(d.strftime('%Y%m%d'))
                        cache_value(conn, 'finnhub_earnings', f'{ticker}_{suffix}', today_str, int_val, 'YYYYMMDD')
            except Exception as e:
                print(f"  ✗ Earnings calendar cache write failed: {e}")
            conn.close()

        print(f"  ✓ Earnings calendar: {result}")
        return result

    except Exception as e:
        print(f"  ✗ Finnhub earnings calendar failed for {ticker}: {e}")
        if conn:
            conn.close()
        return None


def fetch_finnhub_news(ticker, days_back=7, api_key=None):
    """Fetch recent company news from Finnhub."""
    key = api_key or FINNHUB_API_KEY
    if not key:
        return None

    from_date = (date.today() - timedelta(days=days_back)).isoformat()
    to_date = date.today().isoformat()

    url = "https://finnhub.io/api/v1/company-news"
    params = {
        'symbol': ticker,
        'from': from_date,
        'to': to_date,
        'token': key
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        articles = response.json()
        if not articles:
            return []
        # Return top 10 most recent articles
        return [{
            'headline': a.get('headline', ''),
            'source': a.get('source', ''),
            'url': a.get('url', ''),
            'summary': a.get('summary', ''),
            'datetime': datetime.fromtimestamp(a['datetime']).isoformat() if a.get('datetime') else '',
            'category': a.get('category', ''),
        } for a in articles[:10]]
    except Exception as e:
        print(f"  ✗ Finnhub news failed for {ticker}: {e}")
        return []


def populate_company_news(conn, company_id, ticker, days_back=7):
    """Fetch news via Finnhub and store in data_sources table. Returns count of new articles."""
    articles = fetch_finnhub_news(ticker, days_back=days_back)
    if not articles:
        return 0

    cursor = conn.cursor()
    inserted = 0
    for article in articles:
        if not article.get('url'):
            continue
        try:
            cursor.execute("""
                INSERT INTO data_sources (company_id, source_type, source_url, title, published_date, content)
                VALUES (%s, 'news', %s, %s, %s, %s)
                ON CONFLICT (source_url) WHERE source_url IS NOT NULL DO NOTHING
            """, (
                company_id,
                article['url'],
                article['headline'][:500],
                article['datetime'][:10] if article['datetime'] else date.today().isoformat(),
                article['summary'][:2000] if article['summary'] else article['headline'],
            ))
            if cursor.rowcount > 0:
                inserted += 1
        except Exception as e:
            print(f"  ✗ Failed to insert news article: {e}")
            conn.rollback()
            continue
    conn.commit()
    cursor.close()
    return inserted


def fetch_fmp_earnings_transcript(ticker, quarter, year, api_key=None):
    """Fetch earnings call transcript from FMP."""
    key = api_key or FMP_API_KEY
    if not key:
        print("  ✗ FMP_API_KEY not set")
        return None

    url = "https://financialmodelingprep.com/stable/earning-call-transcript"
    params = {'symbol': ticker, 'quarter': quarter, 'year': year, 'apikey': key}

    try:
        response = requests.get(url, params=params, timeout=20)
        if response.status_code in (402, 403):
            return None  # Requires paid plan
        response.raise_for_status()
        data = response.json()
        if not data:
            return None
        transcript = data[0] if isinstance(data, list) else data
        content = transcript.get('content', '')
        return {
            'quarter': transcript.get('quarter', quarter),
            'year': transcript.get('year', year),
            'date': transcript.get('date', ''),
            'content': content[:15000] if content else '',  # Truncate to 15K chars
        }
    except Exception as e:
        print(f"  ✗ FMP transcript failed for {ticker} Q{quarter} {year}: {e}")
        return None


def fetch_fmp_analyst_estimates(ticker, api_key=None):
    """Fetch consensus analyst estimates from FMP (requires premium plan)."""
    key = api_key or FMP_API_KEY
    if not key:
        return None

    url = "https://financialmodelingprep.com/stable/analyst-estimates"
    params = {'symbol': ticker, 'period': 'quarter', 'apikey': key}

    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code in (402, 403):
            return None  # Requires premium plan
        response.raise_for_status()
        data = response.json()
        if not data:
            return None
        estimates = []
        for est in (data[:4] if isinstance(data, list) else [data]):
            estimates.append({
                'date': est.get('date', ''),
                'estimated_revenue': est.get('estimatedRevenueAvg'),
                'estimated_ebitda': est.get('estimatedEbitdaAvg'),
                'estimated_eps': est.get('estimatedEpsAvg'),
                'number_analysts_revenue': est.get('numberAnalystEstimatedRevenue'),
                'number_analysts_eps': est.get('numberAnalystsEstimatedEps'),
            })
        return estimates
    except Exception as e:
        print(f"  ✗ FMP analyst estimates failed for {ticker}: {e}")
        return None


def fetch_fmp_price_target(ticker, api_key=None):
    """Fetch price target consensus from FMP (starter plan)."""
    key = api_key or FMP_API_KEY
    if not key:
        return None

    url = "https://financialmodelingprep.com/stable/price-target-consensus"
    params = {'symbol': ticker, 'apikey': key}

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code in (402, 403):
            return None
        response.raise_for_status()
        data = response.json()
        if not data:
            return None
        rec = data[0] if isinstance(data, list) else data
        return {
            'target_high': rec.get('targetHigh'),
            'target_low': rec.get('targetLow'),
            'target_consensus': rec.get('targetConsensus'),
            'target_median': rec.get('targetMedian'),
        }
    except Exception as e:
        print(f"  ✗ FMP price target failed for {ticker}: {e}")
        return None


def fetch_fmp_grades(ticker, limit=5, api_key=None):
    """Fetch recent analyst grade changes from FMP (starter plan)."""
    key = api_key or FMP_API_KEY
    if not key:
        return None

    url = "https://financialmodelingprep.com/stable/grades"
    params = {'symbol': ticker, 'apikey': key}

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code in (402, 403):
            return None
        response.raise_for_status()
        data = response.json()
        if not data:
            return None
        grades = []
        for g in (data[:limit] if isinstance(data, list) else [data]):
            grades.append({
                'date': g.get('date', ''),
                'firm': g.get('gradingCompany', ''),
                'new_grade': g.get('newGrade', ''),
                'previous_grade': g.get('previousGrade', ''),
                'action': g.get('action', ''),
            })
        return grades
    except Exception as e:
        print(f"  ✗ FMP grades failed for {ticker}: {e}")
        return None


def populate_earnings_transcript(conn, company_id, ticker, filing_date=None):
    """
    Fetch most recent earnings transcript and store in data_sources.
    Tries FMP first, falls back to Motley Fool scraping.
    Returns True if new transcript added.
    """
    # Determine which quarter to fetch based on filing date or current date
    ref = datetime.strptime(str(filing_date), '%Y-%m-%d') if filing_date else datetime.now()
    # Go back one quarter from reference date to get the most recent earnings call
    quarter = (ref.month - 1) // 3
    year = ref.year
    if quarter == 0:
        quarter = 4
        year -= 1

    # Check if we already have a transcript for this quarter (any source)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM data_sources
        WHERE company_id = %s AND source_type = 'earnings_transcript'
        AND source_url LIKE %s
    """, (company_id, f"%transcript/{ticker}/Q{quarter}/{year}%"))
    if cursor.fetchone():
        cursor.close()
        return False  # Already have it
    cursor.close()

    # Try FMP first
    transcript = fetch_fmp_earnings_transcript(ticker, quarter, year)
    source = 'fmp'

    # Fall back to Motley Fool
    if not transcript or not transcript.get('content'):
        print(f"    → FMP unavailable, trying Motley Fool...")
        transcript = fetch_motley_fool_transcript(ticker, quarter, year)
        source = 'motley_fool'

    if not transcript or not transcript.get('content'):
        return False

    # Use canonical source_url for deduplication (consistent across sources)
    source_url = f"{source}://transcript/{ticker}/Q{quarter}/{year}"

    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO data_sources (company_id, source_type, source_url, title, published_date, content)
            VALUES (%s, 'earnings_transcript', %s, %s, %s, %s)
            ON CONFLICT (source_url) WHERE source_url IS NOT NULL DO NOTHING
        """, (
            company_id,
            source_url,
            f"{ticker} Q{quarter} {year} Earnings Call Transcript",
            transcript.get('date', '')[:10] if transcript.get('date') else f"{year}-{quarter*3:02d}-01",
            transcript['content'],
        ))
        inserted = cursor.rowcount > 0
        conn.commit()
        cursor.close()
        if inserted:
            print(f"    ✓ Stored Q{quarter} {year} transcript from {source}")
        return inserted
    except Exception as e:
        print(f"  ✗ Failed to store transcript: {e}")
        conn.rollback()
        cursor.close()
        return False


def fetch_edgar_insider_transactions(cik, days_back=90):
    """Fetch recent Form 4 insider transaction filings from SEC EDGAR."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    headers = {'User-Agent': 'IndomitableAutomation admin@example.com'}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        recent = data.get('filings', {}).get('recent', {})
        forms = recent.get('form', [])
        dates = recent.get('filingDate', [])

        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        form4s = []
        for i, form in enumerate(forms):
            if form in ('4', '4/A') and dates[i] >= cutoff:
                form4s.append(dates[i])

        if not form4s:
            return {'count': 0, 'days_back': days_back}

        return {
            'count': len(form4s),
            'most_recent': form4s[0],
            'oldest': form4s[-1],
            'days_back': days_back,
        }
    except Exception as e:
        print(f"  ✗ EDGAR insider fetch failed for CIK {cik}: {e}")
        return None


def fetch_motley_fool_transcript(ticker, quarter, year):
    """
    Fetch earnings call transcript from Motley Fool (free, no API key).
    Discovers transcript URL via the stock quote page, then scrapes content.

    Args:
        ticker: Company ticker (e.g., 'EQT')
        quarter: Quarter number (1-4)
        year: Year (e.g., 2025)

    Returns:
        dict with quarter, year, date, content, source, url — or None
    """
    hdrs = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    # Step 1: Find the stock quote page (try both exchanges)
    quote_url = None
    for exchange in ['nyse', 'nasdaq']:
        url = f'https://www.fool.com/quote/{exchange}/{ticker.lower()}/'
        try:
            resp = requests.get(url, headers=hdrs, timeout=15)
            if resp.status_code == 200:
                quote_url = url
                quote_html = resp.text
                break
        except Exception:
            continue

    if not quote_url:
        print(f"  ✗ Motley Fool: no quote page found for {ticker}")
        return None

    # Step 2: Find transcript URL matching the target quarter
    soup = BeautifulSoup(quote_html, 'html.parser')
    target_slug = f'q{quarter}-{year}'
    target_text = f'Q{quarter} {year}'
    transcript_url = None

    for link in soup.find_all('a', href=True):
        href = link['href']
        if 'earnings/call-transcripts' not in href:
            continue
        # Skip duplicate URLs with /4056/ prefix
        if '/4056/' in href:
            continue
        # Match on URL slug or link text
        if target_slug in href.lower() or target_text in link.get_text():
            transcript_url = href if href.startswith('http') else f'https://www.fool.com{href}'
            break

    if not transcript_url:
        print(f"  ✗ Motley Fool: no Q{quarter} {year} transcript found for {ticker}")
        return None

    # Step 3: Fetch and parse the transcript page
    try:
        time.sleep(1)  # Be polite
        resp = requests.get(transcript_url, headers=hdrs, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ✗ Motley Fool transcript fetch failed: {e}")
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')
    body = soup.find('div', class_='article-body')
    if not body:
        print("  ✗ Motley Fool: could not find article-body div")
        return None

    # Extract text with paragraph structure
    paragraphs = body.find_all(['p', 'h2', 'h3'])
    text_parts = []
    for p in paragraphs:
        text = p.get_text(strip=True)
        if text:
            if p.name in ('h2', 'h3'):
                text_parts.append(f'\n## {text}\n')
            else:
                text_parts.append(text)

    content = '\n\n'.join(text_parts)
    if len(content) < 500:
        print("  ✗ Motley Fool: transcript content too short")
        return None

    # Extract date from the DATE section if present
    call_date = ''
    date_match = re.search(r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+'
                           r'(\w+\.?\s+\d{1,2},\s+\d{4})', content)
    if date_match:
        raw = date_match.group(1).replace('.', '')
        # Try abbreviated month (Oct 22, 2025) then full month (October 30, 2025)
        for fmt in ('%b %d, %Y', '%B %d, %Y'):
            try:
                call_date = datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
                break
            except ValueError:
                continue

    print(f"  ✓ Motley Fool: fetched Q{quarter} {year} transcript ({len(content)} chars)")
    return {
        'quarter': quarter,
        'year': year,
        'date': call_date,
        'content': content[:15000],
        'source': 'motley_fool',
        'url': transcript_url,
    }


def compute_consensus_summary(external_context):
    """
    Build a human-readable consensus summary string from existing external context data.
    Used to inject into the synthesis prompt so Claude can't ignore consensus.

    Returns a string like:
    "ANALYST CONSENSUS: 32 analysts — 9 Strong Buy, 15 Buy, 8 Hold, 0 Sell, 0 Strong Sell.
     Price target: $65.00 consensus (range $50 — $80). Current price: $42.50 (+53% upside to consensus)."
    Or empty string if no analyst data available.
    """
    parts = []

    # Analyst recommendations from Finnhub
    analyst_data = external_context.get('analyst_data', {})
    recs = analyst_data.get('recommendations', {})
    if recs:
        sb = recs.get('strong_buy', 0)
        b = recs.get('buy', 0)
        h = recs.get('hold', 0)
        s = recs.get('sell', 0)
        ss = recs.get('strong_sell', 0)
        total = sb + b + h + s + ss
        if total > 0:
            parts.append(f"ANALYST CONSENSUS: {total} analysts — {sb} Strong Buy, {b} Buy, {h} Hold, {s} Sell, {ss} Strong Sell.")

    # Price target — prefer stockanalysis, fall back to FMP or Finnhub
    price_target_data = external_context.get('price_target', {})
    analyst_targets = analyst_data.get('price_target', {})

    target = None
    target_low = None
    target_high = None
    target_source = None

    if price_target_data.get('target_consensus'):
        target = price_target_data['target_consensus']
        target_low = price_target_data.get('target_low')
        target_high = price_target_data.get('target_high')
        target_source = price_target_data.get('source', 'fmp')
    elif analyst_targets.get('target_median'):
        target = analyst_targets['target_median']
        target_low = analyst_targets.get('target_low')
        target_high = analyst_targets.get('target_high')
        target_source = 'finnhub'

    if target:
        pt_str = f"Price target: ${target:.2f} consensus"
        if target_low and target_high:
            pt_str += f" (range ${target_low} — ${target_high})"
        pt_str += f" [source: {target_source}]."
        parts.append(pt_str)

    # Current stock price
    quote = external_context.get('stock_quote', {})
    price = float(quote.get('current_price', 0)) if quote else 0
    if price and target:
        upside_pct = ((target - price) / price) * 100
        parts.append(f"Current price: ${price:.2f} ({upside_pct:+.1f}% vs consensus target).")

    # EPS/Revenue estimates from Finnhub or StockAnalysis
    estimates_data = external_context.get('consensus_estimates', {})
    eps_estimates = estimates_data.get('eps_estimates', [])
    rev_estimates = estimates_data.get('revenue_estimates', [])
    est_source = estimates_data.get('source', 'unknown')

    if eps_estimates:
        next_q = eps_estimates[0]
        period = next_q.get('period', 'next quarter')
        eps_avg = next_q.get('eps_avg')
        eps_high = next_q.get('eps_high')
        eps_low = next_q.get('eps_low')
        n_analysts = next_q.get('number_analysts')
        if eps_avg is not None:
            eps_str = f"EPS estimate: ${eps_avg:.2f}"
            if eps_low is not None and eps_high is not None:
                eps_str += f" (range ${eps_low:.2f} — ${eps_high:.2f})"
            if n_analysts:
                eps_str += f" ({n_analysts} analysts)"
            eps_str += f" for {period} [{est_source}]."
            parts.append(eps_str)

    if rev_estimates:
        next_q = rev_estimates[0]
        rev_avg = next_q.get('revenue_avg')
        if rev_avg is not None:
            if rev_avg >= 1e9:
                rev_str = f"Revenue estimate: ${rev_avg/1e9:.2f}B"
            else:
                rev_str = f"Revenue estimate: ${rev_avg/1e6:.0f}M"
            rev_high = next_q.get('revenue_high')
            rev_low = next_q.get('revenue_low')
            if rev_low is not None and rev_high is not None:
                if rev_low >= 1e9:
                    rev_str += f" (range ${rev_low/1e9:.2f}B — ${rev_high/1e9:.2f}B)"
                else:
                    rev_str += f" (range ${rev_low/1e6:.0f}M — ${rev_high/1e6:.0f}M)"
            rev_str += f" [{est_source}]."
            parts.append(rev_str)

    return ' '.join(parts)


def fetch_stockanalysis_price_target(ticker):
    """
    Scrape consensus price target from StockAnalysis.com.
    Returns dict with target_consensus, target_low, target_high, num_analysts.
    """
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/forecast/"
    hdrs = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        resp = requests.get(url, headers=hdrs, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ✗ StockAnalysis price target fetch failed for {ticker}: {e}")
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')

    result = {}
    try:
        # Look for the analyst price target data in the page
        # StockAnalysis uses structured data — look for price target text patterns
        text = soup.get_text()

        # Extract consensus/average price target
        import re as _re
        avg_match = _re.search(r'(?:average|consensus)\s+(?:price\s+)?target\s+(?:of\s+|is\s+)?\$?([\d,.]+)', text, _re.IGNORECASE)
        if avg_match:
            result['target_consensus'] = float(avg_match.group(1).replace(',', ''))

        # Extract high target
        high_match = _re.search(r'high\s+(?:forecast|target)\s+(?:of\s+)?\$?([\d,.]+)', text, _re.IGNORECASE)
        if high_match:
            result['target_high'] = float(high_match.group(1).replace(',', ''))

        # Extract low target
        low_match = _re.search(r'low\s+(?:forecast|target)\s+(?:of\s+)?\$?([\d,.]+)', text, _re.IGNORECASE)
        if low_match:
            result['target_low'] = float(low_match.group(1).replace(',', ''))

        # Extract analyst count
        count_match = _re.search(r'(\d+)\s+(?:Wall\s+Street\s+)?analysts', text, _re.IGNORECASE)
        if count_match:
            result['num_analysts'] = int(count_match.group(1))

        if not result.get('target_consensus'):
            # Try alternative: look for the main price target number in structured elements
            for el in soup.select('[data-test]'):
                dt = el.get('data-test', '')
                if 'price-target' in dt.lower():
                    val_text = el.get_text(strip=True).replace('$', '').replace(',', '')
                    try:
                        result['target_consensus'] = float(val_text)
                    except ValueError:
                        pass

        if result.get('target_consensus'):
            result['source'] = 'stockanalysis'
            print(f"  ✓ StockAnalysis: {ticker} target ${result['target_consensus']:.2f}")
            return result
        else:
            print(f"  ✗ StockAnalysis: could not parse price target for {ticker}")
            return None

    except Exception as e:
        print(f"  ✗ StockAnalysis parse error for {ticker}: {e}")
        return None


def fetch_finnhub_estimates(ticker, metric='eps', freq='quarterly', api_key=None):
    """
    Fetch consensus estimates from Finnhub EPS/revenue estimate endpoints.
    Returns list of estimate dicts or None if endpoint not accessible.

    Args:
        ticker: Company ticker
        metric: 'eps' or 'revenue'
        freq: 'quarterly' or 'annual'
        api_key: optional override
    """
    key = api_key or FINNHUB_API_KEY
    if not key:
        return None

    endpoint_map = {
        'eps': 'eps-estimate',
        'revenue': 'revenue-estimate',
    }
    endpoint = endpoint_map.get(metric)
    if not endpoint:
        return None

    url = f"https://finnhub.io/api/v1/stock/{endpoint}"
    params = {'symbol': ticker, 'freq': freq, 'token': key}

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 403:
            return None  # Endpoint not accessible on current plan
        response.raise_for_status()
        data = response.json()
        if not data or not data.get('data'):
            return None

        estimates = []
        for est in data['data'][:4]:
            entry = {
                'period': est.get('period', ''),
                f'{metric}_avg': est.get(f'{metric}Avg'),
                f'{metric}_high': est.get(f'{metric}High'),
                f'{metric}_low': est.get(f'{metric}Low'),
                'number_analysts': est.get('numberAnalysts'),
            }
            estimates.append(entry)

        if estimates:
            print(f"  ✓ Finnhub {metric} estimates: {len(estimates)} periods")
        return estimates
    except Exception as e:
        print(f"  ✗ Finnhub {metric} estimates failed for {ticker}: {e}")
        return None


def fetch_stockanalysis_estimates(ticker):
    """
    Scrape quarterly EPS and revenue estimates from StockAnalysis.com.
    Returns dict with eps_estimates and revenue_estimates lists,
    or None on failure.
    """
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/forecast/?p=quarterly"
    hdrs = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        resp = requests.get(url, headers=hdrs, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ✗ StockAnalysis estimates fetch failed for {ticker}: {e}")
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')
    text = soup.get_text()

    result = {'eps_estimates': [], 'revenue_estimates': [], 'source': 'stockanalysis'}

    try:
        # Extract EPS estimates — look for patterns like "EPS Forecast: $X.XX"
        # StockAnalysis shows quarterly estimates in tables
        tables = soup.find_all('table')

        for table in tables:
            headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
            rows = table.find_all('tr')[1:]  # Skip header row

            # Identify EPS table (has columns like "EPS Estimate" or "Earnings Estimate")
            is_eps = any('eps' in h or 'earnings' in h for h in headers)
            is_revenue = any('revenue' in h for h in headers)

            if not (is_eps or is_revenue):
                continue

            for row in rows[:4]:  # Up to 4 quarters
                cells = [td.get_text(strip=True) for td in row.find_all('td')]
                if len(cells) < 2:
                    continue

                period = cells[0] if cells else ''

                # Parse numeric values, removing $, B, M, commas
                def parse_val(s):
                    if not s or s in ('N/A', '-', '--'):
                        return None
                    s = s.replace('$', '').replace(',', '').strip()
                    multiplier = 1
                    if s.endswith('B'):
                        s = s[:-1]
                        multiplier = 1e9
                    elif s.endswith('M'):
                        s = s[:-1]
                        multiplier = 1e6
                    elif s.endswith('K'):
                        s = s[:-1]
                        multiplier = 1e3
                    try:
                        return float(s) * multiplier
                    except ValueError:
                        return None

                if is_eps and not is_revenue:
                    # Try to find avg/consensus estimate
                    estimate = parse_val(cells[1]) if len(cells) > 1 else None
                    high = parse_val(cells[2]) if len(cells) > 2 else None
                    low = parse_val(cells[3]) if len(cells) > 3 else None
                    analysts = None
                    for c in cells:
                        if c.isdigit() and int(c) < 100:
                            analysts = int(c)
                            break
                    if estimate is not None:
                        result['eps_estimates'].append({
                            'period': period,
                            'eps_avg': estimate,
                            'eps_high': high,
                            'eps_low': low,
                            'number_analysts': analysts,
                        })

                elif is_revenue:
                    estimate = parse_val(cells[1]) if len(cells) > 1 else None
                    high = parse_val(cells[2]) if len(cells) > 2 else None
                    low = parse_val(cells[3]) if len(cells) > 3 else None
                    analysts = None
                    for c in cells:
                        if c.isdigit() and int(c) < 100:
                            analysts = int(c)
                            break
                    if estimate is not None:
                        result['revenue_estimates'].append({
                            'period': period,
                            'revenue_avg': estimate,
                            'revenue_high': high,
                            'revenue_low': low,
                            'number_analysts': analysts,
                        })

        if result['eps_estimates'] or result['revenue_estimates']:
            print(f"  ✓ StockAnalysis estimates: {len(result['eps_estimates'])} EPS, {len(result['revenue_estimates'])} revenue periods")
            return result
        else:
            # Fallback: try regex extraction from page text
            eps_match = re.search(r'(?:EPS|earnings)\s+(?:estimate|forecast)\s+(?:of\s+)?\$?([\d.]+)', text, re.IGNORECASE)
            rev_match = re.search(r'revenue\s+(?:estimate|forecast)\s+(?:of\s+)?\$?([\d.,]+[BMK]?)', text, re.IGNORECASE)

            if eps_match:
                result['eps_estimates'].append({
                    'period': 'next_quarter',
                    'eps_avg': float(eps_match.group(1)),
                    'eps_high': None,
                    'eps_low': None,
                    'number_analysts': None,
                })
            if rev_match:
                val_str = rev_match.group(1).replace(',', '')
                multiplier = 1
                if val_str.endswith('B'):
                    val_str = val_str[:-1]
                    multiplier = 1e9
                elif val_str.endswith('M'):
                    val_str = val_str[:-1]
                    multiplier = 1e6
                try:
                    result['revenue_estimates'].append({
                        'period': 'next_quarter',
                        'revenue_avg': float(val_str) * multiplier,
                        'revenue_high': None,
                        'revenue_low': None,
                        'number_analysts': None,
                    })
                except ValueError:
                    pass

            if result['eps_estimates'] or result['revenue_estimates']:
                print(f"  ✓ StockAnalysis estimates (regex): {len(result['eps_estimates'])} EPS, {len(result['revenue_estimates'])} revenue")
                return result

            print(f"  ✗ StockAnalysis: could not parse estimates for {ticker}")
            return None

    except Exception as e:
        print(f"  ✗ StockAnalysis estimates parse error for {ticker}: {e}")
        return None


def get_industry_context(conn, industry_profile, company_ticker=None):
    """
    Fetch all external data sources defined in an industry profile.
    Returns a structured dict with current market context.

    Args:
        conn: database connection
        industry_profile: dict with external_sources JSONB config
        company_ticker: optional ticker for per-company data sources (e.g., Finnhub)
    """
    if not industry_profile:
        return {}

    external_sources = industry_profile.get('external_sources', [])
    if isinstance(external_sources, str):
        external_sources = json.loads(external_sources)

    context = {}
    today = date.today().isoformat()

    for source in external_sources:
        source_type = source.get('type', '')
        api = source.get('api', '')
        display_name = source.get('display_name', '')
        unit = source.get('unit', '')
        context_key = source.get('context_key', source.get('series_id', source_type).lower())

        if source_type == 'commodity_price' and api == 'eia':
            cached = get_cached_value(conn, 'eia', source['series_id'])
            if cached and str(cached[2]) >= (date.today() - timedelta(days=3)).isoformat():
                context[context_key] = {
                    'price': float(cached[0]),
                    'date': str(cached[2]),
                    'unit': unit,
                    'display_name': display_name,
                    'source': 'cache'
                }
            else:
                spot = fetch_eia_spot()
                if spot:
                    context[context_key] = {
                        'price': spot['price'],
                        'date': spot['date'],
                        'unit': unit,
                        'display_name': display_name,
                        'source': 'eia'
                    }
                    cache_value(conn, 'eia', source['series_id'], spot['date'], spot['price'], unit)

        elif source_type == 'commodity_data' and api == 'eia':
            endpoint = source.get('endpoint', '')
            facets = source.get('facets', {})
            frequency = source.get('frequency', 'weekly')
            series_id = source.get('series_id', '')

            cached = get_cached_value(conn, 'eia', series_id)
            if cached and str(cached[2]) >= (date.today() - timedelta(days=3)).isoformat():
                context[context_key] = {
                    'value': float(cached[0]),
                    'date': str(cached[2]),
                    'unit': unit,
                    'display_name': display_name,
                    'source': 'cache'
                }
            else:
                result = fetch_eia_data(endpoint, facets, frequency=frequency)
                if result:
                    context[context_key] = {
                        'value': result['value'],
                        'date': result['date'],
                        'unit': unit,
                        'display_name': display_name,
                        'source': 'eia'
                    }
                    cache_value(conn, 'eia', series_id, result['date'], result['value'], unit)

        elif source_type == 'futures_curve' and api == 'yahoo':
            months = source.get('months_out', [3, 6, 12, 18, 24])
            futures = fetch_yahoo_futures(months)
            curve = {}
            for key, val in futures.items():
                if val:
                    curve[key] = val
                    cache_value(conn, 'yahoo', val['contract'], today, val['price'], unit)
            if curve:
                context[context_key] = curve
                prices = [v['price'] for v in curve.values() if v]
                if len(prices) >= 2:
                    context['curve_shape'] = 'backwardation' if prices[0] < prices[-1] else 'contango'
                # Compute strip averages
                strip = compute_strip_average(curve)
                if strip:
                    context['strip_averages'] = strip

        elif source_type == 'economic_indicator' and api == 'fred':
            cached = get_cached_value(conn, 'fred', source['series_id'])
            if cached and str(cached[2]) >= (date.today() - timedelta(days=3)).isoformat():
                context[context_key] = {
                    'value': float(cached[0]),
                    'date': str(cached[2]),
                    'unit': unit,
                    'display_name': display_name,
                    'source': 'cache'
                }
            else:
                fred_data = fetch_fred_data(source['series_id'])
                if fred_data:
                    context[context_key] = {
                        'value': fred_data['value'],
                        'date': fred_data['date'],
                        'unit': unit,
                        'display_name': display_name,
                        'source': 'fred'
                    }
                    cache_value(conn, 'fred', source['series_id'], fred_data['date'], fred_data['value'], unit)

        elif source_type == 'stock_quote' and api == 'finnhub':
            if not company_ticker:
                continue
            # Always fetch fresh — quotes change intraday, caching loses high/low/change
            time.sleep(1)  # Finnhub rate limiting
            quote = fetch_finnhub_quote(company_ticker)
            if quote:
                context[context_key] = {
                    **quote,
                    'display_name': f'{company_ticker} Stock Quote',
                    'source': 'finnhub'
                }

        elif source_type == 'analyst_data' and api == 'finnhub':
            if not company_ticker:
                continue
            time.sleep(1)  # Finnhub rate limiting
            recs = fetch_finnhub_recommendations(company_ticker)
            time.sleep(1)
            targets = fetch_finnhub_price_target(company_ticker)
            analyst_context = {}
            if recs:
                analyst_context['recommendations'] = recs
            if targets:
                analyst_context['price_target'] = targets
            if analyst_context:
                analyst_context['display_name'] = f'{company_ticker} Analyst Data'
                context[context_key] = analyst_context

        elif source_type == 'analyst_estimates':
            if not company_ticker:
                continue
            # Try Finnhub first (structured API), fall back to StockAnalysis (scraping)
            time.sleep(1)
            finnhub_eps = fetch_finnhub_estimates(company_ticker, 'eps')
            finnhub_rev = fetch_finnhub_estimates(company_ticker, 'revenue') if finnhub_eps else None

            if finnhub_eps:
                context[context_key] = {
                    'eps_estimates': finnhub_eps,
                    'revenue_estimates': finnhub_rev or [],
                    'display_name': f'{company_ticker} Consensus Estimates',
                    'source': 'finnhub'
                }
            else:
                time.sleep(1)
                sa_estimates = fetch_stockanalysis_estimates(company_ticker)
                if sa_estimates:
                    context[context_key] = {
                        'eps_estimates': sa_estimates.get('eps_estimates', []),
                        'revenue_estimates': sa_estimates.get('revenue_estimates', []),
                        'display_name': f'{company_ticker} Consensus Estimates',
                        'source': 'stockanalysis'
                    }

        elif source_type == 'price_target':
            if not company_ticker:
                continue
            # Try StockAnalysis first (more accurate), fall back to FMP
            time.sleep(1)
            targets = fetch_stockanalysis_price_target(company_ticker)
            if not targets and api == 'fmp':
                targets = fetch_fmp_price_target(company_ticker)
                if targets:
                    targets['source'] = 'fmp'
            if targets:
                context[context_key] = {
                    **targets,
                    'display_name': f'{company_ticker} Price Target Consensus',
                }

        elif source_type == 'analyst_grades' and api == 'fmp':
            if not company_ticker:
                continue
            time.sleep(1)
            grades = fetch_fmp_grades(company_ticker)
            if grades:
                context[context_key] = {
                    'grades': grades,
                    'display_name': f'{company_ticker} Recent Analyst Grades',
                    'source': 'fmp'
                }

        elif source_type == 'insider_activity' and api == 'edgar':
            if not company_ticker:
                continue
            # Look up CIK from companies table
            cursor = conn.cursor()
            cursor.execute("SELECT cik FROM companies WHERE ticker = %s", (company_ticker,))
            row = cursor.fetchone()
            cursor.close()
            if not row:
                continue
            cik = row[0]
            days_back = source.get('days_back', 90)
            insider = fetch_edgar_insider_transactions(cik, days_back=days_back)
            if insider:
                context[context_key] = {
                    **insider,
                    'display_name': f'{company_ticker} Insider Transactions',
                    'source': 'edgar'
                }

    return context


if __name__ == "__main__":
    """Test external data fetching."""
    print("=" * 70)
    print("EXTERNAL DATA FETCH TEST")
    print("=" * 70)

    conn = connect_db()
    if not conn:
        exit(1)

    from psycopg2.extras import RealDictCursor
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM industry_profiles WHERE sic_code = '1311'")
    profile = cursor.fetchone()
    cursor.close()

    if not profile:
        print("✗ No industry profile found for SIC 1311")
        conn.close()
        exit(1)

    print(f"\nIndustry: {profile['industry_name']}")
    print(f"Sector: {profile['sector']}\n")

    # Use ticker from command line or default to EQT
    import sys
    test_ticker = sys.argv[1].upper() if len(sys.argv) > 1 else 'EQT'

    print(f"Fetching external context for {test_ticker}...")
    context = get_industry_context(conn, profile, company_ticker=test_ticker)

    print(f"\n{'=' * 70}")
    print("RESULTS")
    print(f"{'=' * 70}")
    print(json.dumps(context, indent=2, default=str))

    # Test news populator if Finnhub key is available
    if FINNHUB_API_KEY:
        print(f"\nFetching news for {test_ticker}...")
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT id FROM companies WHERE ticker = %s", (test_ticker,))
        company = cursor.fetchone()
        cursor.close()
        if company:
            count = populate_company_news(conn, company['id'], test_ticker)
            print(f"  ✓ Inserted {count} new articles into data_sources")
        else:
            print(f"  — Company {test_ticker} not found in DB")

    # Test transcript populator (FMP → Motley Fool fallback)
    print(f"\nFetching earnings transcript for {test_ticker}...")
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT id FROM companies WHERE ticker = %s", (test_ticker,))
    company = cursor.fetchone()
    cursor.close()
    if company:
        if populate_earnings_transcript(conn, company['id'], test_ticker):
            print(f"  ✓ New transcript stored")
        else:
            print(f"  — Transcript already cached or unavailable")
    else:
        print(f"  — Company {test_ticker} not found in DB")

    conn.close()
    print("\n✓ Done")
