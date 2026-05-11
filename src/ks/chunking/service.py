"""Chunking service — orchestrates chunking text and generating embeddings."""
import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ks.chunking.schemas import ChunkingRequest
from ks.domain.enums import RunStatus
from ks.domain.models import DocumentRegistry, ChunkRun


class ChunkingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start_chunking(self, data: ChunkingRequest) -> ChunkRun:
        # 1. Verify document exists
        result = await self.session.execute(
            select(DocumentRegistry).where(DocumentRegistry.id == data.document_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document {data.document_id} not found")
            
        if not doc.extracted_text_key:
            raise ValueError(f"Document {data.document_id} has no extracted text available. Please run Extraction first.")

        # 2. Check if already chunked and not forcing refresh
        if not data.force_refresh:
            res = await self.session.execute(
                select(ChunkRun)
                .where(ChunkRun.document_id == data.document_id)
                .where(ChunkRun.status == RunStatus.COMPLETED)
            )
            existing = res.scalars().first()
            if existing:
                raise ValueError(f"Document {data.document_id} already chunked. Use force_refresh=True to re-chunk.")

        # 3. Create ChunkRun record
        run = ChunkRun(
            id=uuid.uuid4(),
            document_id=data.document_id,
            status=RunStatus.PENDING,
            embedding_model=data.embedding_model
        )
        self.session.add(run)
        await self.session.flush()

        # 4. Trigger Temporal workflow
        await self._trigger_chunking_workflow(run, doc.extracted_text_key, data)

        return run

    async def _trigger_chunking_workflow(self, run: ChunkRun, extracted_text_key: str, data: ChunkingRequest):
        from temporalio.client import Client
        from ks.config.settings import get_settings
        
        settings = get_settings()
        client = await Client.connect(settings.temporal.address)
        
        payload = {
            "run_id": str(run.id),
            "document_id": str(run.document_id),
            "extracted_text_key": extracted_text_key,
            "embedding_model": data.embedding_model
        }
        
        await client.start_workflow(
            "ChunkingWorkflow",
            payload,
            id=f"chunking-run-{run.id}",
            task_queue=settings.temporal.task_queue,
        )

    async def get_chunk_run(self, run_id: uuid.UUID) -> ChunkRun:
        result = await self.session.execute(
            select(ChunkRun).where(ChunkRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"Chunk run {run_id} not found")
        return run

    async def list_chunk_runs(self, limit: int = 50, offset: int = 0) -> tuple[list[ChunkRun], int]:
        q = select(ChunkRun).order_by(ChunkRun.started_at.desc().nulls_last())
        count_q = select(func.count()).select_from(ChunkRun)
        
        total = (await self.session.execute(count_q)).scalar_one()
        result = await self.session.execute(q.offset(offset).limit(limit))
        
        return list(result.scalars().all()), total
