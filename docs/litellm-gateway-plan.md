# LiteLLM Gateway Integration Plan

## Current State

LiteLLM **is already installed** (`litellm>=1.40.0` in `pyproject.toml`) and used as a Python library across the pipeline, but **not as a unified gateway**. The SDK is invoked directly with `litellm.completion()` / `litellm.embedding()` at 11+ call sites, with copy-pasted patterns and no centralised routing, cost tracking, or safety controls.

### Inventory of current LiteLLM call sites

| Stage | File:line | Function | Model selection | Key issues |
|---|---|---|---|---|
| Acquisition | `acquisition/activities.py:71` | `audit_document_intelligence` | Hardcoded `gpt-4o-mini`, but uses `secondary_api_key` (Gemini key) | **Bug:** model/key mismatch |
| Discovery | `discovery/activities.py:457` | `calculate_priority_score` | `settings.model.primary_model` | OK |
| Discovery | `discovery/activities.py:494` | `evaluate_source_authority` | `settings.model.primary_model` | OK |
| Extraction | `extraction/activities.py:93` | `perform_full_extraction` (LLM cleanup branch) | Hardcoded `deepseek/deepseek-chat` | Bypasses settings |
| Extraction | `extraction/activities.py:175` | `enhance_text_chunk` | Hardcoded `deepseek/deepseek-chat` | Bypasses settings |
| Extraction | `extraction/activities.py:268` | `verify_extraction_activity` | Hardcoded `deepseek/deepseek-chat` | Duplicate of enrichment verify |
| Enrichment | `enrichment/activities.py:119` | `detect_relevant_frameworks` | `payload.get("model", primary_model)` | OK |
| Enrichment | `enrichment/activities.py:298` | `run_llm_enrichment` | Conditional branching on substring `"deepseek"` / `"gpt"` / `"openai"` | Brittle string matching; no fallback chain despite CLAUDE.md saying one exists |
| Enrichment | `enrichment/activities.py:549` | `verify_extraction_activity` | Hardcoded `deepseek/deepseek-chat` | Duplicate of extraction verify |
| Enrichment | `enrichment/normalization.py:34` | `normalize_entity` | `secondary_model` with `primary_api_key` | **Bug:** Gemini model with DeepSeek key |
| Chunking | `chunking/activities.py:169` | `split_and_embed` | `embedding_model` from settings | OK (already cached via Redis) |

### What's missing (per the architecture diagram)

The "Model Gateway" box in the system architecture promises four capabilities. None are actually built:

1. **Model routing & fallback** — `ModelSettings.confidence_fallback_threshold` and `max_retries` exist in `src/ks/config/settings.py` but are **never referenced anywhere**. CLAUDE.md describes a DeepSeek → Gemini → GPT-4o-mini chain; the code has no such chain. If the primary call raises, the activity returns `{"success": False}` and the document fails.
2. **Cost tracking & limits** — `prompt_tokens` / `completion_tokens` / `total_tokens` are saved on `EnrichmentRun`, but not on `FetchRun`, `ExtractionRun`, `ChunkRun`, or `CandidateDiscoveryRun`. There is no per-model `$ cost` field, no aggregation, no daily/document budget cap.
3. **Safety & guardrails** — no PII redaction before sending to third-party providers, no input length guards (only ad-hoc `text[:25000]` truncations), no output validation beyond JSON-parse, no jailbreak/injection filter.
4. **Prompt templates** — every prompt is an inline f-string. The two `verify_extraction_activity` implementations (one in extraction, one in enrichment) drift from each other. The seven framework-specific prompt branches in `run_llm_enrichment` live in a 200-line if/elif. There is no shared template, no versioning, no test harness.

### Existing assets to build on

- `litellm.Router` (already installed at `.venv/.../litellm/router.py`) — supports fallback, retries, weighted load balancing, model groups.
- `litellm.BudgetManager` (already installed) — daily/monthly spend tracking with persistence backends.
- LiteLLM proxy server (same package) — OpenAI-compatible HTTP gateway for centralised observability across services.
- Redis client + cache helpers already in place (`src/ks/common/redis_client.py`) — drop-in target for prompt-response caching.
- `ModelSettings` already wires the three-provider config from `.env` — only the consumer needs to change.

---

## Goals

Convert the scattered direct `litellm.*()` calls into a single in-process gateway that delivers the four capabilities the architecture diagram promises, **without standing up a new infra service in v1**.

| Goal | Concrete deliverable |
|---|---|
| Model routing & fallback | One `complete()` call that automatically tries DeepSeek → Gemini → GPT-4o-mini on retryable failures |
| Cost tracking | Per-call cost row in Postgres, attributable to `(stage, run_id, model, prompt_id)` |
| Budget limits | Hard cap per pipeline run and per day; calls past the cap return a typed error, not silent overspend |
| Safety / guardrails | PII redaction pre-call, output schema validation post-call, input length cap with deterministic truncation |
| Prompt templates | All prompts in `src/ks/prompts/*.py` with explicit `version` strings, rendered through one function |
| Response caching | Prompt+model → response cached in Redis with content-hash key, opt-out per call |
| Observability | Admin UI page showing $ spend, token usage, fallback rate, cache hit rate per stage |

---

## Architecture decision: in-process Router first, proxy later

Two viable shapes for the gateway:

**Option A — In-process `litellm.Router`** (recommended for v1)
- New module `src/ks/common/llm_gateway.py` wrapping `litellm.Router` with our own retry/cost/cache/safety logic on top.
- Activities import `from ks.common.llm_gateway import gateway` and call `await gateway.complete(prompt_key, vars)` instead of `litellm.completion(...)`.
- Zero new infra; works inside Temporal workers as a singleton.
- Cost tracking persists to Postgres directly (new `llm_call` table), survives worker restarts.

**Option B — LiteLLM proxy server** (Docker service)
- Add `litellm-proxy` to `infrastructure/docker/docker-compose.yml`; activities point at `http://litellm:4000/v1` via OpenAI-compatible client.
- Centralised budget/spend dashboard built into LiteLLM proxy (no admin UI work).
- New service to deploy, monitor, and authenticate against; one more failure mode in the path.

**Decision:** ship Option A in Phases 1–6 below. Option B is a future migration once we have multi-language clients or want to expose the gateway outside the worker process. The wrapper API is intentionally shaped like the OpenAI client so swapping to a proxy is a config change, not a code change.

---

## Phase 1 — Gateway module + provider config

### Implementation

**Status:** ✅ Complete

**Files created:**
- `src/ks/common/llm_types.py` — `LLMUsage`, `LLMResponse` dataclasses; `LLMBudgetExceeded` exception
- `src/ks/common/llm_gateway.py` — `_build_router()`, `_get_router()`, `complete()`, `embed()` with all 6 pipeline phases integrated

**Files modified:**
- `src/ks/config/settings.py` — added `fallback_chain_csv`, `fast_chain_csv`, `daily_budget_usd`, `per_doc_budget_usd`, `budget_enforcement`, `prompt_cache_ttl_seconds`, `redact_pii` to `ModelSettings` with `@property` accessors for chain lists

**Design decisions:**
- `litellm.Router` initialised lazily on first call via `_get_router()` singleton — avoids import-time dependency on env vars.
- Fallbacks wired as `[{"default": ["default-fb-1", "default-fb-2"]}]`; Router handles failover on `RateLimitError` / `ServiceUnavailableError` automatically.
- `fast` group maps tertiary (GPT-4o-mini) first, then secondary (Gemini Flash) — opposite of `default` group so low-stakes calls use the cheapest provider.
- All phases (2–6) are integrated in the same `complete()` pipeline — no separate activation needed per phase.

**New files:**
- `src/ks/common/llm_gateway.py` — the gateway wrapper
- `src/ks/common/llm_types.py` — `LLMRequest`, `LLMResponse`, `LLMUsage`, `LLMError` dataclasses

**Changes:**
- `src/ks/config/settings.py` — extend `ModelSettings` with `fallback_chain: list[str]`, `daily_budget_usd`, `per_doc_budget_usd`, `prompt_cache_ttl_seconds`, `redact_pii: bool`.

**Gateway surface area (in-process API):**

```python
# Public API — what activities will call
async def complete(
    prompt_id: str,           # e.g. "enrichment.framework_detection.v1"
    variables: dict,          # template variables
    *,
    stage: str,               # "enrichment" | "discovery" | ...
    run_id: str | None = None,
    response_format: type | dict | None = None,
    model_group: str = "default",   # "default" | "fast" | "vision"
    cache: bool = True,
    max_tokens: int | None = None,
) -> LLMResponse: ...

async def embed(
    texts: list[str],
    *,
    stage: str,
    run_id: str | None = None,
    model_group: str = "embedding",
    cache: bool = True,
) -> list[list[float]]: ...
```

**Internal pipeline per call:**
1. Render prompt from template registry (Phase 5)
2. PII redact + length-cap input (Phase 4)
3. Cache lookup in Redis by `sha256(model_group + rendered_prompt + response_format_schema)` (Phase 6)
4. Budget check against daily + per-run caps (Phase 3)
5. `litellm.Router.acompletion()` with fallback chain
6. Output schema validation
7. Cost calculation via `litellm.completion_cost()`; row inserted into `llm_call` table (Phase 2)
8. Cache write + return

**Model groups** (configured once, used everywhere):
- `default` — DeepSeek V3 → Gemini 1.5 Pro → GPT-4o-mini (the documented chain, **actually wired**)
- `fast` — GPT-4o-mini → Gemini 1.5 Flash (for low-stakes calls: priority scoring, normalization, audit)
- `vision` — GPT-4o → Gemini 1.5 Pro (reserved; not used yet but slot ready for vision intake)
- `embedding` — `text-embedding-3-small` only (single provider; embeds rarely fail)

---

## Phase 2 — Cost tracking

### Implementation

**Status:** ✅ Complete

**Files created:**
- `infrastructure/migrations/versions/a1b2c3d4e5f6_add_llm_call_table.py` — creates `llm_call` table with all columns and two indexes
- `apps/api/routers/llm_usage.py` — 9 endpoints: `spend/daily`, `spend/by-stage`, `spend/by-document/{id}`, `fallback-rate`, `unit-economics`, `prompt-leaderboard`, `cache-hit-by-prompt`, `recent-calls`, `provider-health`, `budget-config`

**Files modified:**
- `src/ks/domain/models.py` — added `LLMCall` ORM model
- `apps/api/main.py` — registered `llm_usage_router` at `/api/v1/llm`
- `src/ks/common/llm_gateway.py` — `_record_call()` writes one row after every call (fail-open)

**Design decisions:**
- `cost_usd` uses `Float` (consistent with existing `authority_score` etc.); sufficient precision for sub-cent amounts.
- `provider-health` endpoint joins on `MAX(created_at) WHERE status='success' GROUP BY model_used` — cheap aggregation query, no extra table.
- `budget-config` is read-only (returns env settings); writable config requires a `system_config` table deferred to a future migration.

**New table:** `llm_call` (Alembic migration)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `created_at` | timestamp | |
| `stage` | str | `discovery`, `acquisition`, `extraction`, `enrichment`, `chunking`, `graph` |
| `run_id` | UUID (nullable) | FK to whichever `*_run` table the stage owns |
| `document_id` | UUID (nullable) | for spend-per-document queries |
| `prompt_id` | str | e.g. `enrichment.framework_detection.v1` |
| `model_used` | str | actual model that responded (post-fallback) |
| `model_requested` | str | first model attempted |
| `fallback_depth` | int | 0 if primary succeeded, 1 if secondary, etc. |
| `prompt_tokens` | int | |
| `completion_tokens` | int | |
| `total_tokens` | int | |
| `cost_usd` | numeric(10,6) | from `litellm.completion_cost()` |
| `latency_ms` | int | |
| `cache_hit` | bool | |
| `status` | str | `success` | `failed` | `budget_exceeded` | `cached` |

**Aggregation views (SQL, no extra code path):**
- `vw_llm_spend_daily` — `SUM(cost_usd) GROUP BY date, stage, model_used`
- `vw_llm_spend_per_document` — `SUM(cost_usd) GROUP BY document_id`

**API endpoints (`apps/api/routers/llm_usage.py`):**
- `GET /api/v1/llm/spend/daily?days=30`
- `GET /api/v1/llm/spend/by-stage`
- `GET /api/v1/llm/spend/by-document/{document_id}`
- `GET /api/v1/llm/fallback-rate?stage=enrichment`

---

## Phase 3 — Budget limits

### Implementation

**Status:** ✅ Complete

**Files modified:**
- `src/ks/common/llm_gateway.py` — budget check block in `complete()` before the Router call; Redis counters updated post-call via `redis_client.incr_spend()`
- `src/ks/common/redis_client.py` — added `incr_spend(key, amount, ex)` using `INCRBYFLOAT` for atomic float increment

**Design decisions:**
- `hard` mode raises `LLMBudgetExceeded` (non-retryable) — propagates to Temporal as `ApplicationError`.
- `soft` mode logs a warning and proceeds — pipeline continues with overspend logged.
- `off` mode skips budget check entirely (default for dev).
- Redis counter keys: `llm:spend:daily:{YYYY-MM-DD}` (TTL 24h), `llm:spend:doc:{document_id}` (TTL 7d).
- Fail-open: Redis errors in budget check are caught and logged; the LLM call proceeds.

**Settings additions** (env-driven):
```
LLM_DAILY_BUDGET_USD=50.0
LLM_PER_DOC_BUDGET_USD=0.50
LLM_BUDGET_ENFORCEMENT=hard   # hard | soft | off
```

**Implementation:**
- Before each `complete()` call, the gateway queries Redis counters:
  - `llm:spend:daily:{YYYY-MM-DD}` — incremented after every successful call
  - `llm:spend:doc:{document_id}` — TTL 7 days
- If `hard` and cap exceeded, raise `LLMBudgetExceeded` (non-retryable Temporal `ApplicationError`).
- If `soft`, log a warning and continue.
- The Redis counters are updated post-call from the same `cost_usd` written to Postgres, so the budget never drifts more than one call past the cap.
- Postgres is the source of truth; Redis is the fast-path. A daily cron resyncs Redis from Postgres (handles drift after Redis restarts).

**Fail-open clause:** if the Redis budget check itself fails (Redis down), the gateway logs and proceeds — Phase 1's design constraint of "Redis downtime degrades gracefully" carries over here.

---

## Phase 4 — Safety & guardrails

### Implementation

**Status:** ✅ Complete

**Files created:**
- `src/ks/common/safety.py` — `redact_pii()`, `check_injection()`, `detect_refusal()` with compiled regex patterns

**Files modified:**
- `src/ks/common/llm_gateway.py` — PII redaction and injection check pre-call; refusal detection post-call

**Design decisions:**
- PII redaction uses four compiled regex patterns (email, SSN, phone, CC). Clinical strings like "70-100 mg/dL" are not flagged — patterns are deliberately narrow.
- Injection guard uses substring matching on the rendered prompt (post-template); returns `LLMResponse(status="blocked", skipped=True)` without making any API call.
- Refusal detection matches common LLM refusal prefix patterns; propagates `status="refusal"` so activities can handle it explicitly rather than storing "I can't help with that" as a clinical fact.

**Pre-call:**
1. **PII redaction.** Use a small allow-list-driven regex set — emails, US SSNs, phone numbers, credit card numbers — replaced with `[REDACTED_EMAIL]` etc. Implemented in `src/ks/common/safety.py`. The redaction map is logged (not stored) so the response can be re-hydrated if needed.
2. **Length cap.** Each prompt template declares `max_input_chars`. The gateway truncates inputs at a sentence boundary near the cap before rendering. Caps:
   - Framework detection: 10k chars (matches current `text[:10000]`)
   - Enrichment: 25k chars (matches current `text[:25000]`)
   - Verification: 12k chars (matches current `source_text[:12000]`)
   - Audit: 5k chars (matches current `content[:5000]`)
3. **Prompt-injection heuristic.** Reject inputs that contain `<|im_start|>`, `### system:`, or `Ignore previous instructions` style markers. Log + skip the call, return a deterministic `LLMResponse(skipped=True)`.

**Post-call:**
1. **Schema validation.** If `response_format` is a Pydantic model or JSON schema, parse + validate. On failure: retry once with `"Return ONLY valid JSON matching this schema"` appended; on second failure mark the call failed.
2. **Output PII scan.** Same regex set applied to the model output before persistence (defense in depth — the model could echo input PII even if we redacted on the way in).
3. **Toxicity / refusal detection.** If the response starts with `"I can't help"` / `"I'm unable to"` / `"As an AI"`, mark as `refusal` and propagate as a typed error rather than persisting the refusal text as a "fact".

---

## Phase 5 — Prompt templates

### Implementation

**Status:** ✅ Complete

**Files created:**
- `src/ks/prompts/__init__.py` — `REGISTRY` dict + `render(prompt_id, variables)` returning `(text, model_group, response_format)`
- `src/ks/prompts/enrichment_framework_detection_v1.py`
- `src/ks/prompts/enrichment_extraction_v1.py` — includes all 7 framework context blocks and clinical source context as dict lookups
- `src/ks/prompts/enrichment_verification_v1.py` — consolidated shared template (was duplicated in extraction + enrichment)
- `src/ks/prompts/discovery_priority_score_v1.py`
- `src/ks/prompts/discovery_source_authority_v1.py`
- `src/ks/prompts/acquisition_intelligence_audit_v1.py`
- `src/ks/prompts/extraction_chunk_enhance_v1.py`
- `src/ks/prompts/extraction_full_cleanup_v1.py`
- `src/ks/prompts/normalization_canonical_v1.py`

**Files modified:**
- `src/ks/enrichment/activities.py` — removed `import litellm`; 200-line `if/elif` framework context block and inline prompt deleted; 3 call sites → `gateway_complete()`; also fixed `run_llm_enrichment` to remove unused `model`, `truncated_text`, `clinical_context`, `framework_context` locals
- `src/ks/discovery/activities.py` — removed `import litellm`; 2 call sites → `gateway_complete()`
- `src/ks/extraction/activities.py` — removed `import litellm`; 3 call sites → `gateway_complete()`; `verify_extraction_activity` now uses the shared `enrichment.verification.v1` template
- `src/ks/acquisition/activities.py` — removed `import litellm`; 1 call site → `gateway_complete()`; fixed latent bug where `gpt-4o-mini` was used with `secondary_api_key` (Gemini key)
- `src/ks/chunking/activities.py` — removed `import litellm`; `litellm.embedding()` → `gateway_embed()`; Redis cache logic moved inside gateway
- `src/ks/enrichment/normalization.py` — removed `import litellm` and `from ks.config.settings import get_settings`; 1 call site → `gateway_complete()`; fixed latent bug where `secondary_model` (Gemini) was called with `primary_api_key` (DeepSeek key)

**New package:** `src/ks/prompts/`

Layout:
```
src/ks/prompts/
  __init__.py              # registry + render()
  enrichment/
    framework_detection_v1.py
    extraction_v1.py
    verification_v1.py
    framework_context/
      nutrition_v1.py
      pharmacology_v1.py
      diagnostics_v1.py
      ...
  discovery/
    priority_score_v1.py
    source_authority_v1.py
  acquisition/
    intelligence_audit_v1.py
  extraction/
    chunk_enhance_v1.py
  normalization/
    canonical_v1.py
```

Each prompt module exposes:
```python
PROMPT_ID = "enrichment.framework_detection.v1"
MODEL_GROUP = "fast"             # routing hint
MAX_INPUT_CHARS = 10_000
RESPONSE_FORMAT = {"type": "json_object"}
TEMPLATE = """..."""             # jinja-style {{ var }} placeholders

def render(variables: dict) -> str: ...
```

**Migration scope (files that lose inline prompts):**
- `enrichment/activities.py` — 3 prompts move out (framework detection, enrichment, verification) + 7 framework-context blocks
- `discovery/activities.py` — 2 prompts move out (priority score, source authority)
- `acquisition/activities.py` — 1 prompt moves out (intelligence audit)
- `extraction/activities.py` — 2 prompts move out (chunk enhancement, verification) — verification is consolidated with the enrichment one into a single shared template
- `enrichment/normalization.py` — 1 prompt moves out (canonical entity)

**Versioning rule:** once a prompt is referenced by stored data (`KnowledgeFact.critique`, `KnowledgeSummary.prompt_version`), it is **frozen**. Edits go into `_v2.py`; the registry resolves the live version via `prompt_version` columns already present in the DB.

---

## Phase 6 — Response caching

### Implementation

**Status:** ✅ Complete

**Files modified:**
- `src/ks/common/llm_gateway.py` — cache lookup before Router call, cache write after successful response; both in `complete()` and `embed()`

**Design decisions:**
- Cache key: `cache:llm:{sha256(model_group + rendered_prompt + str(response_format))}`. Keying on `model_group` (not resolved model) means a Gemini fallback response is reusable under the same key when the primary is down.
- `embed()` per-chunk caching moved from `chunking/activities.py` into the gateway — single source of truth.
- `cache=False` passed by `verify_extraction_activity` callers — verifier re-runs even when source text is identical because the fact list changes between runs.
- Cache writes are fire-and-forget wrapped in `try/except` — a Redis write failure does not fail the LLM call.

Builds on the existing Redis cache helpers (`src/ks/common/redis_client.py`).

| Cache key | Value | TTL | When used |
|---|---|---|---|
| `cache:llm:{sha256(model_group + rendered_prompt + response_format)}` | JSON-serialised `LLMResponse` | 30 days | Every gateway call where `cache=True` |
| `cache:embedding:{sha256(text)}` | embedding vector | 90 days | **already exists** — moves under the gateway |

**Cache key choice rationale:**
- Keying on `model_group` (not the resolved model) means a fallback to Gemini doesn't poison the DeepSeek cache slot — but it also means a successful Gemini answer is reusable next time DeepSeek is down. Trade-off accepted.
- Keying on the rendered prompt (post-template, post-redaction) means template version bumps invalidate cache automatically.

**Opt-out cases:**
- `verify_extraction_activity` — the verifier should re-run when facts are re-extracted, even if the source text is identical, because the verification depends on the new fact list, not just the source.
- Any call with `temperature > 0` (we don't have any today, but the gate is in place).

---

## Phase 7 — Observability UI

### Implementation

**Status:** ✅ Complete

**Files created:**
- `apps/admin-ui/src/pages/LLMGateway.jsx` — full drill-down page: KPI row, 14-day spend stacked bar chart, unit economics, fallback heatmap, prompt leaderboard with metric toggle, cache hit rate bars, recent calls table with status filters

**Files modified:**
- `apps/admin-ui/src/pages/Dashboard.jsx` — added 4 LLM Gateway KPI tiles (total spend, fallback rate, cache hit rate, budget % used) fetching from new endpoints; polling at 15s interval; "View full dashboard →" link
- `apps/admin-ui/src/pages/SystemInspector.jsx` — added "LLM HEALTH" third tab showing provider health table (last success / last error per model)
- `apps/admin-ui/src/App.jsx` — imported `LLMGateway`, added `/llm-gateway` route and "LLM Gateway" sidebar nav item

**Design decisions:**
- No new charting dependency needed — Recharts was already in the project (used by `Dashboard.jsx`).
- `LLMGateway.jsx` fetches all 8 data sources with `Promise.allSettled` so a single failing endpoint doesn't blank the whole page.
- Leaderboard metric is local state — switching between "spend", "count", "p95" re-fetches from the backend rather than sorting client-side so the top-10 list changes correctly.

The data captured in Phases 2–3 (`llm_call` table, Redis budget counters, fallback depth, cache hits) needs to surface in the admin UI; the endpoints in `apps/api/routers/llm_usage.py` cover the data, but nothing in `apps/admin-ui/src/pages/` consumes them today.

Ship in three levels — the cheap ones land alongside Phase 2's endpoints, the heavy one is a separate PR.

### Level 1 — KPI tiles on `Dashboard.jsx`

Four hero tiles at the top of the existing dashboard, each clickable to drill into Level 2:

| Tile | Source endpoint | Visual |
|---|---|---|
| Today's $ spend | `GET /api/v1/llm/spend/daily?days=1` | Single number, % delta vs yesterday |
| Daily budget burn | Redis counter + `LLM_DAILY_BUDGET_USD` | Progress bar 0–100%, red ≥ 80% |
| Fallback rate (24h) | `GET /api/v1/llm/fallback-rate` | Single % with sparkline |
| Cache hit rate (24h) | derived (`cache_hit=true` / total in `llm_call`) | Single % with sparkline |

### Level 2 — New page `LLMGateway.jsx`

The drill-down. New route in `App.jsx`, new sidebar entry between `KnowledgeIntelligence` and `SystemInspector`.

| Widget | Description | Backing data |
|---|---|---|
| Spend chart | Stacked bar, $/day × 30 days, split by stage *or* model (toggle) | `vw_llm_spend_daily` |
| Unit economics table | $/document, $/fact, $/chunk, $/embedding | `llm_call.cost_usd` joined to `DocumentRegistry`, `KnowledgeFact`, `KnowledgeChunk` |
| Fallback heatmap | `stage × model_requested → mean(fallback_depth)` — shows at a glance which stage's primary is flaky | `llm_call` group-by |
| Prompt leaderboard | Top 10 `prompt_id` by spend, call count, p95 latency | `llm_call` group-by |
| Cache hit by prompt | `prompt_id → cache_hit_rate` — surfaces prompts that *should* be cacheable but aren't (template variables drifting per call) | `llm_call` group-by |
| Recent calls table | Last 100 `llm_call` rows; filter chips for `status=failed \| refusal \| budget_exceeded` | `llm_call` direct query |
| Budget controls | Inline edit of `LLM_DAILY_BUDGET_USD` / `LLM_PER_DOC_BUDGET_USD` / `LLM_BUDGET_ENFORCEMENT` | New `system_config` table (key/value), writes gated by `ADMIN_SECRET` |

New endpoints required beyond Phase 2:
- `GET /api/v1/llm/unit-economics`
- `GET /api/v1/llm/prompt-leaderboard?metric=spend|count|p95`
- `GET /api/v1/llm/cache-hit-by-prompt`
- `GET /api/v1/llm/recent-calls?status=&limit=100`
- `GET|PUT /api/v1/llm/budget-config`

### Level 3 — Section in `SystemInspector.jsx`

Ops-facing health, not analytics. Three rows:

- **Provider health:** last-success-timestamp + last-error per model in the chain (`MAX(created_at) WHERE status='success' GROUP BY model_used`).
- **Cache footprint:** approximate key count + memory for `cache:llm:*` and `cache:embedding:*` (via `SCAN` + `MEMORY USAGE`).
- **Live counters:** current values of `llm:spend:daily:{today}` and the top 5 active `llm:spend:doc:{doc_id}` keys.

### Implementation order

1. **Bundled with Phase 2:** Level 1 tiles + Level 3 section ship in the same PR that adds the cost-tracking API endpoints. They reuse those endpoints and need no new chart components.
2. **Separate PR after Phase 6:** Level 2 page is the big lift — 5 new endpoints, 6 chart/table components, sidebar + routing wiring. Defer until Phases 1–6 are validated in production so the dashboard reflects real cost shape, not synthetic data.

### Charting library

The admin UI has no charting dep yet. Recommend **Recharts** (declarative, idiomatic React, ~50 KB gzipped) added to `apps/admin-ui/package.json` as part of Level 2. Chart.js is a smaller alternative but less React-native.

---

## Configuration changes

`.env.example` additions:
```
# --- LLM Gateway ---
LLM_FALLBACK_CHAIN=deepseek/deepseek-chat,gemini/gemini-1.5-pro,gpt-4o-mini
LLM_FAST_CHAIN=gpt-4o-mini,gemini/gemini-1.5-flash
LLM_DAILY_BUDGET_USD=50.0
LLM_PER_DOC_BUDGET_USD=0.50
LLM_BUDGET_ENFORCEMENT=hard
LLM_PROMPT_CACHE_TTL_SECONDS=2592000    # 30 days
LLM_REDACT_PII=true
LLM_INJECTION_GUARD=true
```

`docker-compose.yml` — no changes in v1 (in-process gateway). Phase 7 (deferred) would add:
```yaml
litellm-proxy:
  image: ghcr.io/berriai/litellm:main-stable
  ports: ["14000:4000"]
  env_file: ../../.env
```

---

## Migration sequence (no behavioural change per step)

Each phase is shippable on its own.

| Phase | Status | Description | Files |
|---|---|---|---|
| 1 | ✅ Complete | Gateway module + Router + model groups | `src/ks/common/llm_gateway.py` (new), `src/ks/common/llm_types.py` (new), `src/ks/config/settings.py` |
| 2 | ✅ Complete | `llm_call` table + cost tracking inside gateway | new Alembic migration, `apps/api/routers/llm_usage.py` (new), `src/ks/domain/models.py`, `apps/api/main.py` |
| 3 | ✅ Complete | Budget enforcement on top of cost tracking | `src/ks/common/llm_gateway.py`, `src/ks/common/redis_client.py` |
| 4 | ✅ Complete | PII / injection / refusal guards | `src/ks/common/safety.py` (new), `src/ks/common/llm_gateway.py` |
| 5 | ✅ Complete | Prompt templates extracted; all `litellm.*` calls removed from activities | `src/ks/prompts/` (new package, 9 modules), all `*/activities.py`, `enrichment/normalization.py` |
| 6 | ✅ Complete | Response caching wired into gateway; embedding cache moved under gateway | `src/ks/common/llm_gateway.py`, `src/ks/chunking/activities.py` |
| 7 | ✅ Complete | Observability UI — KPI tiles, dedicated `LLMGateway` page, ops section in SystemInspector | `apps/admin-ui/src/pages/Dashboard.jsx`, `apps/admin-ui/src/pages/LLMGateway.jsx` (new), `apps/admin-ui/src/pages/SystemInspector.jsx`, `apps/admin-ui/src/App.jsx` |
| 8 (deferred) | ⏳ Pending | Optional swap to LiteLLM proxy service | `infrastructure/docker/docker-compose.yml`, `src/ks/common/llm_gateway.py` (HTTP backend) |

Phases 1–4 are invisible to the rest of the codebase — they add the gateway, observability, and guards but leave call sites untouched. Phase 5 is the only step that touches every stage's `activities.py`, and it's a mechanical rewrite (one prompt at a time, one PR per stage if desired). Phase 7 is the only step that touches `apps/admin-ui/`; its Level 1 + Level 3 work piggy-backs on Phase 2's PR, while Level 2 (the dedicated dashboard page) ships independently once enough real call data has accumulated.

---

## Expected outcomes

- **Reliability:** Eliminates the silent single-point-of-failure where a DeepSeek outage kills the pipeline. The documented three-model chain becomes real.
- **Cost visibility:** First time we can answer "what does it cost to ingest one document?" — currently unknown.
- **Cost control:** Hard daily cap stops a runaway loop from burning $$$ on retries.
- **Safety:** PII leaving the worker to third-party providers stops being incidental.
- **Maintainability:** The two divergent copies of `verify_extraction_activity`, the 200-line if/elif in `run_llm_enrichment`, and the brittle `"deepseek" in model.lower()` string matching all go away.
- **Prompt iteration speed:** Versioned templates can be A/B-tested without touching activity code.

---

## Open questions / decisions needed before implementation

1. **Which embedding provider in the fallback chain?** Today `text-embedding-3-small` is OpenAI-only with no fallback. Worth wiring a Gemini embedding fallback, or keep single-provider?
2. **PII redaction scope.** Clinical text intentionally contains personal-sounding strings (patient case studies, drug names that look like phone numbers). What's the false-positive tolerance?
3. **Budget granularity.** Per-document budget is straightforward; do we also want per-stage budgets (e.g. "enrichment can't exceed 60% of total spend")?
4. **Prompt template engine.** Plain `str.format()`, Jinja2, or just Python f-string functions? Jinja2 buys conditionals (useful for the 7 framework-context blocks) but adds a dep.
5. **Caching consent for clinical data.** Caching prompts + responses in Redis means clinical content sits in Redis for 30 days. Acceptable for a self-hosted Redis; needs review if Redis ever moves to managed.
6. **Existing bugs found during inventory** (`acquisition/activities.py:71` gpt-4o-mini + Gemini key; `normalization.py:34` Gemini model + DeepSeek key) — fix as part of Phase 5, or fix immediately in a separate PR? Recommended: separate small PR before Phase 5 so the migration is purely mechanical.
