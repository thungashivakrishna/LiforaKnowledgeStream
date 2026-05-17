# KnowledgeStream — Health Intelligence Platform

Welcome to **KnowledgeStream**! A production-grade, high-fidelity, autonomous clinical engine designed for large-scale health data ingestion, vector-based semantic search, graph-structured clinical mapping, and personalized protocol generation. 

KnowledgeStream bridges the gap between raw clinical literature (PDFs, Web pages, medical articles) and structured, actionable medical protocols by combining state-of-the-art AI-driven extraction with robust, distributed workflow orchestration.

---

## 🏛️ System Architecture

KnowledgeStream follows a highly decoupled, service-oriented architecture designed to handle high-throughput, multi-modal ingestion without bottlenecks.

```mermaid
flowchart TD
    subgraph Client Layer
        UI["React Admin Dashboard (Port 5173)"]
    end

    subgraph Application Services
        API["FastAPI Backend (Port 8000)"]
        Worker["Temporal Background Worker"]
    end

    subgraph Orchestration
        Temporal["Temporal Engine (Port 18233 / 18080)"]
    end

    subgraph Storage & Indexing Layer
        Postgres[("PostgreSQL (Port 18432)")\nMetadata & Registry]
        MinIO[("MinIO Object Storage (Port 18000/18001)")\nRaw & Clean HTML/PDFs]
        Qdrant[("Qdrant Vector DB (Port 18333)")\nSemantic Embeddings]
        Neo4j[("Neo4j Graph DB (Port 17474/17687)")\nClinical Knowledge Graph]
        Redis[("Redis (Port 18379)")\nJob Caching & Queues]
    end

    UI -->|HTTP requests| API
    API -->|Register documents/runs| Postgres
    API -->|Start workflows| Temporal
    Worker -->|Poll tasks| Temporal
    Worker -->|Read/Write text| MinIO
    Worker -->|Extract features| Postgres
    Worker -->|Vectorize chunks| Qdrant
    Worker -->|Sync relationships| Neo4j
    Worker -->|Cache states| Redis
```

### Core Technologies
*   **FastAPI Backend**: Acts as the high-throughput, async REST API Gateway for managing extraction runs, sources, and review queues.
*   **Temporal Workflow Engine**: Manages complex, long-running clinical acquisition, extraction, and sync pipelines with automated retry logic, timeouts, and state tracking.
*   **MinIO (S3-Compatible Storage)**: Prevents Temporal history bloating by storing large binary files (PDFs, multi-megabyte HTML scraped pages) externally, passing only lightweight storage reference keys through workflow states.
*   **Qdrant Vector DB**: Indexes extracted text chunks semantically using advanced embedding models (`text-embedding-3-small`) to power localized clinical context lookups.
*   **Neo4j Graph Database**: Maps synchronized clinical nodes (Symptoms, Biomarkers, Interventions, Protocols) and their high-dimensional semantic relationships for personalized mapping.
*   **PostgreSQL**: Serves as the relational database for audit trails, document registries, pipeline runs, and the exception-based Clinical Review Queue.
*   **Redis**: High-speed caching layer for pipeline job tracking and session states.

---

## 🔄 End-to-End Clinical Processing Pipeline

```
[ Raw Source ] ➔ [ Discovery ] ➔ [ Acquisition ] ➔ [ AI Extraction ] ➔ [ Semantic Sync ] ➔ [ Protocol Mapping ]
```

1.  **Clinical Discovery**: The platform crawls target websites using one of three modes:
    *   `BROAD`: Global website sweeps via sitemaps.
    *   `FOCUSED`: Targeted focus crawls utilizing native search bars (using query inputs like "PCOS") and DuckDuckGo targeted sweeps.
    *   `HYBRID`: Balanced combination of search queries and localized BFS crawling.
2.  **Acquisition & Triage**: Crawled links are fetched, stripped of navigation/boilerplate, scored, and stored securely in MinIO object buckets. 
3.  **AI Extraction & Normalization**: Cleaned content is chunked and analyzed via a multi-model LLM gateway (routing between DeepSeek V3, Gemini 1.5, and GPT-4o-mini). It extracts entities (symptoms, biomarkers, food, interventions) and assigns high-fidelity confidence scores.
4.  **Semantic Synchronization**: High-confidence entities (>0.9 score) are synchronized directly into the Neo4j Knowledge Graph. Entities requiring verification enter the exception-based **Clinical Review Queue** for manual administrator verification.
5.  **Biological Protocol Generation**: Promoted nodes are mapped to individual biological profiles to yield personalized protocol pathways.

---

## 🚀 Quick Start & Local Setup

Follow these exact steps to spin up the entire application stack locally:

### 1. Configure the Environment (`.env`)
The database credentials, service hosts, and LLM API keys reside in a `.env` file in the project root directory. **This file is excluded from Git to prevent exposing credentials.**
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

## 🗺️ Service Dashboard & Ports Directory

Local Docker services are exposed via specific custom ports (prefixed with `18xxx` or `17xxx`) to prevent conflicts with standard databases running on your host machine:

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

## 🛠️ Folder Structure

```
├── apps/
│   ├── api/            # FastAPI router, endpoints, request schemas, and database configuration.
│   ├── worker/         # Temporal worker run loops and runtime environment overrides.
│   └── admin-ui/       # Vite + React Admin SPA Dashboard for pipeline visualization and reviews.
├── src/ks/             # Core clinical Python engine modules.
│   ├── acquisition/    # Web scaper, PDF parser, and direct MinIO storage adapters.
│   ├── discovery/      # Crawlers, search bar integration, sitemap parsers, and synonym matching.
│   ├── extraction/     # AI entities parser, GPT/Gemini cleanups, and triage logic.
│   ├── enrichment/     # Vector database embeddings and Qdrant index synchronizations.
│   ├── graph/          # Neo4j connections and high-dimensional semantic synchronization.
│   └── domain/         # SQLAlchemy database models, schemas, and configurations.
└── infrastructure/
    ├── docker/         # Orchestrated multi-database docker-compose setups.
    ├── migrations/     # Alembic database version control and history.
    └── scripts/        # Database seeders, test scripts, and system agents.
```

---

## 🧠 Architectural & Stability Safeguards

*   **Clinical Synonym Expansion**: FOCUSED crawler runs implement smart clinical expansion maps inside [activities.py](file:///c:/Users/7000034347/Documents/HealthIntelligence/KnowledgeStream/src/ks/discovery/activities.py). Abbreviations like `PCOS` or `RA` automatically expand to include synonyms like `polycystic`, `ovary`, `ovarian`, `rheumatoid`, `arthritis`, etc. in sitemap path validation checklists to prevent false negative exclusions.
*   **Search Engine Bypasses**: Crawled pages returned from native forms or DuckDuckGo targeted sweeps bypass strict URL path checks altogether. Since the search query has pre-verified the content's context, they are retained and passed directly to the AI Critic.
*   **Worker Deadlock Override**: On development systems running under heavy CPU load, the background worker overrides the standard Temporal sandboxing deadlock detector (`debug_mode=True` inside `apps/worker/main.py`). This prevents false deadlock timeouts (`TMPRL1101`) and keeps the pipelines running smoothly and rapidly.
