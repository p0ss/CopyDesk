

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
