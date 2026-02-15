-- 05-financial-claims.sql
-- Add structured financial_claims to company_theses for deterministic consistency
-- Date: 2026-02-12

-- ============================================================
-- company_theses: add financial_claims JSONB column
-- Stores structured numeric claims alongside the narrative thesis,
-- enabling deterministic validation between thesis and synthesis.
-- ============================================================
ALTER TABLE company_theses ADD COLUMN IF NOT EXISTS financial_claims JSONB DEFAULT '{}'::jsonb;
