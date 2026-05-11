"""Discovery workflows — Temporal workflow definitions for content discovery."""
from datetime import timedelta
from typing import Any

from temporalio import workflow

from ks.domain.enums import RunStatus


@workflow.defn
class DiscoveryWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Discovery workflow: coordinates discovery activities across multiple sources.
        Payload keys: run_id, mode, filter_profile (dict), sources (list of dicts)
        """
        run_id = payload["run_id"]
        mode = payload["mode"]
        filter_profile = payload.get("filter_profile", {})
        sources = payload.get("sources", [])
        
        total_discovered = 0

        async def process_single_source(source: dict) -> int:
            # Internal method to handle a source fully parallelized
            import asyncio
            source_discovered = 0
            try:
                activity_payload = {
                    "source_id": source["id"],
                    "root_url": source["root_url"],
                    "mode": mode,
                    "allow_patterns": source.get("allow_patterns", []),
                    "block_patterns": source.get("block_patterns", []),
                    "max_candidates": filter_profile.get("per_source_limit", 20),
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
                
                # Fire off child ingestion workflows for this source's items concurrently
                child_tasks = []
                for item in persisted_items:
                     task = workflow.start_child_workflow(
                         "DocumentIngestionWorkflow",
                         {
                             "document_id": item["document_id"],
                             "url": item["url"],
                             "force_refresh": False
                         },
                         id=f"ingest-doc-{item['document_id']}",
                     )
                     child_tasks.append(task)
                     
                handles = []
                for t in child_tasks:
                    try:
                        handles.append(await t)
                    except Exception:
                        pass

                if handles:
                    await asyncio.gather(*[h for h in handles], return_exceptions=True)
                
                return source_discovered
            except Exception as e:
                workflow.logger.error(f"Failed source processing for {source.get('root_url')}: {e}")
                return 0

        try:
            import asyncio
            # Run process_single_source for every source simultaneously
            source_results = await asyncio.gather(
                *[process_single_source(source) for source in sources],
                return_exceptions=True
            )
            
            # Sum total valid returns
            for res in source_results:
                if isinstance(res, int):
                    total_discovered += res

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
            "status": RunStatus.COMPLETED.value,
        }
