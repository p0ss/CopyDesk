import os
from utils.rate_limiter import ProviderRateLimiter# evaluators/base.py
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
    
    # Class-level rate limiter shared across all evaluators
    _rate_limiter = None
    
    def __init__(self, evaluator_id: str, role: str, config: Dict[str, Any]):
        self.evaluator_id = evaluator_id
        self.role = role  # junior, senior, editor
        self.config = config
        self.model_config = config['models'][role]
        
        # Initialize rate limiter once
        if BaseEvaluator._rate_limiter is None:
            BaseEvaluator._rate_limiter = ProviderRateLimiter(config)
        
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
    
    async def _call_llm(self, client, prompt: str) -> Dict[str, Any]:
        """Call the LLM and get structured response"""
        provider = self.model_config['provider']
        model = self.model_config['model']
        
        # Apply rate limiting
        if self._rate_limiter:
            await self._rate_limiter.acquire(provider, model)
        
        try:
            if provider == 'openai':
                response = await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=self.model_config.get('temperature', 0.5)
                )
                
                content = response.choices[0].message.content
                if not content:
                    logger.warning("Empty response from OpenAI")
                    return self._get_fallback_result()
                
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response from OpenAI. Error: {e}")
                    logger.debug(f"Raw content (first 500 chars): {content[:500]}...")
                    
                    # Try to fix common JSON issues
                    try:
                        # Try to find complete JSON objects in the response
                        import re
                        json_match = re.search(r'\{.*\}', content, re.DOTALL)
                        if json_match:
                            fixed_content = json_match.group(0)
                            return json.loads(fixed_content)
                    except (json.JSONDecodeError, AttributeError):
                        pass
                    
                    logger.warning("Could not recover JSON from response, using fallback")
                    return self._get_fallback_result()
                    
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
                
                if not response_text:
                    logger.warning("Empty response from Google")
                    return self._get_fallback_result()
                
                # Try to find JSON in the response
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    json_str = response_text
                
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response from Google: {response_text}")
                    return self._get_fallback_result()
                    
            else:
                raise NotImplementedError(f"Provider {provider} not implemented")
                
        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            return self._get_fallback_result()
    
    def _get_fallback_result(self) -> Dict[str, Any]:
        """Return a safe fallback result when LLM calls fail"""
        return {
            'score': 0.5,
            'issues': [],
            'summary': 'Error occurred during evaluation - unable to generate detailed analysis.',
            'tokens_used': 0
        }


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
    
    def _parse_result(self, result: Dict[str, Any], context: Dict[str, Any]) -> EvaluationReport:
        """Parse LLM result into evaluation report"""
        # Ensure result is a dictionary
        if not isinstance(result, dict):
            logger.error(f"Expected dict but got {type(result)}: {result}")
            result = self._get_fallback_result()
        
        issues = []
        issues_data = result.get('issues', [])
        
        # Ensure issues is a list
        if not isinstance(issues_data, list):
            logger.warning(f"Issues should be a list, got {type(issues_data)}")
            issues_data = []
            
        for issue_data in issues_data:
            try:
                # Ensure issue_data is a dictionary
                if not isinstance(issue_data, dict):
                    logger.warning(f"Issue data should be dict, got {type(issue_data)}: {issue_data}")
                    continue
                
                # Safely get severity
                severity_str = issue_data.get('severity', 'INFO').upper()
                
                # Map common variations to standard severity levels
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
                
                severity_str = severity_mapping.get(severity_str, severity_str)
                
                try:
                    severity = Severity[severity_str]
                except KeyError:
                    logger.warning(f"Unknown severity '{severity_str}', using INFO")
                    severity = Severity.INFO
                
                issues.append(Issue(
                    description=issue_data.get('description', 'No description provided'),
                    severity=severity,
                    location=issue_data.get('location'),
                    suggestion=issue_data.get('suggestion'),
                    source_url=context.get('source'),
                    quote=issue_data.get('quote')
                ))
            except Exception as e:
                logger.error(f"Error parsing issue data: {e}")
                continue
        
        return EvaluationReport(
            evaluator_id=self.evaluator_id,
            evaluator_role=self.role,
            timestamp=datetime.now(),
            score=float(result.get('score', 0.5)) if result.get('score') is not None else 0.5,
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
        
        if not junior_evaluators:
            logger.warning(f"No junior evaluators available for section: {context.get('section', 'unknown')}")
            return self._create_empty_report(context, "No evaluators available")
        
        # Run evaluations in parallel with rate limiting
        semaphore = asyncio.Semaphore(self.config['performance']['max_concurrent_juniors'])
        
        async def run_junior(evaluator, source):
            try:
                async with semaphore:
                    # Notify that page evaluation is starting
                    if hasattr(self, 'on_page_started') and self.on_page_started:
                        self.on_page_started(source)
                    
                    result = await evaluator.evaluate(content, {'source': source, **context})
                    
                    # Notify that page evaluation is complete
                    if hasattr(self, 'on_page_completed') and self.on_page_completed:
                        self.on_page_completed(source, result.score)
                    
                    return result
            except Exception as e:
                logger.error(f"Junior evaluator failed for {source}: {e}")
                # Return a placeholder report for failed evaluations
                return EvaluationReport(
                    evaluator_id=f"failed_{evaluator.evaluator_id}",
                    evaluator_role="junior",
                    timestamp=datetime.now(),
                    score=0.5,  # Neutral score for failed evaluations
                    issues=[Issue(
                        description=f"Unable to evaluate against {source}: {str(e)}",
                        severity=Severity.MEDIUM,
                        source_url=source
                    )],
                    summary=f"Evaluation failed: {str(e)}",
                    metadata={
                        'source': source,
                        'error': str(e),
                        'failed': True
                    }
                )
        
        tasks = [
            run_junior(evaluator, source) 
            for evaluator, source in junior_evaluators
        ]
        
        # Use gather with return_exceptions=True to handle individual failures
        junior_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and extract reports
        junior_reports = []
        failed_count = 0
        
        for i, result in enumerate(junior_results):
            if isinstance(result, Exception):
                logger.error(f"Junior evaluation task failed: {result}")
                failed_count += 1
                # Create a placeholder report for the exception
                source = junior_evaluators[i][1] if i < len(junior_evaluators) else "unknown"
                junior_reports.append(EvaluationReport(
                    evaluator_id=f"exception_{i}",
                    evaluator_role="junior",
                    timestamp=datetime.now(),
                    score=0.5,
                    issues=[Issue(
                        description=f"Evaluation task failed: {str(result)}",
                        severity=Severity.ERROR,
                        source_url=source
                    )],
                    summary=f"Task exception: {str(result)}",
                    metadata={
                        'source': source,
                        'error': str(result),
                        'failed': True
                    }
                ))
            elif isinstance(result, EvaluationReport):
                junior_reports.append(result)
            else:
                logger.warning(f"Unexpected result type: {type(result)}")
                failed_count += 1
        
        if not junior_reports:
            logger.error("All junior evaluations failed")
            return self._create_empty_report(context, "All evaluations failed")
        
        logger.info(f"Completed {len(junior_reports)} evaluations ({failed_count} failed)")
        
        # Aggregate reports
        try:
            aggregated_report = await self._aggregate_reports(junior_reports, content, context)
            # Add metadata about failed evaluations
            aggregated_report.metadata['failed_evaluations'] = failed_count
            aggregated_report.metadata['successful_evaluations'] = len(junior_reports) - failed_count
            return aggregated_report
        except Exception as e:
            logger.error(f"Report aggregation failed: {e}")
            return self._create_fallback_report(junior_reports, context, str(e))
    
    def _create_empty_report(self, context: Dict[str, Any], reason: str) -> EvaluationReport:
        """Create an empty report when no evaluations are possible"""
        return EvaluationReport(
            evaluator_id=self.evaluator_id,
            evaluator_role=self.role,
            timestamp=datetime.now(),
            score=0.5,
            issues=[Issue(
                description=f"Section evaluation unavailable: {reason}",
                severity=Severity.MEDIUM
            )],
            summary=f"Unable to evaluate section: {reason}",
            metadata={
                'section': context.get('section'),
                'error': reason
            }
        )
    
    def _create_fallback_report(self, junior_reports: List[EvaluationReport], context: Dict[str, Any], error: str) -> EvaluationReport:
        """Create a fallback report when aggregation fails but we have junior reports"""
        # Calculate simple average score
        valid_reports = [r for r in junior_reports if not r.metadata.get('failed', False)]
        if valid_reports:
            avg_score = sum(r.score for r in valid_reports) / len(valid_reports)
        else:
            avg_score = 0.5
        
        # Collect all issues from junior reports
        all_issues = []
        for report in junior_reports:
            all_issues.extend(report.issues)
        
        return EvaluationReport(
            evaluator_id=self.evaluator_id,
            evaluator_role=self.role,
            timestamp=datetime.now(),
            score=avg_score,
            issues=all_issues,
            summary=f"Aggregation failed but collected {len(valid_reports)} individual evaluations. Error: {error}",
            metadata={
                'section': context.get('section'),
                'aggregation_error': error,
                'junior_reports_count': len(junior_reports)
            },
            sub_reports=junior_reports
        )
    
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
        As a senior {context.get('section', '')} evaluator, analyse these junior evaluation reports
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
        consolidated = []
        
        # Add high-priority issues identified by senior evaluator
        issues_data = aggregation_result.get('consolidated_issues', [])
        if not isinstance(issues_data, list):
            logger.warning(f"Expected list for consolidated_issues, got {type(issues_data)}")
            issues_data = []
        
        for issue_data in issues_data:
            try:
                if not isinstance(issue_data, dict):
                    logger.warning(f"Expected dict for issue data, got {type(issue_data)}: {issue_data}")
                    continue
                
                # Safely get severity with mapping
                severity_str = issue_data.get('severity', 'INFO')
                if isinstance(severity_str, str):
                    severity_str = severity_str.upper()
                    
                    # Map common variations
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
                    severity_str = severity_mapping.get(severity_str, severity_str)
                    
                    try:
                        severity = Severity[severity_str]
                    except KeyError:
                        logger.warning(f"Unknown severity '{severity_str}' in consolidation, using INFO")
                        severity = Severity.INFO
                else:
                    logger.warning(f"Non-string severity: {severity_str}, using INFO")
                    severity = Severity.INFO
                
                consolidated.append(Issue(
                    description=issue_data.get('description', 'No description provided'),
                    severity=severity,
                    suggestion=issue_data.get('suggestion'),
                    metadata={'sources': issue_data.get('sources', [])}
                ))
                
            except Exception as e:
                logger.error(f"Error consolidating issue: {e}, issue_data: {issue_data}")
                continue
        
        # If no consolidated issues from senior analysis, use top issues from junior reports
        if not consolidated:
            logger.info("No consolidated issues from senior analysis, using top junior issues")
            for report in reports:
                for issue in report.issues[:2]:  # Take top 2 from each report
                    consolidated.append(issue)
        
        return consolidated
    
    def _calculate_aggregated_score(
        self, 
        reports: List[EvaluationReport], 
        result: Dict[str, Any]
    ) -> float:
        """Calculate aggregated score from junior reports"""
        try:
            # Use senior's score if available
            if result.get('score') is not None:
                score = float(result['score'])
                # Ensure score is in valid range
                return max(0.0, min(1.0, score))
            
            # Calculate weighted average based on number of issues
            valid_reports = []
            for report in reports:
                try:
                    score = float(report.score) if report.score is not None else 0.5
                    if 0.0 <= score <= 1.0:
                        valid_reports.append((report, score))
                except (ValueError, TypeError):
                    logger.warning(f"Invalid score in report {report.evaluator_id}: {report.score}")
            
            if not valid_reports:
                logger.warning("No valid reports for score calculation")
                return 0.5
            
            total_weight = sum(len(report.issues) + 1 for report, _ in valid_reports)
            weighted_sum = sum(score * (len(report.issues) + 1) for report, score in valid_reports)
            
            final_score = weighted_sum / total_weight if total_weight > 0 else 0.5
            return max(0.0, min(1.0, final_score))
            
        except Exception as e:
            logger.error(f"Error calculating aggregated score: {e}")
            return 0.5


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
        return self._create_final_report(result, senior_reports, context)
    
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
        senior_reports: List[EvaluationReport],
        context: Dict[str, Any]
    ) -> EvaluationReport:
        """Create final evaluation report"""
        # Extract top recommendations as issues
        final_issues = []
        for rec in result.get('recommendations', []):
            # Map severity with fallback
            severity_str = rec.get('severity', 'HIGH').upper()
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
            severity_str = severity_mapping.get(severity_str, severity_str)
            
            try:
                severity = Severity[severity_str]
            except KeyError:
                logger.warning(f"Unknown recommendation severity '{rec.get('severity', 'HIGH')}', using CRITICAL")
                severity = Severity.CRITICAL
                
            final_issues.append(Issue(
                description=rec['description'],
                severity=severity,
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
