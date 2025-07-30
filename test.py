#!/usr/bin/env python3
"""
Quick test script using Google's Gemma 3 27B-IT model
Free API access via Google AI Studio
"""

import asyncio
import os
import json
from datetime import datetime
import google.generativeai as genai

# Try to load .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, that's okay


async def quick_style_check(text: str) -> dict:
    """Quick style check using Gemma 3 27B-IT"""

    # Configure with Google AI Studio API key
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))

    # Use Gemma 3 27B-IT (instruction-tuned version)
    model = genai.GenerativeModel('gemma-3-27b-it')

    # Mock style guide content
    style_guide_rules = """
    Australian Government Style Guide - Plain Language:
    - Use simple, everyday words
    - Write short sentences (average 15-20 words)
    - Use active voice
    - Avoid jargon and bureaucratic language
    - Write at Year 8 reading level
    - Be direct and clear
    """

    prompt = f"""
    Check this text against the Australian Government Style Guide rules:

    Rules:
    {style_guide_rules}

    Text to check:
    {text}

    Provide your response in the following JSON format (be sure to output valid JSON):
    {{
        "score": 0.85,
        "issues": [
            "Uses complex words like 'facilitates' instead of simple words",
            "Sentences are too long and complex",
            "Uses passive voice and bureaucratic language"
        ],
        "suggestions": [
            "Replace 'facilitates' with 'helps' or 'provides'",
            "Break long sentences into shorter ones",
            "Use active voice: 'Medicare helps' instead of 'services are provided'"
        ],
        "summary": "The text uses bureaucratic language and complex sentence structures. It needs simplification to meet plain language guidelines."
    }}

    Remember: Output ONLY the JSON, no other text.
    """

    # Generate response without JSON mode
    response = await model.generate_content_async(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.3,
            max_output_tokens=2000
        )
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

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON. Raw response:\n{response_text}")
        # Return a fallback structure
        return {
            "score": 0.5,
            "issues": ["Failed to parse response"],
            "suggestions": ["Check raw response above"],
            "summary": "Error parsing model output"
        }


async def main():
    """Test the evaluation"""

    # Check API key
    api_key = os.getenv('GOOGLE_API_KEY')
    print(f"API Key found: {'Yes' if api_key else 'No'}")
    if api_key:
        print(f"API Key length: {len(api_key)} chars")
        print(f"API Key starts with: {api_key[:10]}...")

    if not api_key:
        print("ERROR: Please set GOOGLE_API_KEY environment variable")
        print("Get your free API key from: https://aistudio.google.com/apikey")
        print("\nDebug info:")
        print(f"All env vars starting with GOOGLE: {[k for k in os.environ.keys() if 'GOOGLE' in k]}")
        return

    # Sample text with obvious style guide violations
    test_text = """
    The Medicare program facilitates the provision of healthcare services to eligible
    Australian residents. Individuals may utilize their Medicare card to access
    subsidized medical consultations. The implementation of this program has been
    instrumental in ensuring equitable healthcare access across the nation.
    """

    print("Testing Style Guide Checker with Gemma 3 27B-IT")
    print("=" * 50)
    print(f"Input text:\n{test_text}")
    print("=" * 50)

    try:
        print("\nCalling Gemma 3 27B-IT API...")
        result = await quick_style_check(test_text)

        print(f"\nCompliance Score: {result['score']:.1%}")
        print(f"\nIssues Found ({len(result['issues'])}):")
        for i, issue in enumerate(result['issues'], 1):
            print(f"{i}. {issue}")

        print(f"\nSuggestions:")
        for i, suggestion in enumerate(result.get('suggestions', []), 1):
            print(f"{i}. {suggestion}")

        print(f"\nSummary: {result['summary']}")

        # Save result
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gemma3_test_{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\nFull result saved to: {filename}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
