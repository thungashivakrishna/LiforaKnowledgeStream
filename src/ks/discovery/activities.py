"""Discovery activities — worker tasks for finding candidate documents."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from temporalio import activity

from apps.api.database import AsyncSessionFactory
from ks.domain.enums import DiscoveryDecision, DiscoveryMode, RunStatus
from ks.domain.models import CandidateDiscoveryRun, CandidateDocumentEvaluation, DocumentRegistry


logger = logging.getLogger(__name__)


class DiscoveryActivities:
    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client

    @activity.defn
    async def discover_candidates(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Main activity to find candidate URLs from a source.
        Payload keys: source_id, root_url, mode, allow_patterns, block_patterns, max_candidates
        """
        root_url = payload["root_url"]
        mode = DiscoveryMode(payload["mode"])
        allow_patterns = payload.get("allow_patterns", [])
        block_patterns = payload.get("block_patterns", [])
        max_candidates = payload.get("max_candidates", 50)

        logger.info(f"Starting discovery for {root_url} in mode {mode}")

        # 1. Try sitemap first
        candidates = await self._sitemap_discovery(root_url, allow_patterns, block_patterns)
        
        # 2. If sitemap failed or found nothing, and mode is not generic, try path discovery
        if not candidates and mode != DiscoveryMode.GENERIC:
            candidates = await self._path_discovery(root_url, allow_patterns, block_patterns, max_candidates)

        # 3. Final filtering and limit
        # Deduplicate and limit
        seen = set()
        unique_candidates = []
        for c in candidates:
            if c["url"] not in seen:
                seen.add(c["url"])
                unique_candidates.append(c)
                if len(unique_candidates) >= max_candidates:
                    break

        logger.info(f"Discovered {len(unique_candidates)} candidates for {root_url}")
        return unique_candidates

    async def _sitemap_discovery(self, root_url: str, allow: list[str], block: list[str]) -> list[dict[str, Any]]:
        """Attempt to find and parse sitemap.xml."""
        sitemap_url = urljoin(root_url, "/sitemap.xml")
        try:
            resp = await self.http_client.get(sitemap_url, follow_redirects=True)
            if resp.status_code != 200:
                return []
            
            # Simple sitemap parsing (regex or XML parser)
            # For prototype, we'll look for <loc> tags
            soup = BeautifulSoup(resp.text, "xml")
            urls = [loc.text for loc in soup.find_all("loc")]
            
            return self._filter_urls(urls, allow, block)
        except Exception as e:
            logger.warning(f"Sitemap discovery failed for {root_url}: {e}")
            return []

    async def _path_discovery(self, root_url: str, allow: list[str], block: list[str], max_cand: int) -> list[dict[str, Any]]:
        """Simple breadth-first crawl to find links."""
        try:
            resp = await self.http_client.get(root_url, follow_redirects=True)
            if resp.status_code != 200:
                return []
            
            soup = BeautifulSoup(resp.text, "html.parser")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                full_url = urljoin(root_url, href)
                # Only same domain
                if urlparse(full_url).netloc == urlparse(root_url).netloc:
                    links.append(full_url)
            
            return self._filter_urls(links, allow, block)
        except Exception as e:
            logger.warning(f"Path discovery failed for {root_url}: {e}")
            return []

    def _filter_urls(self, urls: list[str], allow: list[str], block: list[str]) -> list[dict[str, Any]]:
        results = []
        # Additional patterns to avoid index pages
        index_patterns = ["encyclopedia_", "index.htm", "index.html", "/search?", "/archive/"]
        
        for url in urls:
            # 1. Block patterns from source config
            if any(p in url for p in block):
                continue
            
            # 2. Block common index patterns
            if any(p in url for p in index_patterns):
                # We specifically allow it if it's a deep article link (e.g. /article/)
                if "/article/" not in url and "/ency/article/" not in url:
                    logger.info(f"Skipping potential index page: {url}")
                    continue
                
            # 3. Allow patterns (if specified)
            if allow and not any(p in url for p in allow):
                continue
            
            results.append({
                "url": url,
                "title": None, # Title will be fetched later during fetch/extraction
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            })
        return results

    @activity.defn
    async def persist_candidates(self, payload: dict[str, Any]) -> int:
        """
        Store discovered candidates in the database.
        Payload keys: run_id, source_id, candidates (list of url/title)
        """
        run_id = uuid.UUID(payload["run_id"])
        source_id = uuid.UUID(payload["source_id"])
        candidates = payload["candidates"]
        
        results = []
        async with AsyncSessionFactory() as session:
            for c in candidates:
                res = await session.execute(
                    select(DocumentRegistry).where(DocumentRegistry.canonical_url == c["url"])
                )
                doc = res.scalar_one_or_none()
                
                if not doc:
                    doc = DocumentRegistry(
                        id=uuid.uuid4(),
                        source_id=source_id,
                        canonical_url=c["url"],
                        title=c.get("title"),
                    )
                    session.add(doc)
                    await session.flush()
                
                eval_obj = CandidateDocumentEvaluation(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    document_id=doc.id,
                    score=0.5,
                    matched_terms=[],
                    decision=DiscoveryDecision.INGEST_NOW,
                )
                session.add(eval_obj)
                
                # Add to the return results list
                results.append({
                    "document_id": str(doc.id),
                    "url": doc.canonical_url
                })
            
            await session.commit()
        
        return results

    @activity.defn
    async def finalize_discovery_run(self, payload: dict[str, Any]) -> None:
        run_id = uuid.UUID(payload["run_id"])
        status = RunStatus(payload["status"])
        candidate_count = payload.get("candidate_count", 0)
        error_message = payload.get("error_message")

        async with AsyncSessionFactory() as session:
            result = await session.execute(
                select(CandidateDiscoveryRun).where(CandidateDiscoveryRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if run:
                run.status = status
                run.candidate_count = candidate_count
                run.error_message = error_message
                run.completed_at = datetime.now(timezone.utc)
                await session.commit()
