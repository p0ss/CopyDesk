#!/usr/bin/env python3
"""
Comprehensive Style Guide Evaluator
Evaluates content against ALL pages in the Australian Government Style Manual
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
import json
import os
import yaml
from typing import Dict, List, Any, Tuple
from collections import defaultdict
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add project to path
import sys
sys.path.insert(0, os.getcwd())

from evaluators.base import (
    BaseEvaluator, JuniorEvaluator, SeniorEvaluator, EditorEvaluator,
    EvaluationReport, Issue, Severity
)
from utils.document_fetcher import DocumentFetcher


def load_config() -> Dict[str, Any]:
    """Load configuration from file or use defaults"""
    config_path = Path("config/evaluation_config.yaml")
    
    if config_path.exists():
        logger.info(f"Loading config from: {config_path}")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
        # Log what models we're using
        logger.info("Model configuration:")
        logger.info(f"  Junior: {config['models']['junior']['provider']} / {config['models']['junior']['model']}")
        logger.info(f"  Senior: {config['models']['senior']['provider']} / {config['models']['senior']['model']}")
        logger.info(f"  Editor: {config['models']['editor']['provider']} / {config['models']['editor']['model']}")
        
        return config
    else:
        logger.warning("Config file not found, using defaults")
        # Default config
        return {
            "models": {
                "junior": {
                    "provider": "openai",
                    "model": "gpt-3.5-turbo",
                    "temperature": 0.3,
                    "max_tokens": 2000
                },
                "senior": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.5,
                    "max_tokens": 4000
                },
                "editor": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "temperature": 0.7,
                    "max_tokens": 8000
                }
            },
            "performance": {
                "max_concurrent_juniors": 5,
                "request_timeout": 30
            },
            "cache": {
                "enabled": True,
                "ttl_hours": 24,
                "storage_path": "./cache"
            },
            "reports": {
                "senior": {"priority_threshold": 0.5},
                "editor": {
                    "max_recommendations": 10,
                    "format": "executive",
                    "include_links": True
                }
            }
        }


class SitemapFetcher:
    """Fetches and parses the Style Manual sitemap"""
    
    def __init__(self, sitemap_url: str = "https://www.stylemanual.gov.au/sitemap.xml"):
        self.sitemap_url = sitemap_url
        
    async def fetch_urls(self) -> List[Dict[str, Any]]:
        """Fetch all URLs from the sitemap"""
        async with aiohttp.ClientSession() as session:
            async with session.get(self.sitemap_url) as response:
                content = await response.text()
                
        # Parse XML
        root = ET.fromstring(content)
        
        # Extract URLs - handle namespace
        urls = []
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        
        for url_elem in root.findall('.//ns:url', namespace):
            loc = url_elem.find('ns:loc', namespace)
            lastmod = url_elem.find('ns:lastmod', namespace)
            
            if loc is not None:
                url_data = {
                    'url': loc.text,
                    'lastmod': lastmod.text if lastmod is not None else None
                }
                urls.append(url_data)
                
        logger.info(f"Found {len(urls)} URLs in sitemap")
        return urls
    
    def categorize_urls(self, urls: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Categorize URLs by section"""
        categories = defaultdict(list)
        
        for url_data in urls:
            url = url_data['url']
            
            # Skip non-content pages
            skip_patterns = [
                '/search', '/404', '/sitemap', '/accessibility-statement',
                '/privacy', '/terms', '/feedback', '.pdf'
            ]
            if any(pattern in url for pattern in skip_patterns):
                continue
                
            # Extract section from URL
            parts = url.replace('https://www.stylemanual.gov.au/', '').split('/')
            
            if len(parts) >= 1 and parts[0]:
                section = parts[0].replace('-', ' ').title()
                categories[section].append(url)
            else:
                categories['Home'].append(url)
                
        # Log categorization
        for section, urls in categories.items():
            logger.info(f"Section '{section}': {len(urls)} pages")
            
        return dict(categories)


class StyleManualPageEvaluator(JuniorEvaluator):
    """Evaluates content against a single Style Manual page"""
    
    def __init__(self, evaluator_id: str, config: Dict[str, Any], fetcher: DocumentFetcher):
        super().__init__(evaluator_id, config)
        self.fetcher = fetcher
        
    async def fetch_reference_content(self, source: str) -> str:
        """Fetch style guide page content"""
        try:
            page_data = await self.fetcher.fetch_page(source)
            
            # Format content
            formatted = f"Page: {page_data['title']}\nURL: {source}\n\n"
            
            # Add main content
            if page_data['sections']:
                for section in page_data['sections']:
                    # Skip navigation/feedback sections
                    if any(skip in section['heading'].lower() for skip in 
                          ['feedback', 'help us', 'last updated', 'contact']):
                        continue
                    formatted += f"\n{section['heading']}:\n{section['content']}\n"
            else:
                formatted += page_data['main_content']
                
            return formatted
            
        except Exception as e:
            logger.error(f"Error fetching {source}: {e}")
            return f"Error fetching page: {str(e)}"
    
    def _build_prompt(self, content: str, reference: str, context: Dict[str, Any]) -> str:
        """Build evaluation prompt"""
        return f"""
        Evaluate this text against specific Style Manual guidelines.
        
        Style Manual Page:
        {reference[:2000]}...
        
        Text to evaluate:
        {content}
        
        Instructions:
        1. ONLY flag violations of rules explicitly stated in the Style Manual content above
        2. Do NOT use general style knowledge - only what's in the reference
        3. Quote the specific guideline being violated
        4. Prioritize issues by their impact on clarity and accessibility
        
        Return JSON:
        {{
            "score": 0.0-1.0,
            "issues": [
                {{
                    "description": "what rule was violated",
                    "severity": "CRITICAL|HIGH|MEDIUM|LOW",
                    "location": "where in the text",
                    "quote": "the problematic text",
                    "guideline_quote": "the specific rule from the style guide",
                    "suggestion": "how to fix it"
                }}
            ],
            "summary": "2-3 sentence overview",
            "page_applicable": true/false (is this page relevant to the content?)
        }}
        """


class StyleManualSectionLead(SeniorEvaluator):
    """Aggregates all page evaluations for a section"""
    
    def __init__(self, evaluator_id: str, section_name: str, urls: List[str], 
                 config: Dict[str, Any], fetcher: DocumentFetcher):
        super().__init__(evaluator_id, config)
        self.section_name = section_name
        self.urls = urls
        self.fetcher = fetcher
        
    async def _get_junior_evaluators(self, context: Dict[str, Any]) -> List[Tuple]:
        """Create evaluators for each page in section"""
        evaluators = []
        
        for url in self.urls:
            page_id = url.split('/')[-1] or 'index'
            evaluator = StyleManualPageEvaluator(
                f"{self.section_name}_{page_id}",
                self.config,
                self.fetcher
            )
            evaluators.append((evaluator, url))
            
        return evaluators
    
    def _build_aggregation_prompt(self, reports: List[EvaluationReport], 
                                 content: str, context: Dict[str, Any]) -> str:
        """Build section aggregation prompt"""
        # Filter out non-applicable pages
        applicable_reports = [r for r in reports 
                            if r.metadata.get('page_applicable', True)]
        
        return f"""
        As section lead for "{self.section_name}", synthesize these page evaluations.
        
        Content evaluated:
        {content[:500]}...
        
        Page Reports ({len(applicable_reports)} applicable of {len(reports)} total):
        {self._format_reports_for_aggregation(applicable_reports)}
        
        Tasks:
        1. Identify the most important issues for this section
        2. Find patterns across multiple pages
        3. Consolidate duplicate issues
        4. Prioritize by impact on user comprehension
        
        Return JSON:
        {{
            "score": 0.0-1.0,
            "consolidated_issues": [
                {{
                    "description": "issue description",
                    "severity": "CRITICAL|HIGH|MEDIUM|LOW",
                    "sources": ["page URLs that flagged this"],
                    "pattern": "if this is a recurring issue",
                    "suggestion": "how to address"
                }}
            ],
            "patterns": ["recurring problems"],
            "summary": "section-level insights",
            "pages_evaluated": {len(reports)},
            "pages_applicable": {len(applicable_reports)}
        }}
        """
    
    def _format_reports_for_aggregation(self, reports: List[EvaluationReport]) -> str:
        """Format reports for the aggregation prompt"""
        formatted = []
        
        for report in reports:
            url = report.metadata.get('source', 'Unknown')
            page_name = url.split('/')[-1] or 'home'
            
            issues_text = []
            for issue in report.issues[:3]:  # Top 3 issues per page
                issues_text.append(
                    f"  - {issue.severity.name}: {issue.description}"
                )
            
            formatted.append(f"""
            Page: {page_name}
            Score: {report.score:.2f}
            Issues: {len(report.issues)}
            {chr(10).join(issues_text) if issues_text else '  - No issues found'}
            """)
            
        return "\n---\n".join(formatted)


class ComprehensiveStyleGuideEvaluator:
    """Main orchestrator for full Style Manual evaluation"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Use cache settings from config
        cache_config = config.get('cache', {})
        self.fetcher = DocumentFetcher(
            cache_dir=cache_config.get('storage_path', './cache'),
            cache_ttl_hours=cache_config.get('ttl_hours', 24)
        )
        self.sitemap_fetcher = SitemapFetcher()
        
    async def evaluate_content(self, content: str) -> Dict[str, Any]:
        """Evaluate content against entire Style Manual"""
        start_time = datetime.now()
        
        # Fetch and categorize URLs
        logger.info("Fetching Style Manual sitemap...")
        urls = await self.sitemap_fetcher.fetch_urls()
        categories = self.sitemap_fetcher.categorize_urls(urls)
        
        # Create section evaluators
        section_evaluators = []
        for section_name, section_urls in categories.items():
            if section_urls:  # Only create if section has URLs
                evaluator = StyleManualSectionLead(
                    f"section_{section_name.lower().replace(' ', '_')}",
                    section_name,
                    section_urls,
                    self.config,
                    self.fetcher
                )
                section_evaluators.append(evaluator)
        
        logger.info(f"Created {len(section_evaluators)} section evaluators")
        
        # Run section evaluations in parallel (with limit)
        semaphore = asyncio.Semaphore(3)  # Max 3 sections at once
        
        async def evaluate_section(evaluator):
            async with semaphore:
                logger.info(f"Evaluating section: {evaluator.section_name}")
                return await evaluator.evaluate(content, {
                    'section': evaluator.section_name
                })
        
        section_reports = await asyncio.gather(*[
            evaluate_section(evaluator) for evaluator in section_evaluators
        ])
        
        # Create final editor evaluation
        editor = StyleManualComprehensiveEditor("final_editor", self.config)
        final_report = await editor.evaluate(content, {
            'senior_reports': section_reports,
            'total_pages': len(urls),
            'sections': list(categories.keys())
        })
        
        # Generate comprehensive report
        evaluation_time = (datetime.now() - start_time).total_seconds()
        
        return {
            'final_report': final_report.to_dict(),
            'section_reports': [r.to_dict() for r in section_reports],
            'metadata': {
                'total_pages_checked': len(urls),
                'sections_evaluated': len(categories),
                'evaluation_time_seconds': evaluation_time,
                'timestamp': datetime.now().isoformat()
            }
        }
    
    async def generate_markdown_report(self, evaluation: Dict[str, Any]) -> str:
        """Generate a comprehensive markdown report"""
        final_report = evaluation['final_report']
        section_reports = evaluation['section_reports']
        metadata = evaluation['metadata']
        
        lines = [
            "# Comprehensive Style Manual Compliance Report",
            f"*Generated: {metadata['timestamp']}*",
            f"*Evaluation time: {metadata['evaluation_time_seconds']:.1f} seconds*",
            "",
            "## Executive Summary",
            final_report['summary'],
            "",
            f"**Overall Compliance Score: {final_report['score']:.1%}**",
            "",
            f"- **Pages Evaluated**: {metadata['total_pages_checked']}",
            f"- **Sections Analyzed**: {metadata['sections_evaluated']}",
            f"- **Critical Issues**: {final_report['metadata'].get('critical_count', 0)}",
            f"- **High Priority Issues**: {final_report['metadata'].get('high_count', 0)}",
            ""
        ]
        
        # Top recommendations
        if final_report['issues']:
            lines.extend([
                "## 🎯 Top Recommendations",
                ""
            ])
            
            for i, issue in enumerate(final_report['issues'][:5], 1):
                lines.extend([
                    f"### {i}. {issue['description']}",
                    f"**Severity**: {issue['severity']}",
                    f"**Action**: {issue.get('suggestion', 'Review and update')}",
                    ""
                ])
        
        # Section breakdown
        lines.extend([
            "## 📊 Section Analysis",
            "",
            "| Section | Score | Issues | Pages Checked | Status |",
            "|---------|-------|--------|---------------|--------|"
        ])
        
        for report in section_reports:
            section = report['metadata'].get('section', 'Unknown')
            score = report['score']
            issues = len(report['issues'])
            pages = report['metadata'].get('pages_evaluated', 0)
            status = "🟢" if score > 0.8 else "🟡" if score > 0.6 else "🔴"
            
            lines.append(
                f"| {section} | {score:.1%} | {issues} | {pages} | {status} |"
            )
        
        # Patterns identified
        patterns = final_report['metadata'].get('patterns', [])
        if patterns:
            lines.extend([
                "",
                "## 🔄 Recurring Patterns",
                ""
            ])
            for pattern in patterns:
                lines.append(f"- {pattern}")
        
        # Strengths
        strengths = final_report['metadata'].get('strengths', [])
        if strengths:
            lines.extend([
                "",
                "## ✅ Strengths",
                ""
            ])
            for strength in strengths:
                lines.append(f"- {strength}")
        
        return "\n".join(lines)


class StyleManualComprehensiveEditor(EditorEvaluator):
    """Final editor for comprehensive Style Manual evaluation"""
    
    async def _call_llm(self, client: Any, prompt: str) -> Dict[str, Any]:
        """Call LLM with comprehensive synthesis prompt"""
        # This will use the actual LLM implementation from base.py
        return await super()._call_llm(client, prompt)


async def main():
    """Run comprehensive Style Manual evaluation"""
    
    # Load configuration
    config = load_config()
    
    # Check for appropriate API key based on config
    provider = config['models']['junior']['provider']
    if provider == 'openai' and not os.getenv('OPENAI_API_KEY'):
        print("ERROR: Please set OPENAI_API_KEY environment variable")
        return
    elif provider == 'google' and not os.getenv('GOOGLE_API_KEY'):
        print("ERROR: Please set GOOGLE_API_KEY environment variable")
        return
    
    # Test content
    test_content = """
    The Medicare program facilitates the provision of healthcare services to eligible 
    Australian residents. Individuals may utilize their Medicare card to access 
    subsidized medical consultations. The implementation of this program has been 
    instrumental in ensuring equitable healthcare access across the nation.
    
    To be eligible for Medicare benefits, persons must satisfy specific criteria 
    established by the Department. The application process requires the submission 
    of appropriate documentation to verify eligibility status.
    """
    
    print("🚀 Starting Comprehensive Style Manual Evaluation")
    print("=" * 70)
    print(f"Content to evaluate ({len(test_content)} chars):")
    print(test_content)
    print("=" * 70)
    
    # Create evaluator
    evaluator = ComprehensiveStyleGuideEvaluator(config)
    
    try:
        # Run evaluation
        print("\n📊 Evaluating content against entire Style Manual...")
        print("This will take several minutes as we check against all pages.\n")
        
        evaluation = await evaluator.evaluate_content(test_content)
        
        # Generate report
        markdown_report = await evaluator.generate_markdown_report(evaluation)
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save JSON
        json_filename = f"comprehensive_evaluation_{timestamp}.json"
        with open(json_filename, 'w') as f:
            json.dump(evaluation, f, indent=2)
        print(f"\n💾 Full evaluation saved to: {json_filename}")
        
        # Save markdown
        md_filename = f"comprehensive_report_{timestamp}.md"
        with open(md_filename, 'w') as f:
            f.write(markdown_report)
        print(f"📄 Markdown report saved to: {md_filename}")
        
        # Print summary
        print("\n" + "=" * 70)
        print("EVALUATION COMPLETE")
        print("=" * 70)
        print(f"Overall Score: {evaluation['final_report']['score']:.1%}")
        print(f"Pages Checked: {evaluation['metadata']['total_pages_checked']}")
        print(f"Time Taken: {evaluation['metadata']['evaluation_time_seconds']:.1f} seconds")
        
        # Print top issues
        issues = evaluation['final_report']['issues']
        if issues:
            print(f"\nTop Issues Found:")
            for i, issue in enumerate(issues[:3], 1):
                print(f"{i}. [{issue['severity']}] {issue['description']}")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
