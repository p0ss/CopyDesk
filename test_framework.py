#!/usr/bin/env python3
"""
Test the actual evaluation framework with mock data
"""

import asyncio
import os
import json
import yaml
from datetime import datetime
from pathlib import Path

# Create minimal project structure
Path("evaluators/style_guide").mkdir(parents=True, exist_ok=True)
Path("config").mkdir(exist_ok=True)

# Write the base evaluator if it doesn't exist
if not Path("evaluators/__init__.py").exists():
    Path("evaluators/__init__.py").touch()
    Path("evaluators/style_guide/__init__.py").touch()

# Import after ensuring structure exists
import sys
sys.path.insert(0, os.getcwd())

from evaluators.base import (
    BaseEvaluator, JuniorEvaluator, SeniorEvaluator, EditorEvaluator,
    EvaluationReport, Issue, Severity
)


class TestStyleGuidePageEvaluator(JuniorEvaluator):
    """Test page evaluator using real fetching"""
    
    async def fetch_reference_content(self, source: str) -> str:
        """Actually fetch the page content"""
        from utils.document_fetcher import DocumentFetcher
        fetcher = DocumentFetcher()
        
        print(f"  Fetching real content from: {source}")
        page_data = await fetcher.fetch_page(source)
        
        # Format the content focusing on actual rules
        formatted = f"Page Title: {page_data['title']}\n\n"
        
        # Extract key content sections
        for section in page_data['sections']:
            # Skip feedback forms
            if any(skip in section['heading'].lower() for skip in ['feedback', 'help us']):
                continue
            formatted += f"\n{section['heading']}:\n{section['content']}\n"
        
        print(f"  Fetched {len(formatted)} chars of content")
        return formatted
    
    def _build_prompt(self, content: str, reference: str, context: dict[str, any]) -> str:
        """Build evaluation prompt"""
        return f"""
        Evaluate this text against these style guide rules:
        
        Style Guide Page: {context.get('source', 'Unknown')}
        Rules:
        {reference}
        
        Text to evaluate:
        {content}
        
        Return JSON with:
        - score: compliance score from 0 to 1
        - issues: array of objects with: description, severity (CRITICAL/HIGH/MEDIUM/LOW), suggestion
        - summary: brief 2-sentence overview
        
        Example format:
        {{
            "score": 0.75,
            "issues": [
                {{
                    "description": "Uses complex word 'utilize' instead of 'use'",
                    "severity": "MEDIUM",
                    "suggestion": "Replace 'utilize' with 'use'"
                }}
            ],
            "summary": "Text has some plain language issues. Needs simplification."
        }}
        """


async def test_framework():
    """Test the evaluation framework"""
    
    # Minimal config
    config = {
        "models": {
            "junior": {"provider": "google", "model": "gemma-3-27b-it", "temperature": 0.3, "max_tokens": 2000},
            "senior": {"provider": "google", "model": "gemma-3-27b-it", "temperature": 0.5, "max_tokens": 3000},
            "editor": {"provider": "google", "model": "gemma-3-27b-it", "temperature": 0.7, "max_tokens": 4000}
        },
        "performance": {
            "max_concurrent_juniors": 2,
            "request_timeout": 30
        },
        "reports": {
            "senior": {"priority_threshold": 0.5},
            "editor": {"max_recommendations": 3, "format": "executive", "include_links": True}
        }
    }
    
    # Test text
    test_text = """
    The Medicare program facilitates the provision of healthcare services to eligible 
    Australian residents. Individuals may utilize their Medicare card to access 
    subsidized medical consultations. The implementation of this program has been 
    instrumental in ensuring equitable healthcare access.
    """
    
    print("Testing Evaluation Framework with Gemma 3")
    print("=" * 50)
    
    try:
        # Test a single junior evaluator
        print("\n1. Testing Junior Evaluator...")
        junior = TestStyleGuidePageEvaluator("test_junior", config)
        junior_report = await junior.evaluate(
            test_text, 
            {"source": "https://www.stylemanual.gov.au/writing-style/plain-language"}
        )
        
        print(f"   Score: {junior_report.score:.1%}")
        print(f"   Issues: {len(junior_report.issues)}")
        print(f"   Summary: {junior_report.summary}")
        
        # Save report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(f"framework_test_{timestamp}.json", 'w') as f:
            json.dump(junior_report.to_dict(), f, indent=2)
        
        print(f"\n   Full report saved to: framework_test_{timestamp}.json")
        
        # If junior worked, test senior aggregation
        if junior_report.score > 0:
            print("\n2. Testing Senior Aggregation...")
            # We'd create multiple junior reports and aggregate them
            print("   (Would aggregate multiple junior reports here)")
            
            print("\n3. Testing Editor Synthesis...")
            print("   (Would synthesize senior reports here)")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main entry point"""
    
    # Check API key
    if not os.getenv('GOOGLE_API_KEY'):
        print("ERROR: Please set GOOGLE_API_KEY environment variable")
        return
    
    await test_framework()


if __name__ == "__main__":
    asyncio.run(main())
