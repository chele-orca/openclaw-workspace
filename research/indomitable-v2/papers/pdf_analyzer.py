#!/usr/bin/env python3
"""
PDF Analysis Pipeline for Indomitable 2.0 Investment System
Extracts metrics from research papers using DeepSeek API
"""

import json
import sys
import os
from pathlib import Path
import PyPDF2

# DeepSeek API integration (requires API key)
import requests

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from PDF using PyPDF2"""
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n\n"
    except Exception as e:
        print(f"Error extracting text: {e}")
        return ""
    return text

def analyze_with_deepseek(text: str, prompt: str, api_key: str) -> dict:
    """Call DeepSeek API for analysis"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a financial research analyst specializing in metric extraction for investment systems."},
            {"role": "user", "content": f"{prompt}\n\n{text}"}
        ],
        "response_format": {"type": "json_object"}
    }
    
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"API Error: {e}")
        return {}

def analyze_roic_paper(pdf_path: Path, api_key: str) -> dict:
    """Single-pass analysis for ROIC paper (13 pages)"""
    print(f"Analyzing ROIC paper: {pdf_path}")
    
    text = extract_text_from_pdf(pdf_path)
    if not text:
        return {}
    
    prompt = """Analyze this research paper on ROIC and Intangible Assets. 
Extract the following as JSON:

{
  "paper_title": "exact title",
  "authors": ["author names"],
  "key_metrics": [
    {
      "metric_name": "human readable name",
      "canonical_name": "snake_case_identifier",
      "category": "profitability|growth|capital_allocation|valuation|risk",
      "formula": "mathematical expression",
      "formula_components": [
        {"name": "component", "source": "where to find it", "adjustments": "GAAP adjustments needed"}
      ],
      "data_sources": ["10-K", "10-Q", etc.],
      "frequency": "annual|quarterly",
      "benchmarks": {"type": "absolute|relative", "threshold": "value or comparison"},
      "notes": "special considerations"
    }
  ],
  "intangible_asset_adjustments": {
    "treatment_method": "description",
    "components": ["R&D", "advertising", "training", etc.],
    "capitalization_period": "years",
    "amortization_method": "description"
  },
  "calculation_procedures": ["step-by-step instructions"],
  "data_quality_warnings": ["warnings from paper"],
  "common_pitfalls": ["pitfalls to avoid"],
  "recommended_comparisons": ["peer comparison methodologies"]
}"""
    
    return analyze_with_deepseek(text, prompt, api_key)

def analyze_capital_allocation_paper(pdf_path: Path, api_key: str) -> dict:
    """Hierarchical 3-pass analysis for Capital Allocation paper (88 pages)"""
    print(f"Analyzing Capital Allocation paper: {pdf_path}")
    
    text = extract_text_from_pdf(pdf_path)
    if not text:
        return {}
    
    # Pass 1: Extract document structure
    structure_prompt = """Analyze the structure of this capital allocation research paper.
Identify major sections/chapters and their page ranges.
Return JSON with:
{
  "sections": [
    {"title": "section name", "estimated_pages": "range", "key_topics": ["topics"]}
  ]
}"""
    
    structure = analyze_with_deepseek(text[:15000], structure_prompt, api_key)  # First 15K chars for structure
    
    # Pass 2: Analyze each section (simplified - in real implementation, chunk by sections)
    metrics_prompt = """Extract all capital allocation metrics from this paper.
For each metric, provide:
- Name and formula
- Data sources (SEC forms, line items)
- Calculation logic
- Benchmarks/thresholds
- Tracking frequency
- Edge cases and pitfalls

Return as structured JSON."""
    
    # Process in chunks if needed
    chunk_size = 20000  # characters
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    
    section_analyses = []
    for i, chunk in enumerate(chunks[:6]):  # Limit to first 6 chunks for API efficiency
        print(f"  Processing chunk {i+1}/{len(chunks)}")
        result = analyze_with_deepseek(chunk, metrics_prompt, api_key)
        section_analyses.append(result)
    
    # Pass 3: Synthesis
    synthesis_prompt = """Synthesize these section analyses into a unified capital allocation metrics framework.
Identify:
1. Core metrics that should be tracked
2. Data model requirements
3. Implementation priority
4. Dependencies between metrics

Return structured JSON."""
    
    synthesis_input = json.dumps(section_analyses)
    final_result = analyze_with_deepseek(synthesis_input, synthesis_prompt, api_key)
    
    return {
        "structure": structure,
        "section_analyses": section_analyses,
        "synthesis": final_result
    }

def main():
    # Get API key from environment or 1Password
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        # Try to get from 1Password CLI
        try:
            import subprocess
            result = subprocess.run(
                ["op", "read", "op://Chele.Ops/DeepSeek/api_key"],
                capture_output=True, text=True
            )
            api_key = result.stdout.strip()
        except:
            print("Error: DEEPSEEK_API_KEY not found. Set environment variable or configure 1Password.")
            sys.exit(1)
    
    # Define paths
    papers_dir = Path("/Volumes/T4/openclaw/workspace/research/indomitable-v2/papers")
    results_dir = papers_dir / "results"
    results_dir.mkdir(exist_ok=True)
    
    # Analyze ROIC paper (13 pages - single pass)
    roic_pdf = papers_dir / "article_roicandintangibleassets_us.pdf"
    if roic_pdf.exists():
        roic_result = analyze_roic_paper(roic_pdf, api_key)
        with open(results_dir / "roic_metrics.json", "w") as f:
            json.dump(roic_result, f, indent=2)
        print(f"Saved: {results_dir / 'roic_metrics.json'}")
    
    # Analyze Capital Allocation paper (88 pages - hierarchical)
    capital_pdf = papers_dir / "article_capitalallocation.pdf"
    if capital_pdf.exists():
        capital_result = analyze_capital_allocation_paper(capital_pdf, api_key)
        with open(results_dir / "capital_allocation_metrics.json", "w") as f:
            json.dump(capital_result, f, indent=2)
        print(f"Saved: {results_dir / 'capital_allocation_metrics.json'}")
    
    print("Analysis complete!")

if __name__ == "__main__":
    main()
