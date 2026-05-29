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
        
        # Establish explicit Multi-Step Hierarchy: 
        # 1. Provided by payload -> 2. Default to DeepSeek -> 3. Fallback if needed to GPT.
        model = payload.get("model", "deepseek/deepseek-chat")
        
        extracted_text_key = payload.get("extracted_text_key")
        if not extracted_text_key:
             return {"status": "FAILED", "error": "extracted_text_key missing in payload"}
             
        # No longer need to fetch full text into workflow history! 
        # We stream it directly inside the activities.
            
        # 3. Detect Relevant Frameworks dynamically (using fast model)
        detect_result = await workflow.execute_activity(
            "detect_relevant_frameworks",
            {"extracted_text_key": extracted_text_key, "model": "gpt-4o-mini"},
            start_to_close_timeout=timedelta(minutes=2),
        )
        detected = detect_result.get("frameworks", ["PREVENTIVE_MEDICINE"])
        
        # 3.5 Dynamic Evidence & Study Design Audit
        audit_result = await workflow.execute_activity(
            "audit_clinical_evidence",
            {
                "extracted_text_key": extracted_text_key,
                "document_id": str(doc_id),
                "run_id": str(run_id)
            },
            start_to_close_timeout=timedelta(minutes=2),
        )
        evidence_grade = audit_result.get("evidence_grade", "GRADE_D")
        study_type = audit_result.get("study_type", "Unclassified Study")
        methodology_critique = audit_result.get("methodology_critique", "")
        
        # User Override: Filter framework execution by explicit user input scope
        framework_scope = payload.get("framework_scope", [])
        if framework_scope and isinstance(framework_scope, list) and len(framework_scope) > 0:
            # Intersect detected frameworks with scope, or just force scope if desired
            # To obey the user specifically: just set to scope.
            frameworks = [fw for fw in framework_scope if fw]
            workflow.logger.info(f"🔒 Restricting agents to USER SCOPE: {frameworks}")
        else:
            frameworks = detected
            workflow.logger.info(f"🔓 identified frameworks for parallel agents: {frameworks}")

        # 4. Run Parallel Multi-Perspective Extraction Agents with Robust Fallback
        import asyncio
        
        async def run_agent_for_framework(fw: str):
            p = {
                "extracted_text_key": extracted_text_key,
                "model": model, # Begins with DeepSeek
                "source_type": payload.get("source_type"),
                "framework": fw
            }
            
            workflow.logger.info(f"Agent {fw} starting with primary model: {model}")
            res = await workflow.execute_activity(
                "run_llm_enrichment",
                p,
                start_to_close_timeout=timedelta(minutes=10),
            )
            
            # Validation & Fallback Routine
            should_fallback = not res.get("success", False)
            
            if not should_fallback:
                enrichment = res.get("enrichment", {})
                facts = enrichment.get("facts", [])
                if not facts:
                    should_fallback = True
                else:
                    # Calculate confidence score
                    confidences = [f.get("confidence", 0) for f in facts]
                    avg_conf = sum(confidences) / len(confidences)
                    if avg_conf < 0.5: # Threshold logic
                        workflow.logger.info(f"Low confidence ({avg_conf}) detected for framework {fw}. Initiating fallback.")
                        should_fallback = True
            
            # Critical Path Fallback Mechanism
            if should_fallback and "gpt" not in model.lower():
                workflow.logger.warn(f"Agent {fw} primary failed or low confidence. Falling back to gpt-4o-mini.")
                p["model"] = "gpt-4o-mini"
                res = await workflow.execute_activity(
                    "run_llm_enrichment",
                    p,
                    start_to_close_timeout=timedelta(minutes=10),
                )
                
            return fw, res

        # Run multi-perspective extraction agents sequentially to reduce deadlock starvation risk
        agent_results = []
        for fw in frameworks:
            try:
                res = await run_agent_for_framework(fw)
                agent_results.append(res)
            except Exception as e:
                workflow.logger.error(f"Framework agent {fw} crashed: {e}")
                agent_results.append((fw, {"success": False, "error": str(e)}))
        
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
            "model": model, # Store the actual model identifier for dashboard metrics
            "evidence_grade": evidence_grade,
            "study_type": study_type,
            "methodology_critique": methodology_critique
        }
        
        # 5.5 Multi-Model Verification (Critic)
        # Fetch the full text for the critic to review
        text_result = await workflow.execute_activity(
            "fetch_extracted_text",
            {"extracted_object_key": extracted_text_key},
            start_to_close_timeout=timedelta(minutes=2),
        )
        
        if text_result.get("success"):
            verify_result = await workflow.execute_activity(
                "verify_extraction_activity",
                {
                    "facts": merged_enrichment.get("facts", []),
                    "source_text": text_result["text"]
                },
                start_to_close_timeout=timedelta(minutes=5),
            )
            if verify_result.get("success"):
                persist_payload["verification_report"] = verify_result.get("report", [])
        
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
                "model_used": model, # Propagate final model (includes fallback if it happened)
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_tokens
            },
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        return {"status": "COMPLETED"}
