"""Enrichment service — orchestrates LLM-based knowledge extraction."""
import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ks.enrichment.schemas import EnrichmentRequest
from ks.domain.enums import RunStatus
from ks.domain.models import DocumentRegistry, EnrichmentRun


class EnrichmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start_enrichment(self, data: EnrichmentRequest) -> EnrichmentRun:
        from ks.domain.models import SourceRegistry
        from sqlalchemy.orm import joinedload
        
        # 1. Verify document exists and get source details
        result = await self.session.execute(
            select(DocumentRegistry)
            .options(joinedload(DocumentRegistry.source))
            .where(DocumentRegistry.id == data.document_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document {data.document_id} not found")
            
        source_type = doc.source.source_type.value if doc.source else "GENERAL_HEALTH"
            
        if not doc.extracted_text_key:
            raise ValueError(f"Document {data.document_id} has no extracted text available. Please run Extraction first.")

        # 2. Check if already enriched and not forcing refresh
        if not data.force_refresh:
            res = await self.session.execute(
                select(EnrichmentRun)
                .where(EnrichmentRun.document_id == data.document_id)
                .where(EnrichmentRun.status == RunStatus.COMPLETED)
            )
            existing = res.scalars().first()
            if existing:
                raise ValueError(f"Document {data.document_id} already enriched. Use force_refresh=True to re-enrich.")

        # 3. Create EnrichmentRun record
        run = EnrichmentRun(
            id=uuid.uuid4(),
            document_id=data.document_id,
            status=RunStatus.PENDING,
            model_used=data.model
        )
        self.session.add(run)
        await self.session.flush()

        # 4. Trigger Temporal workflow
        await self._trigger_enrichment_workflow(run, doc.extracted_text_key, data, source_type)

        return run

    async def _trigger_enrichment_workflow(self, run: EnrichmentRun, extracted_text_key: str, data: EnrichmentRequest, source_type: str):
        from temporalio.client import Client
        from ks.config.settings import get_settings
        
        settings = get_settings()
        client = await Client.connect(settings.temporal.address)
        
        payload = {
            "run_id": str(run.id),
            "document_id": str(run.document_id),
            "extracted_text_key": extracted_text_key,
            "model": data.model,
            "source_type": source_type
        }
        
        await client.start_workflow(
            "EnrichmentWorkflow",
            payload,
            id=f"enrichment-run-{run.id}",
            task_queue=settings.temporal.task_queue,
        )

    async def get_enrichment_run(self, run_id: uuid.UUID) -> EnrichmentRun:
        result = await self.session.execute(
            select(EnrichmentRun).where(EnrichmentRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"Enrichment run {run_id} not found")
        return run

    async def list_enrichment_runs(self, limit: int = 50, offset: int = 0) -> tuple[list[EnrichmentRun], int]:
        q = select(EnrichmentRun).order_by(EnrichmentRun.started_at.desc().nulls_last())
        count_q = select(func.count()).select_from(EnrichmentRun)
        
        total = (await self.session.execute(count_q)).scalar_one()
        result = await self.session.execute(q.offset(offset).limit(limit))
        
        return list(result.scalars().all()), total
