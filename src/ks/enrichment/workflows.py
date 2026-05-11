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
            
        # 3. Detect Relevant Frameworks dynamically
        detect_result = await workflow.execute_activity(
            "detect_relevant_frameworks",
            {"text": fetch_result["text"], "model": "gpt-3.5-turbo"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        frameworks = detect_result.get("frameworks", ["PREVENTIVE_MEDICINE"])
        workflow.logger.info(f"Identified frameworks for agents: {frameworks}")

        # 4. Run Parallel Multi-Perspective Extraction Agents
        import asyncio
        
        async def run_agent_for_framework(fw: str):
            p = {
                "text": fetch_result["text"],
                "model": model,
                "source_type": payload.get("source_type"),
                "framework": fw
            }
            res = await workflow.execute_activity(
                "run_llm_enrichment",
                p,
                start_to_close_timeout=timedelta(minutes=10),
            )
            return fw, res

        agent_tasks = [run_agent_for_framework(fw) for fw in frameworks]
        agent_results = await asyncio.gather(*agent_tasks, return_exceptions=True)
        
        # 5. Intelligently Merge Parallel Knowledge
        merged_enrichment = {
            "summary": "",
            "primary_framework": frameworks[0],
            "secondary_frameworks": frameworks[1:],
            "topics": [],
            "conditions": [],
            "symptoms": [],
            "interventions": [],
            "nutrients": [],
            "populations": [],
            "facts": []
        }
        
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tokens = 0
        success_count = 0
        
        for fw, res in agent_results:
            if isinstance(res, dict) and res.get("success"):
                success_count += 1
                data = res.get("enrichment", {})
                
                # Set summary from primary agent if empty
                if not merged_enrichment["summary"]:
                     merged_enrichment["summary"] = data.get("summary", "")
                
                # Append array values with de-duplication where possible
                for key in ["topics", "conditions", "symptoms", "interventions", "nutrients", "populations"]:
                     vals = data.get(key, [])
                     if isinstance(vals, list):
                         merged_enrichment[key].extend(vals)
                         merged_enrichment[key] = list(set(merged_enrichment[key])) # Deduplicate strings
                
                # Merge Facts tagged with Framework Origin
                facts = data.get("facts", [])
                if isinstance(facts, list):
                    for f in facts:
                         # Enhance fact record with perspective tag
                         f["fact_text"] = f"[{fw}] {f.get('fact_text', '')}"
                         merged_enrichment["facts"].append(f)
                         
                total_prompt_tokens += res.get("prompt_tokens", 0)
                total_completion_tokens += res.get("completion_tokens", 0)
                total_tokens += res.get("total_tokens", 0)

        if success_count == 0:
            await workflow.execute_activity(
                "update_enrichment_status",
                {
                    "run_id": run_id,
                    "status": RunStatus.FAILED.value,
                    "error_message": "All parallel agents failed to enrich content."
                },
                start_to_close_timeout=timedelta(seconds=30),
            )
            return {"status": "FAILED", "error": "All parallel agents failed"}
            
        # 6. Persist Merged Unified Knowledge to DB
        persist_payload = {
            "run_id": run_id,
            "document_id": doc_id,
            "enrichment": merged_enrichment,
            "model": f"Multi-Agent ({model})"
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
        
        # 7. Finalize Unified Stream Metrics
        await workflow.execute_activity(
            "update_enrichment_status",
            {
                "run_id": run_id,
                "status": RunStatus.COMPLETED.value,
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_tokens
            },
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        return {"status": "COMPLETED"}
