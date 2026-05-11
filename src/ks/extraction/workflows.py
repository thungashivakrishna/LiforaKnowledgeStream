"""Extraction workflows — Temporal workflow definitions for content extraction."""
from datetime import timedelta
from typing import Any

from temporalio import workflow

from ks.domain.enums import RunStatus

with workflow.unsafe.imports_passed_through():
    from ks.extraction.activities import ExtractionActivities


@workflow.defn
class ExtractionWorkflow:
    @workflow.run
    async def run(self, payload: dict) -> dict:
        """
        Extraction workflow: orchestrates fetching raw bytes, extracting text, and storing it.
        Payload keys: run_id, document_id, raw_object_key, use_ocr, use_llm
        """
        run_id = payload["run_id"]
        doc_id = payload["document_id"]
        raw_object_key = payload["raw_object_key"]
        
        # 1. Fetch Raw Artifact
        fetch_result = await workflow.execute_activity(
            "fetch_raw_artifact",
            {"raw_object_key": raw_object_key},
            start_to_close_timeout=timedelta(minutes=5),
        )
        
        if not fetch_result["success"]:
            await workflow.execute_activity(
                "update_extraction_status",
                {
                    "run_id": run_id,
                    "status": RunStatus.FAILED.value,
                    "error_message": fetch_result["error"]
                },
                start_to_close_timeout=timedelta(seconds=30),
            )
            return {"status": "FAILED", "error": fetch_result["error"]}
            
        # 2. Extract Text
        extract_payload = {
            "object_key": raw_object_key,
            "content": fetch_result["content"],
            "use_ocr": payload.get("use_ocr", False),
            "use_llm": payload.get("use_llm", False)
        }
        
        extract_result = await workflow.execute_activity(
            "extract_text",
            extract_payload,
            start_to_close_timeout=timedelta(minutes=15), # Extraction can take a while if OCR/LLM
        )
        
        if not extract_result["success"]:
            await workflow.execute_activity(
                "update_extraction_status",
                {
                    "run_id": run_id,
                    "status": RunStatus.FAILED.value,
                    "error_message": extract_result["error"]
                },
                start_to_close_timeout=timedelta(seconds=30),
            )
            return {"status": "FAILED", "error": extract_result["error"]}
            
        # 3. Store Extracted Text
        store_payload = {
            "object_key": raw_object_key,
            "extracted_text": extract_result["extracted_text"]
        }
        
        await workflow.execute_activity(
            "store_extracted_artifact",
            store_payload,
            start_to_close_timeout=timedelta(minutes=2),
        )
        
        # 4. Update DB
        await workflow.execute_activity(
            "update_extraction_status",
            {
                "run_id": run_id,
                "status": RunStatus.COMPLETED.value,
                "quality": extract_result["quality"],
                "extracted_object_key": store_payload["object_key"].rsplit(".", 1)[0] + ".txt" if "." in store_payload["object_key"] else store_payload["object_key"] + ".txt"
            },
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        extracted_object_key = store_payload["object_key"].rsplit(".", 1)[0] + ".txt" if "." in store_payload["object_key"] else store_payload["object_key"] + ".txt"
        
        return {"status": "COMPLETED", "extracted_object_key": extracted_object_key}
