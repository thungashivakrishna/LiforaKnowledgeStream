"""Acquisition service — orchestrates fetching and storing document content."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ks.acquisition.schemas import FetchRequest
from ks.domain.enums import RunStatus
from ks.domain.models import DocumentRegistry, FetchRun


class AcquisitionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start_fetch(self, data: FetchRequest) -> FetchRun:
        # 1. Verify document exists
        result = await self.session.execute(
            select(DocumentRegistry).where(DocumentRegistry.id == data.document_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document {data.document_id} not found")

        # 2. Check if already fetched and not forcing refresh
        if not data.force_refresh:
            res = await self.session.execute(
                select(FetchRun)
                .where(FetchRun.document_id == data.document_id)
                .where(FetchRun.status == RunStatus.COMPLETED)
            )
            existing = res.scalars().first()
            if existing:
                raise ValueError(f"Document {data.document_id} already fetched. Use force_refresh=True to refetch.")

        # 3. Create FetchRun record
        run = FetchRun(
            id=uuid.uuid4(),
            document_id=data.document_id,
            status=RunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        await self.session.flush()

        # 4. Trigger Temporal workflow
        await self._trigger_acquisition_workflow(run, doc.canonical_url, data.force_refresh)

        return run

    async def _trigger_acquisition_workflow(self, run: FetchRun, url: str, force_refresh: bool):
        from temporalio.client import Client
        from ks.config.settings import get_settings
        
        settings = get_settings()
        client = await Client.connect(settings.temporal.address)
        
        payload = {
            "run_id": str(run.id),
            "document_id": str(run.document_id),
            "url": url,
            "force_refresh": force_refresh
        }
        
        await client.start_workflow(
            "AcquisitionWorkflow",
            payload,
            id=f"acquisition-run-{run.id}",
            task_queue=settings.temporal.task_queue,
        )

    async def get_fetch_run(self, run_id: uuid.UUID) -> FetchRun:
        result = await self.session.execute(
            select(FetchRun).where(FetchRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"Fetch run {run_id} not found")
        return run

    async def list_fetch_runs(self, limit: int = 50, offset: int = 0) -> tuple[list[FetchRun], int]:
        q = select(FetchRun).order_by(FetchRun.started_at.desc().nulls_last())
        count_q = select(func.count()).select_from(FetchRun)
        
        total = (await self.session.execute(count_q)).scalar_one()
        result = await self.session.execute(q.offset(offset).limit(limit))
        
        return list(result.scalars().all()), total
