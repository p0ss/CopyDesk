#!/usr/bin/env python3
"""
Simple runner to test the evaluation framework
"""

import asyncio
import yaml
import sys
import os
from datetime import datetime
import json

# Import our evaluators
from evaluators.style_guide.page_evaluator import StyleGuidePageEvaluator
from evaluators.style_guide.section_lead import StyleGuideSectionLead
from evaluators.style_guide.editor import StyleGuideEditor


async def load_config():
    """Load configuration from yaml file"""
    # For now, return a minimal config if file doesn't exist
    try:
        with open('config/evaluation_config.yaml', 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print("Config file not found, using minimal config")
        return {
            "models": {
                "junior": {"provider": "openai", "model": "gpt-3.5-turbo", "temperature": 0.3},
                "senior": {"provider": "openai", "model": "gpt-3.5-turbo", "temperature": 0.5},
                "editor": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.7}
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
                        "name": "Writing and designing content",
                        "pages": ["/writing-style/plain-language"]
                    }
                ]
            }
        }


async def evaluate_style_guide(text: str, config: dict):
    """Run style guide evaluation"""
    print("Starting Style Guide Evaluation...")
    print("=" * 50)
    
    # Get sections from config
    sections = config['style_guide']['sections']
    senior_reports = []
    
    # Process each section
    for section in sections:
        print(f"\nEvaluating section: {section['name']}")
        
        # Create section lead evaluator
        section_lead = StyleGuideSectionLead(
            evaluator_id=f"section_lead_{section['name'].replace(' ', '_')}",
            section_name=section['name'],
            config=config
        )
        
        # Run evaluation for this section
        section_report = await section_lead.evaluate(text, {'section': section['name']})
        senior_reports.append(section_report)
        
        print(f"  Section score: {section_report.score:.1%}")
        print(f"  Issues found: {len(section_report.issues)}")
    
    # Create final editor report
    print("\nCreating final report...")
    editor = StyleGuideEditor(
        evaluator_id="style_guide_editor",
        config=config
    )
    
    final_report = await editor.evaluate(text, {'senior_reports': senior_reports})
    
    # Generate markdown report
    markdown_report = await editor.generate_markdown_report(final_report)
    
    return final_report, markdown_report


async def main():
    """Main entry point"""
    # Get text from command line or use default
    if len(sys.argv) > 1:
        text_to_evaluate = ' '.join(sys.argv[1:])
    else:
        text_to_evaluate = """
        The Medicare program helps Australians with the cost of medical services. 
        You can utilize Medicare benefits to facilitate access to healthcare providers.
        The program has been operational since 1984.
        """
        print(f"No text provided, using sample text:\n{text_to_evaluate}\n")
    
    # Load config
    config = await load_config()
    
    # Check for API key
    if not os.getenv('OPENAI_API_KEY'):
        print("ERROR: Please set OPENAI_API_KEY environment variable")
        sys.exit(1)
    
    try:
        # Run evaluation
        report, markdown = await evaluate_style_guide(text_to_evaluate, config)
        
        # Print results
        print("\n" + "=" * 50)
        print("EVALUATION COMPLETE")
        print("=" * 50)
        print(f"\nOverall Score: {report.score:.1%}")
        print(f"Total Issues: {len(report.issues)}")
        
        print("\nTop Issues:")
        for i, issue in enumerate(report.issues[:3], 1):
            print(f"{i}. [{issue.severity.name}] {issue.description}")
            if issue.suggestion:
                print(f"   Suggestion: {issue.suggestion}")
        
        # Save markdown report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"evaluation_report_{timestamp}.md"
        with open(filename, 'w') as f:
            f.write(markdown)
        print(f"\nFull report saved to: {filename}")
        
        # Also save JSON for debugging
        json_filename = f"evaluation_report_{timestamp}.json"
        with open(json_filename, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"JSON report saved to: {json_filename}")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())