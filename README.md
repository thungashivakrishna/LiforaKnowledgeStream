# Knowledge Stream — Health Intelligence Platform

Welcome to the **KnowledgeStream Health Intelligence Platform**! This is a high-fidelity, autonomous clinical engine designed for large-scale health data crawling, vector embedding indexing, graph-based clinical synchronizations, and smart multi-modal knowledge extraction.

---

## 🚀 Quick Start & Onboarding Guide

Follow these exact steps to spin up the entire application stack locally:

### 1. Configure the Environment (`.env`)
The local database credentials and AI API credentials reside in a `.env` file in the project root directory. **This file is excluded from Git to protect API keys.**
*   **Action**: Copy `.env.example` to `.env` in the root:
    ```bash
    cp .env.example .env
    ```
*   **Alternative (Recommended)**: If your team lead has provided a populated `.env` file offline (via Slack, Teams, or password manager), simply drop it directly into the root directory of this workspace.

### 2. Launch Infrastructure Services (Docker)
Navigate to the infrastructure directory and spin up the databases, vector indexers, and the Temporal workflow engine:
```bash
cd infrastructure/docker
docker compose up -d
```

### 3. Initialize Databases & Run Seeds
Run migrations to set up the PostgreSQL tables, followed by the seed script to load clinical sources and frameworks:
```bash
# Activate your virtual environment and install dependencies
pip install -e ".[dev]"

# Apply database migrations
alembic upgrade head

# Seed initial clinical data
python infrastructure/scripts/seed_db.py
```

### 4. Install & Launch the Vite React Frontend
Inside the `apps/admin-ui` folder, run npm install and start the local development server:
```bash
cd apps/admin-ui
npm install
npm run dev
```

### 5. Run the API and Worker Runtime
In separate terminal windows, start the FastAPI server and the Temporal background worker:
*   **FastAPI API**:
    ```bash
    uvicorn apps.api.main:app --reload --port 8000
    ```
*   **Temporal Worker**:
    ```bash
    python -m apps.worker.main
    ```

---

## 🗺️ Local Service Dashboard & Ports

The local Docker infrastructure exposes services via custom ports (prefixed with `18xxx` or `17xxx`) to prevent conflicts with other standard databases running on your machine:

| Service | Local Dashboard / Endpoint | Credentials (Default) | Purpose |
| :--- | :--- | :--- | :--- |
| **FastAPI Backend** | [http://localhost:8000](http://localhost:8000) | — | Main application API gateway |
| **Interactive Docs** | [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs) | — | Swagger API documentation |
| **Vite React UI** | [http://localhost:5173](http://localhost:5173) | — | Admin portal dashboard |
| **Temporal UI** | [http://localhost:18080](http://localhost:18080) | — | Crawling & extraction workflow tracker |
| **MinIO Console** | [http://localhost:18001](http://localhost:18001) | `minioadmin` / `minioadmin` | Clean web S3 bucket file browser |
| **Neo4j Browser** | [http://localhost:17474](http://localhost:17474) | `neo4j` / `ks_password` | Interactive clinical graph viewer |
| **Qdrant API** | [http://localhost:18333](http://localhost:18333) | — | Vector storage index endpoints |
| **PgAdmin UI** | [http://localhost:5051](http://localhost:5051) | `admin@knowledge.stream` / `admin` | Web-based Postgres DB visualizer |

---

## 🔑 Crucial Setup Details & Keys

> [!WARNING]
> **DO NOT** commit the `.env` file back to Git. It contains active production LLM keys (DeepSeek primary, OpenAI/Gemini secondary) and embedded database secrets.

### What is Kept Local-Only?
1.  **`.env` Secrets**: Ignored by git. Sharing this file offline is the easiest way to align keys across the team.
2.  **Docker Volumes**: All database state (Postgres records, MinIO S3 assets, Qdrant vectors, and Neo4j graph nodes) resides within local volumes on your machine. Wiping volumes can be done with `docker compose down -v`.
3.  **Local Packages**: `node_modules/` and `.venv/` are excluded and must be clean-installed on your development system.

---

## 🧠 Architectural Highlights for Teammates

*   **Clinical Synonym Expansion**: In FOCUSED or HYBRID crawler runs, search queries automatically expand. For example, crawling `PCOS` will accept articles with `polycystic`, `ovary`, or `syndrome` in their URLs (configured in `src/ks/discovery/activities.py`).
*   **Search Bypasses**: Crawling pages returned directly from native website search bars or DuckDuckGo targeted sweeps bypass strict string checks on paths, as they are pre-verified for relevance.
*   **Worker Deadlock Override**: On local development machines under heavy CPU load, the background worker uses `debug_mode=True` inside `apps/worker/main.py` to prevent sandboxing timeouts (`_DeadlockError` / `TMPRL1101`).
