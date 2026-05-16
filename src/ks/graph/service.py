"""Graph service — orchestrates syncing relational knowledge to Neo4j."""
import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ks.graph.schemas import GraphSyncRequest
from ks.domain.enums import RunStatus
from ks.domain.models import DocumentRegistry, GraphRun


class GraphService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start_graph_sync(self, data: GraphSyncRequest) -> GraphRun:
        # 1. Verify document exists
        result = await self.session.execute(
            select(DocumentRegistry).where(DocumentRegistry.id == data.document_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document {data.document_id} not found")

        # 2. Check if already synced and not forcing refresh
        if not data.force_refresh:
            res = await self.session.execute(
                select(GraphRun)
                .where(GraphRun.document_id == data.document_id)
                .where(GraphRun.status == RunStatus.COMPLETED)
            )
            existing = res.scalars().first()
            if existing:
                raise ValueError(f"Document {data.document_id} already synced to graph. Use force_refresh=True to re-sync.")

        # 3. Create GraphRun record
        run = GraphRun(
            id=uuid.uuid4(),
            document_id=data.document_id,
            status=RunStatus.PENDING
        )
        self.session.add(run)
        await self.session.flush()

        # 4. Trigger Temporal workflow
        await self._trigger_graph_workflow(run, data)

        return run

    async def _trigger_graph_workflow(self, run: GraphRun, data: GraphSyncRequest):
        from temporalio.client import Client
        from ks.config.settings import get_settings
        
        settings = get_settings()
        client = await Client.connect(settings.temporal.address)
        
        payload = {
            "run_id": str(run.id),
            "document_id": str(run.document_id)
        }
        
        await client.start_workflow(
            "GraphSyncWorkflow",
            payload,
            id=f"graph-sync-run-{run.id}",
            task_queue=settings.temporal.task_queue,
        )

    async def get_graph_run(self, run_id: uuid.UUID) -> GraphRun:
        result = await self.session.execute(
            select(GraphRun).where(GraphRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"Graph sync run {run_id} not found")
        return run

    async def list_graph_runs(self, limit: int = 50, offset: int = 0) -> tuple[list[GraphRun], int]:
        q = select(GraphRun).order_by(GraphRun.started_at.desc().nulls_last())
        count_q = select(func.count()).select_from(GraphRun)
        
        total = (await self.session.execute(count_q)).scalar_one()
        result = await self.session.execute(q.offset(offset).limit(limit))
        
        return list(result.scalars().all()), total
    async def sync_fact_to_graph(self, fact_id: uuid.UUID) -> bool:
        """Sync a single verified fact from PostgreSQL to Neo4j with clinical metadata."""
        from ks.domain.models import KnowledgeFact, KnowledgeTag, DocumentRegistry, SourceFrameworkMap
        from neo4j import AsyncGraphDatabase
        from ks.config.settings import get_settings
        from ks.domain.enums import ValidationStatus

        # 1. Fetch fact and related clinical metadata
        res = await self.session.execute(
            select(KnowledgeFact)
            .where(KnowledgeFact.id == fact_id)
            .options(selectinload(KnowledgeFact.document))
        )
        fact = res.scalar_one_or_none()
        if not fact or not fact.subject or not fact.predicate or not fact.object_:
            return False

        # 2. Lookup Entity Types from Tags for this document
        tag_res = await self.session.execute(
            select(KnowledgeTag).where(KnowledgeTag.document_id == fact.document_id)
        )
        tags = tag_res.scalars().all()
        
        # Build mapping of name -> type
        type_map = {t.tag_value.lower(): t.tag_type.value for t in tags}
        subject_type = type_map.get(fact.subject.lower(), "Entity")
        object_type = type_map.get(fact.object_.lower(), "Entity")
        
        # 3. Lookup Framework from Source
        framework = "GENERAL"
        if fact.document:
            fw_res = await self.session.execute(
                select(SourceFrameworkMap)
                .where(SourceFrameworkMap.source_id == fact.document.source_id)
                .where(SourceFrameworkMap.is_primary == True)
            )
            primary_fw = fw_res.scalar_one_or_none()
            if primary_fw:
                framework = primary_fw.framework.value

        # 4. Sync to Neo4j
        settings = get_settings()
        driver = AsyncGraphDatabase.driver(
            settings.neo4j.uri, 
            auth=(settings.neo4j.user, settings.neo4j.password)
        )
        
        # Dynamic labels based on types
        query = f"""
        MERGE (subj:Entity:{subject_type} {{name: $subject}})
        MERGE (obj:Entity:{object_type} {{name: $object}})
        WITH subj, obj
        MERGE (subj)-[r:RELATED_TO]->(obj)
        SET r.predicate = $predicate, 
            r.confidence = $confidence, 
            r.fact_id = $fact_id,
            r.framework = $framework,
            subj.framework = $framework,
            obj.framework = $framework
        RETURN r
        """
        
        try:
            async with driver.session() as session:
                await session.run(
                    query, 
                    subject=fact.subject, 
                    predicate=fact.predicate, 
                    object=fact.object_, 
                    confidence=fact.confidence,
                    fact_id=str(fact.id),
                    framework=framework
                )
            await driver.close()
            
            # Update validation status
            fact.validation_status = ValidationStatus.VALIDATED
            await self.session.commit()
            return True
        except Exception as e:
            await driver.close()
            raise e
