# Redis Integration Plan

## Current State

Redis is running in Docker and configured in `src/ks/config/settings.py` (`RedisSettings`), but **zero Python code uses it**. The only reference is a `PING` health check in `infrastructure/scripts/system_agent.py`.

Deduplication today is handled entirely by `infrastructure/scripts/dedup_db.py` — a PostgreSQL window function scan that runs *after* duplicates are already inserted. There is no caching, rate limiting, or distributed coordination anywhere in the pipeline.

---

## Phase 1 — Shared Redis Client

**New file:** `src/ks/common/redis_client.py`

A single shared async Redis client with helper utilities used by all phases below:
- `get_redis()` — async connection pool from `RedisSettings`
- `check_dedup(key)` / `mark_seen(key, ttl)` — bloom-filter-style set membership
- `acquire_lock(key, ttl)` / `release_lock(key)` — Redlock pattern
- `get_cache(key)` / `set_cache(key, value, ttl)` — JSON serialisation helpers
- `rate_check(domain, limit)` — sliding window counter via `INCR` + `EXPIRE`

### Implementation

**Status:** ✅ Complete

**Files created:**
- `src/ks/common/__init__.py`
- `src/ks/common/redis_client.py`

**Design decisions:**
- Module-level singleton (`_redis: aioredis.Redis`) initialised from `RedisSettings.url` on first call, reused across all activity instances in the worker process.
- All helpers wrap Redis calls in `try/except` and return safe defaults (e.g. `check_dedup` returns `False`, `acquire_lock` returns `True`) so Redis downtime degrades gracefully to DB-level fallbacks rather than crashing the pipeline.
- TTL constants defined once in the module: `DEDUP_TTL = 7_776_000` (90d), `CACHE_30D = 2_592_000`, `LOCK_ENRICHMENT = 1800`, `LOCK_QDRANT = 900`, `LOCK_GRAPH = 900`.
- `sha256(text)` helper exposed for consistent key generation across callers.

---

## Phase 2 — Deduplication (Highest Impact)

**Problem:** Parallel Temporal workers race to insert the same facts, tags, and URLs. Unique constraints catch them at the DB level but the rows are attempted millions of times — wasting writes and causing noise in logs.

**Files:** `src/ks/enrichment/activities.py`, `src/ks/discovery/activities.py`

### Fact & Tag dedup — `persist_enrichment_results()`
Before inserting each `KnowledgeFact` or `KnowledgeTag`, check a Redis SET. Skip the DB write if the key already exists.

| Key | Value | TTL |
|---|---|---|
| `dedup:fact:{sha256(doc_id+subject+predicate+object)}` | `1` | 90 days |
| `dedup:tag:{sha256(doc_id+tag_type+tag_value)}` | `1` | 90 days |

**Eliminates:** the need for `dedup_db.py` cleanup script.

### URL dedup — `persist_candidates()`
Before the `SELECT canonical_url == url` query per candidate, check Redis first.

| Key | Value | TTL |
|---|---|---|
| `dedup:url:{sha256(url)}` | `1` | 90 days |

**Eliminates:** N individual `SELECT` queries per discovery run.

### Implementation

**Status:** ✅ Complete

**Fact & Tag dedup (`enrichment/activities.py`):**
- Added `redis_keys_to_mark: list[str]` collected during the session, written to Redis only *after* `session.commit()` succeeds. This prevents false-positive dedup on rollback — if the DB write fails and rolls back, the Redis key is never marked so the fact/tag will be re-attempted on the next run.
- `add_tag_if_new()` inner function: checks `dedup:tag:{sha256(doc_id+t_type+t_value)}` before the DB `SELECT`. Appends key to `redis_keys_to_mark` when a new tag is added.
- Facts loop: checks `dedup:fact:{sha256(doc_id+norm_subject+predicate+norm_object)}` before the DB `SELECT`. `predicate` is captured as a local variable and reused in both the Redis key and the DB WHERE clause.

**URL dedup (`discovery/activities.py` — `persist_candidates()`):**
- Cache stores `url → str(doc_id)` (not just `"1"`) so the `SELECT DocumentRegistry` query is skipped entirely on repeat URLs. `doc_id_val = uuid.UUID(cached_doc_id)` is used for evaluation record creation.
- Cache is written after `session.flush()` (which assigns the DB-generated ID) so the stored doc_id is always valid.

---

## Phase 3 — Distributed Locks (Correctness)

**Problem:** Multiple workers can pick up the same document and run enrichment, Qdrant indexing, or Neo4j sync concurrently. No coordination exists — they race and produce duplicate writes.

**Files:** `src/ks/enrichment/activities.py`, `src/ks/chunking/activities.py`, `src/ks/graph/activities.py`

| Lock key | Acquired in | Expiry |
|---|---|---|
| `lock:enrichment:{doc_id}:{framework}` | `run_llm_enrichment()` | 30 min |
| `lock:qdrant:{doc_id}` | `index_in_qdrant()` | 15 min |
| `lock:graph:{doc_id}` | `sync_to_neo4j()` | 15 min |

Pattern: `SET key worker_id NX EX {ttl}` — if lock not acquired, activity raises a retriable Temporal error and backs off.

### Implementation

**Status:** ✅ Complete

All three locks follow the same pattern: `acquire_lock` before work, `try: ... finally: release_lock(key)` so the lock is always released even on exception or early return.

**`enrichment/activities.py` — `run_llm_enrichment()`:**
- `doc_id_prefix` extracted from `extracted_text_key.split("/")[0]` (format is `{doc_id}/{hash}.txt`).
- Lock key: `lock:enrichment:{doc_id_prefix}:{framework}` — per-framework granularity prevents blocking agents running different frameworks on the same document in parallel.
- `finally` block wraps the entire function body including the text-fetch inner try/except.

**`chunking/activities.py` — `index_in_qdrant()`:**
- Lock key: `lock:qdrant:{doc_id}`.
- Lock acquired only when `chunks` is non-empty (guard clause exits early before lock for empty input).
- `finally` block releases the lock regardless of Qdrant upsert success or failure.

**`graph/activities.py` — `sync_to_neo4j()`:**
- Lock key: `lock:graph:{doc['id']}`.
- `finally` block releases after the Neo4j `session.execute_write(_sync_tx)` call.

---

## Phase 4 — Result Caching (Cost & Speed)

**Problem:** Expensive LLM calls (framework detection, embeddings, document audit) are re-run every time the same content is processed. No memoization exists anywhere.

**Files:** `src/ks/enrichment/activities.py`, `src/ks/chunking/activities.py`, `src/ks/acquisition/activities.py`, `src/ks/graph/activities.py`

| Cache key | Cached in | TTL | Estimated saving |
|---|---|---|---|
| `cache:frameworks:{doc_id}` | `detect_relevant_frameworks()` | 90 days | ~$0.01–0.05 per doc |
| `cache:embedding:{sha256(chunk_text)}` | `split_and_embed()` | Permanent | ~$0.0001 per chunk |
| `cache:audit:{content_hash}` | `audit_document_intelligence()` | 90 days | ~$0.02–0.10 per doc |
| `cache:graph:schema_ready` | `initialize_graph_schema()` | Permanent | Skip redundant Cypher per run |
| `cache:search_endpoint:{domain}` | `_find_search_endpoint()` | 30 days | Skip HTTP form parsing per source |

Cache flow: check Redis → on hit return cached value → on miss run LLM call → store result in Redis → return.

### Implementation

**Status:** ✅ Complete

**`cache:frameworks:{doc_id}` — `detect_relevant_frameworks()` (`enrichment/activities.py`):**
- `doc_id_prefix = extracted_text_key.split("/")[0]` used as cache key component when `extracted_text_key` is present in payload. Falls back to no caching when payload only has `"text"` (no derivable doc_id).
- Cache miss triggers the LLM call; the full `{"success": True, "frameworks": [...]}` dict is cached so the return shape is identical on hit or miss.

**`cache:embedding:{chunk_hash}` — `split_and_embed()` (`chunking/activities.py`):**
- Splits all chunks first, then checks Redis for each chunk's embedding. Uncached chunks are collected into a sub-list and sent to `litellm.embedding()` in a single batched call. Cached chunks skip the API entirely.
- `total_tokens` reflects only the tokens consumed for the uncached batch, accurately representing actual API spend.
- No TTL (permanent) — embeddings are deterministic for the same text and the model is fixed.

**`cache:audit:{content_hash}` — `audit_document_intelligence()` (`acquisition/activities.py`):**
- Hash computed over `content[:5000]` (the same slice used in the audit prompt), so cache key matches the exact LLM input.
- Full `{"success": True, "audit": {...}}` dict is cached and returned directly on hit.

**`cache:graph:schema_ready` — `initialize_graph_schema()` (`graph/activities.py`):**
- Check at the top of the activity; returns immediately if key exists. Writes `datetime.now(timezone.utc).isoformat()` as the value after successful Neo4j schema init.
- No TTL (permanent) — schema constraints are idempotent and do not need re-running per session.

**`cache:search_endpoint:{domain}` — `_find_search_endpoint()` (`discovery/activities.py`):**
- Cache key uses `urlparse(root_url).netloc` as domain.
- Cached value is a two-element list `[action, param]`; returned as `tuple(cached)` on hit.
- Both the form-parsed result and the fallback `("/search", "q")` are cached to avoid repeated HTTP fetches for sources where form parsing fails.

---

## Phase 5 — Rate Limiting

**Problem:** No throttle exists on outbound HTTP requests during discovery and acquisition. Parallel workers can flood a single domain (Mayo Clinic, NIH, etc.) and trigger IP bans or 429 responses.

**Files:** `src/ks/discovery/activities.py`, `src/ks/acquisition/activities.py`

**Pattern:** Sliding window counter using `INCR` + `EXPIRE` (1-second window).

| Key | Set in | Default limit |
|---|---|---|
| `rate:{domain}:req_count` | `discover_candidates()` before each HTTP call | Configurable via `crawl_policy` in `SourceRegistry` |
| `rate:{domain}:req_count` | `fetch_content()` before each HTTP call | Same policy |

If counter exceeds the limit, the activity sleeps briefly and retries — Temporal handles the retry loop.

### Implementation

**Status:** ✅ Complete

**`discovery/activities.py`:**
- Rate check added before every outbound `http_client.get()` call in `_sitemap_discovery`, `_path_discovery`, `_search_endpoint_discovery`, and `_find_search_endpoint`.
- Domain extracted with `urlparse(url).netloc` at each call site.
- Over limit: `await asyncio.sleep(1.0)` then proceeds (the 1-second window resets, so the next call is allowed). This avoids raising a Temporal error for internal helper methods that are not themselves activities.

**`acquisition/activities.py` — `fetch_content()`:**
- `urlparse` imported locally inside the activity to avoid circular concerns.
- Same `asyncio.sleep(1.0)` pattern — over limit sleeps once before the HTTP fetch.

---

## Phase 6 — Priority Queue

**Problem:** The `ReviewQueue` table is polled with `SELECT WHERE status='pending' ORDER BY priority` — a full table scan every time the admin UI loads the review page. No push mechanism, no O(1) priority pop.

**Files:** `apps/api` review queue router and service

**Pattern:** Redis Sorted Set — score = priority integer from `ReviewQueue.priority`.

| Operation | Redis command | Replaces |
|---|---|---|
| Enqueue item | `ZADD review_queue {score} {entity_id}` | `INSERT INTO review_queue` |
| Pop highest priority | `ZPOPMAX review_queue` | `SELECT ... ORDER BY priority LIMIT 1` |
| Peek queue | `ZRANGE review_queue 0 -1 WITHSCORES REV` | `SELECT ... ORDER BY priority` |

PostgreSQL `review_queue` table remains as the durable audit record. Redis is the fast dispatch layer on top.

### Implementation

**Status:** ⏳ Not yet implemented — requires `apps/api` review queue router and service, which do not exist yet.

---

## Redis Key Namespace Summary

```
# Deduplication
dedup:fact:{sha256}              → "1"         90d TTL
dedup:tag:{sha256}               → "1"         90d TTL
dedup:url:{sha256}               → "1"         90d TTL

# Distributed locks
lock:enrichment:{doc_id}:{fw}    → worker_id   30m TTL
lock:qdrant:{doc_id}             → worker_id   15m TTL
lock:graph:{doc_id}              → worker_id   15m TTL

# Result caches
cache:frameworks:{doc_id}        → JSON list   90d TTL
cache:embedding:{chunk_hash}     → JSON vector no TTL
cache:audit:{content_hash}       → JSON        90d TTL
cache:graph:schema_ready         → timestamp   no TTL
cache:search_endpoint:{domain}   → JSON        30d TTL

# Rate limiting
rate:{domain}:req_count          → integer     1s TTL (sliding window)

# Priority queue
review_queue                     → Sorted Set  (score = priority)
```

---

## Implementation Order

| Phase | Description | Files |
|---|---|---|
| 1 | Shared Redis client + helpers | `src/ks/common/redis_client.py` (new) |
| 2 | Deduplication — facts, tags, URLs | `enrichment/activities.py`, `discovery/activities.py` |
| 3 | Distributed locks — enrichment, Qdrant, Neo4j | `enrichment/activities.py`, `chunking/activities.py`, `graph/activities.py` |
| 4 | Result caching — LLM calls, embeddings, schema | `enrichment/activities.py`, `chunking/activities.py`, `acquisition/activities.py`, `graph/activities.py` |
| 5 | Rate limiting — discovery and acquisition HTTP | `discovery/activities.py`, `acquisition/activities.py` |
| 6 | Priority queue — review queue dispatch | `apps/api` review router + service |

---

## Expected Outcomes

- **Deduplication:** Eliminates the `dedup_db.py` cleanup script entirely; duplicate facts/tags never reach the DB.
- **Locks:** Removes race conditions between parallel Temporal workers on the same document.
- **Caching:** Reduces LLM API costs by 40–60% on repeated or re-triggered pipeline runs.
- **Rate limiting:** Prevents source IP bans during high-concurrency crawl sessions.
- **Priority queue:** Sub-millisecond review queue dispatch vs full table scan.

---

## Implementation Summary

| Phase | Status | Files Modified |
|---|---|---|
| 1 — Shared Redis client | ✅ Complete | `src/ks/common/__init__.py` (new), `src/ks/common/redis_client.py` (new) |
| 2 — Deduplication | ✅ Complete | `src/ks/enrichment/activities.py`, `src/ks/discovery/activities.py` |
| 3 — Distributed locks | ✅ Complete | `src/ks/enrichment/activities.py`, `src/ks/chunking/activities.py`, `src/ks/graph/activities.py` |
| 4 — Result caching | ✅ Complete | `src/ks/enrichment/activities.py`, `src/ks/chunking/activities.py`, `src/ks/acquisition/activities.py`, `src/ks/graph/activities.py`, `src/ks/discovery/activities.py` |
| 5 — Rate limiting | ✅ Complete | `src/ks/discovery/activities.py`, `src/ks/acquisition/activities.py` |
| 6 — Priority queue | ⏳ Pending | Requires new `apps/api` review queue router + service |

### Key Implementation Notes

- **Fail-open design:** All Redis helpers catch exceptions and return safe defaults. Redis downtime falls back to DB-level dedup/uniqueness constraints — the pipeline keeps running.
- **Commit-gated dedup marks:** Redis dedup keys for facts/tags are only written *after* `session.commit()` succeeds. A DB rollback leaves Redis unchanged, so facts are not silently dropped on retry.
- **Embedding cache is batched:** `split_and_embed()` checks Redis per-chunk, then calls `litellm.embedding()` with only the uncached subset in a single API call. This avoids N individual embedding API calls while still benefiting from partial cache hits.
- **Lock granularity:** Enrichment locks are per `(doc_id, framework)` so parallel framework agents on the same document do not block each other — only duplicate workers running the same framework are serialised.
