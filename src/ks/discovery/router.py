"""Discovery router — API endpoints for content discovery."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from ks.discovery.schemas import (
    CandidateDocumentResponse,
    DiscoveryFilterProfileRequest,
    DiscoveryFilterProfileResponse,
    DiscoveryRunDetailResponse,
    DiscoveryRunRequest,
    DiscoveryRunResponse,
    PaginatedCandidateResponse,
    PaginatedDiscoveryRunResponse,
)
from ks.discovery.service import DiscoveryService

router = APIRouter(prefix="/discovery", tags=["Discovery"])


# ── Filter Profiles ────────────────────────────────────────────────────────────

@router.post("/profiles", response_model=DiscoveryFilterProfileResponse)
async def create_filter_profile(
    data: DiscoveryFilterProfileRequest, 
    db: AsyncSession = Depends(get_db_session)
):
    """Create a new discovery filter profile."""
    service = DiscoveryService(db)
    profile = await service.create_filter_profile(data)
    await db.commit()
    return profile


@router.get("/profiles", response_model=list[DiscoveryFilterProfileResponse])
async def list_filter_profiles(db: AsyncSession = Depends(get_db_session)):
    """List all discovery filter profiles."""
    service = DiscoveryService(db)
    return await service.list_filter_profiles()


# ── Discovery Runs ─────────────────────────────────────────────────────────────

@router.post("/runs", response_model=DiscoveryRunResponse)
async def start_discovery_run(
    data: DiscoveryRunRequest, 
    db: AsyncSession = Depends(get_db_session)
):
    """Start a new discovery run."""
    service = DiscoveryService(db)
    run = await service.create_run(data)
    await db.commit()
    return run


@router.get("/runs", response_model=PaginatedDiscoveryRunResponse)
async def list_discovery_runs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session)
):
    """List discovery runs with pagination."""
    service = DiscoveryService(db)
    items, total = await service.list_runs(limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}
    

@router.delete("/runs/{run_id}")
async def stop_discovery_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db_session)):
    """Terminate a running discovery workflow."""
    service = DiscoveryService(db)
    await service.terminate_run(run_id)
    await db.commit()
    return {"status": "terminating"}


@router.get("/runs/{run_id}", response_model=DiscoveryRunDetailResponse)
async def get_discovery_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db_session)):
    """Get details of a specific discovery run, including candidates."""
    service = DiscoveryService(db)
    try:
        run = await service.get_run(run_id)
        candidates = await service.get_run_candidates(run_id)
        
        topics = []
        if run.filter_profile_id:
            from ks.domain.models import DiscoveryFilterProfile
            res = await db.execute(
                select(DiscoveryFilterProfile).where(DiscoveryFilterProfile.id == run.filter_profile_id)
            )
            profile = res.scalar_one_or_none()
            if profile:
                topics = profile.topics or []
        
        # Manually construct response to include candidates
        return {
            "id": run.id,
            "mode": run.mode,
            "status": run.status,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "candidate_count": run.candidate_count,
            "error_message": run.error_message,
            "created_at": run.created_at,
            "source_scope": run.source_scope,
            "framework_scope": run.framework_scope,
            "topics": topics,
            "candidates": [
                {
                    "id": c.id,
                    "run_id": c.run_id,
                    "document_id": c.document_id,
                    "canonical_url": c.document.canonical_url,
                    "title": c.document.title,
                    "score": c.score,
                    "decision": c.decision,
                    "matched_terms": c.matched_terms,
                    "evaluated_at": c.evaluated_at,
                    "document_status": c.document.status.value if c.document.status else "UNKNOWN"
                } for c in candidates
            ]
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Candidates ────────────────────────────────────────────────────────────

@router.get("/candidates", response_model=PaginatedCandidateResponse)
async def list_all_candidates(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session)
):
    """List all evaluated candidates across all runs."""
    service = DiscoveryService(db)
    items, total = await service.list_all_candidates(limit, offset)
    
    # Format for response
    formatted_items = [
        {
            "id": c.id,
            "run_id": c.run_id,
            "document_id": c.document_id,
            "canonical_url": c.document.canonical_url,
            "title": c.document.title,
            "score": c.score,
            "decision": c.decision,
            "matched_terms": c.matched_terms,
            "evaluated_at": c.evaluated_at,
        } for c in items
    ]
    
    return {"items": formatted_items, "total": total, "limit": limit, "offset": offset}
