#!/usr/bin/env python3
"""
Test specifically for the word substitution table
"""

import asyncio
import os
import sys
sys.path.insert(0, os.getcwd())

from utils.document_fetcher import DocumentFetcher
import google.generativeai as genai


async def test_word_table():
    """Test if we can use the word substitution table"""
    
    # Configure Gemini
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    model = genai.GenerativeModel('gemma-3-27b-it')
    
    # Fetch the page
    fetcher = DocumentFetcher()
    url = "https://www.stylemanual.gov.au/writing-and-designing-content/clear-language-and-writing-style/plain-language-and-word-choice"
    
    print("Fetching style guide page...")
    page_data = await fetcher.fetch_page(url)
    
    # Find the substitution table section
    table_content = None
    for section in page_data['sections']:
        if 'choose simple words' in section['heading'].lower():
            table_content = section['content']
            break
    
    if not table_content:
        print("ERROR: Could not find word substitution table!")
        return
    
    print(f"\nFound table section ({len(table_content)} chars)")
    print("Table preview:")
    print(table_content[:500])
    
    # Test text with words from the table
    test_text = """
    We will facilitate the implementation of the new program.
    Individuals should utilize the online portal.
    We require your assistance with this matter.
    """
    
    # Create a focused prompt
    prompt = f"""
    The style guide provides this word substitution table:
    
    {table_content}
    
    Text to check:
    {test_text}
    
    For each word in the text that appears in the "Don't write this" column of the table,
    identify it and provide the suggested replacement from the "Try this instead" column.
    
    Return JSON with:
    - found_words: list of {{word: "the word used", replacement: "suggested replacement from table"}}
    - score: how well the text follows the table (0-1)
    """
    
    print("\nChecking text against word table...")
    response = await model.generate_content_async(prompt)
    
    print("\nRESULT:")
    print(response.text)


if __name__ == "__main__":
    asyncio.run(test_word_table())
