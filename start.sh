#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "▶ Starting KnowledgeStream..."

# 1. Ensure Docker Desktop is running
if ! docker info > /dev/null 2>&1; then
  echo "  Docker not running — launching Docker Desktop..."
  open -a Docker
  echo -n "  Waiting for Docker"
  until docker info > /dev/null 2>&1; do printf "."; sleep 2; done
  echo " ready."
fi

# 2. Start all infrastructure + API + worker via Docker Compose
echo "  Starting Docker services (postgres, redis, minio, qdrant, neo4j, temporal, api, worker)..."
docker compose -f "$ROOT/infrastructure/docker/docker-compose.yml" up -d

# 3. Wait for the API to be healthy before opening the UI
echo -n "  Waiting for API"
until curl -sf http://localhost:8000/api/v1/health > /dev/null 2>&1; do printf "."; sleep 2; done
echo " ready."

# 4. Start the Admin UI (Vite dev server) in a new Terminal tab
echo "  Starting Admin UI on http://localhost:5173 ..."
osascript -e 'tell application "Terminal" to do script "cd '"$ROOT/apps/admin-ui"' && npm run dev"'

echo ""
echo "✅ All services started:"
echo "   API           → http://localhost:8000/api/v1/docs"
echo "   Admin UI      → http://localhost:5173"
echo "   Temporal UI   → http://localhost:18080"
echo "   MinIO Console → http://localhost:18001  (minioadmin / minioadmin)"
echo "   Neo4j Browser → http://localhost:17474  (neo4j / ks_password)"
echo "   PgAdmin       → http://localhost:5051   (admin@knowledge.stream / admin)"
