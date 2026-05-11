import uuid
from datetime import datetime, timezone
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from temporalio import activity

from apps.api.database import AsyncSessionFactory
from ks.domain.enums import RunStatus
from ks.domain.models import FetchRun, ExtractionRun, EnrichmentRun, ChunkRun, GraphRun

logger = logging.getLogger(__name__)

class SystemActivities:
    @activity.defn
    async def prepare_stage_run(self, payload: dict) -> str:
        """
        Creates a database record for the given stage's run entity.
        Payload keys: stage ("fetch", "extraction", "enrichment", "chunk", "graph"), document_id
        Returns: run_id (str)
        """
        stage = payload["stage"]
        doc_id = uuid.UUID(payload["document_id"])
        run_id = uuid.uuid4()
        
        async with AsyncSessionFactory() as session:
            if stage == "fetch":
                run = FetchRun(id=run_id, document_id=doc_id, status=RunStatus.RUNNING, started_at=datetime.now(timezone.utc))
            elif stage == "extraction":
                run = ExtractionRun(id=run_id, document_id=doc_id, status=RunStatus.RUNNING, started_at=datetime.now(timezone.utc))
            elif stage == "enrichment":
                run = EnrichmentRun(id=run_id, document_id=doc_id, status=RunStatus.RUNNING, started_at=datetime.now(timezone.utc))
            elif stage == "chunk":
                run = ChunkRun(id=run_id, document_id=doc_id, status=RunStatus.RUNNING, started_at=datetime.now(timezone.utc))
            elif stage == "graph":
                run = GraphRun(id=run_id, document_id=doc_id, status=RunStatus.RUNNING, started_at=datetime.now(timezone.utc))
            else:
                raise ValueError(f"Unknown stage: {stage}")
            
            session.add(run)
            await session.commit()
            
        return str(run_id)
