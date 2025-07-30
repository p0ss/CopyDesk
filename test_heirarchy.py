#!/usr/bin/env python3
"""
Test the full hierarchical evaluation flow:
Multiple junior evaluators → Senior aggregator → Editor synthesis
"""

import asyncio
import os
import json
import yaml
from datetime import datetime
from pathlib import Path

# Add to Python path
import sys
sys.path.insert(0, os.getcwd())

from evaluators.style_guide.page_evaluator import StyleGuidePageEvaluator
from evaluators.style_guide.section_lead import StyleGuideSectionLead
from evaluators.style_guide.editor import StyleGuideEditor


async def test_full_hierarchy():
    """Test the complete evaluation pipeline"""
    
    # Load config
    try:
        with open('config/evaluation_config.yaml', 'r') as f:
            config = yaml.safe_load(f)
    except:
        # Use minimal config if file doesn't exist
        config = {
            "models": {
                "junior": {"provider": "google", "model": "gemma-3-27b-it", "temperature": 0.3, "max_tokens": 2000},
                "senior": {"provider": "google", "model": "gemma-3-27b-it", "temperature": 0.5, "max_tokens": 3000},
                "editor": {"provider": "google", "model": "gemma-3-27b-it", "temperature": 0.7, "max_tokens": 4000}
            },
            "performance": {
                "max_concurrent_juniors": 3,
                "request_timeout": 30
            },
            "reports": {
                "senior": {"priority_threshold": 0.5},
                "editor": {"max_recommendations": 5, "format": "executive", "include_links": True}
            },
            "style_guide": {
                "base_url": "https://www.stylemanual.gov.au",
                "sections": [
                    {
                        "name": "Clear language and writing style",
                        "pages": [
                            "/writing-and-designing-content/clear-language-and-writing-style/plain-language-and-word-choice",
                            "/writing-and-designing-content/clear-language-and-writing-style/sentences",
                            "/writing-and-designing-content/clear-language-and-writing-style/voice-and-tone"
                        ]
                    },
                    {
                        "name": "Structuring content",
                        "pages": [
                            "/structuring-content/headings-and-subheadings",
                            "/structuring-content/paragraphs"
                        ]
                    }
                ]
            }
        }
    
    # Test text - intentionally problematic
    test_text = """
    The Medicare program facilitates the provision of healthcare services to eligible 
    Australian residents. Individuals may utilize their Medicare card to access 
    subsidized medical consultations. The implementation of this program has been 
    instrumental in ensuring equitable healthcare access across the nation.
    
    IMPORTANT INFORMATION REGARDING MEDICARE
    
    It is imperative that all individuals who are in possession of a Medicare card 
    ensure that they maintain the aforementioned card in good condition. The card 
    must be presented at the point of service delivery in order to obtain the 
    benefits to which one is entitled.
    """
    
    print("=" * 70)
    print("FULL HIERARCHICAL EVALUATION TEST")
    print("=" * 70)
    print(f"Test text ({len(test_text.split())} words):")
    print(test_text)
    print("=" * 70)
    
    # Step 1: Process each section with senior evaluators
    print("\n1. RUNNING SECTION EVALUATIONS")
    print("-" * 50)
    
    senior_reports = []
    
    for section_config in config['style_guide']['sections']:
        section_name = section_config['name']
        print(f"\n## Evaluating section: {section_name}")
        print(f"   Pages to check: {len(section_config['pages'])}")
        
        # Create section lead evaluator
        section_lead = StyleGuideSectionLead(
            evaluator_id=f"section_{section_name.replace(' ', '_').lower()}",
            section_name=section_name,
            config=config
        )
        
        # Run evaluation (this will spawn junior evaluators)
        try:
            section_report = await section_lead.evaluate(
                test_text, 
                {'section': section_name}
            )
            
            senior_reports.append(section_report)
            
            print(f"   ✓ Section score: {section_report.score:.1%}")
            print(f"   ✓ Issues found: {len(section_report.issues)}")
            print(f"   ✓ Junior reports: {len(section_report.sub_reports)}")
            
            # Show top issues from this section
            if section_report.issues:
                print(f"   Top issues:")
                for i, issue in enumerate(section_report.issues[:3], 1):
                    print(f"     {i}. [{issue.severity.name}] {issue.description[:80]}...")
                    
        except Exception as e:
            print(f"   ✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    if not senior_reports:
        print("\nERROR: No senior reports generated!")
        return
    
    # Step 2: Editor synthesis
    print("\n\n2. EDITOR SYNTHESIS")
    print("-" * 50)
    
    editor = StyleGuideEditor(
        evaluator_id="chief_editor",
        config=config
    )
    
    try:
        final_report = await editor.evaluate(
            test_text,
            {'senior_reports': senior_reports, 'evaluation_type': 'style_guide'}
        )
        
        print(f"✓ Final compliance score: {final_report.score:.1%}")
        print(f"✓ Top recommendations: {len(final_report.issues)}")
        
        # Show recommendations
        print("\nTOP RECOMMENDATIONS:")
        for i, rec in enumerate(final_report.issues[:5], 1):
            print(f"\n{i}. {rec.description}")
            print(f"   Severity: {rec.severity.name}")
            if rec.suggestion:
                print(f"   Action: {rec.suggestion}")
        
        # Generate markdown report
        markdown_report = await editor.generate_markdown_report(final_report)
        
        # Save reports
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save JSON
        json_file = f"full_evaluation_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(final_report.to_dict(), f, indent=2)
        print(f"\n✓ JSON report saved to: {json_file}")
        
        # Save Markdown
        md_file = f"full_evaluation_{timestamp}.md"
        with open(md_file, 'w') as f:
            f.write(markdown_report)
        print(f"✓ Markdown report saved to: {md_file}")
        
    except Exception as e:
        print(f"✗ ERROR in editor synthesis: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("EVALUATION COMPLETE")
    print("=" * 70)


async def main():
    """Main entry point"""
    
    # Check API key
    if not os.getenv('GOOGLE_API_KEY'):
        print("ERROR: Please set GOOGLE_API_KEY environment variable")
        return
    
    await test_full_hierarchy()


if __name__ == "__main__":
    asyncio.run(main())