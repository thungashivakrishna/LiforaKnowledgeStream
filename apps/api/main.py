import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ks.config.settings import get_settings

settings = get_settings()
logger = structlog.get_logger(__name__)

app = FastAPI(
    title=settings.app.app_name,
    version=settings.app.app_version,
    docs_url=f"{settings.app.api_prefix}/docs",
    redoc_url=f"{settings.app.api_prefix}/redoc",
    openapi_url=f"{settings.app.api_prefix}/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from ks.source_registry.router import router as source_router
from ks.discovery.router import router as discovery_router
from ks.acquisition.router import router as acquisition_router
from ks.extraction.router import router as extraction_router
from ks.enrichment.router import router as enrichment_router
from ks.chunking.router import router as chunking_router
from ks.graph.router import router as graph_router
from ks.library.router import router as library_router
from ks.system.router import router as system_router
from apps.api.routers.llm_usage import router as llm_usage_router

app.include_router(source_router, prefix=settings.app.api_prefix)
app.include_router(discovery_router, prefix=settings.app.api_prefix)
app.include_router(acquisition_router, prefix=settings.app.api_prefix)
app.include_router(extraction_router, prefix=settings.app.api_prefix)
app.include_router(enrichment_router, prefix=settings.app.api_prefix)
app.include_router(chunking_router, prefix=settings.app.api_prefix)
app.include_router(graph_router, prefix=settings.app.api_prefix)
app.include_router(library_router, prefix=settings.app.api_prefix)
app.include_router(system_router, prefix=settings.app.api_prefix)
app.include_router(llm_usage_router, prefix=settings.app.api_prefix)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("knowledge_stream_api_starting", version=settings.app.app_version)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("knowledge_stream_api_stopping")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get(f"{settings.app.api_prefix}/health", tags=["Health"])
async def health_check() -> dict:
    """Liveness probe — returns service status."""
    return {
        "status": "ok",
        "service": settings.app.app_name,
        "version": settings.app.app_version,
    }


@app.get(f"{settings.app.api_prefix}/health/ready", tags=["Health"])
async def readiness_check() -> dict:
    """Readiness probe — checks connectivity to dependencies."""
    from apps.api.database import engine
    checks: dict[str, str] = {}

    # DB
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ready" if all_ok else "degraded", "checks": checks}
