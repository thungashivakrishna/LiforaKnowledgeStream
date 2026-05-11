from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from apps.api.database import get_db_session
from typing import List, Dict, Any

router = APIRouter(prefix="/system", tags=["System"])

ALLOWED_TABLES = [
    "source_registry",
    "document_registry",
    "knowledge_summary",
    "knowledge_fact",
    "knowledge_tag",
    "discovery_filter_profile",
    "candidate_discovery_run",
    "candidate_document_evaluation",
    "fetch_run",
    "extraction_run",
    "enrichment_run"
]

@router.get("/tables")
async def list_available_tables():
    """List tables that can be inspected."""
    return {"tables": ALLOWED_TABLES}

@router.get("/tables/{table_name}")
async def get_table_data(
    table_name: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session)
):
    """Fetch rows from a specific table."""
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(status_code=403, detail="Table access not permitted")
    
    try:
        # Fetch rows
        query = text(f"SELECT * FROM {table_name} LIMIT :limit OFFSET :offset")
        result = await db.execute(query, {"limit": limit, "offset": offset})
        
        # Get column names
        columns = result.keys()
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
        
        # Get total count
        count_query = text(f"SELECT COUNT(*) FROM {table_name}")
        total = (await db.execute(count_query)).scalar()
        
        return {
            "table": table_name,
            "columns": list(columns),
            "rows": rows,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
