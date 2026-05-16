import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Enum, Float,
    ForeignKey, Index, Integer, String, Text, func, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ks.domain.enums import (
    AssignedBy, DiscoveryDecision, DiscoveryMode, DocType,
    DocumentStatus, ExtractionQuality, Framework, GraphEdgeType,
    GraphNodeType, GraphProvenance, ReviewDecision, ReviewEntityType,
    RunStatus, SourceApprovalStatus, SourceType, TagType,
    ValidationStatus, WorkflowStatus,
)


class Base(DeclarativeBase):
    pass


# ── Source & Policy ──────────────────────────────────────────────────────────

class SourceRegistry(Base):
    __tablename__ = "source_registry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    root_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en")
    region: Mapped[str | None] = mapped_column(String(100))
    trust_tier: Mapped[int] = mapped_column(Integer, default=3)
    authority_score: Mapped[float | None] = mapped_column(Float)
    evidence_score: Mapped[float | None] = mapped_column(Float)
    transparency_score: Mapped[float | None] = mapped_column(Float)
    stability_score: Mapped[float | None] = mapped_column(Float)
    approval_status: Mapped[SourceApprovalStatus] = mapped_column(
        Enum(SourceApprovalStatus), default=SourceApprovalStatus.CANDIDATE
    )
    crawl_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    extraction_profile: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    freshness_days: Mapped[int] = mapped_column(Integer, default=14)
    review_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    framework_maps: Mapped[list["SourceFrameworkMap"]] = relationship(back_populates="source")
    policies: Mapped[list["SourcePolicy"]] = relationship(back_populates="source")
    reviews: Mapped[list["SourceReview"]] = relationship(back_populates="source")
    documents: Mapped[list["DocumentRegistry"]] = relationship(back_populates="source")

    __table_args__ = (Index("ix_source_registry_approval_status", "approval_status"),)


class SourcePolicy(Base):
    __tablename__ = "source_policy"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_registry.id", ondelete="CASCADE"))
    authority: Mapped[float | None] = mapped_column(Float)
    evidence_orientation: Mapped[float | None] = mapped_column(Float)
    transparency: Mapped[float | None] = mapped_column(Float)
    stability: Mapped[float | None] = mapped_column(Float)
    relevance: Mapped[float | None] = mapped_column(Float)
    extraction_feasibility: Mapped[float | None] = mapped_column(Float)
    safety_risk: Mapped[float | None] = mapped_column(Float)
    policy_compliance: Mapped[float | None] = mapped_column(Float)
    composite_score: Mapped[float | None] = mapped_column(Float)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped["SourceRegistry"] = relationship(back_populates="policies")


class SourceFrameworkMap(Base):
    __tablename__ = "source_framework_map"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_registry.id", ondelete="CASCADE"))
    framework: Mapped[Framework] = mapped_column(Enum(Framework), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped["SourceRegistry"] = relationship(back_populates="framework_maps")

    __table_args__ = (Index("ix_source_framework_map_source_id", "source_id"),)


class SourceReview(Base):
    __tablename__ = "source_review"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_registry.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    actor: Mapped[str] = mapped_column(String(255))
    decision: Mapped[ReviewDecision | None] = mapped_column(Enum(ReviewDecision))
    reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped["SourceRegistry"] = relationship(back_populates="reviews")


# ── Document & Runs ──────────────────────────────────────────────────────────

class DocumentRegistry(Base):
    __tablename__ = "document_registry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_registry.id", ondelete="CASCADE"))
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(Text)
    doc_type: Mapped[DocType] = mapped_column(Enum(DocType), default=DocType.HTML_PAGE)
    discovery_mode: Mapped[DiscoveryMode | None] = mapped_column(Enum(DiscoveryMode))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.DISCOVERED
    )
    priority_score: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    evaluation_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    publication_date: Mapped[date | None] = mapped_column(Date)
    author: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(10), default="en")
    word_count: Mapped[int | None] = mapped_column(Integer)
    raw_object_key: Mapped[str | None] = mapped_column(Text)
    extracted_text_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source: Mapped["SourceRegistry"] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document")
    evaluations: Mapped[list["CandidateDocumentEvaluation"]] = relationship(back_populates="document")
    summary: Mapped["KnowledgeSummary | None"] = relationship(back_populates="document", uselist=False)
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(back_populates="document")
    facts: Mapped[list["KnowledgeFact"]] = relationship(back_populates="document")
    tags: Mapped[list["KnowledgeTag"]] = relationship(back_populates="document")

    __table_args__ = (
        Index("ix_document_registry_source_id", "source_id"),
        Index("ix_document_registry_status", "status"),
    )


class DocumentVersion(Base):
    __tablename__ = "document_version"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_registry.id", ondelete="CASCADE"))
    version_hash: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_object_key: Mapped[str | None] = mapped_column(Text)

    document: Mapped["DocumentRegistry"] = relationship(back_populates="versions")


class CandidateDiscoveryRun(Base):
    __tablename__ = "candidate_discovery_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mode: Mapped[DiscoveryMode] = mapped_column(Enum(DiscoveryMode), nullable=False)
    filter_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("discovery_filter_profile.id", ondelete="SET NULL")
    )
    source_scope: Mapped[dict | None] = mapped_column(JSONB)
    framework_scope: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.PENDING)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    evaluations: Mapped[list["CandidateDocumentEvaluation"]] = relationship(back_populates="run")


class CandidateDocumentEvaluation(Base):
    __tablename__ = "candidate_document_evaluation"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_discovery_run.id", ondelete="CASCADE"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_registry.id", ondelete="CASCADE"))
    score: Mapped[float | None] = mapped_column(Float)
    matched_terms: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    matched_frameworks: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    decision: Mapped[DiscoveryDecision] = mapped_column(
        Enum(DiscoveryDecision), default=DiscoveryDecision.INGEST_NOW
    )
    decision_overridden_by: Mapped[str | None] = mapped_column(String(255))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped["CandidateDiscoveryRun"] = relationship(back_populates="evaluations")
    document: Mapped["DocumentRegistry"] = relationship(back_populates="evaluations")


class FetchRun(Base):
    __tablename__ = "fetch_run"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_registry.id", ondelete="CASCADE"))
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.PENDING)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column(JSONB, name="metadata")


class ExtractionRun(Base):
    __tablename__ = "extraction_run"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_registry.id", ondelete="CASCADE"))
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.PENDING)
    extraction_quality: Mapped[ExtractionQuality | None] = mapped_column(Enum(ExtractionQuality))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column(JSONB, name="metadata")


class EnrichmentRun(Base):
    __tablename__ = "enrichment_run"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_registry.id", ondelete="CASCADE"))
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.PENDING)
    model_used: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[dict | None] = mapped_column(JSONB, name="metadata")


class ChunkRun(Base):
    __tablename__ = "chunk_run"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_registry.id", ondelete="CASCADE"))
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.PENDING)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[dict | None] = mapped_column(JSONB, name="metadata")


class GraphRun(Base):
    __tablename__ = "graph_run"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_registry.id", ondelete="CASCADE"))
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.PENDING)
    nodes_created: Mapped[int] = mapped_column(Integer, default=0)
    edges_created: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column(JSONB, name="metadata")


# ── Knowledge Outputs ─────────────────────────────────────────────────────────

class KnowledgeSummary(Base):
    __tablename__ = "knowledge_summary"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_registry.id", ondelete="CASCADE"), unique=True
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str | None] = mapped_column(String(255))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    validation_status: Mapped[ValidationStatus] = mapped_column(
        Enum(ValidationStatus), default=ValidationStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["DocumentRegistry"] = relationship(back_populates="summary")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunk"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_registry.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    framework: Mapped[Framework | None] = mapped_column(Enum(Framework))
    topics: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    qdrant_point_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["DocumentRegistry"] = relationship(back_populates="chunks")

    __table_args__ = (Index("ix_knowledge_chunk_document_id", "document_id"),)


class KnowledgeFact(Base):
    __tablename__ = "knowledge_fact"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_registry.id", ondelete="CASCADE"))
    fact_type: Mapped[str | None] = mapped_column(String(100))
    fact_text: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str | None] = mapped_column(Text)
    predicate: Mapped[str | None] = mapped_column(Text)
    object_: Mapped[str | None] = mapped_column(Text, name="object")
    confidence: Mapped[float | None] = mapped_column(Float)
    source_span: Mapped[str | None] = mapped_column(Text)
    validation_status: Mapped[ValidationStatus] = mapped_column(
        Enum(ValidationStatus), default=ValidationStatus.PENDING
    )
    is_hallucination: Mapped[bool] = mapped_column(Boolean, default=False)
    critique: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["DocumentRegistry"] = relationship(back_populates="facts")
    
    @property
    def object(self) -> str | None:
        return self.object_
        
    @object.setter
    def object(self, value: str | None):
        self.object_ = value

    __table_args__ = (
        UniqueConstraint('document_id', 'subject', 'predicate', 'object', name='uq_knowledge_fact_content'),
    )


class KnowledgeTag(Base):
    __tablename__ = "knowledge_tag"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_registry.id", ondelete="CASCADE"))
    tag_type: Mapped[TagType] = mapped_column(Enum(TagType), nullable=False)
    tag_value: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_by: Mapped[AssignedBy] = mapped_column(Enum(AssignedBy), default=AssignedBy.MODEL)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["DocumentRegistry"] = relationship(back_populates="tags")

    __table_args__ = (
        UniqueConstraint('document_id', 'tag_type', 'tag_value', name='uq_knowledge_tag_content'),
        Index("ix_knowledge_tag_document_id", "document_id"),
    )


# ── Graph Prototype ───────────────────────────────────────────────────────────

class GraphNode(Base):
    __tablename__ = "graph_node"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_type: Mapped[GraphNodeType] = mapped_column(Enum(GraphNodeType), nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    properties: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    outgoing_edges: Mapped[list["GraphEdge"]] = relationship(
        foreign_keys="GraphEdge.from_node_id", back_populates="from_node"
    )
    incoming_edges: Mapped[list["GraphEdge"]] = relationship(
        foreign_keys="GraphEdge.to_node_id", back_populates="to_node"
    )

    __table_args__ = (
        Index("ix_graph_node_type_external", "node_type", "external_id", unique=True),
    )


class GraphEdge(Base):
    __tablename__ = "graph_edge"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("graph_node.id", ondelete="CASCADE"))
    to_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("graph_node.id", ondelete="CASCADE"))
    edge_type: Mapped[GraphEdgeType] = mapped_column(Enum(GraphEdgeType), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    provenance: Mapped[GraphProvenance] = mapped_column(
        Enum(GraphProvenance), default=GraphProvenance.ENRICHMENT
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    from_node: Mapped["GraphNode"] = relationship(foreign_keys=[from_node_id], back_populates="outgoing_edges")
    to_node: Mapped["GraphNode"] = relationship(foreign_keys=[to_node_id], back_populates="incoming_edges")

    __table_args__ = (
        Index("ix_graph_edge_from_to", "from_node_id", "to_node_id", "edge_type"),
    )


# ── Operations ────────────────────────────────────────────────────────────────

class WorkflowRun(Base):
    __tablename__ = "workflow_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_type: Mapped[str] = mapped_column(String(100), nullable=False)
    temporal_workflow_id: Mapped[str | None] = mapped_column(String(255))
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_registry.id", ondelete="SET NULL"))
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document_registry.id", ondelete="SET NULL"))
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), default=WorkflowStatus.RUNNING)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column(JSONB, name="metadata")

    errors: Mapped[list["JobError"]] = relationship(back_populates="workflow_run")

    __table_args__ = (Index("ix_workflow_run_status", "status"),)


class ReviewQueue(Base):
    __tablename__ = "review_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[ReviewEntityType] = mapped_column(Enum(ReviewEntityType), nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    assigned_to: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobError(Base):
    __tablename__ = "job_error"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_run.id", ondelete="CASCADE"))
    activity_name: Mapped[str | None] = mapped_column(String(255))
    error_type: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    stack_trace: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="errors")


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(Text)
    before_state: Mapped[dict | None] = mapped_column(JSONB)
    after_state: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_admin_audit_log_entity", "entity_type", "entity_id"),)


class DiscoveryFilterProfile(Base):
    __tablename__ = "discovery_filter_profile"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[DiscoveryMode] = mapped_column(Enum(DiscoveryMode), nullable=False)
    topics: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    synonyms: Mapped[dict | None] = mapped_column(JSONB)
    frameworks: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    max_candidates: Mapped[int] = mapped_column(Integer, default=100)
    per_source_limit: Mapped[int] = mapped_column(Integer, default=20)
    reference_context: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    discovery_runs: Mapped[list["CandidateDiscoveryRun"]] = relationship(
        foreign_keys="CandidateDiscoveryRun.filter_profile_id"
    )
