import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import litellm
from bs4 import BeautifulSoup
from sqlalchemy import select
from temporalio import activity

from apps.api.database import AsyncSessionFactory
from ks.config.settings import get_settings
from ks.discovery.schemas import DocumentRelevanceScoreOutput
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
            
            # 4. Simple scoring heuristic
            score = 0.5
            # Bonus for article-like paths
            if any(p in url.lower() for p in ["/article/", "/condition/", "/guide/", "/protocol/", "/health-topics/"]):
                score += 0.3
            # Penalty for suspicious index-like long params
            if "?" in url and len(url.split("?")[1]) > 50:
                score -= 0.2
            
            results.append({
                "url": url,
                "title": None, # Title will be fetched later during fetch/extraction
                "score": round(min(0.99, max(0.01, score)), 2),
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
                
                # 2. Prevent Duplicate Evaluations in the SAME run
                existing_eval = await session.execute(
                    select(CandidateDocumentEvaluation)
                    .where(CandidateDocumentEvaluation.run_id == run_id)
                    .where(CandidateDocumentEvaluation.document_id == doc.id)
                )
                if existing_eval.scalar_one_or_none():
                    continue

                eval_obj = CandidateDocumentEvaluation(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    document_id=doc.id,
                    score=c.get("score", 0.5),
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

    @activity.defn
    async def fetch_page_metadata(self, url: str) -> dict[str, Any]:
        """Fetch lightweight metadata from a URL without downloading the full page."""
        try:
            # Use a fast timeout and fetch only first few KB if possible
            resp = await self.http_client.get(url, follow_redirects=True, timeout=5.0)
            if resp.status_code != 200:
                return {}
            
            soup = BeautifulSoup(resp.content, "html.parser")
            
            metadata = {
                "title": soup.title.string if soup.title else None,
                "meta_description": "",
                "h1_headings": [h1.get_text(strip=True) for h1 in soup.find_all("h1")],
                "canonical_url": "",
                "schema_type": []
            }
            
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                metadata["meta_description"] = meta_desc.get("content", "")
                
            canonical = soup.find("link", rel="canonical")
            if canonical:
                metadata["canonical_url"] = canonical.get("href", "")
                
            schema_tags = soup.find_all("script", type="application/ld+json")
            for tag in schema_tags:
                try:
                    data = json.loads(tag.string)
                    if isinstance(data, dict):
                        metadata["schema_type"].append(data.get("@type", ""))
                    elif isinstance(data, list):
                        for item in data:
                            metadata["schema_type"].append(item.get("@type", ""))
                except Exception:
                    pass
                    
            return metadata
        except Exception as e:
            logger.warning(f"Failed to fetch metadata for {url}: {e}")
            return {}

    @activity.defn
    async def calculate_priority_score(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Use a lightweight model to score clinical relevance based on metadata."""
        url = payload.get("url", "")
        metadata = payload.get("metadata", {})
        topics = payload.get("topics", [])
        source_trust = payload.get("source_trust_score", 1.0)
        
        settings = get_settings()
        # Default to a fast/cheap model for prioritization
        model = settings.model.primary_model
        api_key = settings.model.primary_api_key
        
        prompt = f"""
        You are an advanced Clinical Triage AI. Your job is to prioritize a discovered web document before we spend resources fully extracting it.
        
        URL: {url}
        Target Focus / Topics: {topics}
        Source Trust Score: {source_trust}
        
        Metadata:
        {json.dumps(metadata, indent=2)}
        
        Evaluate the document based on the metadata and return a JSON score object matching the specified output schema.
        - clinical_relevance (0.0 to 1.0)
        - intent_match (0.0 to 1.0): Does it match {topics}?
        - evidence_likelihood (0.0 to 1.0): Does it look like a study, protocol, or guideline?
        - actionability (0.0 to 1.0)
        - safety_value (0.0 to 1.0)
        - freshness (0.0 to 1.0)
        - commercial_bias_risk (0.0 to 1.0): Does it look like SEO spam or a product sales page?
        - source_trust_multiplier (0.5 to 1.5): Based on Source Trust Score provided.
        
        Calculate the overall_priority_score (0 to 100):
        Score = ((clinical_relevance * 0.2) + (intent_match * 0.2) + (evidence_likelihood * 0.15) + 
                (actionability * 0.1) + (safety_value * 0.15) + (freshness * 0.1) - 
                (commercial_bias_risk * 0.3)) * source_trust_multiplier * 100
        Clamp final score to 0-100.
        
        Recommended Action logic:
        - 85-100: EXTRACT
        - 65-84: QUEUE
        - 40-64: METADATA_ONLY
        - 0-39: REJECT
        """
        
        try:
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                api_key=api_key
            )
            
            output = json.loads(response.choices[0].message.content)
            return {"success": True, "score_data": output}
        except Exception as e:
            logger.error(f"Priority scoring failed for {url}: {e}")
            return {"success": False, "error": str(e)}

    @activity.defn
    async def evaluate_source_authority(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Evaluate a new/unknown domain to determine if it should be allowed."""
        domain = payload.get("domain", "")
        snippet = payload.get("snippet", "")
        
        settings = get_settings()
        model = settings.model.primary_model
        api_key = settings.model.primary_api_key
        
        prompt = f"""
        Evaluate the following web domain for clinical and medical authority.
        Domain: {domain}
        Sample Context: {snippet}
        
        Is this a reputable academic, public health, government, or recognized clinical site?
        Return a JSON object with:
        - is_reputable (bool)
        - trust_score (0.0 to 1.0)
        - reason (string)
        - source_type (e.g. ACADEMIC, GOVERNMENT, COMMERCIAL_WELLNESS, SPAM)
        """
        
        try:
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                api_key=api_key
            )
            
            output = json.loads(response.choices[0].message.content)
            return {"success": True, "evaluation": output}
        except Exception as e:
            logger.error(f"Source authority evaluation failed for {domain}: {e}")
            return {"success": False, "error": str(e)}

    @activity.defn
    async def perform_targeted_search(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Execute intent-driven search across configured providers."""
        query = payload.get("query", "")
        limit = payload.get("limit", 20)
        
        # We will use DuckDuckGo as fallback, and EuropePMC for scientific
        from ks.discovery.search import DuckDuckGoProvider, EuropePMCProvider
        
        ddg = DuckDuckGoProvider(self.http_client)
        epmc = EuropePMCProvider(self.http_client)
        
        results = []
        try:
            # First fetch scientific
            epmc_res = await epmc.search(query, limit=limit//2)
            results.extend(epmc_res)
            
            # Then open web fallback
            ddg_res = await ddg.search(query, limit=limit//2)
            results.extend(ddg_res)
            
        except Exception as e:
            logger.error(f"Targeted search failed: {e}")
            
        return results

    @activity.defn
    async def perform_deep_crawl(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Run controlled deep crawl from a high-priority URL."""
        start_url = payload.get("url", "")
        max_depth = payload.get("max_depth", 1)
        max_pages = payload.get("max_pages", 20)
        
        from ks.discovery.crawler import AsyncHttpCrawler, CrawlerConfig
        
        config = CrawlerConfig(
            max_depth=max_depth,
            max_pages=max_pages,
            rate_limit_seconds=1.0,
            max_pdf_size_mb=5
        )
        
        crawler = AsyncHttpCrawler(self.http_client)
        results = await crawler.crawl(start_url, config)
        return results
