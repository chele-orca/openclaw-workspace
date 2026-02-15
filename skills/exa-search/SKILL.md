---
name: exa-search
description: Neural/semantic web search using Exa.ai API. Use for research queries requiring high-quality, semantically relevant results. Better than keyword search for conceptual queries, finding similar content, or research-heavy tasks. Requires EXA_API_KEY environment variable.
---

# Exa Search

Neural search via Exa.ai. Returns semantically relevant results, not just keyword matches.

## When to Use

- Research queries needing deep relevance (not just keywords)
- Finding articles/papers on specific concepts
- Semantic similarity searches
- When Brave search results aren't cutting it

## Usage

python3 scripts/exa_search.py "your search query"
python3 scripts/exa_search.py "your query" --num-results 10 --summary

## Options

| Flag | Description | Default |
|------|-------------|---------|
| --num-results N | Number of results | 5 |
| --text | Include page text snippets | off |
| --summary | Include AI summaries | off |
| --type TYPE | Search type: auto, neural, keyword | auto |