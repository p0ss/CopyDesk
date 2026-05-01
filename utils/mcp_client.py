"""
Async client for the local MCP HTTP bridge.

The MCP server in this repo exposes an HTTP bridge (default http://localhost:8081)
with endpoints for searching Typesense-backed content fragments and related tools.

This client provides thin async wrappers used by evaluators.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import aiohttp


class MCPClient:
    def __init__(self, base_url: Optional[str] = None, session: Optional[aiohttp.ClientSession] = None):
        self.base_url = (base_url or os.getenv("MCP_SERVER_URL") or "http://localhost:8081").rstrip("/")
        self._session = session

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "MCPClient":
        base_url = (
            (config.get("mcp_server", {}) or {}).get("base_url")
            or os.getenv("MCP_SERVER_URL")
            or "http://localhost:8081"
        )
        return cls(base_url=base_url)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session
        self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def health(self) -> Dict[str, Any]:
        session = await self._get_session()
        async with session.get(f"{self.base_url}/health", timeout=10) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def search(self, *, query: str, **params: Any) -> Dict[str, Any]:
        """POST /search

        Args:
            query: Natural-language search query
            params: Optional filters like category, life_event, provider, state, per_page
        Returns:
            JSON dict with results and metadata
        """
        payload = {"query": query, **{k: v for k, v in params.items() if v is not None}}
        session = await self._get_session()
        async with session.post(f"{self.base_url}/search", json=payload, timeout=30) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def analyze_combinations(self, **params: Any) -> Dict[str, Any]:
        session = await self._get_session()
        async with session.post(f"{self.base_url}/analyze-combinations", json=params, timeout=30) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def rank_content(self, *, content_titles: Any, user_profile: Any) -> Dict[str, Any]:
        payload = {"content_titles": content_titles, "user_profile": user_profile}
        session = await self._get_session()
        async with session.post(f"{self.base_url}/rank-content", json=payload, timeout=30) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def facets(self, query: Optional[str] = None) -> Dict[str, Any]:
        session = await self._get_session()
        url = f"{self.base_url}/facets"
        if query:
            from urllib.parse import urlencode
            sep = '&' if ('?' in url) else '?'
            url = f"{url}{sep}{urlencode({'query': query})}"
        async with session.get(url, timeout=20) as resp:
            resp.raise_for_status()
            return await resp.json()
