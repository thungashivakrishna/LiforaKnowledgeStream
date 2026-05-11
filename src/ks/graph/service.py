"""Graph service — orchestrates syncing relational knowledge to Neo4j."""
import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ks.graph.schemas import GraphSyncRequest
from ks.domain.enums import RunStatus
from ks.domain.models import DocumentRegistry, GraphRun


class GraphService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start_graph_sync(self, data: GraphSyncRequest) -> GraphRun:
        # 1. Verify document exists
        result = await self.session.execute(
            select(DocumentRegistry).where(DocumentRegistry.id == data.document_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document {data.document_id} not found")

        # 2. Check if already synced and not forcing refresh
        if not data.force_refresh:
            res = await self.session.execute(
                select(GraphRun)
                .where(GraphRun.document_id == data.document_id)
                .where(GraphRun.status == RunStatus.COMPLETED)
            )
            existing = res.scalars().first()
            if existing:
                raise ValueError(f"Document {data.document_id} already synced to graph. Use force_refresh=True to re-sync.")

        # 3. Create GraphRun record
        run = GraphRun(
            id=uuid.uuid4(),
            document_id=data.document_id,
            status=RunStatus.PENDING
        )
        self.session.add(run)
        await self.session.flush()

        # 4. Trigger Temporal workflow
        await self._trigger_graph_workflow(run, data)

        return run

    async def _trigger_graph_workflow(self, run: GraphRun, data: GraphSyncRequest):
        from temporalio.client import Client
        from ks.config.settings import get_settings
        
        settings = get_settings()
        client = await Client.connect(settings.temporal.address)
        
        payload = {
            "run_id": str(run.id),
            "document_id": str(run.document_id)
        }
        
        await client.start_workflow(
            "GraphSyncWorkflow",
            payload,
            id=f"graph-sync-run-{run.id}",
            task_queue=settings.temporal.task_queue,
        )

    async def get_graph_run(self, run_id: uuid.UUID) -> GraphRun:
        result = await self.session.execute(
            select(GraphRun).where(GraphRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"Graph sync run {run_id} not found")
        return run

    async def list_graph_runs(self, limit: int = 50, offset: int = 0) -> tuple[list[GraphRun], int]:
        q = select(GraphRun).order_by(GraphRun.started_at.desc().nulls_last())
        count_q = select(func.count()).select_from(GraphRun)
        
        total = (await self.session.execute(count_q)).scalar_one()
        result = await self.session.execute(q.offset(offset).limit(limit))
        
        return list(result.scalars().all()), total
