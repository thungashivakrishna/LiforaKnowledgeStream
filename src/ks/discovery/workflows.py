"""Discovery workflows — Temporal workflow definitions for content discovery."""
from datetime import timedelta
from typing import Any

from temporalio import workflow
with workflow.unsafe.imports_passed_through():
    import asyncio

from ks.domain.enums import RunStatus


@workflow.defn
class DiscoveryWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Intent-Driven Discovery Workflow: implements the 10-step intelligent funnel.
        Payload keys: run_id, topics, filter_profile (dict), frameworks, max_candidates
        """
        run_id = payload["run_id"]
        topics = payload.get("topics", [])
        frameworks = payload.get("frameworks", [])
        max_candidates = payload.get("max_candidates", 50)
        
        total_discovered = 0
        extracted_count = 0
        queued_count = 0
        
        workflow.logger.info(f"🚀 Intent-Driven Discovery initiated for topics: {topics}")
        
        try:
            # 1 & 2 & 3. Intent-Driven Search
            query = " ".join(topics)
            search_payload = {
                "query": query,
                "limit": max_candidates
            }
            
            search_results = await workflow.execute_activity(
                "perform_targeted_search",
                search_payload,
                start_to_close_timeout=timedelta(minutes=2)
            )
            
            workflow.logger.info(f"🔎 Search returned {len(search_results)} candidates.")
            
            # Process each search result
            for result in search_results:
                url = result.get("url")
                snippet = result.get("snippet", "")
                
                # 4. Source Scoring (Bouncer)
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
                
                auth_payload = {"domain": domain, "snippet": snippet}
                auth_eval = await workflow.execute_activity(
                    "evaluate_source_authority",
                    auth_payload,
                    start_to_close_timeout=timedelta(minutes=1)
                )
                
                if not auth_eval.get("success") or not auth_eval.get("evaluation", {}).get("is_reputable"):
                    workflow.logger.info(f"🛑 Rejecting domain {domain} due to low authority.")
                    continue
                    
                trust_score = auth_eval.get("evaluation", {}).get("trust_score", 1.0)
                
                # 5 & 6. Metadata Fetch & Priority Scoring
                metadata = await workflow.execute_activity(
                    "fetch_page_metadata",
                    url,
                    start_to_close_timeout=timedelta(minutes=1)
                )
                
                score_payload = {
                    "url": url,
                    "metadata": metadata,
                    "topics": topics,
                    "source_trust_score": trust_score
                }
                
                score_eval = await workflow.execute_activity(
                    "calculate_priority_score",
                    score_payload,
                    start_to_close_timeout=timedelta(minutes=2)
                )
                
                if not score_eval.get("success"):
                    continue
                    
                score_data = score_eval.get("score_data", {})
                priority_score = score_data.get("overall_priority_score", 0)
                action = score_data.get("recommended_action", "REJECT")
                
                workflow.logger.info(f"📊 Scored {url}: {priority_score} -> Action: {action}")
                
                if action == "REJECT" or priority_score < 40:
                    continue
                    
                # Store candidate in registry
                import datetime
                
                persist_payload = {
                    "run_id": str(run_id),
                    "source_id": "e792934e-0d46-4f65-870f-008e74ae1812", # PubMed Central as default open-web/intent source
                    "candidates": [
                        {
                            "url": url,
                            "title": metadata.get("title", url),
                            "score": min(priority_score / 100.0, 0.99),
                            "discovered_at": workflow.now().isoformat()
                        }
                    ]
                }
                
                persisted_docs = await workflow.execute_activity(
                    "persist_candidates",
                    persist_payload,
                    start_to_close_timeout=timedelta(minutes=1)
                )
                
                if persisted_docs:
                    total_discovered += 1
                
                # 7 & 8 & 9. Queueing, Deep Crawling, and Extraction
                if action == "EXTRACT" or priority_score >= 85:
                    # Spawn Deep Crawl around high-value document
                    crawl_payload = {
                        "url": url,
                        "max_depth": 2 if trust_score > 0.8 else 1,
                        "max_pages": 10
                    }
                    # We fire-and-forget the crawl here or process sequentially.
                    # For stability in Temporal, we await it.
                    crawl_results = await workflow.execute_activity(
                        "perform_deep_crawl",
                        crawl_payload,
                        start_to_close_timeout=timedelta(minutes=10)
                    )
                    workflow.logger.info(f"🕷️ Deep crawl around {url} found {len(crawl_results)} related links.")
                    
                    # Spawn DocumentIngestionWorkflow (Fire and forget, track by ID)
                    import uuid
                    doc_id = str(workflow.uuid4())
                    try:
                        await workflow.start_child_workflow(
                            "DocumentIngestionWorkflow",
                            {
                                "document_id": doc_id,
                                "url": url,
                                "force_refresh": False,
                                "framework_scope": frameworks,
                                "targeted_keywords": topics
                            },
                            id=f"ingest-doc-{doc_id}",
                        )
                        extracted_count += 1
                    except Exception as start_err:
                        workflow.logger.warning(f"Could not start child workflow for {url}: {start_err}")
                
                elif action == "QUEUE":
                    queued_count += 1
                    # In a real DB, it remains in QUEUED_FOR_EXTRACTION.
            
            # 10. Finalize
            await workflow.execute_activity(
                "finalize_discovery_run",
                {
                    "run_id": run_id,
                    "status": RunStatus.COMPLETED.value,
                    "candidate_count": total_discovered,
                },
                start_to_close_timeout=timedelta(seconds=30),
            )
            
        except Exception as exc:
            workflow.logger.error(f"Discovery workflow failed: {exc}")
            await workflow.execute_activity(
                "finalize_discovery_run",
                {
                    "run_id": run_id,
                    "status": RunStatus.FAILED.value,
                    "candidate_count": total_discovered,
                    "error_message": str(exc),
                },
                start_to_close_timeout=timedelta(seconds=30),
            )
            raise

        return {
            "run_id": run_id,
            "total_discovered": total_discovered,
            "extracted": extracted_count,
            "queued": queued_count,
            "status": RunStatus.COMPLETED.value,
        }
