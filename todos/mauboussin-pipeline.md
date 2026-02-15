# Mauboussin Pipeline - Action Items

## Immediate

- [ ] **Switch analyzer model** from deepseek-r1:14b to GPT-4o or Claude 3.5 Sonnet
  - Local DeepSeek is hallucinating and failing to parse PDFs
  - Expected fix: 90%+ success rate vs current 6%

- [ ] **Pause or fix cron job** `mauboussin-analysis-review`
  - Currently reporting fake progress (counts files, not quality)
  - Only 2 of 31 "completed" files are actually usable

## Reprocessing Queue

### Hallucinated (7 files) - Re-run with better model
- [ ] mauboussin-article_bayesandbaserates_ltr-metrics.json (contains "OpenAI's Explosive Growth")
- [ ] mauboussin-articles_waccandvol-metrics.json (contains COVID-19 content)
- [ ] mauboussin-article_wealthtransfers_us-metrics.json (fake authors)
- [ ] mauboussin-Mauboussin-metrics.json (wrong author name, parenting content)
- [ ] mauboussin-article_mythbustingpopulardelusions_en-metrics.json
- [ ] mauboussin-article_stockmarketconcentration-metrics.json
- [ ] mauboussin-article_themathofvalueandgrowth_us-metrics.json

### Empty/PDF Parse Failed (12 files) - Extract text first, then analyze
- [ ] article_costofcapitalandcapitalallocation.pdf
- [ ] article_chartsfromthevaultpicturestoponder.pdf
- [ ] article_totalshareholderreturns.pdf
- [ ] article_measuringthemoat.pdf
- [ ] article_returnoninvestedcapital.pdf
- [ ] article_marketshare.pdf
- [ ] article_roicandtheinvestmentprocess.pdf
- [ ] article_theeconomicsofcustomerbusinessesV2_us.pdf
- [ ] article_costofcapital.pdf
- [ ] article_birthdeathandwealthcreation.pdf
- [ ] article_valuationmultiples.pdf
- [ ] article_stockbasedcompensation.pdf

### JSON Parse Errors (10 files) - Extract from raw_response
- [ ] Files have valid content in raw_response field but JSON extraction failed
- [ ] May be salvageable without re-running model

## Exclude from Pipeline

- [ ] **Move large books to separate processing queue** (4MB+)
  - `More Than You Know` (4.2 MB)
  - `Expectations Investing` (3.9 MB)
  - `The Success Equation` (2.3 MB)
  - `Think Twice` (1.6 MB)
  - These need chunked processing or different approach

## Post-Processing

- [ ] **Metrics analysis** once 35 papers are *actually* complete
  - Map metrics to: thesis creation, monitoring, hypothesis testing, data sources
  - Populate Indomitable 2.0 database schema
  - Document calculation procedures and benchmarks

## Reference

- Full quality review: `research/indomitable-v2/papers/QUALITY_REVIEW_REPORT.md`
- Pipeline scripts: `research/indomitable-v2/papers/`
- Valid examples: `capital_allocation_metrics.json`, `roic_metrics.json`
