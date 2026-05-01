#!/usr/bin/env python3
"""
Quick test for the fragment-backed fact checker via the MCP server.

Prereqs:
  - Run the MCP server's HTTP bridge (default port 8081)
    e.g., from the repo root: `node mcp-server/index.js` or via docker-compose
  - Ensure Typesense is populated with `content_fragments`

Usage:
  export OPENAI_API_KEY=...
  # Optional override if MCP is not on localhost:8081
  # export MCP_SERVER_URL=http://127.0.0.1:8081
  python test_facts.py "Your content to check..."
"""

import asyncio
import json
import os
import sys
import yaml

from evaluators.fact_check.fragment_facts import FragmentFactChecker


async def load_config():
    # Use copydesk/config/evaluation_config.yaml if present
    cfg_path = os.path.join(os.path.dirname(__file__), "config", "evaluation_config.yaml")
    repo_cfg_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    for path in (cfg_path, repo_cfg_path):
        if os.path.exists(path):
            with open(path, "r") as f:
                return yaml.safe_load(f)
    return {"models": {"junior": {"provider": "openai", "model": "gpt-3.5-turbo", "temperature": 0.2}}}


async def main():
    if len(sys.argv) > 1:
        content = " ".join(sys.argv[1:])
    else:
        content = (
            "You can replace your Medicare card online and it arrives within 3 days. "
            "NSW residents must apply via Services Australia."
        )
        print("No content provided; using sample text.\n")

    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: Please set OPENAI_API_KEY for LLM parsing.")
        sys.exit(1)

    config = await load_config()
    checker = FragmentFactChecker("fact_fragments_demo", config)

    # Hint the search with a query; fall back to content if omitted
    context = {
        "query": "Medicare card replacement Services Australia",
        "filters": {
            # Example: narrow by state/provider if relevant
            # "state": "NSW",
            # "provider": "Services Australia",
        },
        "per_page": 8,
    }

    report = await checker.evaluate(content, context)

    print("\n=== Fact Check Report ===")
    print(f"Score: {report.score:.1%}")
    print(f"Fragments considered: {report.metadata.get('found')}")
    for i, issue in enumerate(report.issues[:5], 1):
        print(f"{i}. [{issue.severity.name}] {issue.description}")
        if issue.suggestion:
            print(f"   Suggestion: {issue.suggestion}")
        if issue.source_url:
            print(f"   Evidence: {issue.source_url}")
    print("\nSummary:\n" + report.summary)


if __name__ == "__main__":
    asyncio.run(main())
