#!/usr/bin/env python3
"""
Mauboussin 35-Paper Collection Analysis Pipeline - BATCH MODE
Processes papers in batches of 3 to avoid OOM kills.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional
import re

# Configuration
INPUT_DIR = Path("/Volumes/T4/openclaw/workspace/research/indomitable-v2/papers/mauboussin")
OUTPUT_DIR = Path("/Volumes/T4/openclaw/workspace/research/indomitable-v2/papers/results")
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "deepseek-r1:14b-qwen-distill-q8_0"
BATCH_SIZE = 1  # Process 1 paper at a time (memory constrained)
DELAY_BETWEEN_BATCHES = 30  # Seconds to wait between batches

# Paper categorization by page count
SHORT_PAPERS = [
    ("article_wealthtransfers_us.pdf", 9),
    ("article_confidence.pdf", 11),
    ("article_mythbustingpopulardelusions_en.pdf", 11),
    ("article_bayesandbaserates_ltr.pdf", 12),
    ("article_newbuinessboomandbust_us.pdf", 12),
    ("article_everythingisadcfmodel_us.pdf", 13),
    ("article_goodlossesbadlosses.pdf", 13),
    ("article_themathofvalueandgrowth.pdf", 13),
    ("article_themathofvalueandgrowth_us.pdf", 13),
    ("articles_waccandvol.pdf", 13),
    ("article_intangiblesandearnings_us.pdf", 14),
    ("article_theimpactofintangiblesonbaserates.pdf", 14),
    ("Mauboussin.pdf", 15),
    ("article_categorizingforclarity.pdf", 16),
    ("dispersion-and-alpha-conversion.pdf", 16),
    ("article_stockmarketconcentration.pdf", 18),
    ("article_bintheredonethat_us.pdf", 19),
]

MEDIUM_PAPERS = [
    ("article_whichoneisitequityissuanceretirement.pdf", 20),
    ("article_costofcapitalandcapitalallocation.pdf", 21),
    ("article_marketexpectedreturnoninvestment_en.pdf", 22),
    ("article_patternrecognition.pdf", 22),
    ("article_underestimatingtheredqueen.pdf", 22),
    ("article_chartsfromthevaultpicturestoponder.pdf", 23),
    ("article_feedback_us.pdf", 23),
    ("article_tradingstagesinthecompanylifecycle.pdf", 24),
    ("article_turnandfacethestrange_us.pdf", 24),
    ("article_increasingreturns.pdf", 25),
    ("article_onejob.pdf", 25),
    ("article_valuationmultiples.pdf", 26),
    ("article_stockbasedcompensation.pdf", 29),
    ("article_roicandtheinvestmentprocess.pdf", 31),
    ("article_totalshareholderreturns.pdf", 32),
    ("article_birthdeathandwealthcreation.pdf", 34),
    ("article_theeconomicsofcustomerbusinessesV2_us.pdf", 38),
    ("article_returnoninvestedcapital.pdf", 44),
    ("article_costofcapital.pdf", 50),
]

LARGE_PAPERS = [
    ("article_marketshare.pdf", 57),
]

ALL_PAPERS = SHORT_PAPERS + MEDIUM_PAPERS + LARGE_PAPERS


def check_ollama() -> bool:
    """Check if Ollama is running and model is available."""
    import requests
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            for model in models:
                if model["name"] == OLLAMA_MODEL:
                    return True
            print(f"Warning: Model {OLLAMA_MODEL} not found in Ollama.")
            print(f"Available models: {[m['name'] for m in models]}")
            return False
    except Exception as e:
        print(f"Error connecting to Ollama: {e}")
        return False
    return False


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from PDF using available libraries."""
    try:
        import PyPDF2
        text = ""
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n\n"
        return text
    except ImportError:
        pass
    
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
                text += "\n\n"
        return text
    except ImportError:
        pass
    
    # Fallback: use pdftotext if available
    import subprocess
    result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout
    
    raise RuntimeError(f"No PDF extraction method available for {pdf_path}")


def call_ollama(prompt: str, system_prompt: str) -> dict:
    """Call local Ollama API."""
    import requests
    
    headers = {
        "Content-Type": "application/json"
    }
    
    # Combine system and user prompt for Ollama
    full_prompt = f"{system_prompt}\n\n{prompt}"
    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 4000
        }
    }
    
    response = requests.post(OLLAMA_API_URL, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


SYSTEM_PROMPT = """You are a financial research analyst specializing in extracting metrics, formulas, and analytical frameworks from academic and research papers.

Your task is to identify all quantitative metrics discussed in the paper, including:
- Performance metrics (ROIC, ROE, margins, growth rates)
- Valuation metrics (multiples, DCF components)
- Risk metrics (volatility, concentration measures)
- Capital allocation metrics (investment rates, payout ratios)

For each metric, extract:
1. The precise formula or calculation method
2. Required data sources and where to find them
3. Any adjustments needed (GAAP to non-GAAP)
4. Benchmarks or thresholds mentioned
5. Measurement frequency
6. Edge cases and limitations

Respond in valid JSON format only."""


SHORT_PAPER_PROMPT = """Analyze the following research paper text and extract all metrics, formulas, and analytical frameworks.

For each metric found, provide:
- metric_name: Human-readable name
- canonical_name: snake_case identifier
- category: One of [profitability, growth, capital_allocation, valuation, risk, efficiency, other]
- formula: Mathematical expression (if available)
- formula_components: List of inputs with sources and any needed adjustments
- data_sources: Where to find the data (10-K, 10-Q, etc.)
- frequency: How often to measure (annual, quarterly, event_driven)
- benchmarks: Type (absolute/relative) and threshold values
- notes: Special considerations, edge cases, warnings

Also identify:
- Analytical frameworks or models discussed
- Key insights and takeaways
- Common pitfalls or calculation errors to avoid
- Recommended comparisons or context

Paper text:
{text}

Respond in this JSON structure:
{{
  "paper_title": "extracted title",
  "authors": ["author names"],
  "total_metrics": N,
  "metrics": [...],
  "frameworks": [...],
  "key_insights": [...],
  "pitfalls": [...]
}}"""


def analyze_short_paper(pdf_path: Path) -> dict:
    """Single-pass analysis for short papers (<20 pages)."""
    print(f"  Extracting text from {pdf_path.name}...")
    text = extract_text_from_pdf(pdf_path)
    
    # Truncate if needed (Ollama context limit)
    max_chars = 30000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Text truncated due to length]"
    
    prompt = SHORT_PAPER_PROMPT.format(text=text)
    
    print(f"  Calling Ollama (local DeepSeek)...")
    response = call_ollama(prompt, SYSTEM_PROMPT)
    
    # Parse the response content
    try:
        content = response['response']
        result = json.loads(content)
        result['source_file'] = pdf_path.name
        return result
    except (KeyError, json.JSONDecodeError) as e:
        print(f"  Warning: Could not parse response: {e}")
        return {
            "source_file": pdf_path.name,
            "error": str(e),
            "raw_response": response
        }


def analyze_medium_paper(pdf_path: Path, pages: int) -> dict:
    """3-pass hierarchical analysis for medium papers (20-50 pages)."""
    print(f"  Extracting text from {pdf_path.name} ({pages} pages)...")
    text = extract_text_from_pdf(pdf_path)
    
    # Pass 1: Extract structure
    print(f"  Pass 1: Extracting document structure...")
    structure_prompt = f"""Analyze the structure of this {pages}-page research paper.
Identify major sections, chapters, and their approximate content areas.

Text (first 15000 chars):
{text[:15000]}

Return JSON:
{{
  "sections": [
    {{"title": "section name", "estimated_pages": "N-M", "topics": ["key topics"], "char_range": [start, end]}}
  ]
}}"""
    
    structure_response = call_ollama(structure_prompt, SYSTEM_PROMPT)
    try:
        structure = json.loads(structure_response['response'])
    except:
        structure = {"sections": [{"title": "Full Document", "char_range": [0, len(text)]}]}
    
    # Pass 2: Analyze chunks
    print(f"  Pass 2: Analyzing sections...")
    chunk_size = 20000  # characters per chunk
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    
    section_analyses = []
    for i, chunk in enumerate(chunks[:6]):  # Limit to 6 chunks max
        print(f"    Processing chunk {i+1}/{min(len(chunks), 6)}...")
        chunk_prompt = SHORT_PAPER_PROMPT.format(text=chunk[:25000])
        chunk_response = call_ollama(chunk_prompt, SYSTEM_PROMPT)
        try:
            analysis = json.loads(chunk_response['response'])
            section_analyses.append(analysis)
        except:
            pass
    
    # Pass 3: Synthesize
    print(f"  Pass 3: Synthesizing results...")
    synthesis_input = json.dumps(section_analyses, indent=2)[:20000]
    synthesis_prompt = f"""Synthesize these section analyses into a unified metrics framework.
Remove duplicates, resolve conflicts, and organize by category.

Section analyses:
{synthesis_input}

Return unified JSON in the same format with consolidated metrics."""
    
    synthesis_response = call_ollama(synthesis_prompt, SYSTEM_PROMPT)
    try:
        result = json.loads(synthesis_response['response'])
    except:
        # If synthesis fails, combine section analyses manually
        result = combine_analyses(section_analyses)
    
    result['source_file'] = pdf_path.name
    result['structure'] = structure
    result['section_analyses'] = section_analyses
    return result


def combine_analyses(analyses: List[dict]) -> dict:
    """Manually combine multiple section analyses."""
    combined = {
        "paper_title": analyses[0].get("paper_title", "Unknown") if analyses else "Unknown",
        "metrics": [],
        "frameworks": [],
        "key_insights": [],
        "pitfalls": []
    }
    
    seen_metrics = set()
    for analysis in analyses:
        for metric in analysis.get("metrics", []):
            name = metric.get("canonical_name", metric.get("metric_name", ""))
            if name and name not in seen_metrics:
                seen_metrics.add(name)
                combined["metrics"].append(metric)
        
        combined["frameworks"].extend(analysis.get("frameworks", []))
        combined["key_insights"].extend(analysis.get("key_insights", []))
        combined["pitfalls"].extend(analysis.get("pitfalls", []))
    
    # Deduplicate
    combined["frameworks"] = list(set(combined["frameworks"]))
    combined["key_insights"] = list(set(combined["key_insights"]))
    combined["pitfalls"] = list(set(combined["pitfalls"]))
    combined["total_metrics"] = len(combined["metrics"])
    
    return combined


def analyze_large_paper(pdf_path: Path, pages: int) -> dict:
    """4-pass analysis for large papers (>50 pages)."""
    # Similar to medium but with more granular chunking
    return analyze_medium_paper(pdf_path, pages)


def save_result(result: dict, output_path: Path):
    """Save analysis result to JSON file."""
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"  Saved: {output_path}")
    
    # Also generate Markdown version
    md_output_path = output_path.with_suffix('.md')
    generate_markdown(result, md_output_path)
    print(f"  Saved: {md_output_path}")


def generate_markdown(result: dict, output_path: Path):
    """Generate Markdown version of the analysis result."""
    md = []
    
    # Frontmatter
    md.append("---")
    md.append(f"title: \"{result.get('paper_title', 'Unknown')}\"")
    if 'authors' in result:
        authors = result['authors']
        if isinstance(authors, list):
            md.append(f"authors: {', '.join(authors)}")
        else:
            md.append(f"authors: {authors}")
    if 'organization' in result:
        md.append(f"organization: {result['organization']}")
    if 'date' in result:
        md.append(f"date: {result['date']}")
    if 'pages' in result:
        md.append(f"pages: {result['pages']}")
    md.append(f"source_file: {result.get('source_file', 'Unknown')}")
    md.append(f"total_metrics: {result.get('total_metrics', 0)}")
    md.append("category: investment-research")
    md.append("---")
    md.append("")
    
    # Title
    md.append(f"# {result.get('paper_title', 'Unknown')}")
    md.append("")
    
    # Summary
    md.append("## Summary")
    md.append("")
    if 'analysis_summary' in result:
        summary = result['analysis_summary']
        if 'primary_focus' in summary:
            md.append(f"**Primary Focus:** {summary['primary_focus']}")
            md.append("")
        if 'key_insight' in summary:
            md.append(f"**Key Insight:** {summary['key_insight']}")
            md.append("")
        if 'recommendation' in summary:
            md.append(f"**Recommendation:** {summary['recommendation']}")
            md.append("")
    md.append("---")
    md.append("")
    
    # Key Metrics
    md.append("## Key Metrics")
    md.append("")
    
    for metric in result.get('metrics', []):
        md.append(f"### {metric.get('metric_name', 'Unnamed')}")
        md.append(f"- **Canonical Name:** `{metric.get('canonical_name', 'unknown')}`")
        md.append(f"- **Category:** {metric.get('category', 'other')}")
        md.append(f"- **Formula:** {metric.get('formula', 'N/A')}")
        md.append("")
        
        # Formula Components
        if 'formula_components' in metric and metric['formula_components']:
            md.append("**Formula Components:**")
            for comp in metric['formula_components']:
                md.append(f"- **{comp.get('name', 'Unknown')}**")
                if 'source' in comp:
                    md.append(f"  - Source: {comp['source']}")
                if 'adjustments' in comp:
                    md.append(f"  - Adjustments: {comp['adjustments']}")
            md.append("")
        
        # Data Sources and Frequency
        if 'data_sources' in metric:
            sources = metric['data_sources']
            if isinstance(sources, list):
                md.append(f"**Data Sources:** {', '.join(sources)}")
            else:
                md.append(f"**Data Sources:** {sources}")
        if 'frequency' in metric:
            md.append(f"**Frequency:** {metric['frequency']}")
        md.append("")
        
        # Benchmarks
        if 'benchmarks' in metric:
            md.append("**Benchmarks:**")
            benchmarks = metric['benchmarks']
            if 'type' in benchmarks:
                md.append(f"- Type: {benchmarks['type']}")
            if 'threshold' in benchmarks:
                md.append(f"- Threshold: {benchmarks['threshold']}")
            if 'peer_comparison' in benchmarks:
                md.append(f"- Peer Comparison: {benchmarks['peer_comparison']}")
            if 'ranges' in benchmarks:
                md.append("- Ranges:")
                for k, v in benchmarks['ranges'].items():
                    md.append(f"  - {k}: {v}")
            md.append("")
        
        # Notes
        if 'notes' in metric:
            md.append(f"**Notes:** {metric['notes']}")
            md.append("")
        
        md.append("---")
        md.append("")
    
    # Frameworks
    if 'frameworks' in result and result['frameworks']:
        md.append("## Frameworks")
        md.append("")
        for framework in result['frameworks']:
            if isinstance(framework, dict):
                md.append(f"- **{framework.get('name', 'Unknown')}**: {framework.get('description', '')}")
            else:
                md.append(f"- {framework}")
        md.append("")
        md.append("---")
        md.append("")
    
    # Key Insights
    if 'key_insights' in result and result['key_insights']:
        md.append("## Key Insights")
        md.append("")
        for insight in result['key_insights']:
            md.append(f"- {insight}")
        md.append("")
        md.append("---")
        md.append("")
    
    # Pitfalls
    if 'pitfalls' in result and result['pitfalls']:
        md.append("## Pitfalls to Avoid")
        md.append("")
        for pitfall in result['pitfalls']:
            md.append(f"- {pitfall}")
        md.append("")
        md.append("---")
        md.append("")
    
    # Structure (for multi-pass analyses)
    if 'structure' in result:
        md.append("## Document Structure")
        md.append("")
        structure = result['structure']
        if 'sections' in structure:
            for section in structure['sections']:
                md.append(f"- **{section.get('title', 'Unknown')}**")
                if 'estimated_pages' in section:
                    md.append(f"  - Pages: {section['estimated_pages']}")
                if 'topics' in section:
                    md.append(f"  - Topics: {', '.join(section['topics'])}")
        md.append("")
        md.append("---")
        md.append("")
    
    # Write to file
    output_path.write_text('\n'.join(md))


def process_batch(papers: List[tuple], all_results: List[dict]):
    """Process a batch of papers."""
    for paper_name, pages in papers:
        pdf_path = INPUT_DIR / paper_name
        if not pdf_path.exists():
            print(f"\nSkipping {paper_name} (not found)")
            continue
        
        # Check if already processed
        output_file = OUTPUT_DIR / f"mauboussin-{paper_name.replace('.pdf', '')}-metrics.json"
        if output_file.exists():
            print(f"\nSkipping {paper_name} (already processed)")
            try:
                with open(output_file, 'r') as f:
                    result = json.load(f)
                all_results.append(result)
            except:
                pass
            continue
        
        print(f"\nAnalyzing: {paper_name} ({pages} pages)")
        try:
            if pages < 20:
                result = analyze_short_paper(pdf_path)
            elif pages <= 50:
                result = analyze_medium_paper(pdf_path, pages)
            else:
                result = analyze_large_paper(pdf_path, pages)
            
            all_results.append(result)
            save_result(result, output_file)
        except Exception as e:
            print(f"  Error analyzing {paper_name}: {e}")


def main():
    print("=" * 60)
    print("Mauboussin 35-Paper Collection Analysis - BATCH MODE")
    print("Using local DeepSeek via Ollama")
    print(f"Batch size: {BATCH_SIZE} papers, delay: {DELAY_BETWEEN_BATCHES}s")
    print("=" * 60)
    
    # Check Ollama
    if not check_ollama():
        print("Error: Ollama not running or model not found.")
        print(f"Make sure Ollama is running with model: {OLLAMA_MODEL}")
        sys.exit(1)
    
    print(f"Ollama verified: {OLLAMA_MODEL}")
    
    # Ensure directories exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"\nInput directory: {INPUT_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Total papers to analyze: {len(ALL_PAPERS)}")
    
    all_results = []
    
    # Process in batches
    for i in range(0, len(ALL_PAPERS), BATCH_SIZE):
        batch = ALL_PAPERS[i:i+BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(ALL_PAPERS) + BATCH_SIZE - 1) // BATCH_SIZE
        
        print("\n" + "=" * 60)
        print(f"Processing BATCH {batch_num}/{total_batches}")
        print(f"Papers: {[p[0] for p in batch]}")
        print("=" * 60)
        
        process_batch(batch, all_results)
        
        # Delay between batches (except after last batch)
        if i + BATCH_SIZE < len(ALL_PAPERS):
            print(f"\nBatch {batch_num} complete. Waiting {DELAY_BETWEEN_BATCHES}s before next batch...")
            time.sleep(DELAY_BETWEEN_BATCHES)
    
    # Generate summary
    print("\n" + "=" * 60)
    print("Generating summary...")
    print("=" * 60)
    
    # Import summary generation function from original script or inline it
    summary_path = OUTPUT_DIR / "mauboussin-analysis-summary.md"
    generate_summary(all_results, summary_path)
    
    print("\n" + "=" * 60)
    print("Analysis complete!")
    print(f"Results saved in: {OUTPUT_DIR}")
    print("=" * 60)


def generate_summary(all_results: List[dict], output_path: Path):
    """Generate human-readable summary of all analyses."""
    summary = []
    summary.append("# Mauboussin Papers Analysis Summary")
    summary.append(f"\nTotal papers analyzed: {len(all_results)}\n")
    
    # Categorize all metrics
    all_metrics = {}
    for result in all_results:
        source = result.get('source_file', 'Unknown')
        paper_title = result.get('paper_title', 'Unknown')
        
        summary.append(f"\n## {paper_title}")
        summary.append(f"**Source:** `{source}`")
        summary.append(f"**Metrics found:** {result.get('total_metrics', 0)}")
        
        for metric in result.get('metrics', []):
            category = metric.get('category', 'other')
            if category not in all_metrics:
                all_metrics[category] = []
            all_metrics[category].append({
                **metric,
                'source_paper': paper_title
            })
            
            summary.append(f"\n### {metric.get('metric_name', 'Unnamed')}")
            summary.append(f"- **Category:** {category}")
            summary.append(f"- **Formula:** `{metric.get('formula', 'N/A')}`")
            summary.append(f"- **Data Sources:** {', '.join(metric.get('data_sources', ['N/A']))}")
            summary.append(f"- **Frequency:** {metric.get('frequency', 'N/A')}")
    
    # Add consolidated metrics by category
    summary.append("\n\n# Consolidated Metrics by Category\n")
    for category, metrics in sorted(all_metrics.items()):
        summary.append(f"\n## {category.upper().replace('_', ' ')}")
        for metric in metrics:
            summary.append(f"\n### {metric['metric_name']}")
            summary.append(f"- **Canonical:** `{metric['canonical_name']}`")
            summary.append(f"- **Source:** {metric['source_paper']}")
            summary.append(f"- **Formula:** {metric.get('formula', 'N/A')[:100]}...")
    
    output_path.write_text('\n'.join(summary))
    print(f"\nSummary saved: {output_path}")


if __name__ == "__main__":
    main()
