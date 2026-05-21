import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
import xxhash
from minio import Minio
from sqlalchemy import select
from temporalio import activity

from apps.api.database import AsyncSessionFactory
from ks.common import redis_client
from ks.common.llm_gateway import complete as gateway_complete
from ks.config.settings import get_settings
from ks.domain.enums import DocumentStatus, RunStatus
from ks.domain.models import DocumentRegistry, DocumentVersion, FetchRun
from ks.acquisition.schemas import IntelligenceAuditOutput


import io
from docling.datamodel.base_models import DocumentStream
from docling.document_converter import DocumentConverter

logger = logging.getLogger(__name__)


class AcquisitionActivities:
    def __init__(self, http_client: httpx.AsyncClient, minio_client: Minio):
        self.http_client = http_client
        self.minio_client = minio_client
        self.settings = get_settings()

    @activity.defn
    async def audit_document_intelligence(self, payload: dict) -> dict:
        """
        Intelligence Layer: Evaluates document relevance and depth using LLM.
        """
        content = payload.get("content_text", "")
        url = payload.get("url", "")

        audit_cache_key = f"cache:audit:{hashlib.sha256(content[:5000].encode()).hexdigest()}"
        cached = await redis_client.get_cache(audit_cache_key)
        if cached is not None:
            logger.info(f"Cache hit for audit: {url}")
            return cached

        # Use gpt-4o-mini for efficient auditing
        model = "gpt-4o-mini"
        api_key = self.settings.model.secondary_api_key

        prompt = f"""
        You are a Health Intelligence Auditor. Analyze the content from {url} to determine if it's high-value medical knowledge.

        Criteria:
        - HIGH VALUE: Detailed clinical guidelines, specific medication dosages (e.g., 500mg), nutrient stats, symptoms, or treatment protocols.
        - LOW VALUE / INDEX: Lists of links, search results, directory pages, or shallow boilerplate.
        - ENGLISH ONLY: Reject immediately if the primary content language is not English.

        Task:
        1. Decide if high_value (bool). MUST be false if the content is not in English.
        2. Provide reason (string). Mention 'Non-English Content' if rejected for language.
        3. If LOW VALUE but has promising links, list up to 5 absolute URLs to follow.
        4. If HIGH VALUE, extract top 3 key facts as S-P-O triples (subject, predicate, object).

        Content (first 5000 chars):
        {content[:5000]}
        """

        try:
            response = await gateway_complete(
                "acquisition.intelligence_audit.v1",
                {"url": url, "content": content},
                stage="acquisition",
            )
            if response.status not in ("success", "cached"):
                return {"success": False, "audit": {"is_high_value": True, "reason": f"Audit error: {response.status}"}}
            output = json.loads(response.content)
            result = {"success": True, "audit": output}
            await redis_client.set_cache(audit_cache_key, result, ttl=redis_client.DEDUP_TTL)
            return result
        except Exception as e:
            logger.error(f"Intelligence audit failed: {e}")
            return {"success": False, "audit": {"is_high_value": True, "reason": f"Audit error: {e}"}}

    @activity.defn
    async def fetch_content(self, payload: dict) -> dict:
        """
        Fetches the content of a document and returns the raw bytes + metadata.
        Payload keys: document_id, url
        """
        doc_id = payload["document_id"]
        url = payload["url"]

        logger.info(f"Fetching content for document {doc_id} from {url}")

        from urllib.parse import urlparse as _urlparse
        domain = _urlparse(url).netloc
        if not await redis_client.rate_check(domain):
            await asyncio.sleep(1.0)

        try:
            resp = await self.http_client.get(url, follow_redirects=True)
            resp.raise_for_status()

            content = resp.content
            content_type = resp.headers.get("content-type", "application/octet-stream")

            # Content Quality Assessment (for HTML)
            if "html" in content_type:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(content, "html.parser")
                # Remove boilerplate for accurate word count
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.extract()

                text = soup.get_text(separator=" ", strip=True)
                words = text.split()
                links = soup.find_all("a")

                # Criteria 1: Word count (Reject if < 100 words of actual content)
                if len(words) < 100:
                    logger.warning(f"Document {doc_id} rejected: Low word count ({len(words)})")
                    return {"document_id": str(doc_id), "url": url, "success": False, "rejected": True, "error": "Low content volume (index page?)"}

                # Criteria 2: Link-to-Text ratio (Reject if > 50% of the text is inside links)
                link_text_len = sum(len(a.get_text(strip=True)) for a in links)
                if link_text_len / (len(text) + 1) > 0.5:
                    logger.warning(f"Document {doc_id} rejected: High link-to-text ratio")
                    return {"document_id": str(doc_id), "url": url, "success": False, "rejected": True, "error": "High link density (index page?)"}

            # Diagnostic PDF Parsing & Vision Intake
            elif "pdf" in content_type:
                try:
                    stream = DocumentStream(name="diagnostic.pdf", stream=io.BytesIO(content))
                    converter = DocumentConverter()
                    result = converter.convert(stream)
                    text = result.document.export_to_markdown()

                    if len(text.strip()) < 50:
                        logger.warning(f"Low text yield from PDF {doc_id}. Likely a scanned lab report.")
                        text = "[SCANNED DIAGNOSTIC REPORT] - Vision Intake Required for full extraction.\n" + text
                except Exception as e:
                    logger.error(f"Failed to parse diagnostic PDF {doc_id}: {e}")
                    text = ""

            elif "image" in content_type:
                # Vision Intake using Docling OCR for physical medical reports/prescriptions
                try:
                    stream = DocumentStream(name="diagnostic.png", stream=io.BytesIO(content))
                    converter = DocumentConverter()
                    result = converter.convert(stream)
                    text = result.document.export_to_markdown()
                    logger.info(f"Successfully ran OCR Vision Intake on image {doc_id}")
                except Exception as e:
                    logger.error(f"Failed OCR on image {doc_id}: {e}")
                    text = ""
            else:
                text = ""

            # Content hashing
            hasher = xxhash.xxh64()
            hasher.update(content)
            content_hash = hasher.hexdigest()

            # DIRECT STORAGE: Write to Minio immediately to protect Temporal payload history
            ext = "html" if "html" in content_type else "pdf" if "pdf" in content_type else "bin"
            object_key = f"{doc_id}/{content_hash}.{ext}"

            bucket = self.settings.minio.bucket_raw
            if not self.minio_client.bucket_exists(bucket):
                self.minio_client.make_bucket(bucket)

            content_file = io.BytesIO(content)
            self.minio_client.put_object(
                bucket,
                object_key,
                content_file,
                length=len(content),
                content_type=content_type
            )
            logger.info(f"Directly stored {len(content)} bytes to MinIO object_key: {object_key}")

            return {
                "document_id": str(doc_id),
                "url": url,
                "content_hash": content_hash,
                "content_type": content_type,
                "size_bytes": len(content),
                "object_key": object_key,
                "content_text": text[:50000], # Truncate text returns to protect boundary
                "success": True
            }
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return {
                "document_id": str(doc_id),
                "url": url,
                "success": False,
                "error": str(e)
            }

    @activity.defn
    async def store_raw_artifact(self, payload: dict) -> str:
        """
        Stores the raw content in MinIO and returns the object key.
        Payload keys: document_id, content_hash, content_type, content (bytes)
        Note: Passing bytes directly in activity might be heavy, but for prototype it's okay.
        """
        doc_id = payload["document_id"]
        content_hash = payload["content_hash"]
        content_type = payload["content_type"]
        content = payload["content"]

        # Temporal JSON converter might turn bytes into a list of ints
        if isinstance(content, list):
            content = bytes(content)

        # Object key naming: {doc_id}/{hash}.{ext}
        ext = "html" if "html" in content_type else "pdf" if "pdf" in content_type else "bin"
        object_key = f"{doc_id}/{content_hash}.{ext}"

        logger.info(f"Storing artifact in MinIO: {object_key}")

        # Ensure bucket exists
        bucket = self.settings.minio.bucket_raw
        if not self.minio_client.bucket_exists(bucket):
            self.minio_client.make_bucket(bucket)

        # Upload
        content_file = io.BytesIO(content)
        self.minio_client.put_object(
            bucket,
            object_key,
            content_file,
            length=len(content),
            content_type=content_type
        )

        return object_key

    @activity.defn
    async def persist_audit_facts(self, payload: dict) -> None:
        """
        Intelligence Layer: Stores the initial facts captured during audit.
        """
        doc_id = uuid.UUID(payload["document_id"])
        facts = payload.get("facts", [])

        async with AsyncSessionFactory() as session:
            from ks.domain.models import KnowledgeFact
            from ks.domain.enums import ValidationStatus

            for f in facts:
                # Check for existing fact to avoid violating unique constraint
                stmt = select(KnowledgeFact).where(
                    KnowledgeFact.document_id == doc_id,
                    KnowledgeFact.subject == f.get("subject"),
                    KnowledgeFact.predicate == f.get("predicate"),
                    KnowledgeFact.object_ == f.get("object")
                )
                existing = await session.execute(stmt)
                if existing.scalar_one_or_none():
                    continue

                fact = KnowledgeFact(
                    document_id=doc_id,
                    fact_text=f.get("fact_text", ""),
                    subject=f.get("subject"),
                    predicate=f.get("predicate"),
                    object_=f.get("object"),
                    confidence=0.8, # Audit facts are initial indicators
                    validation_status=ValidationStatus.PENDING
                )
                session.add(fact)
            await session.commit()

    @activity.defn
    async def update_fetch_status(self, payload: dict) -> None:
        """
        Updates the database with the fetch result.
        Payload keys: run_id, document_id, status, error_message, version_hash, object_key
        """
        run_id = uuid.UUID(payload["run_id"])
        doc_id = uuid.UUID(payload["document_id"])
        status = RunStatus(payload["status"])
        error_msg = payload.get("error_message")
        v_hash = payload.get("version_hash")
        obj_key = payload.get("object_key")

        async with AsyncSessionFactory() as session:
            # Update FetchRun
            res = await session.execute(select(FetchRun).where(FetchRun.id == run_id))
            run = res.scalar_one_or_none()
            if run:
                run.status = status
                run.completed_at = datetime.now(timezone.utc)
                run.error_message = error_msg

            doc_result = await session.execute(
                select(DocumentRegistry).where(DocumentRegistry.id == doc_id)
            )
            document = doc_result.scalar_one_or_none()

            if status == RunStatus.COMPLETED and v_hash and obj_key:
                version = DocumentVersion(
                    id=uuid.uuid4(),
                    document_id=doc_id,
                    version_hash=v_hash,
                    raw_object_key=obj_key,
                    fetched_at=datetime.now(timezone.utc)
                )
                session.add(version)
                if document:
                    document.status = DocumentStatus.FETCHED
                    document.content_hash = v_hash
                    document.raw_object_key = obj_key
            elif document:
                if payload.get("rejected"):
                    document.status = DocumentStatus.REJECTED
                else:
                    document.status = DocumentStatus.FAILED

            await session.commit()
