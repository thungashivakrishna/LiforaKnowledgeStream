"""Graph activities — worker tasks for syncing knowledge to Neo4j."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List

from neo4j import GraphDatabase
from temporalio import activity

from ks.common import redis_client
from ks.config.settings import get_settings
from ks.domain.enums import RunStatus


logger = logging.getLogger(__name__)


class GraphActivities:
    def __init__(self, neo4j_driver: GraphDatabase.driver):
        self.neo4j_driver = neo4j_driver
        self.settings = get_settings()

    @activity.defn
    async def initialize_graph_schema(self) -> None:
        """Ensures Neo4j constraints and indices exist for high-performance syncing."""
        cached = await redis_client.get_cache("cache:graph:schema_ready")
        if cached is not None:
            logger.info("Graph schema already initialized (cache hit), skipping.")
            return

        def _init_tx(tx):
            # Unique constraints for core nodes
            tx.run("CREATE CONSTRAINT source_id_unique IF NOT EXISTS FOR (s:Source) REQUIRE s.id IS UNIQUE")
            tx.run("CREATE CONSTRAINT doc_id_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE")
            tx.run("CREATE CONSTRAINT entity_name_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE")

            # Indices for specialized tags
            tag_labels = [
                "Framework", "Topic", "Condition", "Symptom", "Intervention",
                "Food", "Nutrient", "ActivityType", "Population"
            ]
            for label in tag_labels:
                tx.run(f"CREATE INDEX {label.lower()}_value_idx IF NOT EXISTS FOR (t:{label}) ON (t.value)")

        try:
            with self.neo4j_driver.session() as session:
                session.execute_write(_init_tx)
            logger.info("Graph schema (constraints/indices) initialized successfully.")
            await redis_client.set_cache("cache:graph:schema_ready", datetime.now(timezone.utc).isoformat())
        except Exception as e:
            logger.error(f"Failed to initialize graph schema: {e}")
            raise e

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

        lock_key = f"lock:graph:{doc['id']}"
        if not await redis_client.acquire_lock(lock_key, ttl=redis_client.LOCK_GRAPH):
            from temporalio.exceptions import ApplicationError
            raise ApplicationError(f"Graph lock held for {doc['id']}", non_retryable=False)

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
                # Standard native Cypher replacement for APOC - store relation name as predicate attribute
                tx.run(
                    "UNWIND $facts AS fact "
                    "MERGE (subj:Entity {name: fact.subject}) "
                    "MERGE (obj:Entity {name: fact.object}) "
                    "WITH subj, obj, fact "
                    "MERGE (subj)-[r:RELATED_TO]->(obj) "
                    "SET r.predicate = fact.predicate, r.confidence = fact.confidence",
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

            node_count = 2 + len(tags) + len(facts)
            edge_count = 1 + len(tags) + len(facts)

            return {
                "success": True,
                "nodes_created": node_count,
                "edges_created": edge_count
            }
        except Exception as e:
            logger.error(f"Failed to sync to Neo4j: {e}")
            return {"success": False, "error": str(e)}
        finally:
            await redis_client.release_lock(lock_key)

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

        from ks.domain.models import GraphRun, DocumentRegistry
        from ks.domain.enums import DocumentStatus

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

                # CRITICAL MISSING LINK: Update the overarching Document state to final state 'INDEXED'
                if status == RunStatus.COMPLETED:
                    doc_res = await session.execute(select(DocumentRegistry).where(DocumentRegistry.id == run.document_id))
                    doc = doc_res.scalar_one_or_none()
                    if doc:
                        logger.info(f"FINALIZING DOCUMENT FLOW: Setting {doc.id} to INDEXED")
                        doc.status = DocumentStatus.INDEXED

            await session.commit()
