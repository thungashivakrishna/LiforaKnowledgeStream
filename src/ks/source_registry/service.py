"""Source registry service — all CRUD and lifecycle operations."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ks.domain.enums import SourceApprovalStatus
from ks.domain.models import SourceFrameworkMap, SourceRegistry, SourceReview
from ks.source_registry.schemas import (
    SourceActionRequest,
    SourceCreateRequest,
    SourceListFilters,
    SourceReviewRequest,
    SourceUpdateRequest,
)


class SourceRegistryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Query helpers ────────────────────────────────────────────────────────

    def _base_query(self):
        return select(SourceRegistry).options(selectinload(SourceRegistry.framework_maps))

    async def _get_or_404(self, source_id: uuid.UUID) -> SourceRegistry:
        result = await self.session.execute(
            self._base_query().where(SourceRegistry.id == source_id)
        )
        source = result.scalar_one_or_none()
        if not source:
            raise ValueError(f"Source {source_id} not found")
        return source

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def create_source(self, data: SourceCreateRequest) -> SourceRegistry:
        # Check for duplicate URL
        existing = await self.session.execute(
            select(SourceRegistry).where(SourceRegistry.root_url == str(data.root_url))
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Source with URL '{data.root_url}' already exists")

        source = SourceRegistry(
            id=uuid.uuid4(),
            name=data.name,
            root_url=str(data.root_url),
            source_type=data.source_type,
            language=data.language,
            region=data.region,
            trust_tier=data.trust_tier,
            approval_status=SourceApprovalStatus.CANDIDATE,
            crawl_policy=data.crawl_policy.model_dump(),
            extraction_profile=data.extraction_profile.model_dump(),
            freshness_days=data.freshness_days,
            review_notes=data.review_notes,
        )
        self.session.add(source)
        await self.session.flush()

        # Framework maps
        maps: list[SourceFrameworkMap] = []
        maps.append(SourceFrameworkMap(
            id=uuid.uuid4(),
            source_id=source.id,
            framework=data.primary_framework,
            is_primary=True,
        ))
        for fw in data.secondary_frameworks:
            maps.append(SourceFrameworkMap(
                id=uuid.uuid4(),
                source_id=source.id,
                framework=fw,
                is_primary=False,
            ))
        self.session.add_all(maps)
        await self.session.flush()

        # Audit
        await self._audit(source.id, "create", "system")

        await self.session.refresh(source, ["framework_maps"])
        return source

    async def get_source(self, source_id: uuid.UUID) -> SourceRegistry:
        return await self._get_or_404(source_id)

    async def list_sources(self, filters: SourceListFilters) -> tuple[list[SourceRegistry], int]:
        q = self._base_query()

        if filters.approval_status:
            q = q.where(SourceRegistry.approval_status == filters.approval_status)
        if filters.trust_tier:
            q = q.where(SourceRegistry.trust_tier == filters.trust_tier)
        if filters.source_type:
            q = q.where(SourceRegistry.source_type == filters.source_type)
        if filters.search:
            term = f"%{filters.search}%"
            q = q.where(SourceRegistry.name.ilike(term))
        if filters.framework:
            subq = (
                select(SourceFrameworkMap.source_id)
                .where(SourceFrameworkMap.framework == filters.framework)
            )
            q = q.where(SourceRegistry.id.in_(subq))

        # Count
        count_q = select(func.count()).select_from(q.subquery())
        total = (await self.session.execute(count_q)).scalar_one()

        # Paginate
        q = q.order_by(SourceRegistry.created_at.desc()).offset(filters.offset).limit(filters.limit)
        result = await self.session.execute(q)
        return list(result.scalars().all()), total

    async def update_source(self, source_id: uuid.UUID, data: SourceUpdateRequest) -> SourceRegistry:
        source = await self._get_or_404(source_id)
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "crawl_policy" and value is not None:
                setattr(source, field, value if isinstance(value, dict) else value.model_dump())
            elif field == "extraction_profile" and value is not None:
                setattr(source, field, value if isinstance(value, dict) else value.model_dump())
            elif field == "primary_framework" and value is not None:
                # Update primary framework map
                for fm in source.framework_maps:
                    if fm.is_primary:
                        fm.framework = value
            elif field == "secondary_frameworks" and value is not None:
                # Remove old secondary maps
                old_secondary = [fm for fm in source.framework_maps if not fm.is_primary]
                for fm in old_secondary:
                    await self.session.delete(fm)
                # Add new
                for fw in value:
                    self.session.add(SourceFrameworkMap(
                        id=uuid.uuid4(), source_id=source.id, framework=fw, is_primary=False
                    ))
            else:
                setattr(source, field, value)

        await self.session.flush()
        await self._audit(source_id, "update", "admin")
        await self.session.refresh(source, ["framework_maps"])
        return source

    # ── Lifecycle Actions ────────────────────────────────────────────────────

    async def approve_source(self, source_id: uuid.UUID, req: SourceActionRequest) -> SourceRegistry:
        source = await self._get_or_404(source_id)
        source.approval_status = SourceApprovalStatus.APPROVED_ACTIVE
        await self._add_review(source_id, "approved", req.actor, None, req.reason, req.notes)
        await self._audit(source_id, "approve", req.actor)
        return source

    async def pause_source(self, source_id: uuid.UUID, req: SourceActionRequest) -> SourceRegistry:
        source = await self._get_or_404(source_id)
        source.approval_status = SourceApprovalStatus.PAUSED
        await self._add_review(source_id, "paused", req.actor, None, req.reason, req.notes)
        await self._audit(source_id, "pause", req.actor)
        return source

    async def block_source(self, source_id: uuid.UUID, req: SourceActionRequest) -> SourceRegistry:
        source = await self._get_or_404(source_id)
        source.approval_status = SourceApprovalStatus.BLOCKED
        await self._add_review(source_id, "blocked", req.actor, None, req.reason, req.notes)
        await self._audit(source_id, "block", req.actor)
        return source

    async def submit_review(self, source_id: uuid.UUID, req: SourceReviewRequest) -> SourceReview:
        await self._get_or_404(source_id)
        review = await self._add_review(
            source_id, "reviewed", req.actor, req.decision, req.reason, req.notes
        )
        await self._audit(source_id, f"review:{req.decision}", req.actor)
        return review

    async def get_review_log(self, source_id: uuid.UUID) -> list[SourceReview]:
        await self._get_or_404(source_id)
        result = await self.session.execute(
            select(SourceReview)
            .where(SourceReview.source_id == source_id)
            .order_by(SourceReview.created_at.desc())
        )
        return list(result.scalars().all())

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _add_review(
        self,
        source_id: uuid.UUID,
        action: str,
        actor: str,
        decision=None,
        reason: str | None = None,
        notes: str | None = None,
    ) -> SourceReview:
        review = SourceReview(
            id=uuid.uuid4(),
            source_id=source_id,
            action=action,
            actor=actor,
            decision=decision,
            reason=reason,
            notes=notes,
        )
        self.session.add(review)
        await self.session.flush()
        return review

    async def _audit(self, source_id: uuid.UUID, action: str, actor: str) -> None:
        from ks.domain.models import AdminAuditLog
        self.session.add(AdminAuditLog(
            id=uuid.uuid4(),
            actor=actor,
            action=action,
            entity_type="source",
            entity_id=str(source_id),
        ))
