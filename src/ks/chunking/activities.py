"""Chunking activities — worker tasks for chunking text, generating embeddings, and indexing in Qdrant."""
import hashlib
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any

from minio import Minio
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from temporalio import activity

from ks.common import redis_client
from ks.common.llm_gateway import embed as gateway_embed
from ks.config.settings import get_settings
from ks.domain.enums import RunStatus
from ks.domain.models import ChunkRun, KnowledgeChunk, DocumentRegistry


logger = logging.getLogger(__name__)


class ChunkingActivities:
    def __init__(self, minio_client: Minio, qdrant_client: QdrantClient):
        self.minio_client = minio_client
        self.qdrant_client = qdrant_client
        self.settings = get_settings()
        self.collection_name = "knowledge_chunks"

    @activity.defn
    async def ensure_qdrant_collection(self, payload: dict) -> dict:
        """
        Ensures the Qdrant collection exists.
        Payload keys: embedding_model
        """
        # We need the vector size based on the model.
        # For text-embedding-3-small or text-embedding-ada-002, size is 1536.
        # We can make this dynamic if needed, but we'll hardcode 1536 for now.
        embedding_model = payload.get("embedding_model", "text-embedding-3-small")
        vector_size = 1536

        try:
            collections = self.qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.collection_name not in collection_names:
                logger.info(f"Creating Qdrant collection '{self.collection_name}' with size {vector_size}")
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qdrant_models.VectorParams(
                        size=vector_size,
                        distance=qdrant_models.Distance.COSINE
                    )
                )
            return {"success": True}
        except Exception as e:
            logger.error(f"Failed to ensure Qdrant collection: {e}")
            return {"success": False, "error": str(e)}

    @activity.defn
    async def fetch_text_and_metadata(self, payload: dict) -> dict:
        """
        Fetches the clean text artifact from MinIO and metadata from Postgres.
        Payload keys: extracted_object_key, document_id
        """
        object_key = payload["extracted_object_key"]
        doc_id_str = payload["document_id"]
        bucket = self.settings.minio.bucket_extracted

        logger.info(f"Fetching extracted text from MinIO: {bucket}/{object_key}")

        try:
            # 1. Fetch Text
            response = self.minio_client.get_object(bucket, object_key)
            content_bytes = response.read()
            text = content_bytes.decode("utf-8")
            response.close()
            response.release_conn()

            # 2. Fetch Metadata (Frameworks, Topics)
            from apps.api.database import SessionLocal
            from ks.domain.models import KnowledgeTag
            from sqlalchemy import select

            doc_id = uuid.UUID(doc_id_str)
            primary_framework = None
            topics = []

            async with SessionLocal() as session:
                res = await session.execute(select(KnowledgeTag).where(KnowledgeTag.document_id == doc_id))
                tags = res.scalars().all()
                for tag in tags:
                    if tag.tag_type.name == "FRAMEWORK" and tag.is_primary:
                        primary_framework = tag.tag_value
                    elif tag.tag_type.name == "TOPIC":
                        topics.append(tag.tag_value)

            return {
                "object_key": object_key,
                "text": text,
                "primary_framework": primary_framework,
                "topics": topics,
                "success": True
            }
        except Exception as e:
            logger.error(f"Failed to fetch extracted text and metadata: {e}")
            return {"success": False, "error": str(e)}

    def _split_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Simple recursive character chunker fallback."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            if end > len(text):
                chunks.append(text[start:])
                break

            # Try to find a good breaking point (newline or space)
            break_point = text.rfind("\n\n", start, end)
            if break_point == -1:
                break_point = text.rfind("\n", start, end)
            if break_point == -1 or break_point < start + (chunk_size // 2):
                break_point = text.rfind(" ", start, end)

            if break_point == -1 or break_point < start + (chunk_size // 2):
                break_point = end

            chunks.append(text[start:break_point].strip())
            start = break_point - overlap

        return [c for c in chunks if c] # Remove empty chunks

    @activity.defn
    async def split_and_embed(self, payload: dict) -> dict:
        """
        Splits text into chunks, generates embeddings.
        Payload keys: text, embedding_model, document_id, primary_framework, topics
        """
        text = payload["text"]

        try:
            # 1. Split Text
            raw_chunks = self._split_text(text)
            logger.info(f"Split text into {len(raw_chunks)} chunks.")

            if not raw_chunks:
                return {"success": True, "chunks": []}

            doc_id = payload.get("document_id")
            vectors = await gateway_embed(
                raw_chunks,
                stage="chunking",
                document_id=doc_id,
                cache=True,
            )
            total_tokens = 0  # tracked inside gateway
            cached_vectors = {i: v for i, v in enumerate(vectors)}

            processed_chunks = []
            for i, chunk_text in enumerate(raw_chunks):
                processed_chunks.append({
                    "chunk_index": i,
                    "chunk_text": chunk_text,
                    "qdrant_point_id": str(uuid.uuid4()),
                    "embedding": cached_vectors[i],
                    "token_count": len(chunk_text) // 4
                })

            return {"success": True, "chunks": processed_chunks, "total_tokens": total_tokens}

        except Exception as e:
            logger.error(f"Failed to split and embed text: {e}")
            return {"success": False, "error": str(e)}

    @activity.defn
    async def index_in_qdrant(self, payload: dict) -> dict:
        """
        Pushes the embeddings and metadata to Qdrant.
        Payload keys: chunks, document_id, primary_framework, topics
        """
        chunks = payload["chunks"]
        doc_id = payload["document_id"]
        primary_fw = payload.get("primary_framework")
        topics = payload.get("topics", [])

        if not chunks:
            return {"success": True}

        lock_key = f"lock:qdrant:{doc_id}"
        if not await redis_client.acquire_lock(lock_key, ttl=redis_client.LOCK_QDRANT):
            from temporalio.exceptions import ApplicationError
            raise ApplicationError(f"Qdrant lock held for {doc_id}", non_retryable=False)

        try:
            points = []
            for chunk in chunks:
                point_id = chunk["qdrant_point_id"]
                vector = chunk["embedding"]

                # Payload metadata
                meta = {
                    "document_id": doc_id,
                    "chunk_index": chunk["chunk_index"],
                    "text": chunk["chunk_text"],
                    "framework": primary_fw,
                    "topics": topics
                }

                points.append(
                    qdrant_models.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=meta
                    )
                )

            logger.info(f"Upserting {len(points)} points into Qdrant collection '{self.collection_name}'")
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=points
            )

            return {"success": True}
        except Exception as e:
            logger.error(f"Failed to index in Qdrant: {e}")
            return {"success": False, "error": str(e)}
        finally:
            await redis_client.release_lock(lock_key)

    @activity.defn
    async def persist_chunk_metadata(self, payload: dict) -> dict:
        """
        Saves the chunk references to PostgreSQL.
        Payload keys: chunks, document_id, primary_framework, topics, embedding_model
        """
        from apps.api.database import SessionLocal

        doc_id = uuid.UUID(payload["document_id"])
        chunks = payload["chunks"]
        model = payload["embedding_model"]
        primary_fw = payload.get("primary_framework")
        topics = payload.get("topics", [])

        # We need to map string to Enum if applicable, but Framework is an Enum.
        # In this prototype, we'll just store it if it matches, or leave it None.
        from ks.domain.enums import Framework
        fw_enum = None
        if primary_fw:
            try:
                fw_enum = Framework(primary_fw)
            except ValueError:
                pass

        async with SessionLocal() as session:
            try:
                for chunk in chunks:
                    db_chunk = KnowledgeChunk(
                        document_id=doc_id,
                        chunk_index=chunk["chunk_index"],
                        chunk_text=chunk["chunk_text"],
                        token_count=chunk["token_count"],
                        framework=fw_enum,
                        topics=topics,
                        qdrant_point_id=uuid.UUID(chunk["qdrant_point_id"]),
                        embedding_model=model
                    )
                    session.add(db_chunk)

                await session.commit()
                return {"success": True}

            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to persist chunk metadata to DB: {e}")
                return {"success": False, "error": str(e)}

    @activity.defn
    async def update_chunk_status(self, payload: dict) -> None:
        """
        Updates the ChunkRun status in the DB.
        """
        from apps.api.database import SessionLocal
        from sqlalchemy import select

        run_id = uuid.UUID(payload["run_id"])
        status = RunStatus(payload["status"])
        chunk_count = payload.get("chunk_count", 0)
        total_tokens = payload.get("total_tokens", 0)
        error_msg = payload.get("error_message")

        async with SessionLocal() as session:
            res = await session.execute(select(ChunkRun).where(ChunkRun.id == run_id))
            run = res.scalar_one_or_none()
            if run:
                run.status = status
                run.completed_at = datetime.now()
                run.chunk_count = chunk_count
                if total_tokens:
                    run.total_tokens = total_tokens
                if error_msg:
                    run.error_message = error_msg

            await session.commit()
