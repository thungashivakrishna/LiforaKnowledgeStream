"""Source registry API router."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from ks.source_registry.policy import evaluate_policy
from ks.source_registry.schemas import (
    PolicyScoreRequest,
    PolicyScoreResponse,
    SourceActionRequest,
    SourceCreateRequest,
    SourceDetailResponse,
    SourceListFilters,
    SourceListResponse,
    SourceReviewRequest,
    SourceReviewResponse,
    SourceUpdateRequest,
)
from ks.source_registry.service import SourceRegistryService

router = APIRouter(prefix="/sources", tags=["Source Registry"])


def get_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> SourceRegistryService:
    return SourceRegistryService(session)


@router.post("", response_model=SourceDetailResponse, status_code=201)
async def create_source(
    data: SourceCreateRequest,
    service: Annotated[SourceRegistryService, Depends(get_service)],
):
    try:
        return await service.create_source(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=SourceListResponse)
async def list_sources(
    service: Annotated[SourceRegistryService, Depends(get_service)],
    filters: Annotated[SourceListFilters, Depends()],
):
    items, total = await service.list_sources(filters)
    return SourceListResponse(
        items=items,
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get("/{source_id}", response_model=SourceDetailResponse)
async def get_source(
    source_id: uuid.UUID,
    service: Annotated[SourceRegistryService, Depends(get_service)],
):
    try:
        return await service.get_source(source_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{source_id}", response_model=SourceDetailResponse)
async def update_source(
    source_id: uuid.UUID,
    data: SourceUpdateRequest,
    service: Annotated[SourceRegistryService, Depends(get_service)],
):
    try:
        return await service.update_source(source_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{source_id}/approve", response_model=SourceDetailResponse)
async def approve_source(
    source_id: uuid.UUID,
    req: SourceActionRequest,
    service: Annotated[SourceRegistryService, Depends(get_service)],
):
    try:
        return await service.approve_source(source_id, req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{source_id}/pause", response_model=SourceDetailResponse)
async def pause_source(
    source_id: uuid.UUID,
    req: SourceActionRequest,
    service: Annotated[SourceRegistryService, Depends(get_service)],
):
    try:
        return await service.pause_source(source_id, req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{source_id}/block", response_model=SourceDetailResponse)
async def block_source(
    source_id: uuid.UUID,
    req: SourceActionRequest,
    service: Annotated[SourceRegistryService, Depends(get_service)],
):
    try:
        return await service.block_source(source_id, req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{source_id}/review", response_model=SourceReviewResponse)
async def submit_review(
    source_id: uuid.UUID,
    req: SourceReviewRequest,
    service: Annotated[SourceRegistryService, Depends(get_service)],
):
    try:
        return await service.submit_review(source_id, req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{source_id}/review-log", response_model=list[SourceReviewResponse])
async def get_review_log(
    source_id: uuid.UUID,
    service: Annotated[SourceRegistryService, Depends(get_service)],
):
    try:
        return await service.get_review_log(source_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/policy/evaluate", response_model=PolicyScoreResponse)
async def evaluate_source_policy(req: PolicyScoreRequest):
    """Utility endpoint to calculate composite score and recommended tier."""
    return evaluate_policy(req.model_dump())
