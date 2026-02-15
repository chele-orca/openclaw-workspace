---
title: "Capital Allocation: Evidence, Analytical Methods, and Assessment Guidance"
authors: Michael J. Mauboussin, Dan Callahan, Darius Majd
organization: Credit Suisse HOLT
pages: 88
source: Credit Suisse Research
category: investment-research
---

# Capital Allocation: Evidence, Analytical Methods, and Assessment Guidance

## Summary

**Primary Focus:** Comprehensive framework for assessing management's capital allocation decisions

**Key Insight:** Capital allocation is the most important job of senior management; patterns reveal strategic priorities and capabilities

**Recommendation:** Track five uses of cash and evaluate against value creation principles

---

## Key Metrics

### Net Investment Rate
- **Canonical Name:** `net_investment_rate`
- **Category:** capital_allocation
- **Formula:** (Capital Expenditures + Acquisitions + R&D + Other Investments - Depreciation) / NOPAT

**Formula Components:**
- **Capital Expenditures**
  - Source: 10-K Cash Flow Statement - Capital Expenditures
  - Adjustments: Gross CapEx, not net of disposals
- **Acquisitions**
  - Source: 10-K Cash Flow Statement - Business Acquisitions
  - Adjustments: Include both cash and stock acquisitions from footnotes
- **R&D Expense**
  - Source: 10-K Income Statement
  - Adjustments: Consider capitalizing for growth companies
- **Depreciation**
  - Source: 10-K Cash Flow Statement
  - Adjustments: Use reported depreciation and amortization
- **NOPAT**
  - Source: Calculated from Operating Income
  - Adjustments: Tax-adjusted operating profit

**Data Sources:** 10-K, 10-Q, Proxy Statement
**Frequency:** annual

**Benchmarks:**
- Type: relative
- Threshold: Sustainable value creation requires Investment Rate < ROIC (positive economic profit)
- Ranges:
  - high_growth: >100% of NOPAT
  - maintenance: 50-100% of NOPAT
  - harvest: <50% of NOPAT

**Notes:** Key indicator of capital allocation strategy: growth vs. maintenance vs. harvest

---

### Cash Flow Allocation Breakdown
- **Canonical Name:** `cash_flow_allocation`
- **Category:** capital_allocation
- **Formula:** Percentage of Operating Cash Flow allocated to: Operations, M&A, Dividends, Buybacks, Debt Paydown

**Formula Components:**
- **Operating Cash Flow**
  - Source: 10-K Cash Flow Statement
  - Adjustments: Use reported OCF
- **Reinvestment (CapEx + Acquisitions)**
  - Source: Cash Flow Statement Investing Activities
  - Adjustments: Include both organic and inorganic investment
- **Dividends**
  - Source: Cash Flow Statement - Financing Activities
  - Adjustments: Total cash dividends paid
- **Share Buybacks**
  - Source: Cash Flow Statement - Financing Activities
  - Adjustments: Repurchases of common stock
- **Debt Changes**
  - Source: Cash Flow Statement - Financing Activities
  - Adjustments: Net debt issuance (positive) or paydown (negative)

**Data Sources:** 10-K, 10-Q
**Frequency:** annual

**Benchmarks:**
- Type: relative
- Threshold: Compare 5-year average allocation pattern to industry norms

**Notes:** Reveals management's strategic priorities and capital allocation philosophy

---

### Return on Invested Capital (ROIC)
- **Canonical Name:** `roic`
- **Category:** profitability
- **Formula:** NOPAT / Average Invested Capital

**Formula Components:**
- **NOPAT**
  - Source: Operating Income × (1 - Tax Rate)
  - Adjustments: Use cash tax rate if significantly different from GAAP
- **Invested Capital**
  - Source: Total Assets - Non-Interest Bearing Current Liabilities
  - Adjustments: May include operating leases, pension liabilities

**Data Sources:** 10-K
**Frequency:** quarterly

**Benchmarks:**
- Type: relative
- Threshold: ROIC > WACC indicates value creation; ROIC > 15% suggests competitive advantage

**Notes:** Primary metric for assessing capital allocation effectiveness

---

### Organic Revenue Growth Rate
- **Canonical Name:** `organic_revenue_growth`
- **Category:** growth
- **Formula:** (Current Revenue - Revenue from Acquisitions - Currency Impact - Prior Revenue) / Prior Revenue

**Formula Components:**
- **Reported Revenue Growth**
  - Source: Income Statement
  - Adjustments: N/A
- **Acquisition Contribution**
  - Source: 10-K Footnotes - Business Combinations
  - Adjustments: Revenue from acquisitions in first year
- **Currency Impact**
  - Source: Segment reporting or MD&A
  - Adjustments: FX translation effects

**Data Sources:** 10-K, Earnings Call Transcripts
**Frequency:** quarterly

**Benchmarks:**
- Type: absolute
- Threshold: Should exceed industry GDP growth for market share gains

**Notes:** Separates true operational performance from M&A-driven growth

---

### Acquisition Performance Analysis
- **Canonical Name:** `acquisition_performance`
- **Category:** capital_allocation
- **Formula:** Compare pre-acquisition expected returns to post-acquisition actual returns

**Formula Components:**
- **Acquisition Price**
  - Source: 8-K, 10-K Footnotes
  - Adjustments: Total consideration including assumed debt
- **Expected Synergies**
  - Source: Management projections at acquisition
  - Adjustments: Document from press releases and investor presentations
- **Post-Acquisition Performance**
  - Source: Segment reporting, subsequent 10-Ks
  - Adjustments: Track acquired business performance separately if disclosed

**Data Sources:** 8-K, 10-K, Proxy Statement, Investor Presentations
**Frequency:** event_driven

**Benchmarks:**
- Type: absolute
- Threshold: Acquisition should generate ROIC > WACC within 3-5 years

**Notes:** Most acquisitions destroy value; track actual vs. promised performance

---

### Share Buyback Effectiveness
- **Canonical Name:** `buyback_effectiveness`
- **Category:** capital_allocation
- **Formula:** Compare buyback price to current price and intrinsic value estimate

**Formula Components:**
- **Average Buyback Price**
  - Source: Calculate from shares repurchased and dollars spent
  - Adjustments: N/A
- **Current Stock Price**
  - Source: Market data
  - Adjustments: N/A
- **Intrinsic Value Estimate**
  - Source: DCF or comparable analysis
  - Adjustments: Use conservative estimates

**Data Sources:** 10-K, 10-Q, Market Data
**Frequency:** quarterly

**Benchmarks:**
- Type: absolute
- Threshold: Effective if buybacks occur below intrinsic value; destructive if above

**Notes:** Many buybacks are value-destroying when done at high multiples

---

### Dividend Payout Ratio
- **Canonical Name:** `dividend_payout_ratio`
- **Category:** capital_allocation
- **Formula:** Total Dividends / Net Income (or Free Cash Flow)

**Formula Components:**
- **Dividends**
  - Source: Cash Flow Statement
  - Adjustments: N/A
- **Net Income**
  - Source: Income Statement
  - Adjustments: N/A

**Data Sources:** 10-K
**Frequency:** quarterly

**Benchmarks:**
- Type: relative
- Threshold: Sustainable payout < 60% of earnings; < 40% for growth companies

**Notes:** High payout may signal lack of reinvestment opportunities

---

### Free Cash Flow Conversion
- **Canonical Name:** `fcf_conversion`
- **Category:** profitability
- **Formula:** Free Cash Flow / Net Income

**Formula Components:**
- **Operating Cash Flow**
  - Source: Cash Flow Statement
  - Adjustments: N/A
- **Capital Expenditures**
  - Source: Cash Flow Statement
  - Adjustments: Use maintenance CapEx if separable from growth CapEx
- **Net Income**
  - Source: Income Statement
  - Adjustments: N/A

**Data Sources:** 10-K
**Frequency:** quarterly

**Benchmarks:**
- Type: absolute
- Threshold: >100% indicates working capital efficiency; <80% warrants investigation

**Notes:** Persistent divergence between earnings and cash flow signals accounting issues

---

### Reinvestment Rate
- **Canonical Name:** `reinvestment_rate`
- **Category:** capital_allocation
- **Formula:** (CapEx - Depreciation + Change in Working Capital + R&D) / Revenue

**Formula Components:**
- **Net CapEx**
  - Source: Cash Flow Statement
  - Adjustments: Gross CapEx less D&A
- **Working Capital Change**
  - Source: Cash Flow Statement
  - Adjustments: Exclude cash and debt
- **R&D**
  - Source: Income Statement
  - Adjustments: Consider as investment, not expense

**Data Sources:** 10-K
**Frequency:** annual

**Benchmarks:**
- Type: relative
- Threshold: Should align with growth stage: high for growth, low for mature

**Notes:** High reinvestment with low ROIC suggests capital destruction

---

### Economic Profit (EP)
- **Canonical Name:** `economic_profit`
- **Category:** profitability
- **Formula:** (ROIC - WACC) × Invested Capital

**Formula Components:**
- **ROIC**
  - Source: Calculated
  - Adjustments: N/A
- **WACC**
  - Source: Calculated from capital structure and costs
  - Adjustments: Use company-specific or industry WACC
- **Invested Capital**
  - Source: Balance Sheet
  - Adjustments: N/A

**Data Sources:** 10-K, Market Data
**Frequency:** annual

**Benchmarks:**
- Type: absolute
- Threshold: Positive EP indicates value creation; negative indicates destruction

**Notes:** Ultimate measure of capital allocation success

---

