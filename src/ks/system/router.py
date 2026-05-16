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
import asyncio
import os
import sys
import json
from fastapi import BackgroundTasks

# Global state to track audit status
AUDIT_STATE = {
    "is_running": False,
    "last_run": None,
    "status": "idle"
}

async def run_audit_task():
    global AUDIT_STATE
    AUDIT_STATE["is_running"] = True
    AUDIT_STATE["status"] = "running"
    
    try:
        script_path = os.path.join(os.path.dirname(__file__), "../../../infrastructure/scripts/system_agent.py")
        script_path = os.path.abspath(script_path)
        
        # Use sys.executable to ensure we use the same python as the API
        process = await asyncio.create_subprocess_shell(
            f"{sys.executable} {script_path}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        AUDIT_STATE["status"] = "completed" if process.returncode == 0 else "failed"
    except Exception as e:
        AUDIT_STATE["status"] = f"error: {str(e)}"
    finally:
        AUDIT_STATE["is_running"] = False
        AUDIT_STATE["last_run"] = __import__("datetime").datetime.now().isoformat()

@router.post("/audit/trigger")
async def trigger_system_audit(background_tasks: BackgroundTasks):
    """Trigger a full system stability audit (Infrastructure + Platform Services)."""
    global AUDIT_STATE
    if AUDIT_STATE["is_running"]:
        return {"status": "already_running", "message": "An audit is already in progress."}
    
    background_tasks.add_task(run_audit_task)
    return {"status": "triggered", "message": "System audit has been started in the background."}

@router.get("/audit/status")
async def get_audit_status():
    """Get the status of the current or last system audit."""
    global AUDIT_STATE
    
    # Read the report generated at the root
    report_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../system_status_report.md"))
    
    report_content = "Report not found."
    if os.path.exists(report_path):
        with open(report_path, 'r') as f:
            report_content = f.read()
            
    return {
        "is_running": AUDIT_STATE["is_running"],
        "status": AUDIT_STATE["status"],
        "last_run": AUDIT_STATE["last_run"],
        "report": report_content
    }
