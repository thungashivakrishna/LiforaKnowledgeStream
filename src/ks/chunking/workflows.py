"""Chunking workflows — Temporal workflow definitions for chunking and embedding."""
from datetime import timedelta
from typing import Any

from temporalio import workflow

from ks.domain.enums import RunStatus

with workflow.unsafe.imports_passed_through():
    from ks.chunking.activities import ChunkingActivities


@workflow.defn
class ChunkingWorkflow:
    @workflow.run
    async def run(self, payload: dict) -> dict:
        """
        Chunking workflow: orchestrates fetching text, chunking, embedding, indexing, and persisting.
        Payload keys: run_id, document_id, extracted_text_key, embedding_model
        """
        run_id = payload["run_id"]
        doc_id = payload["document_id"]
        extracted_text_key = payload.get("extracted_text_key")
        model = payload.get("embedding_model", "text-embedding-3-small")
        
        if not extracted_text_key:
             return {"status": "FAILED", "error": "extracted_text_key missing in payload"}
             
        # 1. Ensure Qdrant Collection Exists
        qdrant_setup = await workflow.execute_activity(
            "ensure_qdrant_collection",
            {"embedding_model": model},
            start_to_close_timeout=timedelta(minutes=1),
        )
        if not qdrant_setup["success"]:
            return await self._fail_workflow(run_id, qdrant_setup["error"])
            
        # 2. Fetch Text and Metadata
        fetch_result = await workflow.execute_activity(
            "fetch_text_and_metadata",
            {
                "extracted_object_key": extracted_text_key,
                "document_id": doc_id
            },
            start_to_close_timeout=timedelta(minutes=5),
        )
        if not fetch_result["success"]:
            return await self._fail_workflow(run_id, fetch_result["error"])
            
        # 3. Split and Embed
        embed_payload = {
            "text": fetch_result["text"],
            "embedding_model": model,
            "document_id": doc_id,
            "primary_framework": fetch_result["primary_framework"],
            "topics": fetch_result["topics"]
        }
        
        embed_result = await workflow.execute_activity(
            "split_and_embed",
            embed_payload,
            start_to_close_timeout=timedelta(minutes=15),
        )
        if not embed_result["success"]:
            return await self._fail_workflow(run_id, embed_result["error"])
            
        chunks = embed_result["chunks"]
        chunk_count = len(chunks)
        
        if chunk_count > 0:
            # 4. Index in Qdrant
            index_payload = {
                "chunks": chunks,
                "document_id": doc_id,
                "primary_framework": fetch_result["primary_framework"],
                "topics": fetch_result["topics"]
            }
            index_result = await workflow.execute_activity(
                "index_in_qdrant",
                index_payload,
                start_to_close_timeout=timedelta(minutes=5),
            )
            if not index_result["success"]:
                return await self._fail_workflow(run_id, index_result["error"])
                
            # 5. Persist Metadata to Postgres
            persist_payload = {
                "chunks": chunks,
                "document_id": doc_id,
                "embedding_model": model,
                "primary_framework": fetch_result["primary_framework"],
                "topics": fetch_result["topics"]
            }
            persist_result = await workflow.execute_activity(
                "persist_chunk_metadata",
                persist_payload,
                start_to_close_timeout=timedelta(minutes=2),
            )
            if not persist_result["success"]:
                return await self._fail_workflow(run_id, persist_result["error"])
        
        # 6. Update Status
        await workflow.execute_activity(
            "update_chunk_status",
            {
                "run_id": run_id,
                "status": RunStatus.COMPLETED.value,
                "chunk_count": chunk_count,
                "total_tokens": embed_result.get("total_tokens", 0)
            },
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        return {"status": "COMPLETED", "chunk_count": chunk_count}
        
    async def _fail_workflow(self, run_id: str, error_msg: str) -> dict:
        await workflow.execute_activity(
            "update_chunk_status",
            {
                "run_id": run_id,
                "status": RunStatus.FAILED.value,
                "error_message": error_msg
            },
            start_to_close_timeout=timedelta(seconds=30),
        )
        return {"status": "FAILED", "error": error_msg}
