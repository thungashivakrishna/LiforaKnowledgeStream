# Knowledge Stream — Health Intelligence Platform

Proactive Knowledge Stream prototype (Phase 1).

## Quick Start

```bash
# 1. Copy env template
cp .env.example .env
# Edit .env with your API keys

# 2. Start all infrastructure services
cd infrastructure/docker
docker compose up -d

# 3. Install Python dependencies
pip install -e ".[dev]"

# 4. Run database migrations
alembic upgrade head

# 5. Seed initial data
python infrastructure/scripts/seed_db.py

# 6. Start the API
uvicorn apps.api.main:app --reload --port 8000
```

## Services

| Service | URL | Purpose |
|---|---|---|
| API | http://localhost:8000 | FastAPI backend |
| API Docs | http://localhost:8000/api/v1/docs | Swagger UI |
| Temporal UI | http://localhost:8080 | Workflow monitoring |
| MinIO Console | http://localhost:9001 | Object storage browser |
| Qdrant | http://localhost:6333 | Vector store dashboard |

## Project Structure

```
apps/api/          FastAPI application
apps/worker/       Temporal worker runtime
apps/admin-ui/     Vite + React admin SPA (Batch 2+)
src/ks/            Python packages (domain, config, modules)
infrastructure/    Docker, migrations, seed data
```

## Development

```bash
# Run tests
pytest

# Lint
ruff check src/

# Generate new migration
alembic revision --autogenerate -m "description"
```
