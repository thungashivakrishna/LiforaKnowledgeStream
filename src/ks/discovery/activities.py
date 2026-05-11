import asyncio
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
from ks.common import redis_client
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
        topics = payload.get("topics", [])

        logger.info(f"Starting discovery for {root_url} in mode {mode}")

        candidates = []

        # 1. If topics are provided, attempt dynamic native search endpoint discovery first
        if topics:
            search_query = " ".join(topics)
            candidates = await self._search_endpoint_discovery(root_url, search_query, allow_patterns, block_patterns, max_candidates, topics=topics, mode=mode)

        # 2. Try sitemap if native search didn't find anything
        if not candidates:
            candidates = await self._sitemap_discovery(root_url, allow_patterns, block_patterns, topics=topics, mode=mode)

        # 3. If sitemap failed or found nothing, try path discovery
        if not candidates and mode != DiscoveryMode.GENERIC:
            candidates = await self._path_discovery(root_url, allow_patterns, block_patterns, max_candidates, topics=topics, mode=mode)

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

    async def _sitemap_discovery(self, root_url: str, allow: list[str], block: list[str], topics: list[str] | None = None, mode: DiscoveryMode | None = None) -> list[dict[str, Any]]:
        """Attempt to find and parse sitemap.xml."""
        sitemap_url = urljoin(root_url, "/sitemap.xml")
        domain = urlparse(sitemap_url).netloc
        if not await redis_client.rate_check(domain):
            await asyncio.sleep(1.0)
        try:
            resp = await self.http_client.get(sitemap_url, follow_redirects=True)
            if resp.status_code != 200:
                return []

            # Simple sitemap parsing (regex or XML parser)
            # For prototype, we'll look for <loc> tags
            soup = BeautifulSoup(resp.text, "xml")
            urls = [loc.text for loc in soup.find_all("loc")]

            return self._filter_urls(urls, allow, block, topics, mode)
        except Exception as e:
            logger.warning(f"Sitemap discovery failed for {root_url}: {e}")
            return []

    async def _path_discovery(self, root_url: str, allow: list[str], block: list[str], max_cand: int, topics: list[str] | None = None, mode: DiscoveryMode | None = None) -> list[dict[str, Any]]:
        """Simple breadth-first crawl to find links."""
        domain = urlparse(root_url).netloc
        if not await redis_client.rate_check(domain):
            await asyncio.sleep(1.0)
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

            return self._filter_urls(links, allow, block, topics, mode)
        except Exception as e:
            logger.warning(f"Path discovery failed for {root_url}: {e}")
            return []

    async def _find_search_endpoint(self, root_url: str) -> tuple[str, str] | None:
        """Find the native search endpoint and parameter name."""
        domain = urlparse(root_url).netloc
        cache_key = f"cache:search_endpoint:{domain}"
        cached = await redis_client.get_cache(cache_key)
        if cached is not None:
            return tuple(cached)

        if not await redis_client.rate_check(domain):
            await asyncio.sleep(1.0)
        try:
            resp = await self.http_client.get(root_url, follow_redirects=True, timeout=5.0)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "html.parser")
            for form in soup.find_all("form"):
                method = form.get("method", "get").lower()
                if method == "get":
                    for inp in form.find_all("input"):
                        type_attr = inp.get("type", "text").lower()
                        if type_attr in ["text", "search"]:
                            name = inp.get("name")
                            action = form.get("action", "")
                            if name:
                                await redis_client.set_cache(cache_key, [action, name], ttl=redis_client.CACHE_30D)
                                return action, name

            # Common fallbacks if form parsing fails
            result = ("/search", "q")
            await redis_client.set_cache(cache_key, list(result), ttl=redis_client.CACHE_30D)
            return result
        except Exception as e:
            logger.warning(f"Failed to find search endpoint for {root_url}: {e}")
            return None

    async def _search_endpoint_discovery(self, root_url: str, query: str, allow: list[str], block: list[str], max_cand: int, topics: list[str] | None = None, mode: DiscoveryMode | None = None) -> list[dict[str, Any]]:
        """Query the native search endpoint and parse results."""
        endpoint_info = await self._find_search_endpoint(root_url)
        if not endpoint_info:
            return []

        action, param = endpoint_info
        search_url = urljoin(root_url, action)
        domain = urlparse(search_url).netloc
        if not await redis_client.rate_check(domain):
            await asyncio.sleep(1.0)

        try:
            resp = await self.http_client.get(search_url, params={param: query}, follow_redirects=True, timeout=10.0)
            if resp.status_code != 200:
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                full_url = urljoin(root_url, href)
                if urlparse(full_url).netloc == urlparse(root_url).netloc:
                    links.append(full_url)

            logger.info(f"Native search for '{query}' on {root_url} found {len(links)} raw links.")
            return self._filter_urls(links, allow, block, topics, mode, is_search_result=True)

        except Exception as e:
            logger.warning(f"Native search failed for {root_url}: {e}")
            return []

    def _filter_urls(self, urls: list[str], allow: list[str], block: list[str], topics: list[str] | None = None, mode: DiscoveryMode | None = None, is_search_result: bool = False) -> list[dict[str, Any]]:
        results = []
        # Additional patterns to avoid index and directory pages
        index_patterns = ["encyclopedia_", "index.htm", "index.html", "/search?", "/archive/", "/health-topics/"]

        # Smart clinical abbreviation/synonym expansion to avoid false negative filtering
        synonym_map = {
            "pcos": ["polycystic", "ovary", "ovarian", "syndrome"],
            "ra": ["rheumatoid", "arthritis"],
            "ibd": ["inflammatory", "bowel", "crohn", "colitis"],
            "ibs": ["irritable", "bowel"],
            "gerd": ["acid", "reflux", "esophageal"],
            "copd": ["pulmonary", "lung", "bronchitis", "emphysema"],
            "adhd": ["attention", "deficit", "hyperactivity"],
            "asd": ["autism", "spectrum"],
            "als": ["amyotrophic", "lateral", "sclerosis", "lou", "gehrig"],
            "sle": ["lupus", "systemic", "erythematosus"],
            "ms": ["multiple", "sclerosis"],
            "t2d": ["type-2-diabetes", "type", "diabetes"],
            "t1d": ["type-1-diabetes", "type", "diabetes"],
            "polycystic ovary syndrome": ["pcos"],
            "rheumatoid arthritis": ["ra"],
        }

        # Prepare keyword match list if topics are present
        focused_keywords = []
        if topics:
            for t in topics:
                # Add the full topic string as a clean keyword if possible
                clean_t = "".join(c for c in t.lower() if c.isalnum() or c == " ")
                if clean_t in synonym_map:
                    focused_keywords.extend(synonym_map[clean_t])

                for word in t.lower().split():
                    clean_word = "".join(c for c in word if c.isalnum())
                    if len(clean_word) >= 3:
                        focused_keywords.append(clean_word)
                        if clean_word in synonym_map:
                            focused_keywords.extend(synonym_map[clean_word])
            # Deduplicate keywords
            focused_keywords = list(set(focused_keywords))

        for url in urls:
            # 0. Skip fragment/anchor links entirely to avoid page-internal navigation jumps (e.g. #K, #A)
            if "#" in url:
                continue

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

            # 4. If in FOCUSED or HYBRID mode, focused_keywords are active, and this is NOT a native/targeted search result,
            # enforce keyword matching in URL path/query to restrict crawl scope.
            if focused_keywords and mode in [DiscoveryMode.FOCUSED, DiscoveryMode.HYBRID] and not is_search_result:
                url_lower = url.lower()
                is_match = any(word in url_lower for word in focused_keywords)
                if not is_match:
                    logger.info(f"Skipping URL not matching focused keywords: {url}")
                    continue

            # 5. Simple scoring heuristic
            score = 0.5
            # Bonus for article-like paths (note: removed '/health-topics/' to prevent directory listing inflation)
            if any(p in url.lower() for p in ["/article/", "/condition/", "/guide/", "/protocol/"]):
                score += 0.3

            # Bonus if topic keyword is explicitly present in the URL
            if focused_keywords:
                url_lower = url.lower()
                if any(word in url_lower for word in focused_keywords):
                    score += 0.2

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
                url = c["url"]
                url_redis_key = f"dedup:url:{redis_client.sha256(url)}"

                cached_doc_id = await redis_client.get_cache(url_redis_key)
                if cached_doc_id:
                    doc_id_val = uuid.UUID(cached_doc_id)
                else:
                    res = await session.execute(
                        select(DocumentRegistry).where(DocumentRegistry.canonical_url == url)
                    )
                    doc = res.scalar_one_or_none()

                    if not doc:
                        doc = DocumentRegistry(
                            id=uuid.uuid4(),
                            source_id=source_id,
                            canonical_url=url,
                            title=c.get("title"),
                        )
                        session.add(doc)
                        await session.flush()

                    doc_id_val = doc.id
                    await redis_client.set_cache(url_redis_key, str(doc_id_val), ttl=redis_client.DEDUP_TTL)

                # 2. Prevent Duplicate Evaluations in the SAME run
                existing_eval = await session.execute(
                    select(CandidateDocumentEvaluation)
                    .where(CandidateDocumentEvaluation.run_id == run_id)
                    .where(CandidateDocumentEvaluation.document_id == doc_id_val)
                )
                if existing_eval.scalar_one_or_none():
                    continue

                eval_obj = CandidateDocumentEvaluation(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    document_id=doc_id_val,
                    score=c.get("score", 0.5),
                    matched_terms=[],
                    decision=DiscoveryDecision.INGEST_NOW,
                )
                session.add(eval_obj)

                results.append({
                    "document_id": str(doc_id_val),
                    "url": url
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
        from ks.domain.models import SourceRegistry
        from ks.domain.enums import SourceApprovalStatus, SourceType
        
        domain = payload.get("domain", "")
        snippet = payload.get("snippet", "")

        # 1. Normalize domain name
        domain_clean = domain.lower().strip()
        if ":" in domain_clean:
            domain_clean = domain_clean.split(":")[0]
        if domain_clean.startswith("www."):
            domain_clean_base = domain_clean[4:]
        else:
            domain_clean_base = domain_clean

        logger.info(f"Evaluating source authority for domain: {domain_clean_base}")

        # 2. Database Lookup
        try:
            async with AsyncSessionFactory() as session:
                # Search for domain in root_url
                res = await session.execute(
                    select(SourceRegistry).where(
                        (SourceRegistry.root_url.ilike(f"%{domain_clean_base}%"))
                    )
                )
                source = res.scalars().first()

                if source:
                    # If blocked/untrustworthy
                    if source.approval_status == SourceApprovalStatus.BLOCKED or source.trust_tier == 5:
                        logger.info(f"Domain {domain_clean_base} found in db and is BLOCKED.")
                        return {
                            "success": True,
                            "evaluation": {
                                "is_reputable": False,
                                "trust_score": 0.0,
                                "reason": f"Domain blocked in database registry: {source.review_notes or 'Low authority.'}",
                                "source_type": "SPAM"
                            }
                        }

                    # If approved
                    is_reputable = source.approval_status in [
                        SourceApprovalStatus.APPROVED_ACTIVE,
                        SourceApprovalStatus.APPROVED_LIMITED,
                        SourceApprovalStatus.CANDIDATE,
                        SourceApprovalStatus.UNDER_REVIEW
                    ]
                    trust_score = source.authority_score if source.authority_score is not None else (1.0 - (source.trust_tier - 1) * 0.2)
                    trust_score = max(0.0, min(1.0, trust_score))

                    logger.info(f"Domain {domain_clean_base} found in db. is_reputable={is_reputable}, trust_score={trust_score}")
                    return {
                        "success": True,
                        "evaluation": {
                            "is_reputable": is_reputable,
                            "trust_score": trust_score,
                            "reason": f"Domain resolved from trust registry: {source.name}. Status: {source.approval_status.value}",
                            "source_type": source.source_type.value
                        }
                    }
        except Exception as db_err:
            logger.error(f"Database lookup failed during source authority evaluation: {db_err}")

        # 3. Static Patterns Check
        static_matched = False
        is_reputable = False
        trust_score = 0.5
        source_type = "SPAM"
        reason = ""

        # A. Trusted Suffixes
        if any(domain_clean_base.endswith(suffix) for suffix in [".gov", ".edu", ".gov.uk", ".gov.au", ".gov.ca"]):
            static_matched = True
            is_reputable = True
            trust_score = 0.95
            source_type = "PUBLIC_HEALTH_SOURCE" if ".gov" in domain_clean_base else "ACADEMIC_SOURCE"
            reason = f"Verified high-authority public health or academic domain extension ({domain_clean_base})."

        # B. Trusted Domain Matches
        elif any(trusted in domain_clean_base for trusted in [
            "who.int", "cochrane.org", "nhs.uk", "mayoclinic.org", "clevelandclinic.org",
            "academic.oup.com", "jamanetwork.com", "thelancet.com", "nejm.org", "nature.com",
            "science.org", "springer.com", "wiley.com", "sciencedirect.com", "cell.com",
            "plos.org", "frontiersin.org", "mdpi.com", "europepmc.org", "ncbi.nlm.nih.gov",
            "pubmed.ncbi.nlm.nih.gov"
        ]):
            static_matched = True
            is_reputable = True
            trust_score = 0.95 if any(x in domain_clean_base for x in ["who.int", "nih.gov", "cochrane.org"]) else 0.90
            source_type = "ACADEMIC_SOURCE" if any(x in domain_clean_base for x in [
                "academic.oup.com", "jamanetwork.com", "thelancet.com", "nejm.org", "nature.com",
                "science.org", "springer.com", "wiley.com", "sciencedirect.com", "cell.com",
                "plos.org", "frontiersin.org", "mdpi.com", "europepmc.org", "ncbi.nlm.nih.gov",
                "pubmed.ncbi.nlm.nih.gov"
            ]) else "HOSPITAL_EDUCATION_SOURCE"
            reason = f"Verified high-authority clinical/medical institution domain ({domain_clean_base})."

        # C. Blocked/Spam Extensions & Keywords
        elif any(spam in domain_clean_base for spam in [
            ".xyz", ".top", ".click", ".review", ".preview", ".club",
            "coupon", "discount", "shopping", "promo", "deal", "best-product"
        ]):
            static_matched = True
            is_reputable = False
            trust_score = 0.1
            source_type = "SPAM"
            reason = f"Blocked domain extension or suspicious commercial spam keywords detected ({domain_clean_base})."

        # 4. If static match, persist & return
        if static_matched:
            logger.info(f"Static pattern match for {domain_clean_base}: is_reputable={is_reputable}, trust_score={trust_score}")
            try:
                async with AsyncSessionFactory() as session:
                    # Double-check inside session to avoid race condition
                    existing = await session.execute(
                        select(SourceRegistry).where(SourceRegistry.root_url == f"https://{domain_clean_base}")
                    )
                    if not existing.scalars().first():
                        new_source = SourceRegistry(
                            id=uuid.uuid4(),
                            name=domain_clean_base.split(".")[0].upper(),
                            root_url=f"https://{domain_clean_base}",
                            source_type=SourceType(source_type) if source_type != "SPAM" else SourceType.MANUAL_REFERENCE_SOURCE,
                            trust_tier=1 if is_reputable else 5,
                            authority_score=trust_score,
                            approval_status=SourceApprovalStatus.APPROVED_ACTIVE if is_reputable else SourceApprovalStatus.BLOCKED,
                            review_notes=reason
                        )
                        session.add(new_source)
                        await session.commit()
                        logger.info(f"Persisted static matching domain {domain_clean_base} as {new_source.approval_status.value}")
            except Exception as persist_err:
                logger.warning(f"Failed to persist static match domain: {persist_err}")

            return {
                "success": True,
                "evaluation": {
                    "is_reputable": is_reputable,
                    "trust_score": trust_score,
                    "reason": reason,
                    "source_type": source_type
                }
            }

        # 5. LLM Fallback (if no DB record and no static match)
        logger.info(f"No DB match or static rule match for {domain_clean_base}. Falling back to LLM evaluation.")
        settings = get_settings()
        model = settings.model.primary_model
        api_key = settings.model.primary_api_key

        prompt = f"""
        Evaluate the following web domain for clinical and medical authority.
        Domain: {domain_clean_base}
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
            llm_is_reputable = output.get("is_reputable", False)
            llm_trust_score = output.get("trust_score", 0.5)
            llm_source_type = output.get("source_type", "COMMERCIAL_WELLNESS")
            llm_reason = output.get("reason", "LLM evaluated.")
            
            # Map source_type to standard enum if possible
            std_source_type = SourceType.MANUAL_REFERENCE_SOURCE
            if llm_source_type == "ACADEMIC":
                std_source_type = SourceType.ACADEMIC_SOURCE
            elif llm_source_type == "GOVERNMENT":
                std_source_type = SourceType.PUBLIC_HEALTH_SOURCE
            elif llm_source_type == "CLINICAL":
                std_source_type = SourceType.CLINICAL_REPORT_SOURCE
                
            # 6. Persist the LLM evaluated domain to the database to cache it permanently!
            try:
                async with AsyncSessionFactory() as session:
                    existing = await session.execute(
                        select(SourceRegistry).where(SourceRegistry.root_url == f"https://{domain_clean_base}")
                    )
                    if not existing.scalars().first():
                        tier = 3
                        if llm_trust_score >= 0.85:
                            tier = 1
                        elif llm_trust_score >= 0.70:
                            tier = 2
                        elif llm_trust_score < 0.40:
                            tier = 5
                            
                        new_source = SourceRegistry(
                            id=uuid.uuid4(),
                            name=domain_clean_base.split(".")[0].upper(),
                            root_url=f"https://{domain_clean_base}",
                            source_type=std_source_type,
                            trust_tier=tier,
                            authority_score=llm_trust_score,
                            approval_status=SourceApprovalStatus.APPROVED_ACTIVE if (llm_is_reputable and tier < 5) else SourceApprovalStatus.BLOCKED,
                            review_notes=f"LLM Authority Eval: {llm_reason}"
                        )
                        session.add(new_source)
                        await session.commit()
                        logger.info(f"Persisted LLM-evaluated domain {domain_clean_base} as {new_source.approval_status.value} with tier {tier}")
            except Exception as persist_err:
                logger.warning(f"Failed to persist LLM-evaluated domain: {persist_err}")
                
            return {"success": True, "evaluation": output}
        except Exception as e:
            logger.error(f"Source authority evaluation LLM failed for {domain_clean_base}: {e}")
            return {"success": False, "error": str(e)}

    @activity.defn
    async def perform_targeted_search(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Execute intent-driven search across configured providers."""
        query = payload.get("query", "")
        limit = payload.get("limit", 20)
        domains = payload.get("domains", [])

        # We will use DuckDuckGo as fallback, and EuropePMC for scientific
        from ks.discovery.search import DuckDuckGoProvider, EuropePMCProvider

        ddg = DuckDuckGoProvider(self.http_client)
        epmc = EuropePMCProvider(self.http_client)

        results = []
        try:
            # If domains are specified, we only want to search those specific domains
            # Note: EuropePMC doesn't easily support domain restriction for non-PMC domains via simple query,
            # so we focus on DuckDuckGo which supports site: filters natively.
            if domains:
                # Build domain query e.g. "(site:domain1 OR site:domain2) query"
                sites_str = " OR ".join([f"site:{d}" for d in domains])
                ddg_query = f"{query} {sites_str}"

                # We allocate all limit to DDG since EuropePMC might return out-of-domain results
                ddg_res = await ddg.search(ddg_query, limit=limit)
                results.extend(ddg_res)
            else:
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

    @activity.defn
    async def expand_discovery_query(self, topics: list[str]) -> str:
        """Use an LLM to expand user search topics into an optimized medical query."""
        if not topics:
            return ""
            
        settings = get_settings()
        model = settings.model.primary_model
        api_key = settings.model.primary_api_key
        
        topics_str = ", ".join(topics)
        prompt = f"""
        You are an advanced Clinical Search Specialist. Your task is to expand the following medical search topics into a single optimized search query string for clinical research and evidence gathering.
        
        Topics: {topics_str}
        
        Rules:
        1. Include standard clinical synonyms, chemical names, acronyms, and scientific names (e.g. expand PCOS to "polycystic ovary syndrome" and include standard abbreviations).
        2. Connect search terms using uppercase OR and AND operators where appropriate.
        3. Do not include search prefix operators like site: or filetype: unless highly related.
        4. Keep the query string standard and compatible with general web search engines.
        5. Return ONLY the raw expanded query string. Do not include markdown, code blocks, prefixes, explanations, or quotes.
        
        Example Output for ["PCOS"]:
        "polycystic ovary syndrome" OR PCOS OR "stein-leventhal syndrome"
        """
        
        try:
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                api_key=api_key
            )
            expanded = response.choices[0].message.content.strip()
            # Clean any surrounding quotes or markdown code block formatting if generated by the LLM
            if expanded.startswith("`") or expanded.startswith('"'):
                expanded = expanded.strip("`").strip('"')
            logger.info(f"Expanded topics {topics} into clinical query: '{expanded}'")
            return expanded
        except Exception as e:
            logger.error(f"Query expansion failed: {e}. Falling back to default query.")
            return " ".join(topics)

    @activity.defn
    async def calculate_semantic_similarity(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Compute the cosine similarity between the candidate document metadata and the search topics."""
        metadata = payload.get("metadata", {})
        topics = payload.get("topics", [])
        threshold = payload.get("threshold", 0.65)
        
        if not topics or not metadata:
            return {"passed": True, "score": 1.0}
            
        settings = get_settings()
        embedding_model = settings.model.embedding_model
        api_key = settings.model.embedding_api_key
        
        topics_text = " ".join(topics)
        doc_title = metadata.get("title", "") or ""
        doc_desc = metadata.get("meta_description", "") or ""
        doc_text = f"{doc_title} {doc_desc}".strip()
        
        if not doc_text:
            return {"passed": False, "score": 0.0}
            
        try:
            logger.info(f"Generating embeddings for pre-triage semantic check using model: {embedding_model}")
            
            # Generate embeddings for both texts
            response = litellm.embedding(
                model=embedding_model,
                input=[topics_text, doc_text],
                api_key=api_key
            )
            
            vec_topics = response.data[0]["embedding"]
            vec_doc = response.data[1]["embedding"]
            
            # Compute Cosine Similarity
            import math
            dot_product = sum(a * b for a, b in zip(vec_topics, vec_doc))
            magnitude_topics = math.sqrt(sum(a * a for a in vec_topics))
            magnitude_doc = math.sqrt(sum(a * a for a in vec_doc))
            
            if magnitude_topics == 0 or magnitude_doc == 0:
                similarity = 0.0
            else:
                similarity = dot_product / (magnitude_topics * magnitude_doc)
                
            passed = similarity >= threshold
            logger.info(f"Semantic similarity between topics '{topics_text}' and doc '{doc_title}': {similarity:.4f} (Threshold: {threshold}) -> Passed: {passed}")
            return {"passed": passed, "score": similarity}
            
        except Exception as e:
            logger.error(f"Semantic pre-triage similarity check failed: {e}. Defaulting to pass.")
            return {"passed": True, "score": 0.5}
