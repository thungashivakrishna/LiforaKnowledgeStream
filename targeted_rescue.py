import asyncio
import uuid
from sqlalchemy import select
from apps.api.database import AsyncSessionFactory
from ks.domain.models import DocumentRegistry
from ks.config.settings import get_settings
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy

async def targeted_rescue():
    settings = get_settings()
    client = await Client.connect(settings.temporal.address)
    
    async with AsyncSessionFactory() as session:
        # Find specifically the NIH Immune Function document that failed on 'io' before
        result = await session.execute(
            select(DocumentRegistry).where(DocumentRegistry.canonical_url.like('%ImmuneFunction%'))
        )
        doc = result.scalar_one_or_none()
        
        if not doc:
            print("Could not find Immune document. Grabbing first non-encyclopedia FETCHED document...")
            res2 = await session.execute(
                select(DocumentRegistry)
                .where(DocumentRegistry.canonical_url.notin_(['https://medlineplus.gov/ency/encyclopedia_A.htm']))
                .limit(1)
            )
            doc = res2.scalar_one_or_none()

        if doc:
            print(f"🎯 TARGETING VALID DOC: {doc.id} - {doc.canonical_url}")
            wf_id = f"ingest-doc-{doc.id}"
            await client.start_workflow(
                "DocumentIngestionWorkflow",
                {
                    "document_id": str(doc.id),
                    "url": doc.canonical_url,
                    "force_refresh": True
                },
                id=wf_id,
                task_queue=settings.temporal.task_queue,
                id_reuse_policy=WorkflowIDReusePolicy.TERMINATE_IF_RUNNING
            )
            print(f"🚀 Target workflow injected successfully! Monitoring database now...")
        else:
            print("Could not find any suitable candidate to target.")

if __name__ == "__main__":
    asyncio.run(targeted_rescue())
