"""Extraction service — orchestrates text extraction and parsing."""
import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ks.extraction.schemas import ExtractionRequest
from ks.domain.enums import RunStatus
from ks.domain.models import DocumentRegistry, DocumentVersion, ExtractionRun


class ExtractionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start_extraction(self, data: ExtractionRequest) -> ExtractionRun:
        # 1. Verify document exists
        result = await self.session.execute(
            select(DocumentRegistry).where(DocumentRegistry.id == data.document_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document {data.document_id} not found")
            
        # 2. Check if raw artifact exists (DocumentVersion)
        v_result = await self.session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == data.document_id)
            .order_by(DocumentVersion.fetched_at.desc())
        )
        version = v_result.scalars().first()
        if not version or not version.raw_object_key:
            raise ValueError(f"No raw artifact found for Document {data.document_id}. Please fetch first.")

        # 3. Check if already extracted and not forcing refresh
        if not data.force_refresh:
            res = await self.session.execute(
                select(ExtractionRun)
                .where(ExtractionRun.document_id == data.document_id)
                .where(ExtractionRun.status == RunStatus.COMPLETED)
            )
            existing = res.scalars().first()
            if existing:
                raise ValueError(f"Document {data.document_id} already extracted. Use force_refresh=True to re-extract.")

        # 4. Create ExtractionRun record
        run = ExtractionRun(
            id=uuid.uuid4(),
            document_id=data.document_id,
            status=RunStatus.PENDING,
        )
        self.session.add(run)
        await self.session.flush()

        # 5. Trigger Temporal workflow
        await self._trigger_extraction_workflow(run, version.raw_object_key, data)

        return run

    async def _trigger_extraction_workflow(self, run: ExtractionRun, raw_object_key: str, data: ExtractionRequest):
        from temporalio.client import Client
        from ks.config.settings import get_settings
        
        settings = get_settings()
        client = await Client.connect(settings.temporal.address)
        
        payload = {
            "run_id": str(run.id),
            "document_id": str(run.document_id),
            "raw_object_key": raw_object_key,
            "use_ocr": data.use_ocr,
            "use_llm": data.use_llm
        }
        
        await client.start_workflow(
            "ExtractionWorkflow",
            payload,
            id=f"extraction-run-{run.id}",
            task_queue=settings.temporal.task_queue,
        )

    async def get_extraction_run(self, run_id: uuid.UUID) -> ExtractionRun:
        result = await self.session.execute(
            select(ExtractionRun).where(ExtractionRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"Extraction run {run_id} not found")
        return run

    async def list_extraction_runs(self, limit: int = 50, offset: int = 0) -> tuple[list[ExtractionRun], int]:
        q = select(ExtractionRun).order_by(ExtractionRun.started_at.desc().nulls_last())
        count_q = select(func.count()).select_from(ExtractionRun)
        
        total = (await self.session.execute(count_q)).scalar_one()
        result = await self.session.execute(q.offset(offset).limit(limit))
        
        return list(result.scalars().all()), total
