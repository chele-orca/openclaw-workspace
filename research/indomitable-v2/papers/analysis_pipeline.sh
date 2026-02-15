#!/bin/bash

# Mauboussin PDF Analysis Pipeline
# Uses DeepSeek API for extraction

INPUT_DIR="/workspace/research/indomitable-v2/papers/mauboussin"
OUTPUT_DIR="/workspace/research/indomitable-v2/papers/results"

# Get DeepSeek API key from environment or file
DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-$(cat ~/.deepseek_api_key 2>/dev/null || cat /workspace/.deepseek_api_key 2>/dev/null || echo '')}"

if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "Error: DeepSeek API key not found"
    echo "Please set DEEPSEEK_API_KEY environment variable or create ~/.deepseek_api_key"
    exit 1
fi

echo "Mauboussin Analysis Pipeline configured"
echo "Input: $INPUT_DIR"
echo "Output: $OUTPUT_DIR"
