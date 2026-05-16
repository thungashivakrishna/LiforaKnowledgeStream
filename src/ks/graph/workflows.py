"""Graph workflows — Temporal workflow definitions for graph synchronization."""
from datetime import timedelta
from typing import Any

from temporalio import workflow

from ks.domain.enums import RunStatus

with workflow.unsafe.imports_passed_through():
    from ks.graph.activities import GraphActivities


@workflow.defn
class GraphSyncWorkflow:
    @workflow.run
    async def run(self, payload: dict) -> dict:
        """
        Graph sync workflow: orchestrates fetching data and pushing to Neo4j.
        Payload keys: run_id, document_id
        """
        run_id = payload["run_id"]
        doc_id = payload["document_id"]

        # 0. Initialize Schema (Idempotent)
        await workflow.execute_activity(
            "initialize_graph_schema",
            start_to_close_timeout=timedelta(minutes=1),
        )
        
        # 1. Fetch Graph Data
        fetch_result = await workflow.execute_activity(
            "fetch_graph_data",
            {"document_id": doc_id},
            start_to_close_timeout=timedelta(minutes=2),
        )
        if not fetch_result["success"]:
            return await self._fail_workflow(run_id, fetch_result["error"])
            
        # 2. Sync to Neo4j
        sync_result = await workflow.execute_activity(
            "sync_to_neo4j",
            {"data": fetch_result["data"]},
            start_to_close_timeout=timedelta(minutes=5),
        )
        if not sync_result["success"]:
            return await self._fail_workflow(run_id, sync_result["error"])
            
        # 3. Update Status
        await workflow.execute_activity(
            "update_graph_status",
            {
                "run_id": run_id,
                "status": RunStatus.COMPLETED.value,
                "nodes_created": sync_result["nodes_created"],
                "edges_created": sync_result["edges_created"]
            },
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        return {
            "status": "COMPLETED", 
            "nodes_created": sync_result["nodes_created"],
            "edges_created": sync_result["edges_created"]
        }
        
    async def _fail_workflow(self, run_id: str, error_msg: str) -> dict:
        await workflow.execute_activity(
            "update_graph_status",
            {
                "run_id": run_id,
                "status": RunStatus.FAILED.value,
                "error_message": error_msg
            },
            start_to_close_timeout=timedelta(seconds=30),
        )
        return {"status": "FAILED", "error": error_msg}
