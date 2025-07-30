# evaluators/style_guide/page_evaluator.py
"""
Junior evaluator for individual style guide pages
"""

import aiohttp
from bs4 import BeautifulSoup
import logging
from typing import Dict, Any, Optional
from evaluators.base import JuniorEvaluator, EvaluationReport

logger = logging.getLogger(__name__)


class StyleGuidePageEvaluator(JuniorEvaluator):
    """Evaluates content against a single style guide page"""
    
    async def fetch_reference_content(self, source: str) -> str:
        """Fetch and parse style guide page content"""
        # Use the document fetcher
        from utils.document_fetcher import DocumentFetcher
        fetcher = DocumentFetcher(
            cache_dir=self.config.get('cache', {}).get('storage_path', './cache'),
            cache_ttl_hours=self.config.get('cache', {}).get('ttl_hours', 24)
        )
        
        # Fetch the page
        page_data = await fetcher.fetch_page(source)
        
        # Format content for evaluation
        formatted_content = f"Page: {page_data['title']}\n\n"
        
        # Add sections
        for section in page_data['sections']:
            formatted_content += f"\n{section['heading']}:\n{section['content']}\n"
        
        # Fallback to main content if no sections
        if not page_data['sections']:
            formatted_content += page_data['main_content']
        
        return formatted_content
    
    def _build_prompt(self, content: str, reference: str, context: Dict[str, Any]) -> str:
        """Build evaluation prompt for style guide checking"""
        return f"""
        You are a junior content designer evaluating text against a specific style guide page.
        
        IMPORTANT: You must ONLY evaluate based on the rules provided below from the style guide page.
        Do NOT use general knowledge about style guides.
        
        Style Guide Page URL: {context['source']}
        Style Guide Content (this is what you must evaluate against):
        ---START OF STYLE GUIDE CONTENT---
        {reference}
        ---END OF STYLE GUIDE CONTENT---
        
        Text to Evaluate:
        {content}
        
        Task:
        1. Identify ONLY violations of the guidelines shown in the style guide content above
        2. For each issue, quote the specific guideline from the content above
        3. If a potential issue is NOT mentioned in the style guide content above, do NOT flag it
        4. Suggest corrections based ONLY on what the style guide says
        
        Return JSON with:
        - score: 0-1 compliance score
        - issues: array of {{
            description: what rule was violated,
            severity: CRITICAL|HIGH|MEDIUM|LOW,
            location: where in the text,
            quote: exact text that violates,
            guideline_quote: the specific rule from the style guide content (REQUIRED),
            suggestion: how to fix it based on the style guide
          }}
        - summary: 2-3 sentence overview
        - ambiguous_cases: any unclear applications
        - style_guide_used: confirm you used the provided content (yes/no)
        """
    
    async def _get_from_cache(self, key: str) -> Optional[str]:
        """Get content from cache if available"""
        # Implement cache retrieval
        # This is a placeholder
        return None
        
    async def _save_to_cache(self, key: str, content: str) -> None:
        """Save content to cache"""
        # Implement cache storage
        pass


# evaluators/style_guide/section_lead.py
"""
Senior evaluator for style guide sections
"""

from typing import List, Dict, Any, Tuple
from evaluators.base import SeniorEvaluator
from evaluators.style_guide.page_evaluator import StyleGuidePageEvaluator

class StyleGuideSectionLead(SeniorEvaluator):
    """Aggregates evaluations for a section of the style guide"""
    
    def __init__(self, evaluator_id: str, section_name: str, config: Dict[str, Any]):
        super().__init__(evaluator_id, config)
        self.section_name = section_name
        
    async def _get_junior_evaluators(self, context: Dict[str, Any]) -> List[Tuple]:
        """Create junior evaluators for each page in this section"""
        evaluators = []
        
        # Get pages for this section from config
        style_config = self.config['style_guide']
        section_config = next(
            (s for s in style_config['sections'] if s['name'] == self.section_name), 
            None
        )
        
        if not section_config:
            logger.warning(f"No configuration found for section: {self.section_name}")
            return []
            
        base_url = style_config['base_url']
        
        for page_path in section_config['pages']:
            url = f"{base_url}{page_path}"
            evaluator = StyleGuidePageEvaluator(
                evaluator_id=f"style_page_{page_path.replace('/', '_')}",
                config=self.config
            )
            evaluators.append((evaluator, url))
            
        return evaluators
    
    def _build_aggregation_prompt(
        self, 
        reports: List[EvaluationReport], 
        content: str,
        context: Dict[str, Any]
    ) -> str:
        """Build prompt for section-level aggregation"""
        return f"""
        You are a senior content designer responsible for the "{self.section_name}" section
        of the Australian Government Style Guide.
        
        Original content being evaluated:
        {content[:1000]}...
        
        Junior evaluator reports from individual style guide pages:
        {self._format_junior_reports(reports)}
        
        Your task:
        1. Identify patterns across multiple page violations
        2. Prioritize issues based on impact and frequency
        3. Consolidate similar issues to avoid duplication
        4. Highlight any conflicting guidance between pages
        5. Provide section-level recommendations
        
        Consider:
        - Which violations are most critical for {self.section_name}?
        - Are there systematic issues with how the content approaches this section?
        - What would have the biggest impact if fixed?
        
        Return JSON with:
        - score: overall section compliance (0-1)
        - consolidated_issues: array of prioritized issues with:
          - description, severity, sources (which pages flagged this)
          - pattern (if this represents multiple similar issues)
        - patterns: recurring problems across pages
        - conflicts: any contradictions found
        - summary: executive summary for this section
        """
    
    def _format_junior_reports(self, reports: List[EvaluationReport]) -> str:
        """Format junior reports with focus on issues and patterns"""
        formatted = []
        
        for report in reports:
            page_url = report.metadata.get('source', 'Unknown')
            page_name = page_url.split('/')[-1] or page_url
            
            issues_summary = []
            for issue in report.issues[:5]:  # Top 5 issues
                issues_summary.append(
                    f"  - {issue.severity.name}: {issue.description[:100]}..."
                )
            
            formatted.append(f"""
            Page: {page_name}
            Score: {report.score:.2f}
            Issues Found: {len(report.issues)}
            Top Issues:
            {chr(10).join(issues_summary)}
            Summary: {report.summary}
            """)
            
        return "\n---\n".join(formatted)


# evaluators/style_guide/editor.py
"""
Editor evaluator for final style guide assessment
"""

from typing import List, Dict, Any
from evaluators.base import EditorEvaluator, EvaluationReport, Issue, Severity

class StyleGuideEditor(EditorEvaluator):
    """Final synthesis of all style guide section evaluations"""
    
    def _build_synthesis_prompt(
        self, 
        reports: List[EvaluationReport], 
        content: str,
        context: Dict[str, Any]
    ) -> str:
        """Build prompt for final style guide synthesis"""
        return f"""
        You are the editor-in-chief reviewing style guide compliance across all sections.
        
        Content Evaluated (excerpt):
        {content[:500]}...
        
        Section Lead Reports:
        {self._format_section_reports(reports)}
        
        Provide an executive assessment including:
        
        1. Overall Style Guide Compliance Score (0-100%)
        2. Top 5 Recommendations (actionable, specific, impactful)
        3. Critical Issues requiring immediate attention
        4. Patterns indicating systematic problems
        5. Strengths - what the content does well
        6. Quick wins - easy fixes with high impact
        
        Consider the audience: senior stakeholders who need clear, actionable insights.
        Each recommendation should include:
        - What to change
        - Why it matters
        - Expected impact
        - Which section(s) it relates to
        
        Return JSON with:
        - final_score: 0-1
        - recommendations: array with description, severity, action, impact, sections
        - critical_issues: issues needing immediate attention
        - systematic_patterns: recurring problems across sections
        - strengths: what's working well
        - quick_wins: easy improvements
        - executive_summary: 3-4 sentences for executives
        """
    
    def _format_section_reports(self, reports: List[EvaluationReport]) -> str:
        """Format section reports with focus on actionable insights"""
        formatted = []
        
        # Group by severity
        critical_count = 0
        high_count = 0
        
        for report in reports:
            section = report.metadata.get('section', 'Unknown Section')
            
            critical_issues = [i for i in report.issues if i.severity == Severity.CRITICAL]
            high_issues = [i for i in report.issues if i.severity == Severity.HIGH]
            
            critical_count += len(critical_issues)
            high_count += len(high_issues)
            
            formatted.append(f"""
            === {section} ===
            Compliance Score: {report.score:.1%}
            Critical Issues: {len(critical_issues)}
            High Priority Issues: {len(high_issues)}
            Total Issues: {len(report.issues)}
            
            Key Findings:
            {report.summary}
            
            Top Issues:
            {self._format_top_issues(report.issues[:3])}
            
            Pages Evaluated: {report.metadata.get('junior_reports_count', 0)}
            """)
        
        header = f"""
        OVERALL STATISTICS:
        - Sections Evaluated: {len(reports)}
        - Critical Issues: {critical_count}
        - High Priority Issues: {high_count}
        - Average Compliance: {sum(r.score for r in reports) / len(reports):.1%}
        
        SECTION DETAILS:
        """
        
        return header + "\n".join(formatted)
    
    def _format_top_issues(self, issues: List[Issue]) -> str:
        """Format top issues for the report"""
        if not issues:
            return "- No significant issues found"
            
        formatted = []
        for issue in issues:
            formatted.append(
                f"- [{issue.severity.name}] {issue.description[:150]}..."
            )
        return "\n".join(formatted)
    
    async def generate_markdown_report(self, report: EvaluationReport) -> str:
        """Generate a formatted markdown report"""
        lines = [
            "# Style Guide Compliance Report",
            f"*Generated: {report.timestamp.strftime('%Y-%m-%d %H:%M')}*",
            "",
            "## Executive Summary",
            report.summary,
            "",
            f"**Overall Compliance Score: {report.score:.1%}**",
            ""
        ]
        
        # Critical issues
        critical_issues = report.metadata.get('critical_count', 0)
        if critical_issues > 0:
            lines.extend([
                "## ⚠️ Critical Issues",
                f"*{critical_issues} issues requiring immediate attention*",
                ""
            ])
            
        # Top recommendations
        lines.extend([
            "## 📋 Top Recommendations",
            ""
        ])
        
        for i, issue in enumerate(report.issues[:5], 1):
            lines.extend([
                f"### {i}. {issue.description}",
                f"**Severity:** {issue.severity.name}",
                f"**Action:** {issue.suggestion or 'Review and update'}",
                ""
            ])
        
        # Strengths
        strengths = report.metadata.get('strengths', [])
        if strengths:
            lines.extend([
                "## ✅ Strengths",
                ""
            ])
            for strength in strengths:
                lines.append(f"- {strength}")
            lines.append("")
        
        # Section breakdown
        if report.sub_reports:
            lines.extend([
                "## 📊 Section Breakdown",
                "",
                "| Section | Score | Issues | Status |",
                "|---------|-------|--------|--------|"
            ])
            
            for sub_report in report.sub_reports:
                section = sub_report.metadata.get('section', 'Unknown')
                score = sub_report.score
                issues = len(sub_report.issues)
                status = "🟢" if score > 0.8 else "🟡" if score > 0.6 else "🔴"
                
                lines.append(
                    f"| {section} | {score:.1%} | {issues} | {status} |"
                )
        
        return "\n".join(lines)
