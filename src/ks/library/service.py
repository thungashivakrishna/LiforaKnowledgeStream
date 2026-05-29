import uuid
from sqlalchemy import select, func, case
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from ks.domain.models import DocumentRegistry, KnowledgeFact, KnowledgeTag, KnowledgeSummary, SourceRegistry
from ks.domain.enums import SourceType, RunStatus

class LibraryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_documents(self, q: str | None = None, status: str | None = None, framework: str | None = None, source_type: str | None = None, limit: int = 50, offset: int = 0):
        # Base query joining necessary relations
        query = (
            select(DocumentRegistry)
            .outerjoin(DocumentRegistry.summary)
            .join(SourceRegistry, DocumentRegistry.source_id == SourceRegistry.id)
            .options(
                selectinload(DocumentRegistry.tags),
                selectinload(DocumentRegistry.summary),
                selectinload(DocumentRegistry.source)
            )
        )
        
        # Fact count subquery for richness scoring
        fact_count_q = (
            select(func.count(KnowledgeFact.id))
            .where(KnowledgeFact.document_id == DocumentRegistry.id)
            .scalar_subquery()
        )
        
        # Filtering logic
        if status:
            query = query.where(DocumentRegistry.status == status)
        if source_type:
            query = query.where(SourceRegistry.source_type == source_type)
        if framework:
            # We need to join KnowledgeTag to filter by framework
            query = query.join(DocumentRegistry.tags).where(
                KnowledgeTag.tag_type == "FRAMEWORK",
                KnowledgeTag.tag_value == framework
            )

        # Add search and ranking logic
        if q:
            # PostgreSQL Full-Text Search for relevance
            search_query = func.plainto_tsquery('english', q)
            # Combine title and summary for the search vector
            search_vector = func.to_tsvector('english', 
                func.coalesce(DocumentRegistry.title, '') + " " + 
                func.coalesce(KnowledgeSummary.summary_text, '')
            )
            
            # Ranking components:
            # 1. Text Match Score (ts_rank)
            match_score = func.ts_rank(search_vector, search_query)
            
            # 2. Content Richness Score (Based on fact density)
            richness_score = func.coalesce(fact_count_q, 0) / 10.0
            
            # 3. Source Authority Score (Guidelines weighted significantly higher)
            authority_score = case(
                (SourceRegistry.source_type == SourceType.GUIDELINE_SOURCE, 1.0),
                (SourceRegistry.source_type == SourceType.ACADEMIC_SOURCE, 0.5),
                else_=0.0
            )
            
            # Composite Weighted Score
            total_score = (match_score * 10.0) + (richness_score * 2.0) + (authority_score * 2.0)
            
            query = query.where(search_vector.op('@@')(search_query))
            query = query.order_by(total_score.desc())
        else:
            # Default sorting by LAST UPDATE date and richness so recently processed items float to top
            query = query.order_by(DocumentRegistry.updated_at.desc(), fact_count_q.desc())

        query = query.limit(limit).offset(offset)
        
        # Count query (replicate filters for accurate total)
        count_query = select(func.count()).select_from(DocumentRegistry).join(SourceRegistry, DocumentRegistry.source_id == SourceRegistry.id)
        if status:
            count_query = count_query.where(DocumentRegistry.status == status)
        if source_type:
            count_query = count_query.where(SourceRegistry.source_type == source_type)
        if framework:
            count_query = count_query.join(DocumentRegistry.tags).where(
                KnowledgeTag.tag_type == "FRAMEWORK",
                KnowledgeTag.tag_value == framework
            )
        if q:
            search_query = func.plainto_tsquery('english', q)
            # Must join summary for count search
            count_query = count_query.outerjoin(DocumentRegistry.summary)
            search_vector = func.to_tsvector('english', 
                func.coalesce(DocumentRegistry.title, '') + " " + 
                func.coalesce(KnowledgeSummary.summary_text, '')
            )
            count_query = count_query.where(search_vector.op('@@')(search_query))
        
        if q:
            result = await self.db.execute(query.add_columns(total_score.label("relevance_score")))
            items = []
            for row in result.all():
                doc = row[0]
                doc.relevance_score = row[1]
                items.append(doc)
        else:
            result = await self.db.execute(query)
            items = result.scalars().all()
            for doc in items:
                doc.relevance_score = None
        
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0
        
        return items, total

    async def get_document_details(self, document_id: uuid.UUID):
        query = (
            select(DocumentRegistry)
            .where(DocumentRegistry.id == document_id)
            .join(DocumentRegistry.source)
            .options(
                selectinload(DocumentRegistry.summary),
                selectinload(DocumentRegistry.tags),
                selectinload(DocumentRegistry.facts),
                selectinload(DocumentRegistry.source)
            )
        )
        result = await self.db.execute(query)
        document = result.scalar_one_or_none()
        
        if not document:
            raise ValueError(f"Document with ID {document_id} not found.")
            
        return document

    async def get_actionable_guidelines(self):
        from sqlalchemy import or_
        predicates = ["requires", "suggests", "prescribes", "contains", "steps", "improves", "reduces", "treats", "prevents"]
        conditions = [KnowledgeFact.predicate.ilike(f"%{p}%") for p in predicates]
        
        query = (
            select(KnowledgeFact)
            .where(or_(*conditions))
            .options(selectinload(KnowledgeFact.document))
        )
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_personalized_guidelines(self, profile: dict):
        from sqlalchemy import or_, and_
        conditions = profile.get("conditions", [])
        goals = profile.get("goals", [])
        
        if not conditions and not goals:
            return await self.get_actionable_guidelines()
            
        # Target predicates that indicate a positive effect
        predicates = ["treats", "improves", "reduces", "prevents", "manages", "prescribed for", "good for", "benefits"]
        pred_filters = [KnowledgeFact.predicate.ilike(f"%{p}%") for p in predicates]
        
        target_filters = []
        for c in conditions + goals:
            target_filters.append(KnowledgeFact.object_.ilike(f"%{c}%"))
            target_filters.append(KnowledgeFact.subject.ilike(f"%{c}%"))
            
        query = (
            select(KnowledgeFact)
            .where(and_(
                or_(*pred_filters),
                or_(*target_filters)
            ))
            .options(
                selectinload(KnowledgeFact.document).selectinload(DocumentRegistry.tags),
                selectinload(KnowledgeFact.document)
            )
        )
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_library_intelligence(self):
        """Aggregate metrics to evaluate the quality and quantity of the knowledge base."""
        # 1. Facts by Framework
        fw_stats_q = (
            select(KnowledgeTag.tag_value, func.count(KnowledgeFact.id))
            .join(DocumentRegistry, DocumentRegistry.id == KnowledgeTag.document_id)
            .join(KnowledgeFact, KnowledgeFact.document_id == DocumentRegistry.id)
            .where(KnowledgeTag.tag_type == "FRAMEWORK")
            .group_by(KnowledgeTag.tag_value)
        )
        
        # 2. Avg Confidence and total facts
        total_stats_q = select(
            func.count(KnowledgeFact.id),
            func.avg(KnowledgeFact.confidence)
        )
        
        # 3. Recent Actionable Items
        recent_actionable_q = (
            select(KnowledgeFact)
            .order_by(KnowledgeFact.created_at.desc())
            .limit(10)
            .options(selectinload(KnowledgeFact.document))
        )
        
        fw_res = await self.db.execute(fw_stats_q)
        total_res = await self.db.execute(total_stats_q)
        recent_res = await self.db.execute(recent_actionable_q)
        
        total_count, avg_conf = total_res.first()
        
        return {
            "total_facts": total_count or 0,
            "avg_confidence": float(avg_conf or 0),
            "framework_distribution": {row[0]: row[1] for row in fw_res.all()},
            "recent_findings": recent_res.scalars().all()
        }

    async def get_clinical_quality_metrics(self):
        """Aggregate data to visualize the Levels of Evidence (LoE) and dynamic clinical audits."""
        # 1. Distribution of Evidence Grades
        grade_stats_q = (
            select(DocumentRegistry.evidence_grade, func.count(DocumentRegistry.id))
            .group_by(DocumentRegistry.evidence_grade)
        )
        
        # 2. Avg Confidence and total facts
        total_stats_q = select(
            func.count(KnowledgeFact.id),
            func.avg(KnowledgeFact.confidence)
        )
        
        # 3. Domain credibility rankings
        domain_rankings_q = (
            select(
                SourceRegistry.name,
                SourceRegistry.source_type,
                func.count(DocumentRegistry.id),
                func.avg(DocumentRegistry.priority_score)
            )
            .join(DocumentRegistry, DocumentRegistry.source_id == SourceRegistry.id)
            .group_by(SourceRegistry.name, SourceRegistry.source_type)
            .order_by(func.avg(DocumentRegistry.priority_score).desc())
            .limit(10)
        )
        
        # 4. Critic Agent Audit Log list
        critic_audits_q = (
            select(KnowledgeFact)
            .where(KnowledgeFact.is_hallucination == True)
            .order_by(KnowledgeFact.created_at.desc())
            .limit(10)
            .options(selectinload(KnowledgeFact.document))
        )
        
        grade_res = await self.db.execute(grade_stats_q)
        total_res = await self.db.execute(total_stats_q)
        domain_res = await self.db.execute(domain_rankings_q)
        critic_res = await self.db.execute(critic_audits_q)
        
        total_count, avg_conf = total_res.first()
        
        # Format Grade Distribution
        grade_dist = {"GRADE_A": 0, "GRADE_B": 0, "GRADE_C": 0, "GRADE_D": 0}
        for row in grade_res.all():
            g = row[0] or "GRADE_D"
            grade_dist[g] = row[1]
            
        # Format Domain Ledger
        domain_ledger = []
        for row in domain_res.all():
            domain_ledger.append({
                "name": row[0],
                "source_type": row[1].value if row[1] else "OTHER",
                "document_count": row[2],
                "avg_priority_score": float(row[3] or 0.0)
            })
            
        return {
            "total_facts": total_count or 0,
            "avg_confidence": float(avg_conf or 0.0),
            "evidence_grade_distribution": grade_dist,
            "domain_ledger": domain_ledger,
            "critic_audits": critic_res.scalars().all()
        }

    async def get_clinical_quality_pathways(self):
        """Aggregate subject-predicate-object facts grouped by standardized clinical schemas (Biomarker, Intervention, Symptom)."""
        # We query facts where subject_type or object_type is not null
        from sqlalchemy import and_
        query = (
            select(KnowledgeFact)
            .where(and_(
                KnowledgeFact.subject_type != None,
                KnowledgeFact.object_type != None
            ))
            .options(selectinload(KnowledgeFact.document))
            .order_by(KnowledgeFact.confidence.desc())
            .limit(100)
        )
        result = await self.db.execute(query)
        facts = result.scalars().all()
        
        # We'll map them to structured pathway relationships
        pathways = []
        for f in facts:
            pathways.append({
                "id": str(f.id),
                "fact_text": f.fact_text,
                "subject": f.subject,
                "subject_type": f.subject_type,
                "predicate": f.predicate,
                "object": f.object_,
                "object_type": f.object_type,
                "confidence": f.confidence,
                "evidence_grade": f.document.evidence_grade if f.document else "GRADE_D",
                "study_type": f.document.study_type if f.document else "Unclassified",
                "document_title": f.document.title if f.document else "N/A"
            })
        return pathways

