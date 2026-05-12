import asyncio
import uuid
from sqlalchemy import select
from apps.api.database import AsyncSessionFactory
from ks.domain.models import DocumentRegistry
from ks.domain.enums import DocumentStatus
from ks.config.settings import get_settings
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy

async def slow_rescue():
    settings = get_settings()
    client = await Client.connect(settings.temporal.address)
    
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(DocumentRegistry).where(DocumentRegistry.status == DocumentStatus.FETCHED)
        )
        docs = result.scalars().all()
        print(f"RELEASE THE FLOODGATES: Feeding {len(docs)} documents into the fully functional pipeline...")
        
        for doc in docs:
            wf_id = f"ingest-doc-{doc.id}"
            try:
                print(f"🚀 Igniting pipeline for: {doc.id}")
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
                print(f"✅ Successfully launched. Buffering for 15 seconds...")
                await asyncio.sleep(15) 
            except Exception as e:
                print(f"❌ Skip failed injection: {e}")

if __name__ == "__main__":
    asyncio.run(slow_rescue())
