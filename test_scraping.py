#!/usr/bin/env python3
"""
Test to verify we're actually using scraped content
"""

import asyncio
import os
import json
from datetime import datetime
from typing import Dict, Any

# Add to Python path
import sys
sys.path.insert(0, os.getcwd())

from evaluators.base_evaluator import JuniorEvaluator, Issue, Severity, EvaluationReport
from utils.document_fetcher import DocumentFetcher


class DebugStyleGuideEvaluator(JuniorEvaluator):
    """Debug evaluator that shows what content it's using"""

    async def fetch_reference_content(self, source: str) -> str:
        """Fetch and show what we're getting"""
        print(f"\n{'='*60}")
        print(f"FETCHING: {source}")
        print(f"{'='*60}")

        # Use document fetcher
        fetcher = DocumentFetcher()
        page_data = await fetcher.fetch_page(source)

        # Show what we got
        print(f"Title: {page_data['title']}")
        print(f"Content length: {len(page_data['main_content'])} chars")
        print(f"Sections found: {len(page_data['sections'])}")

        # Build content focusing on the actual rules
        content_parts = []

        # Add the main description
        if page_data['sections']:
            # Find the main content sections (skip navigation/feedback)
            for section in page_data['sections']:
                # Skip feedback forms and navigation
                if any(skip in section['heading'].lower() for skip in ['help us improve', 'feedback', 'last updated']):
                    continue

                content_parts.append(f"\n## {section['heading']}\n{section['content'][:500]}...")

        formatted_content = "\n".join(content_parts)

        print(f"\nFORMATTED CONTENT PREVIEW:")
        print(formatted_content[:1000])
        print(f"\n{'='*60}\n")

        return formatted_content

    def _build_prompt(self, content: str, reference: str, context: Dict[str, Any]) -> str:
        """Build a prompt that forces use of the reference content"""
        return f"""
        You are evaluating text against SPECIFIC style guide rules from this webpage.

        IMPORTANT: Base your evaluation ONLY on the rules provided below, not on general knowledge.

        Style Guide Content from {context.get('source', 'Unknown')}:
        {reference[:2000]}

        Text to evaluate:
        {content}

        Instructions:
        1. Find SPECIFIC violations based ONLY on the rules shown above
        2. Quote the exact rule from the style guide content
        3. If the style guide content doesn't mention a rule, don't flag it

        For example, if the style guide says "use 'help' instead of 'facilitate'",
        then flag uses of 'facilitate'. But if it doesn't mention a word, don't flag it.

        Return JSON with:
        - score: 0-1 compliance
        - issues: array of:
          - description: what rule was violated
          - severity: CRITICAL/HIGH/MEDIUM/LOW
          - suggestion: how to fix
          - rule_quote: exact text from the style guide about this rule
        - summary: 2 sentences
        - content_used: confirm you used the provided content (yes/no)
        """


async def test_real_scraping():
    """Test with real scraping"""

    # Test text
    test_text = """
    The Medicare program facilitates the provision of healthcare services to eligible
    Australian residents. Individuals may utilize their Medicare card to access
    subsidized medical consultations.
    """

    # Config
    config = {
        "models": {
            "junior": {"provider": "google", "model": "gemma-3-27b-it", "temperature": 0.3}
        }
    }

    # Test both URLs
    urls = [
        "https://www.stylemanual.gov.au/writing-and-designing-content/clear-language-and-writing-style/plain-language-and-word-choice",
        "https://www.stylemanual.gov.au/writing-style/plain-language"  # This should 404
    ]

    for url in urls:
        print(f"\n{'#'*70}")
        print(f"TESTING URL: {url}")
        print(f"{'#'*70}")

        evaluator = DebugStyleGuideEvaluator("debug_evaluator", config)

        try:
            report = await evaluator.evaluate(test_text, {"source": url})

            print(f"\nEVALUATION RESULTS:")
            print(f"Score: {report.score:.1%}")
            print(f"Issues: {len(report.issues)}")

            # Check if it used real content
            if report.issues:
                print("\nFirst issue:")
                issue = report.issues[0]
                print(f"- Description: {issue.description}")
                print(f"- Rule quote: {issue.metadata.get('rule_quote', 'NO QUOTE PROVIDED')}")

            # Save for comparison
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"scraping_test_{url.split('/')[-1]}_{timestamp}.json"

            with open(filename, 'w') as f:
                json.dump(report.to_dict(), f, indent=2)

            print(f"\nSaved to: {filename}")

        except Exception as e:
            print(f"ERROR: {e}")


async def test_content_extraction():
    """Test just the content extraction"""
    print("\nTesting content extraction only...")

    fetcher = DocumentFetcher()
    url = "https://www.stylemanual.gov.au/writing-and-designing-content/clear-language-and-writing-style/plain-language-and-word-choice"

    page_data = await fetcher.fetch_page(url)

    # Find the word substitution table
    for section in page_data['sections']:
        if 'Words to avoid' in section['heading']:
            print(f"\nFound substitution table!")
            print(section['content'][:500])
            break
    else:
        print("\nCouldn't find the substitution table!")


if __name__ == "__main__":
    asyncio.run(test_real_scraping())
