# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Install & Setup
```bash
pip install -e ".[dev]"           # Install Python package with dev dependencies
alembic upgrade head              # Apply all database migrations
python infrastructure/scripts/seed_db.py  # Seed clinical sources and frameworks
```

### Run Services
```bash
# Start all infrastructure (PostgreSQL, Temporal, MinIO, Qdrant, Neo4j, Redis)
cd infrastructure/docker && docker compose up -d

# FastAPI backend (port 8000, auto-reload)
uvicorn apps.api.main:app --reload --port 8000

# Temporal background worker
python -m apps.worker.main

# Admin UI (port 5173)
cd apps/admin-ui && npm install && npm run dev
```

### Testing & Linting
```bash
pytest                            # Run all tests (asyncio_mode=auto)
pytest tests/path/to/test_file.py # Run a single test file
ruff check .                      # Lint
ruff format .                     # Format
mypy src/                         # Type check
```

### Database Migrations
```bash
alembic revision --autogenerate -m "description"  # Generate new migration
alembic upgrade head                               # Apply migrations
alembic downgrade -1                               # Roll back one step
```

## Architecture

### Pipeline Flow
Raw content moves through six sequential pipeline stages, each implemented as a Temporal workflow + activities pair:

```
Discovery → Acquisition → Extraction → Enrichment → Chunking → Graph Sync
```

1. **Discovery** (`src/ks/discovery/`) — crawls sources via sitemap, native site search, or DuckDuckGo; produces candidate URLs; supports `BROAD`, `FOCUSED`, and `HYBRID` modes.
2. **Acquisition** (`src/ks/acquisition/`) — fetches and stores raw HTML/PDF to MinIO (`raw-artifacts` bucket); large binaries never transit Temporal's gRPC history.
3. **Extraction** (`src/ks/extraction/`) — pulls from MinIO, strips boilerplate (BeautifulSoup/lxml), runs OCR (Tesseract) for images, and writes clean text back to MinIO (`extracted-text` bucket).
4. **Enrichment** (`src/ks/enrichment/`) — routes through a multi-model LLM gateway (LiteLLM: DeepSeek V3 primary → Gemini 1.5 secondary → GPT-4o-mini tertiary); extracts clinical entities with confidence scores; entities ≥ 0.9 go directly to graph, lower-confidence entities enter the `review_queue`.
5. **Chunking** (`src/ks/chunking/`) — splits extracted text into overlapping chunks, embeds with `text-embedding-3-small`, indexes into Qdrant collection `knowledge_chunks`.
6. **Graph Sync** (`src/ks/graph/`) — merges clinical nodes (Symptoms, Biomarkers, Interventions, Protocols) and edges into Neo4j.

### Module Structure
Each pipeline stage in `src/ks/<stage>/` follows the same pattern:
- `activities.py` — Temporal `@activity.defn` functions (the actual work)
- `workflows.py` — Temporal `@workflow.defn` orchestrators (retry/timeout logic)
- `router.py` — FastAPI endpoints to trigger/query the stage
- `service.py` — Database service layer (SQLAlchemy async sessions)
- `schemas.py` — Pydantic request/response models

The `DocumentIngestionWorkflow` in `src/ks/system/` chains all stages end-to-end.

### Data Layer
- **PostgreSQL** (`src/ks/domain/models.py`): All SQLAlchemy ORM models. Key tables: `source_registry`, `document_registry`, `knowledge_fact`, `knowledge_chunk`, `review_queue`, `workflow_run`.
- **Enums** (`src/ks/domain/enums.py`): All domain enumerations (DiscoveryMode, RunStatus, Framework, GraphNodeType, etc.).
- **Settings** (`src/ks/config/settings.py`): Pydantic-settings classes per service, each reading from `.env` with prefixed env vars (e.g., `POSTGRES_HOST`, `NEO4J_PASSWORD`). Accessed via `get_settings()` (LRU-cached).

### Frontend
React 18 SPA (`apps/admin-ui/src/`), Vite + Tailwind + React Router v6. Pages map 1:1 to pipeline stages: Dashboard, SourceRegistry, Discovery, ReviewQueue, KnowledgeLibrary, GraphExplorer, KnowledgeIntelligence, SystemInspector. Communicates with the FastAPI backend via `axios`.

### Non-Obvious Constraints
- `debug_mode=True` is set on the Temporal worker (`apps/worker/main.py`) to disable deadlock detection (`TMPRL1101`) under heavy CPU load on dev machines.
- The discovery crawler uses clinical synonym expansion (e.g., `PCOS` → `polycystic`, `ovarian`) to avoid false-negative URL filtering — see `src/ks/discovery/activities.py`.
- URLs returned from native site search or DuckDuckGo sweeps skip strict path-pattern filtering because the search query already validates content relevance.
- MinIO buckets: `raw-artifacts` for original fetched content; `extracted-text` for cleaned text. Object keys are passed through Temporal workflow state; full content is not.
