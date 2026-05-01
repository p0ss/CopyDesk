"""
Fact-check evaluator that uses the MCP HTTP bridge to fetch
ground-truth fragments from Typesense and validate claims.

Usage:
  from evaluators.fact_check.fragment_facts import FragmentFactChecker
  checker = FragmentFactChecker("facts_fragments_1", config)
  report = await checker.evaluate(text, context={"query": "medicare card replacement", "filters": {"state": "NSW"}})
"""

from __future__ import annotations

from typing import Any, Dict, Optional, List
from datetime import datetime
import json

from evaluators.base import JuniorEvaluator, EvaluationReport, Issue, Severity
from utils.mcp_client import MCPClient


def _snip(text: str, limit: int = 800) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


class FragmentFactChecker(JuniorEvaluator):
    """Validates content against retrieved fragments from the MCP server."""

    def __init__(self, evaluator_id: str, config: Dict[str, Any]):
        super().__init__(evaluator_id, config)
        self._mcp = MCPClient.from_config(config)

    async def fetch_reference_content(self, source: str) -> str:
        """Not used for this evaluator (we fetch via MCP search),
        but maintained for interface compatibility.
        `source` is interpreted as the search query when provided.
        """
        # Delegate to search with `source` as the query
        result = await self._do_search(query=source or "*")
        return self._format_references_for_prompt(result)

    async def _do_search(self, *, query: str, filters: Optional[Dict[str, Any]] = None, per_page: Optional[int] = None) -> Dict[str, Any]:
        filters = filters or {}
        default_per_page = (
            (self.config.get("fact_check_fragments", {}) or {}).get("per_page")
            or (self.config.get("fact_check", {}) or {}).get("per_page")
            or 8
        )
        per_page = per_page if per_page is not None else default_per_page
        # Map allowed filters directly (category, life_event, provider, state)
        search_kwargs = {
            "category": filters.get("category"),
            "life_event": filters.get("life_event"),
            "provider": filters.get("provider"),
            "state": filters.get("state"),
            "per_page": per_page,
        }
        return await self._mcp.search(query=query, **search_kwargs)

    def _format_references_for_prompt(self, search_result: Dict[str, Any]) -> str:
        """Prepare a compact reference pack for the LLM prompt."""
        items: List[str] = []
        for doc in search_result.get("results", []):
            title = doc.get("title") or "Untitled"
            url = doc.get("url") or ""
            provider = doc.get("provider") or ""
            categories = ", ".join(doc.get("categories", []) or [])
            life_events = ", ".join(doc.get("life_events", []) or [])
            states = ", ".join(doc.get("states", []) or [])
            snippet = _snip(doc.get("content_text") or doc.get("content_html") or "")
            items.append(
                f"- Title: {title}\n  URL: {url}\n  Provider: {provider}\n  Categories: {categories}\n  Life Events: {life_events}\n  States: {states}\n  Excerpt: {snippet}"
            )
        if not items:
            return "No reference fragments found."
        return "\n\n".join(items)

    def _build_prompt(self, content: str, reference: str, context: Dict[str, Any]) -> str:
        """Build a fact-checking prompt using fragment references as ground truth."""
        # Explain constraints: only rely on provided reference fragments
        return f"""
You are a fact-checking assistant. Validate the user's content strictly against the provided ground-truth fragments. Do not rely on outside knowledge.

Ground Truth Fragments (from authoritative sources):
{reference}

User Content to Fact-Check:
{content}

Tasks:
1. Extract concrete claims (numbers, deadlines, eligibility, steps, provider names, state applicability, URLs).
2. For each claim, determine if it is Supported, Contradicted, or Not Found in the fragments.
3. Highlight mismatches in provider/state/eligibility or missing/incorrect URLs.
4. Suggest precise corrections, quoting the relevant fragment (with URL).

Return JSON only with:
{{
  "score": <float 0-1 overall factual accuracy>,
  "issues": [
    {{
      "description": <what is wrong>,
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "location": <optional where in text>,
      "quote": <exact user text>,
      "suggestion": <corrected statement>,
      "evidence_url": <fragment URL>,
      "evidence_excerpt": <short quote from fragment>
    }}
  ],
  "summary": <2-3 sentences overview>
}}
"""

    async def evaluate(self, content: str, context: Dict[str, Any]) -> EvaluationReport:
        # Build search parameters
        query = (context or {}).get("query") or content[:256]
        filters = (context or {}).get("filters") or {}
        per_page = (context or {}).get("per_page")

        # Search MCP for ground-truth fragments
        search_result = await self._do_search(query=query, filters=filters, per_page=per_page)
        reference_pack = self._format_references_for_prompt(search_result)

        # Call LLM with our ground-truth pack
        client = await self.get_llm_client()
        prompt = self._build_prompt(content, reference_pack, context or {})
        result = await self._call_llm(client, prompt)

        # Parse into EvaluationReport
        issues: List[Issue] = []
        for issue_data in result.get("issues", []) or []:
            sev = issue_data.get("severity", "MEDIUM").upper()
            # Map severity variations
            severity_mapping = {
                'HIGH': 'HIGH',
                'MEDIUM': 'MEDIUM', 
                'LOW': 'LOW',
                'SEVERE': 'CRITICAL',
                'MODERATE': 'MEDIUM',
                'MINOR': 'LOW',
                'WARN': 'MEDIUM',
                'WARNING': 'MEDIUM',
                'ERROR': 'CRITICAL',
                'ALERT': 'MEDIUM',
                # Handle mixed case variations
                'High': 'HIGH',
                'Medium': 'MEDIUM',
                'Low': 'LOW'
            }
            sev = severity_mapping.get(sev, sev)
            
            try:
                severity = Severity[sev]
            except KeyError:
                severity = Severity.MEDIUM
            issues.append(
                Issue(
                    description=issue_data.get("description", ""),
                    severity=severity,
                    location=issue_data.get("location"),
                    suggestion=issue_data.get("suggestion"),
                    source_url=issue_data.get("evidence_url"),
                    quote=issue_data.get("quote"),
                    metadata={"evidence_excerpt": issue_data.get("evidence_excerpt")},
                )
            )

        report = EvaluationReport(
            evaluator_id=self.evaluator_id,
            evaluator_role=self.role,
            timestamp=datetime.now(),
            score=float(result.get("score", 0.0) or 0.0),
            issues=issues,
            summary=result.get("summary", ""),
            metadata={
                "mcp_query": query,
                "filters": filters,
                "found": len(search_result.get("results", [])),
                "search_time_ms": (search_result.get("search_metadata") or {}).get("search_time_ms"),
            },
        )
        return report
