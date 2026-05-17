"""Discovery workflows — Temporal workflow definitions for content discovery."""
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.workflow import ParentClosePolicy
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
            tasks = []
            
            async def run_intent_driven():
                nonlocal total_discovered, extracted_count, queued_count
                workflow.logger.info(f"🚀 Intent-Driven Discovery initiated for topics: {topics}")
                
                # If sources are provided, restrict the search to those domains
                domains = []
                from urllib.parse import urlparse
                for s in payload.get("sources", []):
                    domains.append(urlparse(s["root_url"]).netloc)
                
                query = " ".join(topics)
                search_payload = {
                    "query": query,
                    "limit": max_candidates,
                    "domains": domains
                }
                
                search_results = await workflow.execute_activity(
                    "perform_targeted_search",
                    search_payload,
                    start_to_close_timeout=timedelta(minutes=2)
                )
                
                workflow.logger.info(f"🔎 Search returned {len(search_results)} candidates.")
                
                for result in search_results:
                    url = result.get("url")
                    snippet = result.get("snippet", "")
                    
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
                        
                    import datetime
                    
                    persist_payload = {
                        "run_id": str(run_id),
                        "source_id": "e792934e-0d46-4f65-870f-008e74ae1812", 
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
                    
                    if action == "EXTRACT" or priority_score >= 85:
                        crawl_payload = {
                            "url": url,
                            "max_depth": 2 if trust_score > 0.8 else 1,
                            "max_pages": 10
                        }
                        crawl_results = await workflow.execute_activity(
                            "perform_deep_crawl",
                            crawl_payload,
                            start_to_close_timeout=timedelta(minutes=10)
                        )
                        workflow.logger.info(f"🕷️ Deep crawl around {url} found {len(crawl_results)} related links.")
                        
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
                                parent_close_policy=ParentClosePolicy.ABANDON,
                            )
                            extracted_count += 1
                        except Exception as start_err:
                            workflow.logger.warning(f"Could not start child workflow for {url}: {start_err}")
                    
                    elif action == "QUEUE":
                        queued_count += 1

            async def run_source_discovery():
                nonlocal total_discovered, extracted_count
                sources = payload.get("sources", [])
                workflow.logger.info(f"🚀 Generic Source Discovery initiated for {len(sources)} sources.")
                
                async def process_single_source(source: dict) -> int:
                    import asyncio
                    source_discovered = 0
                    try:
                        activity_payload = {
                            "source_id": source["id"],
                            "root_url": source["root_url"],
                            "mode": payload.get("mode", 1),
                            "allow_patterns": source.get("allow_patterns", []),
                            "block_patterns": source.get("block_patterns", []),
                            "max_candidates": payload.get("filter_profile", {}).get("per_source_limit", 20),
                            "topics": topics,
                        }

                        candidates = await workflow.execute_activity(
                            "discover_candidates",
                            activity_payload,
                            start_to_close_timeout=timedelta(minutes=5),
                        )

                        if not candidates:
                            return 0

                        persist_payload = {
                            "run_id": run_id,
                            "source_id": source["id"],
                            "candidates": candidates,
                        }

                        persisted_items = await workflow.execute_activity(
                            "persist_candidates",
                            persist_payload,
                            start_to_close_timeout=timedelta(minutes=2),
                        )
                        source_discovered = len(persisted_items)
                        
                        child_tasks = []
                        for item in persisted_items:
                             task = workflow.start_child_workflow(
                                 "DocumentIngestionWorkflow",
                                 {
                                     "document_id": item["document_id"],
                                     "url": item["url"],
                                     "force_refresh": False,
                                     "framework_scope": frameworks,
                                     "targeted_keywords": topics
                                 },
                                 id=f"ingest-doc-{item['document_id']}",
                                 parent_close_policy=ParentClosePolicy.ABANDON,
                             )
                             child_tasks.append(task)
                             
                        # Fire and forget: await the start of each child workflow, but do NOT wait for completion
                        for t in child_tasks:
                            try:
                                await t
                            except Exception as e:
                                workflow.logger.warning(f"Failed to initiate child ingestion: {e}")

                        return source_discovered
                    except Exception as e:
                        workflow.logger.error(f"Failed source processing for {source.get('root_url')}: {e}")
                        return 0

                import asyncio
                source_results = await asyncio.gather(
                    *[process_single_source(source) for source in sources],
                    return_exceptions=True
                )
                
                for res in source_results:
                    if isinstance(res, int):
                        total_discovered += res
                        extracted_count += res

            # Determine execution path based on selected inputs
            has_topics = bool(topics)
            has_sources = bool(payload.get("sources", []))
            
            import asyncio
            execution_tasks = []
            
            if has_topics:
                execution_tasks.append(run_intent_driven())
                
            if has_sources:
                execution_tasks.append(run_source_discovery())
                
            if execution_tasks:
                await asyncio.gather(*execution_tasks)
                
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
