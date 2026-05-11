"""Acquisition workflows — Temporal workflow definitions for content acquisition."""
from datetime import timedelta
from typing import Any

from temporalio import workflow

from ks.domain.enums import RunStatus

@workflow.defn
class AcquisitionWorkflow:
    @workflow.run
    async def run(self, payload: dict) -> dict:
        """
        Acquisition workflow: orchestrates fetching and storing a document.
        Payload keys: run_id, document_id, url, force_refresh
        """
        run_id = payload["run_id"]
        doc_id = payload["document_id"]
        url = payload["url"]

        try:
            fetch_result = await workflow.execute_activity(
                "fetch_content",
                {"document_id": doc_id, "url": url},
                start_to_close_timeout=timedelta(minutes=5),
            )

            if not fetch_result["success"]:
                # ... (failure handling stays the same)
                return {"status": RunStatus.FAILED.value, "error": fetch_result["error"]}

            # ── Intelligence Audit ───────────────────────────────────────────────
            audit_result = await workflow.execute_activity(
                "audit_document_intelligence",
                {"content_text": fetch_result["content_text"], "url": url},
                start_to_close_timeout=timedelta(minutes=2),
            )
            
            audit_data = audit_result["audit"]
            if not audit_data["is_high_value"]:
                await workflow.execute_activity(
                    "update_fetch_status",
                    {
                        "run_id": run_id,
                        "document_id": doc_id,
                        "status": RunStatus.FAILED.value,
                        "rejected": True,
                        "error_message": f"Intelligence Audit Rejected: {audit_data['reason']}",
                    },
                    start_to_close_timeout=timedelta(seconds=30),
                )
                return {
                    "status": RunStatus.FAILED.value, 
                    "rejected": True, 
                    "reason": audit_data["reason"],
                    "suggested_links": audit_data.get("suggested_links", [])
                }

            # ── Capture initial facts from audit ────────────────────────────────
            if audit_data.get("initial_facts"):
                await workflow.execute_activity(
                    "persist_audit_facts",
                    {"document_id": doc_id, "facts": audit_data["initial_facts"]},
                    start_to_close_timeout=timedelta(minutes=1),
                )

            object_key = await workflow.execute_activity(
                "store_raw_artifact",
                {
                    "document_id": doc_id,
                    "content_hash": fetch_result["content_hash"],
                    "content_type": fetch_result["content_type"],
                    "content": fetch_result["content"],
                },
                start_to_close_timeout=timedelta(minutes=5),
            )

            await workflow.execute_activity(
                "update_fetch_status",
                {
                    "run_id": run_id,
                    "document_id": doc_id,
                    "status": RunStatus.COMPLETED.value,
                    "version_hash": fetch_result["content_hash"],
                    "object_key": object_key,
                },
                start_to_close_timeout=timedelta(seconds=30),
            )

            return {"status": RunStatus.COMPLETED.value, "object_key": object_key}
        except Exception as exc:
            await workflow.execute_activity(
                "update_fetch_status",
                {
                    "run_id": run_id,
                    "document_id": doc_id,
                    "status": RunStatus.FAILED.value,
                    "error_message": str(exc),
                },
                start_to_close_timeout=timedelta(seconds=30),
            )
            raise
