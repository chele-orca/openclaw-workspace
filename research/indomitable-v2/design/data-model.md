# Indomitable 2.0 — Data Model

**Date:** 2026-02-14  
**Purpose:** Forward-compatible database schema for thesis-driven investment analysis

---

## Overview

This data model supports:

1. **Multi-ticker analysis** — Track multiple companies simultaneously
2. **Dynamic data discovery** — Sources discovered per company based on business type
3. **Thesis-driven investing** — Core "why own" document with validation
4. **Hypothesis tracking** — Pre/post earnings predictions with accuracy scoring
5. **Management accountability** — Guidance history and change tracking
6. **Continuous monitoring** — Data feeds confirming/disconfirming theses
7. **Future-ready** — Kill criteria, position sizing, backtesting built in

---

## Entity Relationship Diagram

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    companies    │────▶│  data_sources   │     │  earnings_events│
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                                              │
         │                                              │
         ▼                                              ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│     theses      │◀────│  hypotheses     │◀────│ pre_event_      │
│   (core doc)    │     │  (predictions)  │     │   hypotheses    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                                              │
         │                                              │
         ▼                                              ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ guidance_       │     │ monitoring_data │     │ post_event_     │
│   history       │     │ (continuous)    │     │   analysis      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                                              │
         │                                              │
         ▼                                              ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  kill_criteria  │     │     reports     │     │   positions     │
│   (future)      │     │   (output)      │     │   (future)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ backtest_results│
                       │   (future)      │
                       └─────────────────┘
```

---

## Core Tables

### 1. companies

The companies being analyzed.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Internal ID |
| ticker | VARCHAR(10) UNIQUE | Stock ticker (EQT, CRK, etc.) |
| name | VARCHAR(255) | Company name |
| sector | VARCHAR(100) | High-level sector (Energy, Tech, etc.) |
| industry | VARCHAR(100) | Specific industry (E&P, Software, etc.) |
| commodity_exposure | TEXT[] | Commodities if applicable ['natural_gas', 'oil'] |
| created_at | TIMESTAMP | When added to system |
| updated_at | TIMESTAMP | Last update |

---

### 2. data_sources

Dynamic data sources discovered per company based on business type.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Internal ID |
| company_id | INTEGER FK | → companies.id |
| source_type | VARCHAR(50) | 'sec_edgar', 'eia', 'yahoo_finance', 'fred', 'commodity_futures' |
| source_name | VARCHAR(100) | Human-readable name |
| config | JSONB | Source-specific config {ticker, cik, feed_url, etc.} |
| is_active | BOOLEAN | Is this source currently used? |
| discovery_date | TIMESTAMP | When we discovered this source |
| last_fetch | TIMESTAMP | Last successful fetch |
| fetch_frequency | VARCHAR(20) | 'daily', 'weekly', 'on_demand' |

---

### 3. theses

The core investment thesis — "why own this company."

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Internal ID |
| company_id | INTEGER FK | → companies.id |
| thesis_version | INTEGER | Version number (1, 2, 3...) |
| status | VARCHAR(20) | 'active', 'closed', 'invalidated' |
| investment_rationale | TEXT | The narrative — why this is a good investment |
| key_drivers | JSONB | ['roic_spread', 'commodity_recovery', 'cost_reduction'] |
| roic_wacc_spread | DECIMAL | Expected spread (the core metric) |
| competitive_moat | TEXT | Description of competitive advantage |
| conviction_level | INTEGER | 1-5 scale (future use) |
| target_position_size | DECIMAL | % of portfolio (future use) |
| created_at | TIMESTAMP | When thesis created |
| closed_at | TIMESTAMP | When thesis closed |
| closed_reason | VARCHAR(50) | 'thesis_played_out', 'thesis_broken', 'stopped_out' |

**Key Feature:** One company can have multiple theses over time. When a thesis breaks, close it and create a new one.

---

### 4. hypotheses

Individual predictions made to test the thesis — tracked for backtesting accuracy.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Internal ID |
| company_id | INTEGER FK | → companies.id |
| thesis_id | INTEGER FK | → theses.id |
| hypothesis_type | VARCHAR(50) | 'revenue', 'costs', 'capex', 'guidance', 'commodity_price' |
| metric_name | VARCHAR(100) | 'Q4_2025_Revenue', '2026_CapEx_Guidance' |
| predicted_value | DECIMAL | Our prediction |
| predicted_range_low | DECIMAL | Confidence interval lower bound |
| predicted_range_high | DECIMAL | Confidence interval upper bound |
| confidence_level | INTEGER | 1-5 confidence |
| prediction_date | TIMESTAMP | When we made this prediction |
| actual_value | DECIMAL | What actually happened |
| variance_percent | DECIMAL | ((actual - predicted) / predicted) * 100 |
| was_accurate | BOOLEAN | Within prediction range? |
| resolved_at | TIMESTAMP | When we got the actual data |
| source_earnings_event_id | INTEGER FK | → earnings_events.id |

**Key Feature:** Every prediction is tracked. This enables future backtesting of our accuracy.

---

### 5. earnings_events

Quarterly and annual earnings releases.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Internal ID |
| company_id | INTEGER FK | → companies.id |
| fiscal_quarter | INTEGER | 1, 2, 3, 4 |
| fiscal_year | INTEGER | 2025, 2026, etc. |
| event_type | VARCHAR(20) | 'Q1', 'Q2', 'Q3', 'Q4', 'Annual' |
| release_date | TIMESTAMP | Expected release date |
| release_datetime_actual | TIMESTAMP | When it actually dropped |
| pre_event_analysis_done | BOOLEAN | Did we generate pre-earnings hypotheses? |
| post_event_analysis_done | BOOLEAN | Did we complete post-earnings analysis? |
| reported_revenue | DECIMAL | From the filing |
| reported_ebitda | DECIMAL | From the filing |
| reported_capex | DECIMAL | From the filing |
| reported_ocf | DECIMAL | Operating cash flow |
| eps_actual | DECIMAL | Actual EPS |
| price_before | DECIMAL | Stock price before release |
| price_after | DECIMAL | Stock price after release |
| price_change_percent | DECIMAL | Market reaction |

---

### 6. guidance_history

Management guidance tracking — the "accountability" layer.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Internal ID |
| company_id | INTEGER FK | → companies.id |
| thesis_id | INTEGER FK | → theses.id |
| earnings_event_id | INTEGER FK | → earnings_events.id |
| guidance_type | VARCHAR(50) | 'capex', 'production', 'cost_guidance', 'revenue' |
| guidance_metric | VARCHAR(100) | '2026_Total_CapEx', 'Q4_Production_Growth' |
| guidance_value | DECIMAL | The guidance number |
| guidance_range_low | DECIMAL | Low end of range |
| guidance_range_high | DECIMAL | High end of range |
| guidance_qualifier | VARCHAR(50) | 'confirmed', 'raised', 'lowered', 'introduced', 'withdrawn' |
| prior_guidance_id | INTEGER FK | → guidance_history.id (self-reference) |
| change_reason | TEXT | Why did guidance change? |
| actual_result | DECIMAL | What actually happened (filled in later) |
| guidance_accuracy | DECIMAL | Variance from guidance to actual |

**Key Feature:** Self-referencing `prior_guidance_id` lets us track: "In Q3 they said $X, in Q4 they said $Y."

---

### 7. monitoring_data

Continuous data feed for thesis confirmation/disconfirmation.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Internal ID |
| company_id | INTEGER FK | → companies.id |
| thesis_id | INTEGER FK | → theses.id |
| data_type | VARCHAR(50) | 'commodity_price', 'stock_price', 'futures_curve', 'news', 'peer_comparison' |
| source | VARCHAR(100) | 'EIA', 'Yahoo Finance', 'SEC Filing' |
| data_date | TIMESTAMP | When this data point is from |
| raw_data | JSONB | Full data payload (flexible) |
| thesis_impact | VARCHAR(20) | 'confirms', 'disconfirms', 'neutral', 'unknown' |
| impact_notes | TEXT | Why this confirms or breaks thesis |
| alert_generated | BOOLEAN | Did we flag this for attention? |
| alert_sent_at | TIMESTAMP | When alert was delivered |

---

### 8. pre_event_hypotheses

Pre-earnings prediction package — what we expect to see.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Internal ID |
| earnings_event_id | INTEGER FK | → earnings_events.id |
| thesis_id | INTEGER FK | → theses.id |
| created_at | TIMESTAMP | When predictions made |
| hypothesis_summary | JSONB | All predictions for this event in one object |
| confidence_overall | INTEGER | 1-5 overall confidence |
| key_things_to_watch | TEXT[] | ['capex_guidance', 'cost_trends', 'production_growth'] |

---

### 9. post_event_analysis

Post-earnings comparison — how did we do?

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Internal ID |
| earnings_event_id | INTEGER FK | → earnings_events.id |
| thesis_id | INTEGER FK | → theses.id |
| hypothesis_vs_actual | JSONB | {metric: {predicted, actual, variance}} |
| guidance_changes | TEXT[] | List of what guidance changed |
| management_surprises | TEXT[] | Unexpected items |
| thesis_impact | VARCHAR(20) | 'strengthened', 'weakened', 'unchanged', 'invalidated' |
| thesis_impact_notes | TEXT | Narrative explanation |
| guidance_accuracy_score | DECIMAL | 0-100 — how accurate was prior guidance |
| promises_vs_delivery | TEXT | Summary of mgmt accountability |
| key_takeaways | TEXT[] | Bullet points for reports |
| recommended_action | VARCHAR(50) | 'hold', 'increase', 'decrease', 'close' |

---

### 10. kill_criteria

Automatic exit triggers (future implementation).

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Internal ID |
| thesis_id | INTEGER FK | → theses.id |
| criterion_type | VARCHAR(50) | 'stop_loss', 'thesis_break', 'valuation', 'time' |
| metric | VARCHAR(100) | 'stock_price', 'roic_spread', 'commodity_price' |
| operator | VARCHAR(10) | '<', '>', '=', '<=', '>=' |
| threshold_value | DECIMAL | Trigger point |
| is_triggered | BOOLEAN | Did this trigger? |
| triggered_at | TIMESTAMP | When it triggered |
| triggered_value | DECIMAL | The value that triggered it |

---

### 11. reports

Generated reports — HTML, PDF, email tracking.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Internal ID |
| company_id | INTEGER FK | → companies.id |
| thesis_id | INTEGER FK | → theses.id |
| earnings_event_id | INTEGER FK | → earnings_events.id (optional) |
| report_type | VARCHAR(50) | 'thesis_creation', 'pre_earnings', 'post_earnings', 'thesis_update' |
| format | VARCHAR(20) | 'html', 'pdf', 'email' |
| status | VARCHAR(20) | 'generating', 'ready', 'delivered', 'error' |
| file_path | VARCHAR(500) | Where the report lives |
| content_summary | TEXT | AI summary of report contents |
| generated_at | TIMESTAMP | When created |
| delivered_at | TIMESTAMP | When sent/viewed |
| delivery_method | VARCHAR(50) | 'email', 'web', 'slack', etc. |

---

### 12. positions

Portfolio positions (future implementation).

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Internal ID |
| company_id | INTEGER FK | → companies.id |
| thesis_id | INTEGER FK | → theses.id |
| entry_date | TIMESTAMP | When position opened |
| entry_price | DECIMAL | Entry price |
| shares | INTEGER | Number of shares |
| position_size_percent | DECIMAL | % of total portfolio |
| exit_date | TIMESTAMP | When closed |
| exit_price | DECIMAL | Exit price |
| pnl_percent | DECIMAL | Realized return |
| exit_reason | VARCHAR(50) | Why we closed |

---

### 13. backtest_results

Historical accuracy testing (future implementation).

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PRIMARY KEY | Internal ID |
| thesis_id | INTEGER FK | → theses.id |
| test_period_start | DATE | Start of backtest period |
| test_period_end | DATE | End of backtest period |
| hypothetical_entry_price | DECIMAL | Simulated entry |
| hypothetical_exit_price | DECIMAL | Simulated exit |
| hypothetical_return | DECIMAL | Simulated return % |
| thesis_accuracy_score | DECIMAL | 0-100 based on hypothesis accuracy |
| key_learnings | TEXT | What we learned from this backtest |

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Separate `theses` table** | One company can have multiple theses over time (evolution, invalidation, new thesis) |
| **Every prediction tracked** | `hypotheses` table enables future backtesting of our accuracy |
| **Self-referencing guidance** | `guidance_history.prior_guidance_id` tracks "they said X, then said Y" |
| **Continuous monitoring with impact scoring** | `monitoring_data` links data → thesis impact assessment |
| **Pre/post event separation** | Clean workflow: predict → compare → assess impact |
| **JSONB for flexibility** | Different companies have different metrics — JSONB accommodates variety |
| **Kill criteria as separate table** | Future feature ready — can trigger alerts when criteria met |

---

## Example Query Patterns

### How accurate are our revenue predictions?

```sql
SELECT 
    AVG(ABS(variance_percent)) as avg_variance,
    COUNT(*) as total_predictions,
    SUM(CASE WHEN was_accurate THEN 1 ELSE 0 END) as accurate_count
FROM hypotheses 
WHERE hypothesis_type = 'revenue' 
AND resolved_at IS NOT NULL;
```

### Which companies changed CapEx guidance recently?

```sql
SELECT 
    c.ticker, 
    c.name,
    gh.guidance_metric, 
    gh.guidance_qualifier,
    gh.change_reason,
    ee.fiscal_quarter,
    ee.fiscal_year
FROM guidance_history gh
JOIN companies c ON gh.company_id = c.id
JOIN earnings_events ee ON gh.earnings_event_id = ee.id
WHERE gh.guidance_qualifier IN ('raised', 'lowered')
AND gh.created_at > NOW() - INTERVAL '90 days'
ORDER BY gh.created_at DESC;
```

### What's confirming/disconfirming our active theses?

```sql
SELECT 
    c.ticker, 
    t.investment_rationale, 
    md.data_type, 
    md.thesis_impact,
    md.impact_notes,
    md.data_date
FROM monitoring_data md
JOIN companies c ON md.company_id = c.id
JOIN theses t ON md.thesis_id = t.id
WHERE t.status = 'active'
AND md.thesis_impact != 'neutral'
ORDER BY md.data_date DESC
LIMIT 20;
```

### Management guidance accuracy scorecard

```sql
SELECT 
    c.ticker,
    AVG(gh.guidance_accuracy) as avg_accuracy,
    COUNT(*) as total_guidance_items,
    SUM(CASE WHEN ABS(gh.guidance_accuracy) < 10 THEN 1 ELSE 0 END) as within_10_percent
FROM guidance_history gh
JOIN companies c ON gh.company_id = c.id
WHERE gh.actual_result IS NOT NULL
GROUP BY c.ticker
ORDER BY avg_accuracy ASC;
```

---

## Future Extensions

This model supports:

- ✅ Multi-ticker portfolios
- ✅ Backtesting prediction accuracy
- ✅ Kill criteria with automatic alerts
- ✅ Position sizing recommendations
- ✅ Management scorecards over time
- ✅ Peer comparison analysis
- ✅ Commodity-exposed business modeling

---

## Files

**Location:** `/Volumes/T4/openclaw/workspace/research/indomitable-v2/design/`

- `data-model.md` — This file
- Future: `schema.sql` — PostgreSQL DDL
- Future: `erd.png` — Visual diagram
