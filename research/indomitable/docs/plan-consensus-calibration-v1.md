# Consensus-Calibrated Report Rework

## Context

The synthesis pipeline produces "URGENT" red-banner reports for EQT based on standard risk disclosures from a 10-Q filing. Meanwhile, 32 analysts rate EQT Strong Buy with 14% upside and 10% EPS growth. The report is crying wolf.

**The Eisenhower insight:** Importance × urgency should drive report classification. Known priced-in risks are important but NOT urgent. With EQT earnings 7 days away (Feb 18), the report's primary value is as a preparation brief — not an alarm on a 4-month-old filing. Red should only flash when we have a specific contrarian thesis the street is missing.

**Root causes:**
1. Claude's prompt frames the task as "prepare an intelligence brief" — biasing toward risk-hunting because 10-Q text is structurally heavy on risk language
2. Urgency scoring stacks points for negative findings with no counterweight from market consensus (3 high-materiality negatives + primary watchlist = 80 points → immediate)
3. Report leads with backward-looking filing analysis; the earnings preview is buried at section #9

---

## Changes

### 1. Synthesis Prompt — Consensus-First Framing

**File:** `scripts/synthesize_intelligence.py` → `build_synthesis_prompt()`

Reframe Claude's task from "prepare an intelligence brief" to "reconcile this filing against what Wall Street already believes":

- New opening instructs Claude: "Your job is NOT to produce a risk report. The filing's risk factor section is legally required to enumerate risks regardless of their novelty. Assess what is GENUINELY NEW INFORMATION relative to what the street already believes."
- Add `TODAY'S DATE: {date}` so Claude knows where we are in the earnings cycle
- Inject a pre-computed **consensus summary string** right before the instructions (e.g., "32 analysts: 9 Strong Buy, 15 Buy, 8 Hold, 0 Sell. Price target $41.11 consensus.") — making consensus impossible to ignore when Claude encounters risk-factor language
- New `compute_consensus_summary()` helper in `external_data.py` builds this string from existing Finnhub/FMP data

### 2. New JSON Schema Fields

**File:** `scripts/synthesize_intelligence.py` → `build_synthesis_prompt()`

Add `consensus_calibration` block requiring Claude to explicitly reason about consensus:

```
"consensus_calibration": {
    "street_position": "summary of analyst consensus",
    "filing_vs_consensus": "Confirms|Challenges|Neutral",
    "explanation": "how this filing relates to what the market believes",
    "priced_in_risks": ["risks from filing that analysts already model"],
    "genuinely_new_information": ["findings NOT in current consensus"]
}
```

Additional schema changes:
- `"report_type": "contrarian_alert|earnings_briefing|filing_update"` with reasoning
- Each `key_insight` gains `"consensus_status": "Priced_In|New_Information|Confirms_Thesis"`
- `urgency_indicators` gains `"contrarian_signal"` (bool) and `"contrarian_thesis"` (string, required if true)

### 3. Prompt Guidelines Rewrite

**File:** `scripts/synthesize_intelligence.py` → `build_synthesis_prompt()`

Replace current guidelines with consensus-calibrated instructions:
- **Consensus-first**: Before writing insights, reconcile each finding against analyst consensus. Risk factors in every 10-Q are definitionally priced in.
- **Priced-in test**: A risk is priced in if it appears in standard disclosures, has been reported in news, or is a known industry factor. Only `New_Information` if it represents a CHANGE or QUANTITATIVE SURPRISE.
- **Report type rules**: `contrarian_alert` requires a specific thesis; `earnings_briefing` is the default when earnings are within ~30 days; `filing_update` is the default otherwise.
- **Balanced summary**: Executive summary MUST open by acknowledging consensus position, then state whether filing confirms/challenges/is neutral.

### 4. Urgency Scoring Rewrite

**File:** `scripts/synthesize_intelligence.py` → `compute_urgency()`

Two-phase consensus-calibrated scoring replaces the current additive system.

**Phase 1 — Raw significance:**
- `New_Information` high-materiality insights: +15 each
- `Priced_In` high-materiality insights: +3 each (minimal)
- `material_change_detected`: +15
- 8-K: +15, 10-Q/10-K: +5
- Primary watchlist: +5

**Phase 2 — Consensus calibration:**
- New `compute_consensus_strength()` helper: computes 0.0–1.0 score from analyst buy/sell counts
- If filing `Confirms`/`Neutral` and consensus is strong (>0.6): apply dampener (~0.5× for strong bullish consensus)
- If filing `Challenges` AND Claude provides contrarian thesis: +30 bonus
- `contrarian_alert` without a thesis gets downgraded to `filing_update`

**EQT walkthrough:** 3 priced-in highs (9) + 1 new-info (15) + material change (15) + 10-Q (5) + primary (5) = 49 pre-dampening. Consensus strength 0.875, filing confirms → dampener 0.475 → score 23 → `daily_digest`. Correct.

New return signature: `(urgency_level, report_type, urgency_detail_dict)`

### 5. Report Type Visual Identity

**File:** `scripts/report_templates.py`

Three report types replace the single urgency-color axis:

| Type | Header Color | Label | Subtitle | When |
|---|---|---|---|---|
| `contrarian_alert` | Red | CONTRARIAN ALERT | Filing diverges from consensus | Claude identifies specific contrarian thesis |
| `earnings_briefing` | Blue | EARNINGS BRIEFING | Pre-earnings preparation brief | Approaching earnings |
| `filing_update` | Gray | FILING UPDATE | Confirms consensus | Default for routine filings |

Urgency becomes a small delivery-timing badge (DELIVER NOW / DAILY DIGEST / WEEKLY) in the header corner, separate from the header color. Only `contrarian_alert` gets red.

### 6. New Consensus Calibration Section

**File:** `scripts/report_templates.py`

Rendered immediately after Executive Summary. Shows:
- "Filing vs. Consensus: **Confirms**" (green border) / "**Challenges**" (red) / "**Neutral**" (gray)
- Street position summary
- "Already Priced In" items in muted gray
- "Genuinely New Information" items emphasized

### 7. Section Reordering by Report Type

**File:** `scripts/report_templates.py`

Build sections into a dict, then assemble in report-type-dependent order:

**`earnings_briefing`** (the EQT case):
1. Header → 2. Executive Summary → 3. Consensus Calibration → 4. **Earnings Preview** (promoted from #9) → 5. Market Context → 6. Key Insights → 7-9. Financial/Operational/Strategic → 10. Risks → 11. Peer → 12. Takeaways

**`contrarian_alert`**: Key Insights promoted to #4 (evidence for the thesis).

**`filing_update`**: Standard order with Consensus Calibration at #3.

### 8. Key Insights Table — Consensus Status Column

**File:** `scripts/report_templates.py`

Add 5th column: `Priced_In` (muted gray), `New_Information` (red bold), `Confirms_Thesis` (green). Reader instantly sees which insights are novel vs already known.

### 9. Fix Price Target Data

**Problem:** FMP `/stable/price-target-consensus` returns stale data — $41.11 consensus when the real consensus is ~$65. This actively misleads the analysis.

**Fix:** Replace FMP price targets with StockAnalysis.com scraping (same pattern as Motley Fool transcripts):
- New `fetch_stockanalysis_price_target(ticker)` in `external_data.py`
- Scrape `https://stockanalysis.com/stocks/{ticker}/forecast/` for consensus target, analyst count, high/low range
- Replace the `price_target/fmp` dispatcher routing with `price_target/stockanalysis`
- Update industry profile configs to use the new source
- Remove `fetch_fmp_price_target()` calls

### 10. Minor Updates

- **`deliver_reports.py`**: Subject line uses report type prefix (`[CONTRARIAN ALERT]`, `[EARNINGS BRIEFING]`, or none)
- **`save_synthesis()`**: Updated to store `report_type` and `urgency_detail` in `generation_metadata`
- **SQL migration**: `ALTER TABLE intelligence_reports ADD COLUMN report_type VARCHAR(30) DEFAULT 'filing_update'`
- **`generate_intelligence_html()` signature**: Accepts `report_type` and `urgency_detail` params

---

## Files Modified

| File | Changes |
|---|---|
| `scripts/synthesize_intelligence.py` | Prompt framing, JSON schema, guidelines, new `compute_consensus_strength()`, `compute_urgency()` rewrite, `process_report()` + `save_synthesis()` updated signatures |
| `scripts/report_templates.py` | `REPORT_TYPE_STYLES` dict, `_consensus_calibration_html()`, `SECTION_ORDER` dict, `_render_header()`, insights table consensus column, `generate_intelligence_html()` signature |
| `scripts/external_data.py` | New `compute_consensus_summary()` helper, new `fetch_stockanalysis_price_target()`, remove stale FMP price target |
| `scripts/deliver_reports.py` | Subject line format for report types |
| SQL (via docker exec) | `ALTER TABLE intelligence_reports ADD COLUMN report_type`, update industry profile external_sources |

---

## Verification

1. Run `synthesize_intelligence.py --filing-id 15` for EQT
2. Expected: `report_type = earnings_briefing`, `urgency = daily_digest`
3. Header: blue "EARNINGS BRIEFING", NOT red "URGENT"
4. Executive summary opens by acknowledging the Strong Buy consensus
5. Consensus Calibration section: "Filing vs. Consensus: Confirms" in green, regulatory risks listed as "Priced In"
6. Earnings Preview is section #4, not #9
7. Key Insights table: consensus_status column, most items "Priced In" in gray
8. Export HTML, visually verify layout
