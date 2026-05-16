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


@router.post("/sync/fact/{fact_id}")
async def sync_fact_to_graph(fact_id: uuid.UUID, db: AsyncSession = Depends(get_db_session)):
    """Sync a specific validated fact to the graph database."""
    service = GraphService(db)
    try:
        success = await service.sync_fact_to_graph(fact_id)
        if not success:
            raise HTTPException(status_code=404, detail="Fact not found or incomplete")
        return {"message": "Fact successfully synchronized to Knowledge Graph"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

@router.get("/explorer/data")
async def get_explorer_data(
    q: str | None = Query(None),
    type: str | None = Query(None),
    framework: str | None = Query(None)
):
    """Fetches nodes and edges for the graph explorer UI with multi-dimensional filtering."""
    settings = get_settings()
    driver = AsyncGraphDatabase.driver(
        settings.neo4j.uri, 
        auth=(settings.neo4j.user, settings.neo4j.password)
    )
    
    # Base query logic
    where_clauses = []
    params = {"q": q or ""}
    
    if q:
        where_clauses.append("(toLower(n.name) CONTAINS toLower($q) OR toLower(n.value) CONTAINS toLower($q) OR toLower(n.title) CONTAINS toLower($q))")
    
    if framework and framework != "ALL":
        where_clauses.append("n.framework = $framework")
        params["framework"] = framework
        
    where_str = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    # Handle Label (Type) filtering
    label_filter = f":{type}" if type and type != "ALL" else ""
    
    query = f"""
    MATCH (n{label_filter}){where_str}
    OPTIONAL MATCH (n)-[r]-(m:Entity)
    RETURN n, r, m
    LIMIT 300
    """
    
    try:
        async with driver.session() as session:
            result = await session.run(query, **params)
            records = await result.data()
            
        nodes_map = {}
        links = []
        
        for record in records:
            for key in ["n", "m"]:
                node = record.get(key)
                if not node: continue
                
                n_id = node.get("name") or node.get("value") or node.get("title") or node.get("id") or str(uuid.uuid4())
                
                if n_id not in nodes_map:
                    # Get labels and find the most specific one (not 'Entity')
                    labels = list(node.labels) if hasattr(node, 'labels') else []
                    specific_type = next((l for l in labels if l != "Entity"), "Entity")
                    
                    nodes_map[n_id] = {
                        "id": n_id,
                        "label": node.get("name") or node.get("value") or node.get("title") or "Unknown",
                        "type": specific_type,
                        "properties": dict(node)
                    }
            
            r = record.get("r")
            if r:
                source_node = record.get("n")
                target_node = record.get("m")
                if source_node and target_node:
                    s_id = source_node.get("name") or source_node.get("value") or source_node.get("title")
                    t_id = target_node.get("name") or target_node.get("value") or target_node.get("title")
                    
                    links.append({
                        "source": s_id,
                        "target": t_id,
                        "type": r.type if hasattr(r, 'type') else "RELATED_TO"
                    })
                
        await driver.close()
        return {"nodes": list(nodes_map.values()), "links": links}
    except Exception as e:
        import logging
        logging.error(f"EXPLORER_DATA_ERROR: {str(e)}")
        await driver.close()
        raise HTTPException(status_code=500, detail=str(e))
