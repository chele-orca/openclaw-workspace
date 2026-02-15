#!/bin/bash
#
# Mauboussin Paper Analysis Script
# Extracts metrics from PDFs using DeepSeek API
#

set -e

# Configuration
INPUT_DIR="/workspace/research/indomitable-v2/papers/mauboussin"
OUTPUT_DIR="/workspace/research/indomitable-v2/papers/results"
DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"
DEEPSEEK_API_URL="https://api.deepseek.com/v1/chat/completions"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Function to make HTTP POST request using /dev/tcp (bash built-in)
http_post() {
    local host="$1"
    local port="$2"
    local path="$3"
    local data="$4"
    local headers="$5"
    
    exec 3<>/dev/tcp/$host/$port
    echo -e "POST $path HTTP/1.1\r
Host: $host\r
Content-Type: application/json\r
$headers\r
Content-Length: ${#data}\r
\r
$data" >&3
    
    cat <&3
    exec 3<&-
    exec 3>&-
}

# Function to extract text from PDF
extract_pdf_text() {
    local pdf_path="$1"
    local output_file="$2"
    
    # Use strings command to extract readable text
    strings "$pdf_path" | sed 's/[[:space:]]+/ /g' | sed '/^$/d' > "$output_file"
    
    # Count lines extracted
    local lines=$(wc -l < "$output_file")
    echo "Extracted $lines lines from $pdf_path"
}

# Function to truncate text to fit API limits
truncate_text() {
    local text_file="$1"
    local max_chars="${2:-15000}"
    
    head -c "$max_chars" "$text_file"
}

# Function to call DeepSeek API
call_deepseek_api() {
    local prompt="$1"
    local system_prompt="${2:-You are a financial analyst extracting metrics and formulas from academic papers.}"
    
    # Escape special characters for JSON
    local escaped_prompt=$(echo "$prompt" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g' | tr -d '\r')
    local escaped_system=$(echo "$system_prompt" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g' | tr -d '\r')
    
    local json_payload="{
        \"model\": \"deepseek-chat\",
        \"messages\": [
            {\"role\": \"system\", \"content\": \"$escaped_system\"},
            {\"role\": \"user\", \"content\": \"$escaped_prompt\"}
        ],
        \"temperature\": 0.1,
        \"max_tokens\": 4000,
        \"response_format\": {\"type\": \"json_object\"}
    }"
    
    # Use curl if available, otherwise use wget or /dev/tcp
    if command -v curl >/dev/null 2>&1; then
        curl -s -X POST "$DEEPSEEK_API_URL" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
            -d "$json_payload"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- --post-data="$json_payload" \
            --header="Content-Type: application/json" \
            --header="Authorization: Bearer $DEEPSEEK_API_KEY" \
            "$DEEPSEEK_API_URL"
    else
        echo "Neither curl nor wget available" >&2
        return 1
    fi
}

# Analysis prompt template for short papers
SHORT_PAPER_PROMPT='Analyze the following financial research paper text and extract all metrics, formulas, and analytical frameworks discussed.

For each metric found, provide:
1. Human-readable name
2. Snake_case identifier
3. Category (profitability|growth|capital_allocation|valuation|risk|other)
4. Mathematical formula if available
5. Formula components (what inputs are needed)
6. Data sources (10-K, 10-Q, earnings reports, etc.)
7. Measurement frequency (annual, quarterly, event-driven)
8. Benchmarks or thresholds mentioned
9. Special considerations or edge cases

Paper text:
===BEGIN PAPER===
PAPER_TEXT_PLACEHOLDER
===END PAPER===

Respond in valid JSON format with this structure:
{
  "paper_title": "extracted title",
  "total_metrics": N,
  "metrics": [
    {
      "metric_name": "human-readable name",
      "canonical_name": "snake_case_identifier",
      "category": "profitability|growth|capital_allocation|valuation|risk|other",
      "formula": "mathematical expression or null",
      "formula_components": ["list of input variables"],
      "data_sources": ["10-K", "10-Q", etc.],
      "frequency": "annual|quarterly|event_driven|as_needed",
      "benchmarks": {"type": "absolute|relative", "threshold": "description"},
      "notes": "special considerations"
    }
  ],
  "frameworks": ["analytical frameworks mentioned"],
  "key_insights": ["key takeaways"]
}'

# Function to analyze a short paper (single pass)
analyze_short_paper() {
    local paper_name="$1"
    local paper_path="$INPUT_DIR/$paper_name"
    local text_output="$OUTPUT_DIR/${paper_name%.pdf}.txt"
    local json_output="$OUTPUT_DIR/${paper_name%.pdf}-metrics.json"
    
    echo "====================================="
    echo "Analyzing: $paper_name"
    echo "====================================="
    
    if [ ! -f "$paper_path" ]; then
        echo "Error: PDF not found at $paper_path"
        return 1
    fi
    
    # Extract text
    echo "Extracting text..."
    extract_pdf_text "$paper_path" "$text_output"
    
    # Truncate to API limit
    local truncated=$(truncate_text "$text_output" 12000)
    
    # Prepare prompt
    local prompt="${SHORT_PAPER_PROMPT/PAPER_TEXT_PLACEHOLDER/$truncated}"
    
    # Call API
    echo "Calling DeepSeek API..."
    if [ -n "$DEEPSEEK_API_KEY" ]; then
        local response=$(call_deepseek_api "$prompt")
        echo "$response" > "$json_output"
        echo "Results saved to: $json_output"
    else
        echo "Warning: No DEEPSEEK_API_KEY set, saving prompt for later analysis"
        echo "$prompt" > "$OUTPUT_DIR/${paper_name%.pdf}-prompt.txt"
    fi
    
    echo ""
}

# Function to analyze medium paper (3-pass)
analyze_medium_paper() {
    local paper_name="$1"
    local paper_path="$INPUT_DIR/$paper_name"
    local text_output="$OUTPUT_DIR/${paper_name%.pdf}.txt"
    local json_output="$OUTPUT_DIR/${paper_name%.pdf}-metrics.json"
    
    echo "====================================="
    echo "Analyzing (3-pass): $paper_name"
    echo "====================================="
    
    if [ ! -f "$paper_path" ]; then
        echo "Error: PDF not found at $paper_path"
        return 1
    fi
    
    # Extract text
    echo "Extracting text..."
    extract_pdf_text "$paper_path" "$text_output"
    
    # Count total lines for chunking
    local total_lines=$(wc -l < "$text_output")
    local chunk_size=$((total_lines / 3 + 1))
    
    echo "Total lines: $total_lines, Chunk size: ~$chunk_size"
    
    # Pass 1: Document structure
    echo "Pass 1: Extracting document structure..."
    local structure_prompt="Analyze the following research paper and identify its major sections and structure. Return JSON with 'sections' array containing section titles and approximate line ranges.

Text:
$(head -c 8000 "$text_output")

Respond with JSON: {\"sections\": [{\"title\": \"...\", \"start_line\": N, \"end_line\": N}]}"
    
    if [ -n "$DEEPSEEK_API_KEY" ]; then
        call_deepseek_api "$structure_prompt" > "$OUTPUT_DIR/${paper_name%.pdf}-structure.json"
    fi
    
    # Pass 2: Analyze each chunk
    for i in 1 2 3; do
        echo "Pass 2: Analyzing chunk $i..."
        local start_line=$(((i-1) * chunk_size + 1))
        local end_line=$((i * chunk_size))
        local chunk=$(sed -n "${start_line},${end_line}p" "$text_output" | head -c 12000)
        
        local chunk_prompt="${SHORT_PAPER_PROMPT/PAPER_TEXT_PLACEHOLDER/$chunk}"
        
        if [ -n "$DEEPSEEK_API_KEY" ]; then
            call_deepseek_api "$chunk_prompt" > "$OUTPUT_DIR/${paper_name%.pdf}-chunk${i}.json"
        else
            echo "$chunk_prompt" > "$OUTPUT_DIR/${paper_name%.pdf}-chunk${i}-prompt.txt"
        fi
    done
    
    # Pass 3: Synthesize (if API key available)
    if [ -n "$DEEPSEEK_API_KEY" ] && [ -f "$OUTPUT_DIR/${paper_name%.pdf}-chunk1.json" ]; then
        echo "Pass 3: Synthesizing results..."
        local synthesis_prompt="Synthesize the following three analysis chunks into a unified metrics framework. Remove duplicates, resolve conflicts, and organize by category.

Chunk 1: $(cat "$OUTPUT_DIR/${paper_name%.pdf}-chunk1.json")

Chunk 2: $(cat "$OUTPUT_DIR/${paper_name%.pdf}-chunk2.json")

Chunk 3: $(cat "$OUTPUT_DIR/${paper_name%.pdf}-chunk3.json")

Respond with unified JSON in the same format."
        
        call_deepseek_api "$synthesis_prompt" > "$json_output"
    fi
    
    echo ""
}

# Main execution
main() {
    echo "Mauboussin Paper Analysis Pipeline"
    echo "=================================="
    echo "Input: $INPUT_DIR"
    echo "Output: $OUTPUT_DIR"
    echo "API Key: ${DEEPSEEK_API_KEY:+SET}${DEEPSEEK_API_KEY:-NOT SET}"
    echo ""
    
    # Check input directory
    if [ ! -d "$INPUT_DIR" ]; then
        echo "Error: Input directory not found: $INPUT_DIR"
        exit 1
    fi
    
    # Source paper configurations
    source "$(dirname "$0")/papers_config.sh"
    
    # Process short papers
    echo "Processing SHORT papers (<20 pages)..."
    for paper_spec in "${SHORT_PAPERS[@]}"; do
        IFS=':' read -r paper_name _ <<< "$paper_spec"
        analyze_short_paper "$paper_name"
    done
    
    # Process medium papers
    echo "Processing MEDIUM papers (20-50 pages)..."
    for paper_spec in "${MEDIUM_PAPERS[@]}"; do
        IFS=':' read -r paper_name _ <<< "$paper_spec"
        analyze_medium_paper "$paper_name"
    done
    
    # Process large papers
    echo "Processing LARGE papers (>50 pages)..."
    for paper_spec in "${LARGE_PAPERS[@]}"; do
        IFS=':' read -r paper_name _ <<< "$paper_spec"
        # Use 4-pass for large papers (same as medium but with more chunks)
        analyze_medium_paper "$paper_name"  # Adapted function
    done
    
    echo "=================================="
    echo "Analysis complete!"
    echo "Results in: $OUTPUT_DIR"
}

# Run if executed directly
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi
