import uuid
from sqlalchemy import select, func, case
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from ks.domain.models import DocumentRegistry, KnowledgeFact, KnowledgeTag, KnowledgeSummary, SourceRegistry
from ks.domain.enums import SourceType, RunStatus

class LibraryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_documents(self, q: str | None = None, limit: int = 50, offset: int = 0):
        # Base query joining necessary relations
        query = (
            select(DocumentRegistry)
            .join(DocumentRegistry.summary)
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
        
        # Add search and ranking logic
        if q:
            # PostgreSQL Full-Text Search for relevance
            search_query = func.plainto_tsquery('english', q)
            # Combine title and summary for the search vector
            search_vector = func.to_tsvector('english', DocumentRegistry.title + " " + KnowledgeSummary.summary_text)
            
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
            # Default sorting by creation date and richness
            query = query.order_by(DocumentRegistry.created_at.desc(), fact_count_q.desc())

        query = query.limit(limit).offset(offset)
        
        # Count query
        count_query = select(func.count()).select_from(DocumentRegistry).join(DocumentRegistry.summary)
        if q:
            search_query = func.plainto_tsquery('english', q)
            search_vector = func.to_tsvector('english', DocumentRegistry.title + " " + KnowledgeSummary.summary_text)
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
            .options(selectinload(KnowledgeFact.document))
        )
        
        result = await self.db.execute(query)
        return result.scalars().all()
