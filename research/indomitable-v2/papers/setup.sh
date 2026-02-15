#!/bin/bash
# Quick setup script for Mauboussin analysis

echo "Setting up Mauboussin Paper Analysis Environment"
echo "================================================"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 not found"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

echo "Python version: $(python3 --version)"

# Install dependencies
echo ""
echo "Installing dependencies..."
pip3 install -q -r requirements.txt

# Check API key
if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo ""
    echo "Warning: DEEPSEEK_API_KEY not set"
    echo "Please set it with: export DEEPSEEK_API_KEY='your-key-here'"
    exit 1
fi

echo ""
echo "Environment ready!"
echo "Run the analysis with: python3 analyze_all_mauboussin.py"
