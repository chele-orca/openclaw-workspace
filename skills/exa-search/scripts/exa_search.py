#!/usr/bin/env python3
"""Exa.ai neural search CLI."""

import argparse
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

API_URL = "https://api.exa.ai/search"

# Load .env file if present
def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().strip().split("\n"):
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                if key.strip() not in os.environ:
                    os.environ[key.strip()] = val.strip()

load_env()


def search(query, num_results=5, include_text=False, include_summary=False, search_type="auto"):
    """Execute Exa search."""
    api_key = os.environ.get("EXA_API_KEY")
    if not api_key:
        return {"error": "EXA_API_KEY not set. Add it to .env file or environment."}

    payload = {
        "query": query,
        "numResults": num_results,
        "type": search_type,
    }

    contents = {}
    if include_text:
        contents["text"] = True
    if include_summary:
        contents["summary"] = True
    if contents:
        payload["contents"] = contents

    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "OpenClaw/1.0",
        "Accept": "application/json",
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"}
    except urllib.error.URLError as e:
        return {"error": f"Request failed: {e.reason}"}


def format_results(data):
    """Format results for display."""
    if "error" in data:
        return f"Error: {data['error']}"

    results = data.get("results", [])
    if not results:
        return "No results found."

    lines = [f"Found {len(results)} results:\n"]

    for i, r in enumerate(results, 1):
        lines.append(f"## {i}. {r.get('title', 'Untitled')}")
        lines.append(f"URL: {r.get('url', 'N/A')}")

        if r.get("publishedDate"):
            lines.append(f"Published: {r['publishedDate'][:10]}")
        if r.get("author"):
            lines.append(f"Author: {r['author']}")
        if r.get("summary"):
            lines.append(f"\nSummary: {r['summary']}")
        if r.get("text"):
            text = r["text"][:500] + "..." if len(r.get("text", "")) > 500 else r.get("text", "")
            lines.append(f"\nText: {text}")
        lines.append("")

    if data.get("costDollars"):
        lines.append(f"Cost: ${data['costDollars'].get('total', 0):.4f}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Exa.ai neural search")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--num-results", "-n", type=int, default=5)
    parser.add_argument("--text", "-t", action="store_true", help="Include text snippets")
    parser.add_argument("--summary", "-s", action="store_true", help="Include AI summaries")
    parser.add_argument("--type", choices=["auto", "neural", "keyword"], default="auto")
    parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")

    args = parser.parse_args()

    result = search(
        query=args.query,
        num_results=args.num_results,
        include_text=args.text,
        include_summary=args.summary,
        search_type=args.type,
    )

    print(json.dumps(result, indent=2) if args.json else format_results(result))


if __name__ == "__main__":
    main()
    