---
title: "ROIC and Intangible Assets: Adjusting for the Modern Economy"
authors: Alla Maya Abidor (Credit Suisse)
date: 2022-11-08
pages: 13
source: Credit Suisse Research
category: investment-research
---

# ROIC and Intangible Assets: Adjusting for the Modern Economy

## Summary

**Primary Focus:** Proper calculation of ROIC incorporating intangible asset investments

**Key Insight:** Traditional GAAP ROIC understates returns for intangible-intensive companies

**Recommendation:** Capitalize and amortize strategic intangible investments for accurate ROIC

---

## Key Metrics

### Adjusted Return on Invested Capital
- **Canonical Name:** `adjusted_roic`
- **Category:** profitability
- **Formula:** NOPAT / Average Invested Capital (including capitalized intangibles)

**Formula Components:**
- **NOPAT**
  - Source: 10-K Item 7 - Operating Income less adjusted taxes
  - Adjustments: Add back intangible amortization expense; adjust taxes accordingly
- **Invested Capital**
  - Source: 10-K Balance Sheet - Total Assets less Non-Interest Bearing Current Liabilities
  - Adjustments: Add capitalized intangible assets (R&D, advertising, training)

**Data Sources:** 10-K, 10-Q, Proxy Statement
**Frequency:** quarterly

**Benchmarks:**
- Type: relative
- Threshold: ROIC > WACC by at least 200-300 basis points for value creation
- Peer Comparison: Compare within industry; intangible-heavy sectors show wider spreads

**Notes:** Most relevant for technology, pharma, and consumer brands with significant intangible investments

---

### Capitalized Intangible Assets
- **Canonical Name:** `capitalized_intangibles`
- **Category:** capital_allocation
- **Formula:** Sum of capitalized R&D + capitalized advertising + capitalized training/other

**Formula Components:**
- **Capitalized R&D**
  - Source: 10-K Item 7 - Research and Development expenses
  - Adjustments: Capitalize R&D over amortization period (typically 3-7 years depending on industry)
- **Capitalized Advertising**
  - Source: 10-K - SG&A breakdown if available, or estimate from industry norms
  - Adjustments: Capitalize brand-building advertising over 1-3 years
- **Capitalized Training**
  - Source: Often not separately disclosed; may need estimation
  - Adjustments: Capitalize over expected employee tenure (typically 2-4 years)

**Data Sources:** 10-K, 10-Q, Earnings Call Transcripts
**Frequency:** annual

**Benchmarks:**
- Type: absolute
- Threshold: Compare capitalized amount to market cap; >20% suggests significant adjustment needed

**Notes:** Data quality varies significantly by company disclosure practices

---

### Intangible Asset Intensity Ratio
- **Canonical Name:** `intangible_intensity_ratio`
- **Category:** valuation
- **Formula:** Capitalized Intangibles / Total Assets

**Formula Components:**
- **Capitalized Intangibles**
  - Source: Calculated from above
  - Adjustments: N/A
- **Total Assets**
  - Source: 10-K Balance Sheet
  - Adjustments: Use reported GAAP total assets

**Data Sources:** 10-K
**Frequency:** annual

**Benchmarks:**
- Type: absolute
- Threshold: >0.30 indicates high intangible intensity requiring adjustments

**Notes:** Use to identify companies where traditional metrics are most misleading

---

### Adjusted Invested Capital Turnover
- **Canonical Name:** `adjusted_invested_capital_turnover`
- **Category:** efficiency
- **Formula:** Revenue / Average Adjusted Invested Capital

**Formula Components:**
- **Revenue**
  - Source: 10-K Income Statement
  - Adjustments: Use reported revenue
- **Adjusted Invested Capital**
  - Source: Calculated per above
  - Adjustments: Include capitalized intangibles

**Data Sources:** 10-K, 10-Q
**Frequency:** quarterly

**Benchmarks:**
- Type: relative
- Threshold: Compare to unadjusted turnover; significant divergence indicates adjustment importance

**Notes:** Intangible-intensive firms show lower turnover but higher margins

---

