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
        Extraction workflow: Orchestrates consolidated extraction pipeline without passing large payloads.
        Payload keys: run_id, document_id, raw_object_key, use_ocr, use_llm
        """
        run_id = payload["run_id"]
        raw_object_key = payload["raw_object_key"]
        
        # Execute the unified activity that streams locally
        result = await workflow.execute_activity(
            "perform_full_extraction",
            {
                "raw_object_key": raw_object_key,
                "use_ocr": payload.get("use_ocr", False),
                "use_llm": payload.get("use_llm", False)
            },
            start_to_close_timeout=timedelta(minutes=15),
        )
        
        if not result["success"]:
            await workflow.execute_activity(
                "update_extraction_status",
                {
                    "run_id": run_id,
                    "status": RunStatus.FAILED.value,
                    "error_message": result.get("error", "Unified extraction failed")
                },
                start_to_close_timeout=timedelta(seconds=30),
            )
            return {"status": "FAILED", "error": result.get("error")}
            
        # Update DB with the results from the unified run
        await workflow.execute_activity(
            "update_extraction_status",
            {
                "run_id": run_id,
                "status": RunStatus.COMPLETED.value,
                "quality": result["quality"],
                "extracted_object_key": result["extracted_object_key"]
            },
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        return {"status": "COMPLETED", "extracted_object_key": result["extracted_object_key"]}
