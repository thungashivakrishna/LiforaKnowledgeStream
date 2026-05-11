"""Discovery service — orchestrates candidate document discovery."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ks.discovery.schemas import (
    DiscoveryFilterProfileRequest,
    DiscoveryRunRequest,
)
from ks.domain.enums import RunStatus, SourceApprovalStatus
from ks.domain.models import (
    CandidateDiscoveryRun,
    CandidateDocumentEvaluation,
    DiscoveryFilterProfile,
    SourceRegistry,
)


class DiscoveryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Filter Profiles ───────────────────────────────────────────────────────

    async def create_filter_profile(self, data: DiscoveryFilterProfileRequest) -> DiscoveryFilterProfile:
        profile = DiscoveryFilterProfile(
            id=uuid.uuid4(),
            name=data.name,
            mode=data.mode,
            topics=data.topics,
            synonyms=data.synonyms,
            frameworks=data.frameworks,
            max_candidates=data.max_candidates,
            per_source_limit=data.per_source_limit,
            reference_context=data.reference_context,
        )
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def list_filter_profiles(self) -> list[DiscoveryFilterProfile]:
        result = await self.session.execute(
            select(DiscoveryFilterProfile).order_by(DiscoveryFilterProfile.created_at.desc())
        )
        return list(result.scalars().all())

    # ── Discovery Runs ────────────────────────────────────────────────────────

    async def create_run(self, data: DiscoveryRunRequest) -> CandidateDiscoveryRun:
        run = CandidateDiscoveryRun(
            id=uuid.uuid4(),
            mode=data.mode,
            filter_profile_id=data.filter_profile_id,
            source_scope={"source_ids": [str(sid) for sid in data.source_ids]},
            framework_scope={"frameworks": data.framework_scope},
            status=RunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        await self.session.flush()
        
        # Trigger Temporal discovery workflow
        await self._trigger_discovery_workflow(run)
        
        return run

    async def _trigger_discovery_workflow(self, run: CandidateDiscoveryRun):
        from temporalio.client import Client
        from ks.config.settings import get_settings
        
        settings = get_settings()
        client = await Client.connect(settings.temporal.address)
        
        # 1. Fetch sources to discover
        # If specific source_ids provided, use them, else use all approved
        source_ids = run.source_scope.get("source_ids", [])
        q = select(SourceRegistry)
        if source_ids:
            q = q.where(SourceRegistry.id.in_([uuid.UUID(sid) for sid in source_ids]))
        else:
            q = q.where(SourceRegistry.approval_status == SourceApprovalStatus.APPROVED_ACTIVE)
        
        res = await self.session.execute(q)
        sources = res.scalars().all()
        
        source_data = []
        for s in sources:
            policy = s.crawl_policy or {}
            source_data.append({
                "id": str(s.id),
                "root_url": s.root_url,
                "allow_patterns": policy.get("allow_patterns", []),
                "block_patterns": policy.get("block_patterns", []),
            })
            
        # 2. Get filter profile (if any)
        profile_data = {}
        if run.filter_profile_id:
            res = await self.session.execute(
                select(DiscoveryFilterProfile).where(DiscoveryFilterProfile.id == run.filter_profile_id)
            )
            profile = res.scalar_one_or_none()
            if profile:
                profile_data = {
                    "per_source_limit": profile.per_source_limit,
                }

        # 3. Start workflow
        payload = {
            "run_id": str(run.id),
            "mode": run.mode,
            "filter_profile": profile_data,
            "sources": source_data,
        }
        
        await client.start_workflow(
            "DiscoveryWorkflow",
            payload,
            id=f"discovery-run-{run.id}",
            task_queue=settings.temporal.task_queue,
        )

    async def terminate_run(self, run_id: uuid.UUID):
        from temporalio.client import Client
        from ks.config.settings import get_settings
        
        settings = get_settings()
        client = await Client.connect(settings.temporal.address)
        
        workflow_id = f"discovery-run-{run_id}"
        try:
            handle = client.get_workflow_handle(workflow_id)
            await handle.terminate(reason="User requested termination via UI")
            
            # Optionally update DB status immediately
            from ks.domain.models import CandidateDiscoveryRun
            from ks.domain.enums import RunStatus
            result = await self.session.execute(
                select(CandidateDiscoveryRun).where(CandidateDiscoveryRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if run and run.status == RunStatus.RUNNING:
                run.status = RunStatus.FAILED
                run.error_message = "Terminated by user"
                await self.session.flush()
        except Exception as e:
            # If workflow already finished, just ignore
            pass

    async def get_run(self, run_id: uuid.UUID) -> CandidateDiscoveryRun:
        result = await self.session.execute(
            select(CandidateDiscoveryRun).where(CandidateDiscoveryRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"Discovery run {run_id} not found")
        return run

    async def list_runs(self, limit: int = 20, offset: int = 0) -> tuple[list[CandidateDiscoveryRun], int]:
        q = select(CandidateDiscoveryRun).order_by(CandidateDiscoveryRun.created_at.desc())
        
        # Count
        count_q = select(func.count()).select_from(CandidateDiscoveryRun)
        total = (await self.session.execute(count_q)).scalar_one()
        
        # Data
        result = await self.session.execute(q.offset(offset).limit(limit))
        return list(result.scalars().all()), total

    # ── Candidates ────────────────────────────────────────────────────────────

    async def get_run_candidates(self, run_id: uuid.UUID) -> list[CandidateDocumentEvaluation]:
        result = await self.session.execute(
            select(CandidateDocumentEvaluation)
            .where(CandidateDocumentEvaluation.run_id == run_id)
            .options(selectinload(CandidateDocumentEvaluation.document))
            .order_by(CandidateDocumentEvaluation.score.desc())
        )
        return list(result.scalars().all())

    async def list_all_candidates(self, limit: int = 50, offset: int = 0) -> tuple[list[CandidateDocumentEvaluation], int]:
        q = select(CandidateDocumentEvaluation).options(selectinload(CandidateDocumentEvaluation.document))
        
        count_q = select(func.count()).select_from(CandidateDocumentEvaluation)
        total = (await self.session.execute(count_q)).scalar_one()
        
        result = await self.session.execute(
            q.order_by(CandidateDocumentEvaluation.evaluated_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total
