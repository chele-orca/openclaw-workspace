# Mauboussin PDF Analysis Pipeline — Document Handling

## Single-Pass Analysis (< 20 pages)

| # | Document | Pages |
|---|----------|-------|
| 1 | article_wealthtransfers_us.pdf | 9 |
| 2 | article_confidence.pdf | 11 |
| 3 | article_mythbustingpopulardelusions_en.pdf | 11 |
| 4 | article_bayesandbaserates_ltr.pdf | 12 |
| 5 | article_newbuinessboomandbust_us.pdf | 12 |
| 6 | article_everythingisadcfmodel_us.pdf | 13 |
| 7 | article_goodlossesbadlosses.pdf | 13 |
| 8 | article_themathofvalueandgrowth.pdf | 13 |
| 9 | article_themathofvalueandgrowth_us.pdf | 13 |
| 10 | articles_waccandvol.pdf | 13 |
| 11 | article_intangiblesandearnings_us.pdf | 14 |
| 12 | article_theimpactofintangiblesonbaserates.pdf | 14 |
| 13 | Mauboussin.pdf | 15 |
| 14 | article_categorizingforclarity.pdf | 16 |
| 15 | dispersion-and-alpha-conversion.pdf | 16 |
| 16 | article_stockmarketconcentration.pdf | 18 |
| 17 | article_bintheredonethat_us.pdf | 19 |

**Total: 17 papers**

**Strategy:** Convert entire PDF to text, feed to DeepSeek in one prompt with structured extraction instructions.

---

## 3-Pass Hierarchical Analysis (20–50 pages)

| # | Document | Pages |
|---|----------|-------|
| 1 | article_whichoneisitequityissuanceretirement.pdf | 20 |
| 2 | article_costofcapitalandcapitalallocation.pdf | 21 |
| 3 | article_marketexpectedreturnoninvestment_en.pdf | 22 |
| 4 | article_patternrecognition.pdf | 22 |
| 5 | article_underestimatingtheredqueen.pdf | 22 |
| 6 | article_chartsfromthevaultpicturestoponder.pdf | 23 |
| 7 | article_feedback_us.pdf | 23 |
| 8 | article_tradingstagesinthecompanylifecycle.pdf | 24 |
| 9 | article_turnandfacethestrange_us.pdf | 24 |
| 10 | article_increasingreturns.pdf | 25 |
| 11 | article_onejob.pdf | 25 |
| 12 | article_valuationmultiples.pdf | 26 |
| 13 | article_stockbasedcompensation.pdf | 29 |
| 14 | article_roicandtheinvestmentprocess.pdf | 31 |
| 15 | article_totalshareholderreturns.pdf | 32 |
| 16 | article_birthdeathandwealthcreation.pdf | 34 |
| 17 | article_theeconomicsofcustomerbusinessesV2_us.pdf | 38 |
| 18 | article_returnoninvestedcapital.pdf | 44 |
| 19 | article_costofcapital.pdf | 50 |

**Total: 19 papers**

**Strategy:**
- **Pass 1:** Extract document structure (TOC/major sections)
- **Pass 2:** Analyze each section independently (~15-page chunks)
- **Pass 3:** Synthesize into unified metrics framework

---

## Deferred — Book-Length (Requires Modified Pipeline)

| # | Document | Pages | Notes |
|---|----------|-------|-------|
| 1 | article_marketshare.pdf | 57 | Borderline — could use 4-pass |
| 2 | article_measuringthemoat.pdf | 104 | Research report — needs chapter extraction |
| 3 | articles_publictoprivateequityintheusalongtermlook_us.pdf | 82 | Long research piece |
| 4 | Think Twice.pdf | 209 | Full book |
| 5 | The Success Equation.pdf | 240 | Full book |
| 6 | Expectations Investing.pdf | 241 | Full book |
| 7 | More Than You Know.pdf | 453 | Full book |

**Total: 7 documents**

**Strategy:** Not yet determined. Options:
- Chapter-by-chapter extraction, then per-chapter analysis
- TOC + intro/conclusion only for frameworks
- Skip full analysis, extract key metrics from summaries only

---

## Summary

| Category | Count | Pipeline |
|----------|-------|----------|
| Single-pass | 17 | Full text → DeepSeek |
| 3-pass | 19 | Structure → Sections → Synthesis |
| Deferred | 7 | TBD (books + long research) |
| **Total** | **43** | |

---

*Document created: 2026-02-14*
*Location: `/Volumes/T4/openclaw/workspace/research/indomitable-v2/papers/ANALYSIS_PIPELINE.md`*
