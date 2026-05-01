# utils/document_fetcher.py
"""
Document fetching utilities with caching support
"""

import aiohttp
from bs4 import BeautifulSoup
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
import logging
from typing import Dict, Any, Optional
import asyncio

logger = logging.getLogger(__name__)


class DocumentFetcher:
    """Fetches and caches web pages and documents"""
    
    def __init__(self, cache_dir: str = "./cache", cache_ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    def _get_cache_path(self, url: str) -> Path:
        """Generate cache file path for URL"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"{url_hash}.json"
        
    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cached file is still valid"""
        if not cache_path.exists():
            return False
            
        # Check age
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        age = datetime.now() - mtime
        
        return age < self.cache_ttl
        
    async def fetch_page(self, url: str, use_cache: bool = True) -> Dict[str, Any]:
        """Fetch and parse a web page"""
        cache_path = self._get_cache_path(url)
        
        # Check cache first
        if use_cache and self._is_cache_valid(cache_path):
            logger.debug(f"Using cached content for {url}")
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        # Fetch fresh content
        logger.info(f"Fetching fresh content from {url}")
        
        # Use a temporary session if we don't have one
        temp_session = None
        try:
            # Create session if needed
            if not self.session:
                temp_session = aiohttp.ClientSession()
                session_to_use = temp_session
            else:
                session_to_use = self.session
                
            async with session_to_use.get(url, timeout=30) as response:
                response.raise_for_status()
                html = await response.text()
                
            # Parse HTML
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract content based on Style Manual structure
            page_data = self._parse_style_manual_page(soup, url)
            
            # Cache the result
            if use_cache:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(page_data, f, indent=2)
                    
            return page_data
            
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching {url}: {e}")
            # Return minimal data on error
            return {
                'url': url,
                'title': 'Error fetching page',
                'main_content': f'Error: {str(e)}',
                'sections': [],
                'error': str(e)
            }
        finally:
            # Clean up temporary session if we created one
            if temp_session:
                await temp_session.close()
            
    def _parse_style_manual_page(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Parse Australian Government Style Manual page structure"""
        
        # Get title
        title = soup.find('h1')
        title_text = title.get_text(strip=True) if title else 'Untitled'
        
        # Get main content area
        main_content = soup.find('main') or soup.find('div', {'class': 'content'})
        
        if not main_content:
            # Fallback to body
            main_content = soup.find('body')
            
        # Extract sections
        sections = []
        
        # Look for h2 and h3 headings with their content
        for heading in main_content.find_all(['h2', 'h3']):
            section_title = heading.get_text(strip=True)
            
            # Skip navigation/meta sections
            if any(skip in section_title.lower() for skip in 
                  ['on this page', 'help us improve', 'last updated', 'feedback']):
                continue
                
            # Get content until next heading
            content_parts = []
            for sibling in heading.find_next_siblings():
                if sibling.name in ['h2', 'h3']:
                    break
                    
                # Extract text from various elements
                if sibling.name == 'p':
                    content_parts.append(sibling.get_text(strip=True))
                elif sibling.name == 'ul':
                    for li in sibling.find_all('li'):
                        content_parts.append(f"• {li.get_text(strip=True)}")
                elif sibling.name == 'ol':
                    for i, li in enumerate(sibling.find_all('li'), 1):
                        content_parts.append(f"{i}. {li.get_text(strip=True)}")
                elif sibling.name == 'table':
                    # Extract table content
                    content_parts.append(self._parse_table(sibling))
                elif sibling.name == 'blockquote':
                    content_parts.append(f"Quote: {sibling.get_text(strip=True)}")
                    
            section_content = '\n'.join(content_parts)
            
            if section_content.strip():
                sections.append({
                    'heading': section_title,
                    'content': section_content,
                    'level': int(heading.name[1])  # h2 -> 2, h3 -> 3
                })
                
        # Get all text content as fallback
        all_text = main_content.get_text(separator='\n', strip=True) if main_content else ''
        
        return {
            'url': url,
            'title': title_text,
            'main_content': all_text,
            'sections': sections,
            'fetched_at': datetime.now().isoformat()
        }
        
    def _parse_table(self, table) -> str:
        """Parse HTML table into readable text"""
        rows = []
        
        # Get headers
        headers = []
        header_row = table.find('thead')
        if header_row:
            for th in header_row.find_all('th'):
                headers.append(th.get_text(strip=True))
                
        if headers:
            rows.append(' | '.join(headers))
            rows.append('-' * len(' | '.join(headers)))
            
        # Get body rows
        tbody = table.find('tbody') or table
        for tr in tbody.find_all('tr'):
            cells = []
            for td in tr.find_all(['td', 'th']):
                cells.append(td.get_text(strip=True))
            if cells:
                rows.append(' | '.join(cells))
                
        return '\n'.join(rows)
        
    async def clear_cache(self):
        """Clear all cached files"""
        for cache_file in self.cache_dir.glob('*.json'):
            cache_file.unlink()
        logger.info("Cache cleared")
        
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        cache_files = list(self.cache_dir.glob('*.json'))
        total_size = sum(f.stat().st_size for f in cache_files)
        
        return {
            'cache_dir': str(self.cache_dir),
            'file_count': len(cache_files),
            'total_size_mb': total_size / (1024 * 1024),
            'ttl_hours': self.cache_ttl.total_seconds() / 3600
        }


# Example usage
async def test_fetcher():
    """Test the document fetcher"""
    fetcher = DocumentFetcher()
    
    # Test URL
    url = "https://www.stylemanual.gov.au/writing-and-designing-content/clear-language-and-writing-style/plain-language-and-word-choice"
    
    print(f"Fetching: {url}")
    page_data = await fetcher.fetch_page(url)
    
    print(f"\nTitle: {page_data['title']}")
    print(f"Sections found: {len(page_data['sections'])}")
    
    for section in page_data['sections'][:3]:
        print(f"\n{section['heading']}:")
        print(f"{section['content'][:200]}...")
        
    # Check cache stats
    stats = await fetcher.get_cache_stats()
    print(f"\nCache stats: {stats}")


if __name__ == "__main__":
    asyncio.run(test_fetcher())
