# evaluators/style_guide/section_lead.py
"""
Senior evaluator for style guide sections
"""

from typing import List, Dict, Any, Tuple
from evaluators.base import SeniorEvaluator, EvaluationReport
from evaluators.style_guide.page_evaluator import StyleGuidePageEvaluator
import logging

logger = logging.getLogger(__name__)

class StyleGuideSectionLead(SeniorEvaluator):
    """Aggregates evaluations for a section of the style guide"""

    def __init__(self, evaluator_id: str, section_name: str, config: Dict[str, Any]):
        super().__init__(evaluator_id, config)
        self.section_name = section_name
        self.on_page_started = None
        self.on_page_completed = None

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
