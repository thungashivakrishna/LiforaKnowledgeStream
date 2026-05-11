"""Graph router — API endpoints for knowledge graph synchronization."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database import get_db_session
from ks.graph.schemas import GraphSyncRequest, GraphRunResponse
from ks.graph.service import GraphService

router = APIRouter(prefix="/graph", tags=["Graph"])


@router.post("/sync", response_model=GraphRunResponse)
async def start_graph_sync(
    data: GraphSyncRequest, 
    db: AsyncSession = Depends(get_db_session)
):
    """Start a graph synchronization run for a specific document."""
    service = GraphService(db)
    try:
        run = await service.start_graph_sync(data)
        await db.commit()
        return run
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/runs", response_model=dict)
async def list_graph_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session)
):
    """List graph sync runs with pagination."""
    service = GraphService(db)
    items, total = await service.list_graph_runs(limit, offset)
    
    # Format for response
    formatted_items = [
        {
            "id": r.id,
            "document_id": r.document_id,
            "status": r.status,
            "nodes_created": r.nodes_created,
            "edges_created": r.edges_created,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "error_message": r.error_message,
        } for r in items
    ]
    
    return {"items": formatted_items, "total": total, "limit": limit, "offset": offset}


@router.get("/runs/{run_id}", response_model=GraphRunResponse)
async def get_graph_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db_session)):
    """Get details of a specific graph sync run."""
    service = GraphService(db)
    try:
        run = await service.get_graph_run(run_id)
        return run
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

from neo4j import AsyncGraphDatabase
from ks.config.settings import get_settings

@router.get("/traversal/interventions")
async def traverse_interventions(symptom: str, condition: str):
    """
    Advanced Cypher Query:
    Find all interventions that target symptom X but do not contradict condition Y.
    """
    settings = get_settings()
    driver = AsyncGraphDatabase.driver(
        settings.neo4j.uri, 
        auth=(settings.neo4j.user, settings.neo4j.password)
    )
    
    query = """
    // 1. Find interventions treating the symptom
    MATCH (i:Entity)-[r1]->(s:Entity)
    WHERE toLower(s.name) CONTAINS toLower($symptom)
      AND (toLower(type(r1)) CONTAINS 'treat' 
           OR toLower(type(r1)) CONTAINS 'improv' 
           OR toLower(type(r1)) CONTAINS 'manag' 
           OR toLower(type(r1)) CONTAINS 'alleviat'
           OR toLower(type(r1)) CONTAINS 'reduc')
           
    // 2. Check for negative effects on the specified condition
    OPTIONAL MATCH (i)-[r2]->(c:Entity)
    WHERE toLower(c.name) CONTAINS toLower($condition)
      AND (toLower(type(r2)) CONTAINS 'contraindicat' 
           OR toLower(type(r2)) CONTAINS 'worsen' 
           OR toLower(type(r2)) CONTAINS 'avoid' 
           OR toLower(type(r2)) CONTAINS 'risk'
           OR toLower(type(r2)) CONTAINS 'harm')
           
    // 3. Filter out contradictions
    WITH i, s, type(r1) as mechanism, r2
    WHERE r2 IS NULL
    
    RETURN DISTINCT i.name AS intervention, mechanism, s.name AS target
    LIMIT 50
    """
    
    try:
        async with driver.session() as session:
            result = await session.run(query, symptom=symptom, condition=condition)
            records = await result.data()
            
        await driver.close()
        return {"data": records, "query": query}
    except Exception as e:
        await driver.close()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/traversal/query")
async def raw_cypher_query(cypher: dict):
    """Run a custom Cypher traversal (Admin only)."""
    settings = get_settings()
    driver = AsyncGraphDatabase.driver(
        settings.neo4j.uri, 
        auth=(settings.neo4j.user, settings.neo4j.password)
    )
    
    try:
        async with driver.session() as session:
            result = await session.run(cypher.get("query", ""), **cypher.get("params", {}))
            records = await result.data()
            
        await driver.close()
        return {"data": records}
    except Exception as e:
        await driver.close()
        raise HTTPException(status_code=500, detail=str(e))
