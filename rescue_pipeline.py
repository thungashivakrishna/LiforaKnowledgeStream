import asyncio
import uuid
from sqlalchemy import select
from temporalio.client import Client

from apps.api.database import AsyncSessionFactory
from ks.domain.models import DocumentRegistry
from ks.domain.enums import DocumentStatus
from ks.config.settings import get_settings

from temporalio.common import WorkflowIDReusePolicy

async def rescue():
    settings = get_settings()
    client = await Client.connect(settings.temporal.address)
    
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(DocumentRegistry).where(DocumentRegistry.status == DocumentStatus.FETCHED)
        )
        docs = result.scalars().all()
        print(f"Rescuing {len(docs)} documents with FORCE OVERRIDE...")
        
        for doc in docs:
            wf_id = f"ingest-doc-{doc.id}"
            try:
                # Force start it, overriding any currently hung iteration!
                await client.start_workflow(
                    "DocumentIngestionWorkflow",
                    {
                        "document_id": str(doc.id),
                        "url": doc.canonical_url,
                        "force_refresh": False
                    },
                    id=wf_id,
                    task_queue=settings.temporal.task_queue,
                    id_reuse_policy=WorkflowIDReusePolicy.TERMINATE_IF_RUNNING
                )
                print(f"FORCED RESTART for workflow: {wf_id}")
            except Exception as e:
                print(f"Failed to start {wf_id}: {e}")

if __name__ == "__main__":
    asyncio.run(rescue())
