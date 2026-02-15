# PDF Analysis Strategy for Indomitable 2.0

## Document Inventory

| Paper | Size | Pages | Complexity |
|-------|------|-------|------------|
| `article_capitalallocation.pdf` | 1.1 MB (1,160,670 bytes) | 88 pages | High — comprehensive research report |
| `article_roicandintangibleassets_us.pdf` | 507 KB (519,507 bytes) | 13 pages | Medium — focused whitepaper |

---

## Chunking Strategy

### For 13-Page Papers (ROIC & Intangibles)

**Approach: Single-pass analysis**

- Convert entire PDF to text (~15-30K tokens estimated)
- Feed to DeepSeek in one prompt with structured instructions
- No chunking needed — well within context window

**Prompt Structure:**
```
You are a financial metrics analyst. Read this research paper on [TOPIC] and extract:

1. KEY METRICS mentioned (with formulas if provided)
2. DATA SOURCES required to calculate each metric
3. CALCULATION LOGIC (step-by-step if described)
4. BENCHMARKS or thresholds mentioned (e.g., "ROIC > WACC")
5. TRACKING FREQUENCY (quarterly, annual, etc.)
6. EDGE CASES or adjustments noted (e.g., treatment of R&D, stock comp)

Format as structured JSON matching our data model.
```

### For 88-Page Papers (Capital Allocation)

**Approach: Hierarchical chunking with synthesis**

**Phase 1: Section Extraction** (DeepSeek pass #1)
- Chunk by document structure (TOC sections, chapters)
- Typical academic paper: 5-8 major sections
- Output: Section summaries + key metrics per section

**Phase 2: Cross-Section Synthesis** (DeepSeek pass #2)
- Feed all section summaries back to DeepSeek
- Ask for integrated view: "Synthesize these findings into a unified metrics framework"
- Output: Consolidated tracking recommendations

**Chunk Size Guidelines:**
| Paper Length | Chunk Size | Overlap | Rationale |
|--------------|------------|---------|-----------|
| <20 pages | No chunking | N/A | Fits in single prompt |
| 20-50 pages | 10-page sections | 1 page | Preserve context at section boundaries |
| 50-100 pages | 15-page sections | 2 pages | Balance granularity vs. API calls |
| 100+ pages | Chapter-based | Contextual | Follow document structure |

---

## DeepSeek Analysis Prompt Template

### System Prompt
```
You are a financial research analyst specializing in metric extraction for investment systems. 
Your task is to read academic/research papers and identify what metrics should be tracked, 
how to calculate them, and where to source the data.

Be precise about:
- Formula components (numerator/denominator definitions)
- Data source specificity ("10-K Item 7" vs "financial statements")
- Adjustment methodologies (GAAP to non-GAAP transformations)
- Frequency and timing requirements
```

### User Prompt Structure
```
Paper: [FILENAME]
Topic: [INFERRED TOPIC]

Read the attached paper and extract metrics tracking recommendations.

For each metric identified, provide:
{
  "metric_name": "human-readable name",
  "canonical_name": "snake_case_identifier",
  "category": "profitability|growth|capital_allocation|valuation|risk",
  "formula": "mathematical expression",
  "formula_components": [
    {"name": "component_name", "source": "where to find it", " adjustments": "any GAAP adjustments needed"}
  ],
  "data_sources": ["10-K", "10-Q", "earnings_call", "proxy_statement", etc.],
  "frequency": "annual|quarterly|event_driven",
  "benchmarks": {"type": "absolute|relative", "threshold": "value or comparison"},
  "notes": "special considerations from paper"
}

Also identify:
1. Any "composite" frameworks (e.g., "Economic Profit = NOPAT - Capital Charge")
2. Data quality warnings mentioned by authors
3. Common pitfalls in calculation
4. Recommended peer comparisons or industry contexts
```

---

## Analysis Output Schema

Results should populate these data model tables:

1. **`metrics_definitions`** — Canonical metric definitions extracted from papers
2. **`metric_formulas`** — Versioned formulas with component breakdowns
3. **`data_source_mappings`** — Where to fetch each component (SEC form, line item)
4. **`calculation_procedures`** — Step-by-step computation logic (JSONB)
5. **`benchmark_rules`** — Thresholds and comparison logic

---

## Reusable Pipeline

```python
# Pseudocode for PDF → Metrics Pipeline

def analyze_pdf(pdf_path: Path) -> AnalysisResult:
    pages = get_page_count(pdf_path)
    text = extract_text(pdf_path)
    
    if pages <= 20:
        # Single-pass analysis
        return deepseek_analyze(text, prompt=FULL_ANALYSIS_PROMPT)
    else:
        # Multi-pass hierarchical analysis
        chunks = chunk_by_structure(text, target_chunk_pages=15)
        section_analyses = [deepseek_analyze(chunk, prompt=SECTION_PROMPT) for chunk in chunks]
        return deepseek_synthesize(section_analyses, prompt=SYNTHESIS_PROMPT)

def deepseek_analyze(text: str, prompt: str) -> dict:
    # Call DeepSeek API with structured prompt
    # Return parsed JSON
    pass
```

---

## Execution Plan for Current Papers

### Paper 1: `article_roicandintangibleassets_us.pdf` (13 pages)
- **Strategy:** Single-pass full analysis
- **Expected output:** ROIC calculation methodology, intangible asset adjustments, data source mappings
- **Estimated tokens:** ~20K input, ~5K output

### Paper 2: `article_capitalallocation.pdf` (88 pages)
- **Strategy:** 3-pass analysis
  - Pass 1: Extract document structure and section summaries (identify major sections)
  - Pass 2: Analyze each major section for metrics (~6 sections × 15 pages)
  - Pass 3: Synthesize into unified capital allocation framework
- **Expected output:** Comprehensive capital allocation metrics, decision frameworks, governance indicators
- **Estimated tokens:** ~80K input across passes, ~15K output

---

## Key Questions to Answer for Indomitable 2.0

1. **What metrics should we track?** (the "what")
2. **How do we calculate them?** (the "how")
3. **Where do we get the data?** (the "where")
4. **How often do we update?** (the "when")
5. **What are the decision thresholds?** (the "so what")
6. **What are the edge cases?** (the "watch out for")

---

## Next Steps

1. Run single-pass analysis on ROIC paper (quick win, validates approach)
2. Design document structure extraction for Capital Allocation paper
3. Store results in database tables (metrics_definitions, etc.)
4. Create reusable `papers/` ingestion pipeline
5. Document findings in Obsidian for human review

---

*Document created: 2026-02-14*
*Location: `/Volumes/T4/openclaw/workspace/research/indomitable-v2/papers/ANALYSIS_STRATEGY.md`*
