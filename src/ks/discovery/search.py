"""Search Provider Abstraction for Intent-Driven Discovery."""
import logging
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)


class SearchProvider(Protocol):
    """Protocol for abstracting search engine providers."""

    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Execute a search query and return a list of results.
        Expected result format:
        [
            {
                "url": "https://example.com/article",
                "title": "Article Title",
                "snippet": "A brief snippet or description..."
            },
            ...
        ]
        """
        ...


class DuckDuckGoProvider:
    """DuckDuckGo HTML search provider (free/open-source fallback)."""

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client

    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        try:
            from duckduckgo_search import AsyncDDGS
            
            results = []
            async with AsyncDDGS() as ddgs:
                async for r in ddgs.text(query, max_results=limit):
                    results.append({
                        "url": r.get("href"),
                        "title": r.get("title"),
                        "snippet": r.get("body")
                    })
            return results
        except ImportError:
            logger.error("duckduckgo-search package is not installed.")
            return []
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return []


class EuropePMCProvider:
    """Europe PMC search provider for scientific and medical evidence."""

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client
        self.base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        try:
            params = {
                "query": query,
                "format": "json",
                "resultType": "lite",
                "pageSize": limit
            }
            resp = await self.http_client.get(self.base_url, params=params)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("resultList", {}).get("result", []):
                # EPMC URLs typically point to the PMC article or DOI
                url = f"https://europepmc.org/article/MED/{item.get('pmid')}" if item.get('pmid') else ""
                if not url and item.get("doi"):
                    url = f"https://doi.org/{item.get('doi')}"
                
                if url:
                    results.append({
                        "url": url,
                        "title": item.get("title", ""),
                        "snippet": item.get("abstractText", "") or item.get("journalTitle", "")
                    })
            return results
        except Exception as e:
            logger.error(f"Europe PMC search failed: {e}")
            return []
