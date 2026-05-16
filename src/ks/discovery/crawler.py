"""Asynchronous Recursive Deep Crawler for KnowledgeStream Discovery."""
import asyncio
import logging
from typing import Any, Protocol, Set
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

import httpx

logger = logging.getLogger(__name__)


class CrawlerConfig:
    def __init__(
        self,
        max_depth: int = 1,
        max_pages: int = 50,
        rate_limit_seconds: float = 1.0,
        allowed_patterns: list[str] | None = None,
        blocked_patterns: list[str] | None = None,
        max_pdf_size_mb: int = 5,
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.rate_limit_seconds = rate_limit_seconds
        self.allowed_patterns = allowed_patterns or []
        self.blocked_patterns = blocked_patterns or []
        self.max_pdf_size_bytes = max_pdf_size_mb * 1024 * 1024


class DeepCrawler(Protocol):
    async def crawl(self, start_url: str, config: CrawlerConfig) -> list[dict[str, Any]]:
        """Start deep crawl from a root URL and return discovered pages."""
        ...


class AsyncHttpCrawler:
    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client

    async def crawl(self, start_url: str, config: CrawlerConfig) -> list[dict[str, Any]]:
        visited: Set[str] = set()
        results: list[dict[str, Any]] = []
        queue = [(start_url, 0)]  # (url, depth)
        
        domain = urlparse(start_url).netloc

        while queue and len(results) < config.max_pages:
            url, depth = queue.pop(0)
            
            if url in visited:
                continue
                
            visited.add(url)
            
            # Rate limiting
            if len(visited) > 1:
                await asyncio.sleep(config.rate_limit_seconds)
                
            try:
                # Issue HEAD request first to check size and content type
                head_resp = await self.http_client.head(url, follow_redirects=True, timeout=5.0)
                if head_resp.status_code != 200:
                    continue
                    
                content_type = head_resp.headers.get("content-type", "").lower()
                
                # Handle PDF limits
                if "pdf" in content_type:
                    content_length = int(head_resp.headers.get("content-length", 0))
                    if content_length > config.max_pdf_size_bytes:
                        logger.warning(f"Skipping PDF {url} - Exceeds max size limit")
                        continue
                        
                    results.append({"url": url, "type": "pdf", "depth": depth})
                    continue # Do not parse links from PDF
                    
                # Skip non-HTML
                if "html" not in content_type:
                    continue

                # Fetch full HTML
                resp = await self.http_client.get(url, follow_redirects=True, timeout=10.0)
                if resp.status_code != 200:
                    continue
                    
                results.append({"url": url, "type": "html", "depth": depth})
                
                # If we haven't reached max depth, parse links and add to queue
                if depth < config.max_depth:
                    soup = BeautifulSoup(resp.content, "html.parser")
                    for a_tag in soup.find_all("a", href=True):
                        href = a_tag["href"]
                        full_url = urljoin(url, href)
                        
                        # Only follow links on the same domain
                        if urlparse(full_url).netloc != domain:
                            continue
                            
                        # Strip fragments
                        full_url = full_url.split("#")[0]
                        
                        # Apply pattern filters
                        if config.blocked_patterns and any(p in full_url for p in config.blocked_patterns):
                            continue
                        if config.allowed_patterns and not any(p in full_url for p in config.allowed_patterns):
                            continue
                            
                        if full_url not in visited:
                            queue.append((full_url, depth + 1))
                            
            except Exception as e:
                logger.error(f"Failed to crawl {url}: {e}")
                continue
                
        return results
