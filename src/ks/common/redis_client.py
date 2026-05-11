"""Shared async Redis client used by all pipeline stages."""
import hashlib
import json
import logging
import uuid
from typing import Any

import redis.asyncio as aioredis

from ks.config.settings import get_settings

logger = logging.getLogger(__name__)

# TTL constants (seconds)
DEDUP_TTL = 7_776_000   # 90 days
CACHE_30D = 2_592_000   # 30 days
LOCK_ENRICHMENT = 1800  # 30 min
LOCK_QDRANT = 900       # 15 min
LOCK_GRAPH = 900        # 15 min

_redis: aioredis.Redis | None = None


def _get_client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = aioredis.Redis.from_url(
            settings.redis.url,
            max_connections=20,
            decode_responses=True,
        )
    return _redis


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def check_dedup(key: str) -> bool:
    """Returns True if key was already seen. Returns False on Redis error (safe fallback)."""
    try:
        return await _get_client().exists(key) == 1
    except Exception as e:
        logger.warning("Redis check_dedup error: %s", e)
        return False


async def mark_seen(key: str, ttl: int = DEDUP_TTL) -> None:
    try:
        await _get_client().set(key, "1", ex=ttl)
    except Exception as e:
        logger.warning("Redis mark_seen error: %s", e)


async def acquire_lock(key: str, ttl: int, worker_id: str | None = None) -> bool:
    """Returns True if lock acquired. Returns True on Redis error (fail-open)."""
    try:
        if worker_id is None:
            worker_id = str(uuid.uuid4())
        result = await _get_client().set(key, worker_id, nx=True, ex=ttl)
        return result is not None
    except Exception as e:
        logger.warning("Redis acquire_lock error (failing open): %s", e)
        return True


async def release_lock(key: str) -> None:
    try:
        await _get_client().delete(key)
    except Exception as e:
        logger.warning("Redis release_lock error: %s", e)


async def get_cache(key: str) -> Any | None:
    """Returns cached value or None on miss/error."""
    try:
        val = await _get_client().get(key)
        if val is None:
            return None
        return json.loads(val)
    except Exception as e:
        logger.warning("Redis get_cache error: %s", e)
        return None


async def set_cache(key: str, value: Any, ttl: int | None = None) -> None:
    try:
        serialized = json.dumps(value)
        if ttl:
            await _get_client().set(key, serialized, ex=ttl)
        else:
            await _get_client().set(key, serialized)
    except Exception as e:
        logger.warning("Redis set_cache error: %s", e)


async def rate_check(domain: str, limit: int = 10) -> bool:
    """
    Sliding-window rate check (1-second window).
    Returns True if request is allowed, False if over limit.
    Returns True on Redis error (fail-open).
    """
    try:
        key = f"rate:{domain}:req_count"
        r = _get_client()
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 1)
        results = await pipe.execute()
        return results[0] <= limit
    except Exception as e:
        logger.warning("Redis rate_check error (failing open): %s", e)
        return True
