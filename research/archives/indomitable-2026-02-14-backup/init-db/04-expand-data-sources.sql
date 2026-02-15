-- 04-expand-data-sources.sql
-- Expands industry profiles, adds new companies, updates external_sources config
-- Date: 2026-02-11

-- ============================================================
-- Prerequisites: unique constraint on sic_code for ON CONFLICT
-- ============================================================
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'industry_profiles_sic_code_key') THEN
        ALTER TABLE industry_profiles ADD CONSTRAINT industry_profiles_sic_code_key UNIQUE (sic_code);
    END IF;
END $$;

-- ============================================================
-- Update existing SIC 1311 profile: add context_key fields + new FRED series
-- ============================================================
UPDATE industry_profiles
SET external_sources = '[
  {"type":"commodity_price","api":"eia","series_id":"RNGWHHD","context_key":"henry_hub_spot","display_name":"Henry Hub Natural Gas Spot Price","unit":"$/MMBtu"},
  {"type":"futures_curve","api":"yahoo","months_out":[3,6,12,18,24],"context_key":"forward_curve","display_name":"NYMEX Natural Gas Futures","unit":"$/MMBtu"},
  {"type":"economic_indicator","api":"fred","series_id":"DCOILWTICO","context_key":"wti_crude","display_name":"WTI Crude Oil Price","unit":"$/barrel"},
  {"type":"economic_indicator","api":"fred","series_id":"DFF","context_key":"fed_funds_rate","display_name":"Federal Funds Effective Rate","unit":"%"},
  {"type":"economic_indicator","api":"fred","series_id":"T10Y2Y","context_key":"yield_curve_spread","display_name":"10Y-2Y Treasury Spread","unit":"%"},
  {"type":"economic_indicator","api":"fred","series_id":"CPIAUCSL","context_key":"cpi","display_name":"CPI Urban Consumers","unit":"index"},
  {"type":"economic_indicator","api":"fred","series_id":"INDPRO","context_key":"industrial_production","display_name":"Industrial Production Index","unit":"index"}
]'::jsonb
WHERE sic_code = '1311';

-- ============================================================
-- New industry profile: Midstream Natural Gas (SIC 4922)
-- ============================================================
INSERT INTO industry_profiles (sic_code, industry_name, sector, key_metrics, prompt_context, external_sources)
VALUES (
    '4922',
    'Natural Gas Transmission & Distribution',
    'Energy - Midstream',
    '["throughput_volume_bcf", "revenue", "ebitda", "distributable_cash_flow", "distribution_coverage_ratio", "contracted_capacity_pct", "capex_growth_vs_maintenance", "net_debt_to_ebitda"]'::jsonb,
    'You are analyzing a midstream natural gas company (gathering, processing, transmission, or distribution). Key value drivers include: contracted capacity and utilization rates, throughput volumes, fee-based vs commodity-exposed revenue mix, distributable cash flow and distribution coverage ratios, growth capex vs maintenance capex, customer counterparty credit quality, regulatory/tariff changes, and pipeline expansion project execution. Midstream companies are valued primarily on distributable cash flow yield and EBITDA multiples, with less direct commodity price exposure than upstream producers.',
    '[
      {"type":"commodity_price","api":"eia","series_id":"RNGWHHD","context_key":"henry_hub_spot","display_name":"Henry Hub Natural Gas Spot Price","unit":"$/MMBtu"},
      {"type":"futures_curve","api":"yahoo","months_out":[3,6,12,18,24],"context_key":"forward_curve","display_name":"NYMEX Natural Gas Futures","unit":"$/MMBtu"},
      {"type":"economic_indicator","api":"fred","series_id":"DCOILWTICO","context_key":"wti_crude","display_name":"WTI Crude Oil Price","unit":"$/barrel"},
      {"type":"economic_indicator","api":"fred","series_id":"DFF","context_key":"fed_funds_rate","display_name":"Federal Funds Effective Rate","unit":"%"},
      {"type":"economic_indicator","api":"fred","series_id":"T10Y2Y","context_key":"yield_curve_spread","display_name":"10Y-2Y Treasury Spread","unit":"%"},
      {"type":"economic_indicator","api":"fred","series_id":"CPIAUCSL","context_key":"cpi","display_name":"CPI Urban Consumers","unit":"index"}
    ]'::jsonb
) ON CONFLICT (sic_code) DO NOTHING;

-- ============================================================
-- New industry profile: Big Tech / Cloud Computing (SIC 7372)
-- ============================================================
INSERT INTO industry_profiles (sic_code, industry_name, sector, key_metrics, prompt_context, external_sources)
VALUES (
    '7372',
    'Prepackaged Software & Cloud Computing',
    'Technology',
    '["revenue", "revenue_growth_yoy", "operating_income", "operating_margin", "free_cash_flow", "cloud_revenue", "cloud_revenue_growth", "capex", "headcount", "earnings_per_share"]'::jsonb,
    'You are analyzing a large-cap technology and cloud computing company. Key value drivers include: total revenue growth and acceleration/deceleration trends, cloud/infrastructure segment revenue and growth rates, operating margins and margin trajectory, capital expenditure (especially AI/data center investment), free cash flow generation and capital return programs (buybacks, dividends), competitive positioning in cloud (AWS vs Azure vs GCP), AI product monetization progress, and regulatory risks (antitrust, data privacy, international). Technology companies are valued primarily on revenue growth, margin expansion potential, and free cash flow yield.',
    '[
      {"type":"economic_indicator","api":"fred","series_id":"DFF","context_key":"fed_funds_rate","display_name":"Federal Funds Effective Rate","unit":"%"},
      {"type":"economic_indicator","api":"fred","series_id":"T10Y2Y","context_key":"yield_curve_spread","display_name":"10Y-2Y Treasury Spread","unit":"%"},
      {"type":"economic_indicator","api":"fred","series_id":"CPIAUCSL","context_key":"cpi","display_name":"CPI Urban Consumers","unit":"index"},
      {"type":"economic_indicator","api":"fred","series_id":"PCEPI","context_key":"pce_price_index","display_name":"PCE Price Index","unit":"index"},
      {"type":"economic_indicator","api":"fred","series_id":"UNRATE","context_key":"unemployment_rate","display_name":"Unemployment Rate","unit":"%"}
    ]'::jsonb
) ON CONFLICT (sic_code) DO NOTHING;

-- ============================================================
-- New companies
-- ============================================================
INSERT INTO companies (ticker, cik, company_name, sic, sic_description, state_of_incorporation, fiscal_year_end)
VALUES
    ('CRK', '0000023194', 'Comstock Resources Inc', '1311', 'Crude Petroleum & Natural Gas', 'NV', '1231'),
    ('DTM', '0001859007', 'DT Midstream Inc', '4922', 'Natural Gas Transmission', 'DE', '1231'),
    ('AMZN', '0001018724', 'Amazon.com Inc', '5961', 'Catalog & Mail-Order Houses', 'DE', '1231'),
    ('MSFT', '0000789019', 'Microsoft Corp', '7372', 'Prepackaged Software', 'WA', '0630')
ON CONFLICT (ticker) DO NOTHING;

-- ============================================================
-- Link companies to industry profiles and set watchlist config
-- ============================================================
UPDATE companies SET
    industry_profile_id = (SELECT id FROM industry_profiles WHERE sic_code = '1311'),
    active = TRUE,
    watchlist_priority = 'standard'
WHERE ticker = 'CRK';

UPDATE companies SET
    industry_profile_id = (SELECT id FROM industry_profiles WHERE sic_code = '4922'),
    active = TRUE,
    watchlist_priority = 'standard'
WHERE ticker = 'DTM';

UPDATE companies SET
    industry_profile_id = (SELECT id FROM industry_profiles WHERE sic_code = '7372'),
    active = TRUE,
    watchlist_priority = 'standard'
WHERE ticker = 'AMZN';

UPDATE companies SET
    industry_profile_id = (SELECT id FROM industry_profiles WHERE sic_code = '7372'),
    active = TRUE,
    watchlist_priority = 'standard'
WHERE ticker = 'MSFT';

-- Add unique index on data_sources.source_url to prevent duplicate news/transcript insertions
CREATE UNIQUE INDEX IF NOT EXISTS idx_data_sources_unique_url
ON data_sources(source_url) WHERE source_url IS NOT NULL;
