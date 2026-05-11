"""Graph activities — worker tasks for syncing knowledge to Neo4j."""
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List

from neo4j import GraphDatabase
from temporalio import activity

from ks.config.settings import get_settings
from ks.domain.enums import RunStatus


logger = logging.getLogger(__name__)


class GraphActivities:
    def __init__(self, neo4j_driver: GraphDatabase.driver):
        self.neo4j_driver = neo4j_driver
        self.settings = get_settings()

    @activity.defn
    async def fetch_graph_data(self, payload: dict) -> dict:
        """
        Fetches related knowledge data from PostgreSQL.
        Payload keys: document_id
        """
        from apps.api.database import SessionLocal
        from ks.domain.models import DocumentRegistry, SourceRegistry, KnowledgeTag, KnowledgeFact
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload
        
        doc_id = uuid.UUID(payload["document_id"])
        
        async with SessionLocal() as session:
            try:
                # 1. Fetch Doc and Source
                stmt = select(DocumentRegistry).options(joinedload(DocumentRegistry.source)).where(DocumentRegistry.id == doc_id)
                res = await session.execute(stmt)
                doc = res.scalar_one_or_none()
                
                if not doc:
                    return {"success": False, "error": f"Document {doc_id} not found"}
                
                # 2. Fetch Tags
                res = await session.execute(select(KnowledgeTag).where(KnowledgeTag.document_id == doc_id))
                tags = res.scalars().all()
                
                # 3. Fetch Facts
                res = await session.execute(select(KnowledgeFact).where(KnowledgeFact.document_id == doc_id))
                facts = res.scalars().all()
                
                data = {
                    "document": {
                        "id": str(doc.id),
                        "title": doc.title,
                        "url": doc.canonical_url,
                    },
                    "source": {
                        "id": str(doc.source.id),
                        "name": doc.source.name,
                        "url": doc.source.root_url,
                    },
                    "tags": [
                        {"type": t.tag_type.name, "value": t.tag_value, "is_primary": t.is_primary}
                        for t in tags
                    ],
                    "facts": [
                        {
                            "text": f.fact_text,
                            "subject": f.subject,
                            "predicate": f.predicate,
                            "object": f.object_,
                            "confidence": f.confidence
                        }
                        for f in facts
                    ]
                }
                
                return {"success": True, "data": data}
            except Exception as e:
                logger.error(f"Failed to fetch graph data: {e}")
                return {"success": False, "error": str(e)}

    @activity.defn
    async def sync_to_neo4j(self, payload: dict) -> dict:
        """
        Performs Cypher queries to sync data to Neo4j.
        Payload keys: data
        """
        data = payload["data"]
        doc = data["document"]
        src = data["source"]
        tags = data["tags"]
        facts = data["facts"]
        
        nodes_created = 0
        edges_created = 0
        
        def _sync_tx(tx):
            # ── 1. Source + Document nodes ────────────────────────────────────────
            tx.run(
                "MERGE (s:Source {id: $id}) SET s.name = $name, s.url = $url",
                id=src["id"], name=src["name"], url=src["url"]
            )
            tx.run(
                "MERGE (d:Document {id: $id}) SET d.title = $title, d.url = $url",
                id=doc["id"], title=doc["title"], url=doc["url"]
            )
            # ── 2. Source → Document edge ─────────────────────────────────────────
            tx.run(
                "MATCH (s:Source {id: $src_id}) "
                "MATCH (d:Document {id: $doc_id}) "
                "MERGE (s)-[:PUBLISHED]->(d)",
                src_id=src["id"], doc_id=doc["id"]
            )
            
            # ── 3. Tags — specialized labels ─────────────────────────────────────
            # Map tag types to Neo4j labels
            label_map = {
                "FRAMEWORK": "Framework",
                "TOPIC": "Topic",
                "CONDITION": "Condition",
                "SYMPTOM": "Symptom",
                "INTERVENTION": "Intervention",
                "FOOD": "Food",
                "NUTRIENT": "Nutrient",
                "ACTIVITY": "ActivityType",
                "POPULATION": "Population",
            }
            
            for t_type, label in label_map.items():
                filtered_tags = [t for t in tags if t["type"] == t_type]
                if filtered_tags:
                    tx.run(
                        f"UNWIND $tags AS tag "
                        f"MERGE (t:{label} {{value: tag.value}}) "
                        f"WITH t, tag "
                        f"MATCH (d:Document {{id: $doc_id}}) "
                        f"MERGE (d)-[:HAS_{label.upper()}]->(t)",
                        tags=filtered_tags, doc_id=doc["id"]
                    )
            
            # ── 4. Facts — SPO triples with semantic labels ──────────────────────
            spo_facts = [f for f in facts if f.get("subject") and f.get("predicate") and f.get("object")]
            if spo_facts:
                # We try to infer labels from the tags we already processed
                tx.run(
                    "UNWIND $facts AS fact "
                    "MERGE (subj:Entity {name: fact.subject}) "
                    "MERGE (obj:Entity {name: fact.object}) "
                    "WITH subj, obj, fact "
                    "CALL apoc.merge.relationship(subj, fact.predicate, {}, {confidence: fact.confidence}, obj) "
                    "YIELD rel RETURN count(rel)",
                    facts=spo_facts
                )
                
                # Semantic Refinement: Link Entity nodes to specialized Tag nodes if names match
                tx.run(
                    "MATCH (e:Entity) MATCH (t:Condition) WHERE e.name = t.value MERGE (e)-[:IS_A]->(t)"
                )
                tx.run(
                    "MATCH (e:Entity) MATCH (t:Symptom) WHERE e.name = t.value MERGE (e)-[:IS_A]->(t)"
                )
                tx.run(
                    "MATCH (e:Entity) MATCH (t:Intervention) WHERE e.name = t.value MERGE (e)-[:IS_A]->(t)"
                )
        
        try:
            with self.neo4j_driver.session() as session:
                session.execute_write(_sync_tx)
            
            node_count = 2 + len(tags) + len(facts)  # source + doc + tags + facts
            edge_count = 1 + len(tags) + len(facts)  # published + tag edges + contains
            
            return {
                "success": True,
                "nodes_created": node_count,
                "edges_created": edge_count
            }
        except Exception as e:
            logger.error(f"Failed to sync to Neo4j: {e}")
            # If APOC isn't available, retry without SPO triples
            if "apoc" in str(e).lower():
                try:
                    with self.neo4j_driver.session() as session:
                        def _sync_no_apoc(tx):
                            tx.run("MERGE (s:Source {id: $id}) SET s.name = $name, s.url = $url", id=src["id"], name=src["name"], url=src["url"])
                            tx.run("MERGE (d:Document {id: $id}) SET d.title = $title, d.url = $url", id=doc["id"], title=doc["title"], url=doc["url"])
                            tx.run("MATCH (s:Source {id: $src_id}) MATCH (d:Document {id: $doc_id}) MERGE (s)-[:PUBLISHED]->(d)", src_id=src["id"], doc_id=doc["id"])
                            if fw_tags:
                                tx.run("UNWIND $tags AS tag MERGE (t:Framework {value: tag.value}) WITH t MATCH (d:Document {id: $doc_id}) MERGE (d)-[:BELONGS_TO]->(t)", tags=fw_tags, doc_id=doc["id"])
                            if tp_tags:
                                tx.run("UNWIND $tags AS tag MERGE (t:Topic {value: tag.value}) WITH t MATCH (d:Document {id: $doc_id}) MERGE (d)-[:HAS_TOPIC]->(t)", tags=tp_tags, doc_id=doc["id"])
                            if facts:
                                tx.run("UNWIND $facts AS fact MERGE (f:Fact {text: fact.text}) SET f.confidence = fact.confidence WITH f MATCH (d:Document {id: $doc_id}) MERGE (d)-[:CONTAINS]->(f)", facts=facts, doc_id=doc["id"])
                        session.execute_write(_sync_no_apoc)
                    node_count = 2 + len(tags) + len(facts)
                    edge_count = 1 + len(tags) + len(facts)
                    return {"success": True, "nodes_created": node_count, "edges_created": edge_count}
                except Exception as e2:
                    logger.error(f"Failed retry without APOC: {e2}")
                    return {"success": False, "error": str(e2)}
            return {"success": False, "error": str(e)}

    @activity.defn
    async def update_graph_status(self, payload: dict) -> None:
        """
        Updates the GraphRun status in the DB.
        """
        from apps.api.database import SessionLocal
        from sqlalchemy import select
        
        run_id = uuid.UUID(payload["run_id"])
        status = RunStatus(payload["status"])
        nodes = payload.get("nodes_created", 0)
        edges = payload.get("edges_created", 0)
        error_msg = payload.get("error_message")
        
        from ks.domain.models import GraphRun
        async with SessionLocal() as session:
            res = await session.execute(select(GraphRun).where(GraphRun.id == run_id))
            run = res.scalar_one_or_none()
            if run:
                run.status = status
                run.completed_at = datetime.now()
                run.nodes_created = nodes
                run.edges_created = edges
                if error_msg:
                    run.error_message = error_msg
            
            await session.commit()
