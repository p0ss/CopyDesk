# utils/document_fetcher.py
"""
Document fetcher with intelligent caching and content extraction
"""

import aiohttp
from bs4 import BeautifulSoup
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta
import logging
from typing import Dict, Any, Optional
import asyncio

logger = logging.getLogger(__name__)


class DocumentFetcher:
    """Fetches and caches web documents with intelligent content extraction"""

    def __init__(self, cache_dir: str = "./cache", cache_ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_ttl = timedelta(hours=cache_ttl_hours)

    def _get_cache_path(self, url: str) -> Path:
        """Generate cache file path from URL"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"{url_hash}.json"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cached content is still valid"""
        if not cache_path.exists():
            return False

        # Check age
        modified_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
        return datetime.now() - modified_time < self.cache_ttl

    async def fetch_page(self, url: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetch a page and extract relevant content

        Returns dict with:
        - url: original URL
        - title: page title
        - raw_html: complete HTML (for debugging)
        - main_content: extracted main content text
        - sections: parsed sections with headings
        - metadata: extraction metadata
        - cached: whether this came from cache
        - fetched_at: timestamp
        """
        cache_path = self._get_cache_path(url)

        # Check cache first
        if not force_refresh and self._is_cache_valid(cache_path):
            logger.info(f"Using cached content for {url}")
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data['cached'] = True
                return data

        # Fetch fresh content
        logger.info(f"Fetching fresh content from {url}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    html = await response.text()

            # Parse and extract content
            soup = BeautifulSoup(html, 'html.parser')

            # Extract title
            title = soup.find('title')
            title_text = title.text.strip() if title else "No title"

            # Try different content extraction strategies
            main_content = None
            content_selectors = [
                ('main', {}),
                ('article', {}),
                ('div', {'class': 'content'}),
                ('div', {'class': 'main-content'}),
                ('div', {'id': 'content'}),
                ('div', {'role': 'main'})
            ]

            for tag, attrs in content_selectors:
                element = soup.find(tag, attrs)
                if element:
                    main_content = element
                    break

            if not main_content:
                # Fallback: use body
                main_content = soup.find('body')

            # Clean up content
            if main_content:
                # Remove navigation, scripts, etc.
                for tag in main_content.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                    tag.decompose()

            # Extract structured sections
            sections = self._extract_sections(main_content)

            # Get plain text
            main_text = main_content.get_text(separator='\n', strip=True) if main_content else ""

            # Build result
            result = {
                "url": url,
                "title": title_text,
                "raw_html": html,
                "main_content": main_text,
                "sections": sections,
                "metadata": {
                    "content_length": len(main_text),
                    "section_count": len(sections),
                    "extraction_method": "BeautifulSoup"
                },
                "cached": False,
                "fetched_at": datetime.now().isoformat()
            }

            # Cache the result
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            return result

        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            # Return a minimal error result
            return {
                "url": url,
                "title": "Error",
                "raw_html": "",
                "main_content": f"Error fetching page: {str(e)}",
                "sections": [],
                "metadata": {"error": str(e)},
                "cached": False,
                "fetched_at": datetime.now().isoformat()
            }

    def _extract_sections(self, content_element) -> list:
        """Extract sections with headings and content"""
        if not content_element:
            return []

        sections = []
        current_section = None

        # Track what we've seen to avoid duplicates
        seen_content = set()

        for element in content_element.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'table']):
            if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                # Save previous section if it has content
                if current_section and current_section['content'].strip():
                    sections.append(current_section)

                # Start new section
                heading_text = element.get_text(strip=True)

                # Skip duplicate headings or form-related headings
                if heading_text in seen_content:
                    current_section = None
                    continue

                seen_content.add(heading_text)

                current_section = {
                    'heading': heading_text,
                    'level': element.name,
                    'content': ''
                }
            elif current_section:
                # Add content to current section
                content_text = element.get_text(separator=' ', strip=True)

                # Skip if we've seen this exact content before (duplicates)
                if content_text in seen_content or len(content_text) < 10:
                    continue

                seen_content.add(content_text)

                # Special handling for tables
                if element.name == 'table':
                    # Extract table as structured data
                    rows = element.find_all('tr')
                    if rows:
                        table_text = "\n"
                        for row in rows:
                            cells = row.find_all(['td', 'th'])
                            row_text = " | ".join(cell.get_text(strip=True) for cell in cells)
                            table_text += row_text + "\n"
                        current_section['content'] += table_text
                else:
                    current_section['content'] += content_text + " "

        # Don't forget the last section
        if current_section and current_section['content'].strip():
            sections.append(current_section)

        # Clean up sections - remove feedback forms
        cleaned_sections = []
        for section in sections:
            # Skip feedback/form sections
            if any(skip in section['heading'].lower() for skip in
                   ['help us improve', 'feedback', 'do you work', 'email',
                    'given name', 'family name', 'tell us']):
                continue

            # Clean up content
            section['content'] = ' '.join(section['content'].split())  # Normalize whitespace
            cleaned_sections.append(section)

        return cleaned_sections

    async def fetch_multiple(self, urls: list, max_concurrent: int = 5) -> Dict[str, Dict[str, Any]]:
        """Fetch multiple pages concurrently"""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_limit(url):
            async with semaphore:
                return await self.fetch_page(url)

        results = await asyncio.gather(*[fetch_with_limit(url) for url in urls])

        return {url: result for url, result in zip(urls, results)}

    def clear_cache(self, older_than_hours: Optional[int] = None):
        """Clear cache files"""
        for cache_file in self.cache_dir.glob("*.json"):
            if older_than_hours:
                modified_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
                age_hours = (datetime.now() - modified_time).total_seconds() / 3600
                if age_hours > older_than_hours:
                    cache_file.unlink()
            else:
                cache_file.unlink()


# Example usage for testing
async def test_fetcher():
    """Test the document fetcher"""
    fetcher = DocumentFetcher()

    # Test with a style guide page
    url = "https://www.stylemanual.gov.au/writing-style/plain-language"

    print(f"Fetching {url}...")
    result = await fetcher.fetch_page(url)

    print(f"\nTitle: {result['title']}")
    print(f"Content length: {result['metadata']['content_length']} chars")
    print(f"Sections found: {result['metadata']['section_count']}")
    print(f"From cache: {result['cached']}")

    # Show first few sections
    print("\nFirst 3 sections:")
    for section in result['sections'][:3]:
        print(f"\n[{section['level']}] {section['heading']}")
        print(f"Content preview: {section['content'][:200]}...")

    # Test caching
    print("\n\nFetching again (should use cache)...")
    result2 = await fetcher.fetch_page(url)
    print(f"From cache: {result2['cached']}")


if __name__ == "__main__":
    asyncio.run(test_fetcher())
