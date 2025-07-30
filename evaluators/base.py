import os# evaluators/base.py
"""
Base classes for the hierarchical evaluation framework
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
import asyncio
from enum import Enum
import logging
import json

logger = logging.getLogger(__name__)


class Severity(Enum):
    """Issue severity levels"""
    CRITICAL = 1.0
    HIGH = 0.8
    MEDIUM = 0.5
    LOW = 0.3
    INFO = 0.1


@dataclass
class Issue:
    """Represents a single issue found during evaluation"""
    description: str
    severity: Severity
    location: Optional[str] = None
    suggestion: Optional[str] = None
    source_url: Optional[str] = None
    quote: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationReport:
    """Base evaluation report structure"""
    evaluator_id: str
    evaluator_role: str  # junior, senior, editor
    timestamp: datetime
    score: float  # 0-1, where 1 is perfect
    issues: List[Issue]
    summary: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    sub_reports: List['EvaluationReport'] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary for serialization"""
        return {
            "evaluator_id": self.evaluator_id,
            "evaluator_role": self.evaluator_role,
            "timestamp": self.timestamp.isoformat(),
            "score": self.score,
            "issues": [
                {
                    "description": issue.description,
                    "severity": issue.severity.name,
                    "location": issue.location,
                    "suggestion": issue.suggestion,
                    "source_url": issue.source_url,
                    "quote": issue.quote,
                    "metadata": issue.metadata
                }
                for issue in self.issues
            ],
            "summary": self.summary,
            "metadata": self.metadata,
            "sub_reports": [report.to_dict() for report in self.sub_reports]
        }


class BaseEvaluator(ABC):
    """Abstract base class for all evaluators"""

    def __init__(self, evaluator_id: str, role: str, config: Dict[str, Any]):
        self.evaluator_id = evaluator_id
        self.role = role  # junior, senior, editor
        self.config = config
        self.model_config = config['models'][role]

    @abstractmethod
    async def evaluate(self, content: str, context: Dict[str, Any]) -> EvaluationReport:
        """Perform evaluation and return report"""
        pass

    async def get_llm_client(self):
        """Get appropriate LLM client based on config"""
        provider = self.model_config['provider']

        if provider == 'openai':
            from openai import AsyncOpenAI
            return AsyncOpenAI()
        elif provider == 'google':
            import google.generativeai as genai
            genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
            return genai.GenerativeModel(self.model_config['model'])
        elif provider == 'anthropic':
            from anthropic import AsyncAnthropic
            return AsyncAnthropic()
        else:
            raise ValueError(f"Unknown provider: {provider}")


class JuniorEvaluator(BaseEvaluator):
    """Base class for junior evaluators that check against single sources"""

    def __init__(self, evaluator_id: str, config: Dict[str, Any]):
        super().__init__(evaluator_id, "junior", config)

    @abstractmethod
    async def fetch_reference_content(self, source: str) -> str:
        """Fetch the reference content to evaluate against"""
        pass

    async def evaluate(self, content: str, context: Dict[str, Any]) -> EvaluationReport:
        """Evaluate content against a single reference source"""
        reference_content = await self.fetch_reference_content(context['source'])

        client = await self.get_llm_client()

        # Build evaluation prompt
        prompt = self._build_prompt(content, reference_content, context)

        # Get evaluation from LLM
        result = await self._call_llm(client, prompt)

        # Parse result into report
        report = self._parse_result(result, context)

        return report

    @abstractmethod
    def _build_prompt(self, content: str, reference: str, context: Dict[str, Any]) -> str:
        """Build the evaluation prompt"""
        pass

    async def _call_llm(self, client: Any, prompt: str) -> Dict[str, Any]:
        """Call the LLM and get structured response"""
        provider = self.model_config['provider']

        if provider == 'openai':
            response = await client.chat.completions.create(
                model=self.model_config['model'],
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=self.model_config.get('temperature', 0.5)
            )
            return json.loads(response.choices[0].message.content)
        elif provider == 'google':
            # Google Gemini/Gemma implementation
            # Add instruction to output JSON
            json_prompt = prompt + "\n\nIMPORTANT: Output your response as valid JSON only, with no additional text."

            response = await client.generate_content_async(
                json_prompt,
                generation_config={
                    "temperature": self.model_config.get('temperature', 0.5),
                    "max_output_tokens": self.model_config.get('max_tokens', 2000)
                }
            )

            # Extract JSON from response
            response_text = response.text.strip()

            # Try to find JSON in the response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response_text

            return json.loads(json_str)
        else:
            raise NotImplementedError(f"Provider {provider} not implemented")

    def _parse_result(self, result: Dict[str, Any], context: Dict[str, Any]) -> EvaluationReport:
        """Parse LLM result into evaluation report"""
        issues = []
        for issue_data in result.get('issues', []):
            issues.append(Issue(
                description=issue_data['description'],
                severity=Severity[issue_data['severity']],
                location=issue_data.get('location'),
                suggestion=issue_data.get('suggestion'),
                source_url=context.get('source'),
                quote=issue_data.get('quote')
            ))

        return EvaluationReport(
            evaluator_id=self.evaluator_id,
            evaluator_role=self.role,
            timestamp=datetime.now(),
            score=result.get('score', 0.5),
            issues=issues,
            summary=result.get('summary', ''),
            metadata={
                'source': context.get('source'),
                'tokens_used': result.get('tokens_used', 0)
            }
        )


class SeniorEvaluator(BaseEvaluator):
    """Base class for senior evaluators that aggregate junior reports"""

    def __init__(self, evaluator_id: str, config: Dict[str, Any]):
        super().__init__(evaluator_id, "senior", config)

    async def evaluate(self, content: str, context: Dict[str, Any]) -> EvaluationReport:
        """Coordinate junior evaluators and aggregate their reports"""
        # Get junior evaluators for this section
        junior_evaluators = await self._get_junior_evaluators(context)

        # Run evaluations in parallel with rate limiting
        semaphore = asyncio.Semaphore(self.config['performance']['max_concurrent_juniors'])

        async def run_junior(evaluator, source):
            async with semaphore:
                return await evaluator.evaluate(content, {'source': source, **context})

        tasks = [
            run_junior(evaluator, source)
            for evaluator, source in junior_evaluators
        ]

        junior_reports = await asyncio.gather(*tasks)

        # Aggregate reports
        aggregated_report = await self._aggregate_reports(junior_reports, content, context)

        return aggregated_report

    @abstractmethod
    async def _get_junior_evaluators(self, context: Dict[str, Any]) -> List[tuple]:
        """Get list of (junior_evaluator, source) tuples"""
        pass

    async def _aggregate_reports(
        self,
        reports: List[EvaluationReport],
        content: str,
        context: Dict[str, Any]
    ) -> EvaluationReport:
        """Aggregate junior reports into senior report"""
        client = await self.get_llm_client()

        # Build aggregation prompt
        prompt = self._build_aggregation_prompt(reports, content, context)

        # Get aggregated analysis
        result = await self._call_llm(client, prompt)

        # Create aggregated report
        aggregated_issues = self._consolidate_issues(reports, result)

        return EvaluationReport(
            evaluator_id=self.evaluator_id,
            evaluator_role=self.role,
            timestamp=datetime.now(),
            score=self._calculate_aggregated_score(reports, result),
            issues=aggregated_issues,
            summary=result.get('summary', ''),
            metadata={
                'section': context.get('section'),
                'junior_reports_count': len(reports)
            },
            sub_reports=reports
        )

    def _build_aggregation_prompt(
        self,
        reports: List[EvaluationReport],
        content: str,
        context: Dict[str, Any]
    ) -> str:
        """Build prompt for aggregating junior reports"""
        return f"""
        As a senior {context.get('section', '')} evaluator, analyze these junior evaluation reports
        and provide an aggregated assessment.

        Original content being evaluated:
        {content[:1000]}...

        Junior Reports Summary:
        {self._summarize_reports(reports)}

        Provide:
        1. Overall assessment of compliance with {context.get('section', 'guidelines')}
        2. Consolidated list of significant issues (severity > {self.config['reports']['senior']['priority_threshold']})
        3. Patterns or recurring problems
        4. Strategic recommendations

        Return as JSON with: score, issues, patterns, summary
        """

    def _summarize_reports(self, reports: List[EvaluationReport]) -> str:
        """Create summary of junior reports for prompt"""
        summary_parts = []
        for report in reports:
            summary_parts.append(f"""
            Source: {report.metadata.get('source', 'Unknown')}
            Score: {report.score:.2f}
            Issues: {len(report.issues)}
            Key findings: {report.summary[:200]}...
            """)
        return "\n".join(summary_parts)

    def _consolidate_issues(
        self,
        reports: List[EvaluationReport],
        aggregation_result: Dict[str, Any]
    ) -> List[Issue]:
        """Consolidate issues from junior reports based on senior analysis"""
        # This would implement intelligent deduplication and prioritization
        consolidated = []

        # Add high-priority issues identified by senior evaluator
        for issue_data in aggregation_result.get('consolidated_issues', []):
            consolidated.append(Issue(
                description=issue_data['description'],
                severity=Severity[issue_data['severity']],
                suggestion=issue_data.get('suggestion'),
                metadata={'sources': issue_data.get('sources', [])}
            ))

        return consolidated

    def _calculate_aggregated_score(
        self,
        reports: List[EvaluationReport],
        result: Dict[str, Any]
    ) -> float:
        """Calculate aggregated score from junior reports"""
        if result.get('score') is not None:
            return result['score']

        # Weighted average based on number of issues
        total_weight = sum(len(r.issues) + 1 for r in reports)
        weighted_sum = sum(r.score * (len(r.issues) + 1) for r in reports)

        return weighted_sum / total_weight if total_weight > 0 else 0.5


class EditorEvaluator(BaseEvaluator):
    """Final editor that synthesizes all senior reports"""

    def __init__(self, evaluator_id: str, config: Dict[str, Any]):
        super().__init__(evaluator_id, "editor", config)

    async def evaluate(self, content: str, context: Dict[str, Any]) -> EvaluationReport:
        """Synthesize all senior reports into final evaluation"""
        senior_reports = context.get('senior_reports', [])

        client = await self.get_llm_client()

        # Build synthesis prompt
        prompt = self._build_synthesis_prompt(senior_reports, content, context)

        # Get final synthesis
        result = await self._call_llm(client, prompt)

        # Create final report
        return self._create_final_report(result, senior_reports)

    def _build_synthesis_prompt(
        self,
        reports: List[EvaluationReport],
        content: str,
        context: Dict[str, Any]
    ) -> str:
        """Build prompt for final synthesis"""
        return f"""
        As the editor, provide a final evaluation synthesis.

        Content evaluated:
        {content[:500]}...

        Senior Section Reports:
        {self._format_senior_reports(reports)}

        Provide an executive summary including:
        1. Overall compliance score and assessment
        2. Top {self.config['reports']['editor']['max_recommendations']} recommendations
        3. Critical issues requiring immediate attention
        4. Strengths to maintain

        Format for {self.config['reports']['editor']['format']} audience.
        Include source links: {self.config['reports']['editor']['include_links']}

        Return as JSON with: final_score, recommendations, critical_issues, strengths, executive_summary
        """

    def _format_senior_reports(self, reports: List[EvaluationReport]) -> str:
        """Format senior reports for editor prompt"""
        formatted = []
        for report in reports:
            formatted.append(f"""
            Section: {report.metadata.get('section', 'Unknown')}
            Score: {report.score:.2f}
            Critical Issues: {sum(1 for i in report.issues if i.severity == Severity.CRITICAL)}
            Summary: {report.summary}
            """)
        return "\n".join(formatted)

    def _create_final_report(
        self,
        result: Dict[str, Any],
        senior_reports: List[EvaluationReport]
    ) -> EvaluationReport:
        """Create final evaluation report"""
        # Extract top recommendations as issues
        final_issues = []
        for rec in result.get('recommendations', []):
            final_issues.append(Issue(
                description=rec['description'],
                severity=Severity[rec.get('severity', 'HIGH')],
                suggestion=rec.get('action'),
                metadata={'category': rec.get('category')}
            ))

        return EvaluationReport(
            evaluator_id=self.evaluator_id,
            evaluator_role=self.role,
            timestamp=datetime.now(),
            score=result.get('final_score', 0.5),
            issues=final_issues,
            summary=result.get('executive_summary', ''),
            metadata={
                'evaluation_type': context.get('evaluation_type'),
                'strengths': result.get('strengths', []),
                'critical_count': len(result.get('critical_issues', []))
            },
            sub_reports=senior_reports
        )
