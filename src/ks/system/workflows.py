from datetime import timedelta
from typing import Any

from temporalio import workflow

from ks.acquisition.workflows import AcquisitionWorkflow
from ks.extraction.workflows import ExtractionWorkflow
from ks.enrichment.workflows import EnrichmentWorkflow
from ks.chunking.workflows import ChunkingWorkflow
from ks.graph.workflows import GraphSyncWorkflow


@workflow.defn
class DocumentIngestionWorkflow:
    @workflow.run
    async def run(self, payload: dict) -> dict:
        """
        End-to-End Ingestion Orchestrator for a single document.
        Coordinates chain: Acquisition -> Extraction -> Enrichment -> Chunking -> GraphSync
        Payload keys: document_id, url
        """
        doc_id = payload["document_id"]
        url = payload["url"]
        
        # ── Phase 1: Fetch ────────────────────────────────────────────────────────────
        fetch_run_id = await workflow.execute_activity(
            "prepare_stage_run",
            {"stage": "fetch", "document_id": doc_id},
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        acq_result = await workflow.execute_child_workflow(
            AcquisitionWorkflow.run,
            {
                "run_id": fetch_run_id,
                "document_id": doc_id,
                "url": url,
                "force_refresh": payload.get("force_refresh", False),
            },
            id=f"acq-{doc_id}",
        )
        
        if acq_result.get("status") != "COMPLETED":
            return {"status": "FAILED_AT_ACQUISITION", "details": acq_result}
            
        raw_object_key = acq_result.get("object_key")
        
        # ── Phase 2: Extraction ───────────────────────────────────────────────────────
        extract_run_id = await workflow.execute_activity(
            "prepare_stage_run",
            {"stage": "extraction", "document_id": doc_id},
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        ext_result = await workflow.execute_child_workflow(
            ExtractionWorkflow.run,
            {
                "run_id": extract_run_id,
                "document_id": doc_id,
                "raw_object_key": raw_object_key,
                "use_ocr": False,
                "use_llm": True
            },
            id=f"ext-{doc_id}",
        )
        
        if ext_result.get("status") != "COMPLETED":
            return {"status": "FAILED_AT_EXTRACTION", "details": ext_result}
            
        extracted_text_key = ext_result.get("extracted_object_key")

        # ── Phase 3: Enrichment ───────────────────────────────────────────────────────
        enrich_run_id = await workflow.execute_activity(
            "prepare_stage_run",
            {"stage": "enrichment", "document_id": doc_id},
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        enr_result = await workflow.execute_child_workflow(
            EnrichmentWorkflow.run,
            {
                "run_id": enrich_run_id,
                "document_id": doc_id,
                "extracted_text_key": extracted_text_key,
                "model": "deepseek/deepseek-chat", # Default to deepseek
                "framework_scope": payload.get("framework_scope", [])
            },
            id=f"enr-{doc_id}",
        )
        # NOTE: If enrichment fails it shouldn't block chunking/indexing, but let's stop for now for stability.

        # ── Phase 4: Chunking ─────────────────────────────────────────────────────────
        chunk_run_id = await workflow.execute_activity(
            "prepare_stage_run",
            {"stage": "chunk", "document_id": doc_id},
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        chunk_result = await workflow.execute_child_workflow(
            ChunkingWorkflow.run,
            {
                "run_id": chunk_run_id,
                "document_id": doc_id,
                "extracted_text_key": extracted_text_key,
                "embedding_model": "text-embedding-3-small"
            },
            id=f"chnk-{doc_id}",
        )

        # ── Phase 5: Graph Sync ─────────────────────────────────────────────────────
        graph_run_id = await workflow.execute_activity(
            "prepare_stage_run",
            {"stage": "graph", "document_id": doc_id},
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        graph_result = await workflow.execute_child_workflow(
            GraphSyncWorkflow.run,
            {
                "run_id": graph_run_id,
                "document_id": doc_id,
            },
            id=f"grph-{doc_id}",
        )

        return {
            "status": "COMPLETED",
            "document_id": doc_id,
            "pipeline": ["acquisition", "extraction", "enrichment", "chunking", "graph_sync"]
        }
