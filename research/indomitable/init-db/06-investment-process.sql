-- 06-investment-process.sql
-- Investment process redesign: thesis-driven analysis with testable hypotheses
-- Date: 2026-02-12

-- ============================================================
-- investment_theses (replaces company_theses)
-- ============================================================
CREATE TABLE IF NOT EXISTS investment_theses (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) NOT NULL,

    -- Core thesis
    position_type VARCHAR(20) NOT NULL DEFAULT 'own',  -- own / avoid / short
    thesis_summary TEXT NOT NULL,                       -- why own/avoid/short

    -- Variant perception
    market_view TEXT NOT NULL,         -- what consensus believes
    our_view TEXT NOT NULL,            -- what we believe differently
    variant_edge TEXT NOT NULL,        -- why we think market is wrong

    -- Pre-mortem
    pre_mortem TEXT,                   -- "it's 12 months later, we lost 30%. what happened?"

    -- Confidence (probabilistic, not binary)
    confidence_bull DECIMAL(4,1) DEFAULT 50.0,
    confidence_base DECIMAL(4,1) DEFAULT 30.0,
    confidence_bear DECIMAL(4,1) DEFAULT 20.0,

    -- Timeboxing
    catalyst_description TEXT,
    catalyst_deadline DATE,
    review_date DATE,

    -- Structured financial data
    financial_claims JSONB DEFAULT '{}',
    model_parameters JSONB DEFAULT '{}',

    -- Metadata
    source_filing_ids JSONB,
    generated_by VARCHAR(50) DEFAULT 'claude',
    approved_by VARCHAR(50),
    model_used VARCHAR(100),
    is_active BOOLEAN DEFAULT FALSE,
    is_draft BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_investment_theses_company ON investment_theses(company_id);
CREATE INDEX IF NOT EXISTS idx_investment_theses_active ON investment_theses(company_id, is_active) WHERE is_active = TRUE;

-- ============================================================
-- kill_criteria (explicit exit conditions)
-- ============================================================
CREATE TABLE IF NOT EXISTS kill_criteria (
    id SERIAL PRIMARY KEY,
    thesis_id INTEGER REFERENCES investment_theses(id) ON DELETE CASCADE,
    criterion TEXT NOT NULL,
    metric_name VARCHAR(255),
    threshold_value DECIMAL(20,6),
    threshold_operator VARCHAR(10),
    threshold_unit VARCHAR(50),
    triggered BOOLEAN DEFAULT FALSE,
    triggered_date DATE,
    triggered_evidence TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_kill_criteria_thesis ON kill_criteria(thesis_id);

-- ============================================================
-- hypotheses (first-class, can span companies)
-- ============================================================
CREATE TABLE IF NOT EXISTS hypotheses (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    industry_profile_id INTEGER REFERENCES industry_profiles(id),
    thesis_id INTEGER REFERENCES investment_theses(id),

    hypothesis TEXT NOT NULL,
    counter_hypothesis TEXT NOT NULL,

    confirming_evidence TEXT,
    disproving_evidence TEXT,

    status VARCHAR(20) DEFAULT 'active',  -- active / strengthened / weakened / disproved / superseded
    confidence DECIMAL(4,1) DEFAULT 50.0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_hypotheses_thesis ON hypotheses(thesis_id);
CREATE INDEX IF NOT EXISTS idx_hypotheses_company ON hypotheses(company_id);

-- ============================================================
-- hypothesis_evidence (trail of evidence for/against)
-- ============================================================
CREATE TABLE IF NOT EXISTS hypothesis_evidence (
    id SERIAL PRIMARY KEY,
    hypothesis_id INTEGER REFERENCES hypotheses(id) ON DELETE CASCADE,
    direction VARCHAR(10) NOT NULL,     -- 'for' or 'against'
    evidence TEXT NOT NULL,
    source_type VARCHAR(50),
    source_id INTEGER,
    source_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_hypothesis_evidence_hypothesis ON hypothesis_evidence(hypothesis_id);

-- ============================================================
-- management_scorecard (promises vs delivery)
-- ============================================================
CREATE TABLE IF NOT EXISTS management_scorecard (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) NOT NULL,

    promise_date DATE NOT NULL,
    promise_text TEXT NOT NULL,
    promise_metric VARCHAR(255),
    promise_value_low DECIMAL(20,6),
    promise_value_high DECIMAL(20,6),
    promise_unit VARCHAR(50),
    source_filing_id INTEGER REFERENCES filings(id),

    actual_date DATE,
    actual_value DECIMAL(20,6),
    actual_unit VARCHAR(50),
    delta_pct DECIMAL(10,2),
    result_filing_id INTEGER REFERENCES filings(id),

    assessment VARCHAR(20),
    notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_management_scorecard_company ON management_scorecard(company_id);

-- ============================================================
-- expectations (pre-earnings quantitative predictions)
-- ============================================================
CREATE TABLE IF NOT EXISTS expectations (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) NOT NULL,
    thesis_id INTEGER REFERENCES investment_theses(id),

    period VARCHAR(20) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    event_date DATE,

    metric_name VARCHAR(255) NOT NULL,
    expected_low DECIMAL(20,6),
    expected_mid DECIMAL(20,6),
    expected_high DECIMAL(20,6),
    expected_unit VARCHAR(50),

    assumption_basis TEXT,
    hypothesis_id INTEGER REFERENCES hypotheses(id),

    consensus_value DECIMAL(20,6),
    consensus_source VARCHAR(100),
    our_vs_consensus TEXT,

    published BOOLEAN DEFAULT FALSE,
    published_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_expectations_company ON expectations(company_id);
CREATE INDEX IF NOT EXISTS idx_expectations_period ON expectations(company_id, period);

-- ============================================================
-- expectation_results (post-earnings actuals vs expectations)
-- ============================================================
CREATE TABLE IF NOT EXISTS expectation_results (
    id SERIAL PRIMARY KEY,
    expectation_id INTEGER REFERENCES expectations(id) ON DELETE CASCADE,

    actual_value DECIMAL(20,6),
    actual_unit VARCHAR(50),
    source_filing_id INTEGER REFERENCES filings(id),

    vs_our_expectation_pct DECIMAL(10,2),
    vs_consensus_pct DECIMAL(10,2),

    thesis_impact VARCHAR(20),
    confidence_update DECIMAL(4,1),
    hypothesis_updates JSONB,
    kill_criteria_triggered JSONB,

    interpretation TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_expectation_results_expectation ON expectation_results(expectation_id);

-- ============================================================
-- decision_log (institutional memory)
-- ============================================================
CREATE TABLE IF NOT EXISTS decision_log (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    thesis_id INTEGER REFERENCES investment_theses(id),

    decision_date DATE NOT NULL DEFAULT CURRENT_DATE,
    decision_type VARCHAR(50) NOT NULL,
    decision_text TEXT NOT NULL,
    rationale TEXT,

    information_snapshot JSONB,

    outcome TEXT,
    outcome_date DATE,
    lessons_learned TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_decision_log_company ON decision_log(company_id);
CREATE INDEX IF NOT EXISTS idx_decision_log_thesis ON decision_log(thesis_id);
