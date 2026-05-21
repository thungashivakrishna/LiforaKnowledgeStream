"""LLM gateway — unified routing, cost tracking, safety guards, and caching for all LLM calls."""
import logging
import time
import uuid
from datetime import date

import litellm

from ks.common import redis_client, safety
from ks.common.llm_types import LLMBudgetExceeded, LLMResponse, LLMUsage
from ks.config.settings import get_settings

logger = logging.getLogger(__name__)

_router: litellm.Router | None = None


def _build_router() -> litellm.Router:
    settings = get_settings()
    model_list = []
    fallbacks = []

    # Default group: primary → secondary → tertiary
    chain = settings.model.fallback_chain
    api_keys = [
        settings.model.primary_api_key,
        settings.model.secondary_api_key,
        settings.model.tertiary_api_key,
    ]
    for i, model in enumerate(chain):
        name = "default" if i == 0 else f"default-fb-{i}"
        params: dict = {"model": model, "api_key": api_keys[min(i, 2)]}
        if i == 0 and settings.model.primary_api_base:
            params["api_base"] = settings.model.primary_api_base
        model_list.append({"model_name": name, "litellm_params": params})
    if len(chain) > 1:
        fallbacks.append({"default": [f"default-fb-{i}" for i in range(1, len(chain))]})

    # Fast group: tertiary first, secondary fallback
    fast_chain = settings.model.fast_chain
    fast_api_keys = [settings.model.tertiary_api_key, settings.model.secondary_api_key]
    for i, model in enumerate(fast_chain):
        name = "fast" if i == 0 else f"fast-fb-{i}"
        params = {"model": model, "api_key": fast_api_keys[min(i, 1)]}
        model_list.append({"model_name": name, "litellm_params": params})
    if len(fast_chain) > 1:
        fallbacks.append({"fast": [f"fast-fb-{i}" for i in range(1, len(fast_chain))]})

    # Embedding group (single model, no fallback)
    model_list.append({
        "model_name": "embedding",
        "litellm_params": {
            "model": settings.model.embedding_model,
            "api_key": settings.model.embedding_api_key,
        },
    })

    return litellm.Router(
        model_list=model_list,
        fallbacks=fallbacks,
        num_retries=settings.model.max_retries,
        retry_after=1,
    )


def _get_router() -> litellm.Router:
    global _router
    if _router is None:
        _router = _build_router()
    return _router


async def _record_call(
    *,
    stage: str,
    run_id: str | None,
    document_id: str | None,
    prompt_id: str,
    model_used: str,
    model_requested: str,
    fallback_depth: int,
    usage: LLMUsage,
    status: str,
) -> None:
    """Write one row to llm_call; fail-open on any error."""
    try:
        from apps.api.database import SessionLocal
        from ks.domain.models import LLMCall

        row = LLMCall(
            stage=stage,
            run_id=uuid.UUID(run_id) if run_id else None,
            document_id=uuid.UUID(document_id) if document_id else None,
            prompt_id=prompt_id,
            model_used=model_used,
            model_requested=model_requested,
            fallback_depth=fallback_depth,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            cost_usd=usage.cost_usd,
            latency_ms=usage.latency_ms,
            cache_hit=usage.cache_hit,
            status=status,
        )
        async with SessionLocal() as session:
            session.add(row)
            await session.commit()
    except Exception as e:
        logger.warning("Failed to record LLM call (non-fatal): %s", e)


def _resolve_fallback_depth(model_used: str, model_group: str, settings) -> int:
    chain = settings.model.fallback_chain if model_group == "default" else settings.model.fast_chain
    try:
        return chain.index(model_used)
    except ValueError:
        return 0


async def complete(
    prompt_id: str,
    variables: dict,
    *,
    stage: str,
    run_id: str | None = None,
    document_id: str | None = None,
    response_format: type | dict | None = None,
    model_group: str = "default",
    cache: bool = True,
    max_tokens: int | None = None,
) -> LLMResponse:
    """Route a completion call through the full gateway pipeline."""
    from ks.prompts import REGISTRY, render as render_prompt

    settings = get_settings()

    # Phase 5: Render prompt from template registry
    if prompt_id in REGISTRY:
        rendered_text, suggested_group, fmt = render_prompt(prompt_id, variables)
        if response_format is None:
            response_format = fmt
        if model_group == "default" and suggested_group and suggested_group != "default":
            model_group = suggested_group
    else:
        # Raw text passed directly (pre-Phase-5 callers)
        rendered_text = variables.get("_text", "")

    # Phase 4: PII redaction
    if settings.model.redact_pii:
        rendered_text = safety.redact_pii(rendered_text)

    # Phase 4: Injection guard
    if safety.check_injection(rendered_text):
        logger.warning("Injection attempt blocked for prompt_id=%s stage=%s", prompt_id, stage)
        return LLMResponse(
            content="",
            model_used="",
            model_requested=model_group,
            skipped=True,
            status="blocked",
        )

    # Phase 6: Cache lookup
    cache_key = f"cache:llm:{redis_client.sha256(model_group + rendered_text + str(response_format))}"
    if cache:
        cached = await redis_client.get_cache(cache_key)
        if cached is not None:
            await _record_call(
                stage=stage, run_id=run_id, document_id=document_id,
                prompt_id=prompt_id, model_used=cached.get("model_used", ""),
                model_requested=model_group, fallback_depth=0,
                usage=LLMUsage(cache_hit=True), status="cached",
            )
            return LLMResponse(
                content=cached["content"],
                model_used=cached.get("model_used", ""),
                model_requested=model_group,
                usage=LLMUsage(cache_hit=True),
                status="cached",
            )

    # Phase 3: Budget check
    today = date.today().isoformat()
    daily_key = f"llm:spend:daily:{today}"
    doc_key = f"llm:spend:doc:{document_id}" if document_id else None
    if settings.model.budget_enforcement == "hard":
        try:
            daily_spend = float(await redis_client.get_cache(daily_key) or 0)
            if daily_spend >= settings.model.daily_budget_usd:
                raise LLMBudgetExceeded(
                    f"Daily LLM budget exceeded: ${daily_spend:.2f} >= ${settings.model.daily_budget_usd}"
                )
            if doc_key:
                doc_spend = float(await redis_client.get_cache(doc_key) or 0)
                if doc_spend >= settings.model.per_doc_budget_usd:
                    raise LLMBudgetExceeded(
                        f"Per-document LLM budget exceeded: ${doc_spend:.2f}"
                    )
        except LLMBudgetExceeded:
            raise
        except Exception as e:
            logger.warning("Budget check failed (fail-open): %s", e)
    elif settings.model.budget_enforcement == "soft":
        try:
            daily_spend = float(await redis_client.get_cache(daily_key) or 0)
            if daily_spend >= settings.model.daily_budget_usd:
                logger.warning("Daily LLM budget soft-exceeded: $%.4f", daily_spend)
        except Exception:
            pass

    # Phase 1: Route through litellm.Router with fallback chain
    router = _get_router()
    messages = [{"role": "user", "content": rendered_text}]
    call_kwargs: dict = {"model": model_group, "messages": messages}
    if max_tokens:
        call_kwargs["max_tokens"] = max_tokens
    if response_format:
        call_kwargs["response_format"] = response_format

    start_ms = int(time.time() * 1000)
    try:
        response = await router.acompletion(**call_kwargs)
    except LLMBudgetExceeded:
        raise
    except Exception as e:
        latency_ms = int(time.time() * 1000) - start_ms
        logger.error("LLM call failed prompt_id=%s: %s", prompt_id, e)
        await _record_call(
            stage=stage, run_id=run_id, document_id=document_id,
            prompt_id=prompt_id, model_used="", model_requested=model_group,
            fallback_depth=0, usage=LLMUsage(latency_ms=latency_ms), status="failed",
        )
        return LLMResponse(content="", model_used="", model_requested=model_group, status="failed")

    latency_ms = int(time.time() * 1000) - start_ms
    model_used = getattr(response, "model", model_group) or model_group
    content = response.choices[0].message.content or ""

    # Phase 4: Refusal detection
    if safety.detect_refusal(content):
        logger.warning("Model refusal detected prompt_id=%s model=%s", prompt_id, model_used)
        await _record_call(
            stage=stage, run_id=run_id, document_id=document_id,
            prompt_id=prompt_id, model_used=model_used, model_requested=model_group,
            fallback_depth=_resolve_fallback_depth(model_used, model_group, settings),
            usage=LLMUsage(latency_ms=latency_ms), status="refusal",
        )
        return LLMResponse(
            content=content, model_used=model_used, model_requested=model_group, status="refusal"
        )

    # Phase 2: Cost tracking
    raw_usage = getattr(response, "usage", None)
    cost_usd = 0.0
    try:
        cost_usd = litellm.completion_cost(completion_response=response) or 0.0
    except Exception:
        pass

    usage = LLMUsage(
        prompt_tokens=getattr(raw_usage, "prompt_tokens", 0) if raw_usage else 0,
        completion_tokens=getattr(raw_usage, "completion_tokens", 0) if raw_usage else 0,
        total_tokens=getattr(raw_usage, "total_tokens", 0) if raw_usage else 0,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        fallback_depth=_resolve_fallback_depth(model_used, model_group, settings),
    )

    await _record_call(
        stage=stage, run_id=run_id, document_id=document_id,
        prompt_id=prompt_id, model_used=model_used, model_requested=model_group,
        fallback_depth=usage.fallback_depth, usage=usage, status="success",
    )

    # Update Redis budget counters
    try:
        await redis_client.incr_spend(daily_key, cost_usd, ex=86400)
        if doc_key:
            await redis_client.incr_spend(doc_key, cost_usd, ex=604800)
    except Exception as e:
        logger.warning("Failed to update budget counters: %s", e)

    # Phase 6: Cache write
    if cache:
        await redis_client.set_cache(
            cache_key,
            {"content": content, "model_used": model_used},
            ttl=settings.model.prompt_cache_ttl_seconds,
        )

    return LLMResponse(
        content=content,
        model_used=model_used,
        model_requested=model_group,
        usage=usage,
        status="success",
    )


async def embed(
    texts: list[str],
    *,
    stage: str,
    run_id: str | None = None,
    document_id: str | None = None,
    cache: bool = True,
) -> list[list[float]]:
    """Generate embeddings via the gateway (with per-chunk Redis caching)."""
    settings = get_settings()
    router = _get_router()

    cached_vectors: dict[int, list[float]] = {}
    uncached_indices: list[int] = []
    uncached_texts: list[str] = []

    if cache:
        for i, text in enumerate(texts):
            key = f"cache:embedding:{redis_client.sha256(text)}"
            cached = await redis_client.get_cache(key)
            if cached is not None:
                cached_vectors[i] = cached
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)
    else:
        uncached_indices = list(range(len(texts)))
        uncached_texts = texts

    total_tokens = 0
    cost_usd = 0.0
    start_ms = int(time.time() * 1000)

    if uncached_texts:
        try:
            response = await router.aembedding(model="embedding", input=uncached_texts)
            raw_usage = getattr(response, "usage", None)
            total_tokens = getattr(raw_usage, "total_tokens", 0) if raw_usage else 0
            try:
                cost_usd = litellm.completion_cost(completion_response=response) or 0.0
            except Exception:
                pass

            for j, idx in enumerate(uncached_indices):
                vector = response.data[j]["embedding"]
                cached_vectors[idx] = vector
                if cache:
                    key = f"cache:embedding:{redis_client.sha256(texts[idx])}"
                    await redis_client.set_cache(key, vector, ttl=redis_client.DEDUP_TTL)
        except Exception as e:
            logger.error("Embedding call failed stage=%s: %s", stage, e)
            raise

    latency_ms = int(time.time() * 1000) - start_ms
    await _record_call(
        stage=stage, run_id=run_id, document_id=document_id,
        prompt_id="embedding",
        model_used=settings.model.embedding_model,
        model_requested="embedding",
        fallback_depth=0,
        usage=LLMUsage(total_tokens=total_tokens, cost_usd=cost_usd, latency_ms=latency_ms,
                       cache_hit=len(uncached_texts) == 0),
        status="success",
    )

    return [cached_vectors[i] for i in range(len(texts))]
