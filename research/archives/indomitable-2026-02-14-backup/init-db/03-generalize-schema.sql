-- Schema migration: Generalize for multi-company, multi-industry support
-- Run against existing sec_filings database

-- ============================================================
-- New table: industry_profiles
-- ============================================================
CREATE TABLE IF NOT EXISTS industry_profiles (
    id SERIAL PRIMARY KEY,
    sic_code VARCHAR(10) NOT NULL,
    industry_name VARCHAR(100) NOT NULL,
    sector VARCHAR(100),
    key_metrics JSONB NOT NULL DEFAULT '[]',
    prompt_context TEXT NOT NULL DEFAULT '',
    external_sources JSONB NOT NULL DEFAULT '[]',
    peer_group_sic_codes JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- New table: data_sources (press releases, earnings calls, etc.)
-- ============================================================
CREATE TABLE IF NOT EXISTS data_sources (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    source_type VARCHAR(50) NOT NULL,
    source_url TEXT,
    title VARCHAR(500),
    published_date DATE,
    content TEXT,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_data_sources_company_id ON data_sources(company_id);
CREATE INDEX IF NOT EXISTS idx_data_sources_type ON data_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_data_sources_date ON data_sources(published_date);

-- ============================================================
-- New table: external_context_cache (EIA, Yahoo Finance, FRED)
-- ============================================================
CREATE TABLE IF NOT EXISTS external_context_cache (
    id SERIAL PRIMARY KEY,
    source_api VARCHAR(50) NOT NULL,
    series_id VARCHAR(100) NOT NULL,
    data_date DATE NOT NULL,
    value DECIMAL(20, 6),
    unit VARCHAR(50),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_api, series_id, data_date)
);

CREATE INDEX IF NOT EXISTS idx_external_cache_lookup ON external_context_cache(source_api, series_id, data_date);

-- ============================================================
-- Alter companies: add industry profile link and watchlist fields
-- ============================================================
ALTER TABLE companies ADD COLUMN IF NOT EXISTS industry_profile_id INTEGER REFERENCES industry_profiles(id);
ALTER TABLE companies ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS watchlist_priority VARCHAR(20) DEFAULT 'standard';

-- ============================================================
-- Alter intelligence_reports: add generalization columns
-- ============================================================
ALTER TABLE intelligence_reports ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id);
ALTER TABLE intelligence_reports ADD COLUMN IF NOT EXISTS comparison_filing_id INTEGER REFERENCES filings(id);
ALTER TABLE intelligence_reports ADD COLUMN IF NOT EXISTS industry_context JSONB;
ALTER TABLE intelligence_reports ADD COLUMN IF NOT EXISTS peer_data JSONB;
ALTER TABLE intelligence_reports ADD COLUMN IF NOT EXISTS generation_metadata JSONB;

-- ============================================================
-- Seed: Natural gas industry profile
-- ============================================================
INSERT INTO industry_profiles (sic_code, industry_name, sector, key_metrics, prompt_context, external_sources)
VALUES (
    '1311',
    'Crude Petroleum & Natural Gas',
    'Energy - Upstream',
    '["production_volume_bcfe", "proved_reserves_tcfe", "average_realized_price", "cash_operating_cost_per_mcfe", "net_debt_to_ebitda", "free_cash_flow", "hedging_percentage"]',
    'You are analyzing a natural gas exploration and production company. Key value drivers for this sector include: production volumes (measured in Bcfe or equivalent), proved reserves base and reserve replacement ratio, realized natural gas prices relative to Henry Hub benchmarks, basis differentials between production basins and trading hubs, gathering/processing/transportation costs per Mcfe, drilling efficiency and well productivity, hedging portfolio coverage and pricing, and free cash flow generation. The natural gas market is heavily influenced by weather patterns, LNG export capacity, pipeline constraints, and the pace of associated gas production from oil-directed drilling.',
    '[{"type":"commodity_price","api":"eia","series_id":"RNGWHHD","display_name":"Henry Hub Natural Gas Spot Price","unit":"$/MMBtu"},{"type":"futures_curve","api":"yahoo","months_out":[3,6,12,18,24],"display_name":"NYMEX Natural Gas Futures","unit":"$/MMBtu"},{"type":"economic_indicator","api":"fred","series_id":"DCOILWTICO","display_name":"WTI Crude Oil Price","unit":"$/barrel"}]'
)
ON CONFLICT DO NOTHING;

-- ============================================================
-- Update EQT: link to industry profile, set as primary
-- ============================================================
UPDATE companies
SET industry_profile_id = (SELECT id FROM industry_profiles WHERE sic_code = '1311' LIMIT 1),
    active = TRUE,
    watchlist_priority = 'primary'
WHERE ticker = 'EQT';

-- ============================================================
-- Grant privileges on new tables
-- ============================================================
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO sec_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO sec_user;
