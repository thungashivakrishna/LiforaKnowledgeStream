"""Enrichment workflows — Temporal workflow definitions for knowledge enrichment."""
from datetime import timedelta
from typing import Any

from temporalio import workflow

from ks.domain.enums import RunStatus

with workflow.unsafe.imports_passed_through():
    from ks.enrichment.activities import EnrichmentActivities


@workflow.defn
class EnrichmentWorkflow:
    @workflow.run
    async def run(self, payload: dict) -> dict:
        """
        Enrichment workflow: orchestrates fetching text, running LLM enrichment, and persisting structured data.
        Payload keys: run_id, document_id, model
        """
        run_id = payload["run_id"]
        doc_id = payload["document_id"]
        model = payload.get("model", "gpt-3.5-turbo")
        
        # 1. We need the extracted text key from the DB to fetch the text.
        # However, to keep workflows deterministic, we can either pass it in payload or use an activity.
        # Let's create a quick activity to get the extracted_text_key from DB, or we can just pass it in payload from the Service.
        # I didn't pass it in service. Let's pass it in service. 
        # I will modify EnrichmentService to pass extracted_text_key.
        
        extracted_text_key = payload.get("extracted_text_key")
        if not extracted_text_key:
             return {"status": "FAILED", "error": "extracted_text_key missing in payload"}
             
        # 2. Fetch Extracted Text
        fetch_result = await workflow.execute_activity(
            "fetch_extracted_text",
            {"extracted_object_key": extracted_text_key},
            start_to_close_timeout=timedelta(minutes=5),
        )
        
        if not fetch_result["success"]:
            await workflow.execute_activity(
                "update_enrichment_status",
                {
                    "run_id": run_id,
                    "status": RunStatus.FAILED.value,
                    "error_message": fetch_result["error"]
                },
                start_to_close_timeout=timedelta(seconds=30),
            )
            return {"status": "FAILED", "error": fetch_result["error"]}
            
        # 3. Run LLM Enrichment
        enrich_payload = {
            "text": fetch_result["text"],
            "model": model,
            "source_type": payload.get("source_type")
        }
        
        enrich_result = await workflow.execute_activity(
            "run_llm_enrichment",
            enrich_payload,
            start_to_close_timeout=timedelta(minutes=10),
        )
        
        # --- Fallback Logic ---
        should_fallback = not enrich_result["success"]
        if enrich_result["success"]:
            enrichment = enrich_result.get("enrichment", {})
            facts = enrichment.get("facts", [])
            if not facts:
                # No facts extracted from a significant document is a red flag
                should_fallback = True
            else:
                # Check average confidence
                confidences = [f.get("confidence", 0) for f in facts]
                avg_conf = sum(confidences) / len(confidences)
                if avg_conf < 0.6: # Threshold for fallback
                    should_fallback = True
        
        if should_fallback and "gpt" not in model.lower():
            workflow.logger.info(f"Primary model {model} yielded low quality or failed. Falling back to gpt-4o-mini.")
            model = "gpt-4o-mini"
            enrich_payload["model"] = model
            enrich_result = await workflow.execute_activity(
                "run_llm_enrichment",
                enrich_payload,
                start_to_close_timeout=timedelta(minutes=10),
            )

        if not enrich_result["success"]:
            await workflow.execute_activity(
                "update_enrichment_status",
                {
                    "run_id": run_id,
                    "status": RunStatus.FAILED.value,
                    "error_message": enrich_result["error"]
                },
                start_to_close_timeout=timedelta(seconds=30),
            )
            return {"status": "FAILED", "error": enrich_result["error"]}
            
        # 4. Persist Results to DB
        persist_payload = {
            "run_id": run_id,
            "document_id": doc_id,
            "enrichment": enrich_result["enrichment"],
            "model": model
        }
        
        persist_result = await workflow.execute_activity(
            "persist_enrichment_results",
            persist_payload,
            start_to_close_timeout=timedelta(minutes=2),
        )
        
        if not persist_result["success"]:
            await workflow.execute_activity(
                "update_enrichment_status",
                {
                    "run_id": run_id,
                    "status": RunStatus.FAILED.value,
                    "error_message": persist_result["error"]
                },
                start_to_close_timeout=timedelta(seconds=30),
            )
            return {"status": "FAILED", "error": persist_result["error"]}
        
        # 5. Update Status
        await workflow.execute_activity(
            "update_enrichment_status",
            {
                "run_id": run_id,
                "status": RunStatus.COMPLETED.value,
                "prompt_tokens": enrich_result.get("prompt_tokens"),
                "completion_tokens": enrich_result.get("completion_tokens"),
                "total_tokens": enrich_result.get("total_tokens")
            },
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        return {"status": "COMPLETED"}
