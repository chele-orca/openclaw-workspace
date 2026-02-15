-- 07-guidance-history.sql
-- Guidance history tracking + management credibility support
-- Date: 2026-02-12

-- ============================================================
-- guidance_history (tracks every guidance number with date)
-- ============================================================
-- Captures every guidance issuance so we can compute:
-- "Capex guidance was $840M in Q3 2024, revised to $1.0-1.1B in Q1 2025,
--  now $1.4-1.5B for 2026 = 67-79% increase over 18 months"
CREATE TABLE IF NOT EXISTS guidance_history (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) NOT NULL,
    metric_name VARCHAR(255) NOT NULL,       -- 'capex_guidance', 'production_guidance', etc.
    guidance_value_low DECIMAL(20,6),
    guidance_value_high DECIMAL(20,6),
    guidance_unit VARCHAR(50),
    guidance_period VARCHAR(50),             -- '2026', 'FY2026', etc.
    source_filing_id INTEGER REFERENCES filings(id),
    source_date DATE NOT NULL,
    superseded_by INTEGER REFERENCES guidance_history(id),  -- points to revision
    revision_pct DECIMAL(10,2),             -- % change from prior guidance
    revision_reason TEXT,                   -- stated reason for change
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_guidance_history_company_metric
    ON guidance_history(company_id, metric_name);

-- ============================================================
-- Add management_credibility to investment_theses
-- ============================================================
ALTER TABLE investment_theses
    ADD COLUMN IF NOT EXISTS management_credibility TEXT;

-- ============================================================
-- Update position_type constraint to include pass/avoid/sell
-- ============================================================
-- Drop old constraint if exists, add new one
-- (safe: IF NOT EXISTS on CHECK constraints not supported, use DO block)
DO $$
BEGIN
    -- Remove any existing check constraint on position_type
    ALTER TABLE investment_theses DROP CONSTRAINT IF EXISTS investment_theses_position_type_check;
    -- Add new constraint allowing own/pass/avoid/sell
    ALTER TABLE investment_theses
        ADD CONSTRAINT investment_theses_position_type_check
        CHECK (position_type IN ('own', 'pass', 'avoid', 'sell'));
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'position_type constraint update: %', SQLERRM;
END $$;

-- Grant permissions to sec_user
GRANT ALL ON guidance_history TO sec_user;
GRANT USAGE, SELECT ON SEQUENCE guidance_history_id_seq TO sec_user;

-- ============================================================
-- Update E&P industry_profiles.prompt_context with macro framework
-- ============================================================
UPDATE industry_profiles
SET prompt_context = 'You are analyzing a natural gas exploration and production company.

=== MACRO FRAMEWORK (address FIRST, before company specifics) ===

DEMAND DRIVERS for US natural gas:
- Residential/commercial heating (~30% of demand, weather-sensitive)
- Power generation (~35%, growing with coal retirements and data centers)
- Industrial use (~25%, steady)
- LNG exports (~14 Bcf/d in 2025, growing to 20+ Bcf/d by 2028 with new terminals)
- Data centers: AI-driven power demand is real but often overstated — even 50-100 GW of new data center load = ~7-10 Bcf/d at gas-fired generation rates, but 200+ GW of renewables under development will offset much of this

SUPPLY DRIVERS:
- Permian associated gas (~8 Bcf/d and growing): produced as byproduct of oil drilling, output grows regardless of gas price
- Appalachian production (Marcellus/Utica): mature, pipeline-constrained, growth limited
- Haynesville production: most price-sensitive basin, producers add/curtail based on gas price economics
- Key dynamic: Permian associated gas growth can offset incremental demand growth, capping gas prices

KEY QUESTION: At what gas price does supply growth = demand growth? If the answer is below $4/MMBtu, pure-play gas producers with high breakeven costs face structural headwinds.

=== COMPANY ANALYSIS FRAMEWORK ===

Key value drivers: production volumes (Bcfe), proved reserves and replacement ratio, realized prices vs Henry Hub, basis differentials, operating costs per Mcfe, drilling efficiency, hedging portfolio, and free cash flow generation. The natural gas market is heavily influenced by weather patterns, LNG export capacity, pipeline constraints, and Permian associated gas production.',
    updated_at = CURRENT_TIMESTAMP
WHERE sic_code = '1311';
