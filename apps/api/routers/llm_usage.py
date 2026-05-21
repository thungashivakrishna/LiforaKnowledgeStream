"""LLM gateway observability — spend, fallback, cache, and unit-economics endpoints."""
import uuid
from datetime import date, timedelta
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Query
from sqlalchemy import func, select

from apps.api.database import SessionLocal
from ks.config.settings import get_settings
from ks.domain.models import LLMCall, KnowledgeFact, KnowledgeChunk

router = APIRouter(prefix="/llm", tags=["LLM Gateway"])


async def _query(stmt) -> list[Any]:
    async with SessionLocal() as session:
        result = await session.execute(stmt)
        return result.all()


@router.get("/spend/daily")
async def llm_spend_daily(days: int = Query(30, ge=1, le=365)):
    """Daily $ spend for the past N days, grouped by stage and model."""
    cutoff = date.today() - timedelta(days=days)
    stmt = (
        select(
            func.date(LLMCall.created_at).label("day"),
            LLMCall.stage,
            LLMCall.model_used,
            func.sum(LLMCall.cost_usd).label("cost_usd"),
            func.count().label("calls"),
            func.sum(LLMCall.total_tokens).label("total_tokens"),
        )
        .where(LLMCall.created_at >= cutoff, LLMCall.status != "cached")
        .group_by(func.date(LLMCall.created_at), LLMCall.stage, LLMCall.model_used)
        .order_by(func.date(LLMCall.created_at).desc())
    )
    rows = await _query(stmt)
    return [
        {"day": str(r.day), "stage": r.stage, "model": r.model_used,
         "cost_usd": round(r.cost_usd or 0, 6), "calls": r.calls, "total_tokens": r.total_tokens}
        for r in rows
    ]


@router.get("/spend/by-stage")
async def llm_spend_by_stage():
    """All-time spend aggregated by stage."""
    stmt = (
        select(
            LLMCall.stage,
            func.sum(LLMCall.cost_usd).label("cost_usd"),
            func.count().label("calls"),
            func.avg(LLMCall.latency_ms).label("avg_latency_ms"),
        )
        .where(LLMCall.status != "cached")
        .group_by(LLMCall.stage)
        .order_by(func.sum(LLMCall.cost_usd).desc())
    )
    rows = await _query(stmt)
    return [
        {"stage": r.stage, "cost_usd": round(r.cost_usd or 0, 6),
         "calls": r.calls, "avg_latency_ms": int(r.avg_latency_ms or 0)}
        for r in rows
    ]


@router.get("/spend/by-document/{document_id}")
async def llm_spend_by_document(document_id: str):
    """Spend breakdown for a single document."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        return {"error": "invalid document_id"}
    stmt = (
        select(
            LLMCall.stage,
            LLMCall.prompt_id,
            LLMCall.model_used,
            func.sum(LLMCall.cost_usd).label("cost_usd"),
            func.sum(LLMCall.total_tokens).label("total_tokens"),
            func.count().label("calls"),
        )
        .where(LLMCall.document_id == doc_uuid)
        .group_by(LLMCall.stage, LLMCall.prompt_id, LLMCall.model_used)
        .order_by(func.sum(LLMCall.cost_usd).desc())
    )
    rows = await _query(stmt)
    total = sum(r.cost_usd or 0 for r in rows)
    return {
        "document_id": document_id,
        "total_cost_usd": round(total, 6),
        "breakdown": [
            {"stage": r.stage, "prompt_id": r.prompt_id, "model": r.model_used,
             "cost_usd": round(r.cost_usd or 0, 6), "total_tokens": r.total_tokens, "calls": r.calls}
            for r in rows
        ],
    }


@router.get("/fallback-rate")
async def llm_fallback_rate(stage: str | None = None):
    """Fallback rate (% of calls that hit fallback ≥1) by stage and primary model."""
    stmt = select(
        LLMCall.stage,
        LLMCall.model_requested,
        func.count().label("total"),
        func.sum(
            func.cast(LLMCall.fallback_depth > 0, type_=func.count().type)
        ).label("fallbacks"),
        func.avg(LLMCall.fallback_depth).label("avg_depth"),
    ).where(LLMCall.status.notin_(["cached", "blocked"]))
    if stage:
        stmt = stmt.where(LLMCall.stage == stage)
    stmt = stmt.group_by(LLMCall.stage, LLMCall.model_requested)
    rows = await _query(stmt)
    return [
        {
            "stage": r.stage,
            "model_group": r.model_requested,
            "total_calls": r.total,
            "fallback_calls": int(r.fallbacks or 0),
            "fallback_rate_pct": round((r.fallbacks or 0) / max(r.total, 1) * 100, 2),
            "avg_fallback_depth": round(r.avg_depth or 0, 2),
        }
        for r in rows
    ]


@router.get("/unit-economics")
async def llm_unit_economics():
    """Cost per document, per fact, per chunk."""
    async with SessionLocal() as session:
        spend = (await session.execute(
            select(func.sum(LLMCall.cost_usd)).where(LLMCall.status == "success")
        )).scalar() or 0.0

        doc_count = (await session.execute(
            select(func.count(func.distinct(LLMCall.document_id)))
            .where(LLMCall.document_id.isnot(None))
        )).scalar() or 1

        fact_count = (await session.execute(select(func.count(KnowledgeFact.id)))).scalar() or 1
        chunk_count = (await session.execute(select(func.count(KnowledgeChunk.id)))).scalar() or 1

    return {
        "total_spend_usd": round(spend, 4),
        "cost_per_document_usd": round(spend / doc_count, 6),
        "cost_per_fact_usd": round(spend / fact_count, 6),
        "cost_per_chunk_usd": round(spend / chunk_count, 6),
        "documents_processed": doc_count,
        "facts_extracted": fact_count,
        "chunks_indexed": chunk_count,
    }


@router.get("/prompt-leaderboard")
async def llm_prompt_leaderboard(metric: str = Query("spend", pattern="^(spend|count|p95)$")):
    """Top 10 prompt_ids by spend, call count, or p95 latency."""
    if metric == "p95":
        order_col = func.percentile_cont(0.95).within_group(LLMCall.latency_ms).label("value")
    elif metric == "count":
        order_col = func.count().label("value")
    else:
        order_col = func.sum(LLMCall.cost_usd).label("value")

    stmt = (
        select(
            LLMCall.prompt_id,
            func.count().label("calls"),
            func.sum(LLMCall.cost_usd).label("total_cost_usd"),
            func.avg(LLMCall.latency_ms).label("avg_latency_ms"),
            func.percentile_cont(0.95).within_group(LLMCall.latency_ms).label("p95_latency_ms"),
        )
        .where(LLMCall.status.notin_(["cached", "blocked"]))
        .group_by(LLMCall.prompt_id)
        .order_by(order_col.desc())
        .limit(10)
    )
    rows = await _query(stmt)
    return [
        {
            "prompt_id": r.prompt_id,
            "calls": r.calls,
            "total_cost_usd": round(r.total_cost_usd or 0, 6),
            "avg_latency_ms": int(r.avg_latency_ms or 0),
            "p95_latency_ms": int(r.p95_latency_ms or 0),
        }
        for r in rows
    ]


@router.get("/cache-hit-by-prompt")
async def llm_cache_hit_by_prompt():
    """Cache hit rate per prompt_id — surfaces prompts with unexpectedly low cache hit rates."""
    async with SessionLocal() as session:
        result = await session.execute(
            select(
                LLMCall.prompt_id,
                func.count().label("total"),
                func.sum(sa.cast(LLMCall.cache_hit, sa.Integer)).label("hits"),
            )
            .group_by(LLMCall.prompt_id)
            .order_by(func.count().desc())
        )
        rows = result.all()
    return [
        {
            "prompt_id": r.prompt_id,
            "total_calls": r.total,
            "cache_hits": int(r.hits or 0),
            "hit_rate_pct": round((r.hits or 0) / max(r.total, 1) * 100, 2),
        }
        for r in rows
    ]


@router.get("/recent-calls")
async def llm_recent_calls(
    status: str | None = None,
    stage: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """Last N llm_call rows with optional status/stage filter."""
    stmt = select(LLMCall).order_by(LLMCall.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(LLMCall.status == status)
    if stage:
        stmt = stmt.where(LLMCall.stage == stage)
    async with SessionLocal() as session:
        result = await session.execute(stmt)
        rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "stage": r.stage,
            "prompt_id": r.prompt_id,
            "model_used": r.model_used,
            "model_requested": r.model_requested,
            "fallback_depth": r.fallback_depth,
            "cost_usd": r.cost_usd,
            "latency_ms": r.latency_ms,
            "total_tokens": r.total_tokens,
            "cache_hit": r.cache_hit,
            "status": r.status,
        }
        for r in rows
    ]


@router.get("/provider-health")
async def llm_provider_health():
    """Last success timestamp and last error per model, for SystemInspector."""
    async with SessionLocal() as session:
        success_stmt = (
            select(LLMCall.model_used, func.max(LLMCall.created_at).label("last_success"))
            .where(LLMCall.status == "success")
            .group_by(LLMCall.model_used)
        )
        error_stmt = (
            select(LLMCall.model_used, func.max(LLMCall.created_at).label("last_error"))
            .where(LLMCall.status == "failed")
            .group_by(LLMCall.model_used)
        )
        successes = {r.model_used: r.last_success for r in (await session.execute(success_stmt)).all()}
        errors = {r.model_used: r.last_error for r in (await session.execute(error_stmt)).all()}

    settings = get_settings()
    models = settings.model.fallback_chain + settings.model.fast_chain
    return [
        {
            "model": m,
            "last_success": successes.get(m).isoformat() if successes.get(m) else None,
            "last_error": errors.get(m).isoformat() if errors.get(m) else None,
            "healthy": successes.get(m) is not None,
        }
        for m in dict.fromkeys(models)  # deduplicate while preserving order
    ]


@router.get("/budget-config")
async def get_budget_config():
    """Current budget configuration (read from env settings)."""
    settings = get_settings()
    return {
        "daily_budget_usd": settings.model.daily_budget_usd,
        "per_doc_budget_usd": settings.model.per_doc_budget_usd,
        "enforcement": settings.model.budget_enforcement,
        "fallback_chain": settings.model.fallback_chain,
        "fast_chain": settings.model.fast_chain,
    }
