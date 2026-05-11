"""Initial schema — all 20 tables

Revision ID: 001
Revises:
Create Date: 2026-05-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enums ─────────────────────────────────────────────────────────────────
    source_approval_status = sa.Enum(
        "CANDIDATE", "UNDER_REVIEW", "APPROVED_LIMITED", "APPROVED_ACTIVE",
        "PAUSED", "BLOCKED", "RETIRED", name="sourceapprovalstatus"
    )
    source_type = sa.Enum(
        "GUIDELINE_SOURCE", "PUBLIC_HEALTH_SOURCE", "ACADEMIC_SOURCE",
        "HOSPITAL_EDUCATION_SOURCE", "NUTRITION_GUIDANCE_SOURCE",
        "EXERCISE_SCIENCE_SOURCE", "BEHAVIORAL_HEALTH_SOURCE",
        "TRADITIONAL_SYSTEM_SOURCE", "RECIPE_OR_LIFESTYLE_SOURCE",
        "DATASET_OR_API_SOURCE", "MANUAL_REFERENCE_SOURCE", name="sourcetype"
    )
    framework = sa.Enum(
        "EVIDENCE_BASED_WESTERN_MEDICINE", "NUTRITION_SCIENCE",
        "PHYSICAL_ACTIVITY_SCIENCE", "HOLISTIC_TRADITIONAL_SYSTEMS",
        "LIFESTYLE_BEHAVIORAL_HEALTH", name="framework"
    )
    document_status = sa.Enum(
        "DISCOVERED", "QUEUED_FOR_FETCH", "FETCHED", "EXTRACTION_PENDING",
        "EXTRACTED", "ENRICHMENT_PENDING", "ENRICHED", "INDEXED",
        "REVIEW_REQUIRED", "FAILED", name="documentstatus"
    )
    doc_type = sa.Enum("HTML_PAGE", "PDF", "OTHER", name="doctype")
    discovery_mode = sa.Enum("GENERIC", "FOCUSED", "HYBRID", name="discoverymode")
    discovery_decision = sa.Enum("INGEST_NOW", "INGEST_LATER", "REJECT_FOR_NOW", name="discoverydecision")
    review_decision = sa.Enum("APPROVED", "REJECTED", "NEEDS_CHANGES", "ESCALATE", name="reviewdecision")
    workflow_status = sa.Enum("RUNNING", "COMPLETED", "FAILED", "CANCELLED", name="workflowstatus")
    run_status = sa.Enum("PENDING", "RUNNING", "COMPLETED", "FAILED", "SKIPPED", name="runstatus")
    extraction_quality = sa.Enum("HIGH", "MEDIUM", "LOW", "FAILED", name="extractionquality")
    validation_status = sa.Enum("VALID", "INVALID", "PENDING", "REVIEW_REQUIRED", name="validationstatus")
    tag_type = sa.Enum(
        "FRAMEWORK", "TOPIC", "CONDITION", "SYMPTOM",
        "INTERVENTION", "SUPPLEMENT", "FOOD", name="tagtype"
    )
    assigned_by = sa.Enum("RULE", "MODEL", "MANUAL", name="assignedby")
    graph_node_type = sa.Enum(
        "SOURCE", "DOCUMENT", "FRAMEWORK", "TOPIC", "CONDITION",
        "SYMPTOM", "INTERVENTION", "SUPPLEMENT", "FOOD", name="graphnodetype"
    )
    graph_edge_type = sa.Enum(
        "SOURCE_HAS_DOCUMENT", "DOCUMENT_BELONGS_TO_FRAMEWORK", "DOCUMENT_HAS_TOPIC",
        "DOCUMENT_MENTIONS_CONDITION", "DOCUMENT_MENTIONS_SYMPTOM",
        "DOCUMENT_MENTIONS_INTERVENTION", "DOCUMENT_MENTIONS_SUPPLEMENT",
        "DOCUMENT_MENTIONS_FOOD", "TOPIC_RELATED_TO_TOPIC", name="graphedgetype"
    )
    graph_provenance = sa.Enum("EXTRACTION", "ENRICHMENT", "MANUAL", name="graphprovenance")
    review_entity_type = sa.Enum("SOURCE", "DOCUMENT", "ENRICHMENT", name="reviewentitytype")

    # ── source_registry ───────────────────────────────────────────────────────
    op.create_table(
        "source_registry",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("root_url", sa.Text, nullable=False, unique=True),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("language", sa.String(10), server_default="en"),
        sa.Column("region", sa.String(100)),
        sa.Column("trust_tier", sa.Integer, server_default="3"),
        sa.Column("authority_score", sa.Float),
        sa.Column("evidence_score", sa.Float),
        sa.Column("transparency_score", sa.Float),
        sa.Column("stability_score", sa.Float),
        sa.Column("approval_status", source_approval_status, server_default="CANDIDATE"),
        sa.Column("crawl_policy", JSONB),
        sa.Column("extraction_profile", JSONB),
        sa.Column("freshness_days", sa.Integer, server_default="14"),
        sa.Column("review_notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_source_registry_approval_status", "source_registry", ["approval_status"])

    # ── source_policy ─────────────────────────────────────────────────────────
    op.create_table(
        "source_policy",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("source_registry.id", ondelete="CASCADE")),
        sa.Column("authority", sa.Float),
        sa.Column("evidence_orientation", sa.Float),
        sa.Column("transparency", sa.Float),
        sa.Column("stability", sa.Float),
        sa.Column("relevance", sa.Float),
        sa.Column("extraction_feasibility", sa.Float),
        sa.Column("safety_risk", sa.Float),
        sa.Column("policy_compliance", sa.Float),
        sa.Column("composite_score", sa.Float),
        sa.Column("evaluated_at", sa.DateTime(timezone=True)),
    )

    # ── source_framework_map ──────────────────────────────────────────────────
    op.create_table(
        "source_framework_map",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("source_registry.id", ondelete="CASCADE")),
        sa.Column("framework", framework, nullable=False),
        sa.Column("is_primary", sa.Boolean, server_default="false"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_source_framework_map_source_id", "source_framework_map", ["source_id"])

    # ── source_review ─────────────────────────────────────────────────────────
    op.create_table(
        "source_review",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("source_registry.id", ondelete="CASCADE")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("actor", sa.String(255)),
        sa.Column("decision", review_decision),
        sa.Column("reason", sa.Text),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── discovery_filter_profile (needed before candidate_discovery_run FK) ───
    op.create_table(
        "discovery_filter_profile",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("mode", discovery_mode, nullable=False),
        sa.Column("topics", ARRAY(sa.Text)),
        sa.Column("synonyms", JSONB),
        sa.Column("frameworks", ARRAY(sa.Text)),
        sa.Column("max_candidates", sa.Integer, server_default="100"),
        sa.Column("per_source_limit", sa.Integer, server_default="20"),
        sa.Column("reference_context", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── document_registry ─────────────────────────────────────────────────────
    op.create_table(
        "document_registry",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("source_registry.id", ondelete="CASCADE")),
        sa.Column("canonical_url", sa.Text, nullable=False, unique=True),
        sa.Column("title", sa.Text),
        sa.Column("doc_type", doc_type, server_default="HTML_PAGE"),
        sa.Column("discovery_mode", discovery_mode),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("status", document_status, server_default="DISCOVERED"),
        sa.Column("publication_date", sa.Date),
        sa.Column("author", sa.Text),
        sa.Column("language", sa.String(10), server_default="en"),
        sa.Column("word_count", sa.Integer),
        sa.Column("raw_object_key", sa.Text),
        sa.Column("extracted_text_key", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_document_registry_source_id", "document_registry", ["source_id"])
    op.create_index("ix_document_registry_status", "document_registry", ["status"])

    # ── document_version ──────────────────────────────────────────────────────
    op.create_table(
        "document_version",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("document_registry.id", ondelete="CASCADE")),
        sa.Column("version_hash", sa.String(64)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("raw_object_key", sa.Text),
    )

    # ── candidate_discovery_run ───────────────────────────────────────────────
    op.create_table(
        "candidate_discovery_run",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("mode", discovery_mode, nullable=False),
        sa.Column("filter_profile_id", UUID(as_uuid=True),
                  sa.ForeignKey("discovery_filter_profile.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_scope", JSONB),
        sa.Column("framework_scope", JSONB),
        sa.Column("status", run_status, server_default="PENDING"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("candidate_count", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── candidate_document_evaluation ─────────────────────────────────────────
    op.create_table(
        "candidate_document_evaluation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("candidate_discovery_run.id", ondelete="CASCADE")),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("document_registry.id", ondelete="CASCADE")),
        sa.Column("score", sa.Float),
        sa.Column("matched_terms", ARRAY(sa.Text)),
        sa.Column("matched_frameworks", ARRAY(sa.Text)),
        sa.Column("decision", discovery_decision, server_default="INGEST_NOW"),
        sa.Column("decision_overridden_by", sa.String(255)),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── run tables ────────────────────────────────────────────────────────────
    for table_name in ("fetch_run", "extraction_run", "enrichment_run", "chunk_run", "graph_run"):
        extra_cols = []
        if table_name == "extraction_run":
            extra_cols = [sa.Column("extraction_quality", extraction_quality)]
        elif table_name == "enrichment_run":
            extra_cols = [sa.Column("model_used", sa.String(255))]
        elif table_name == "chunk_run":
            extra_cols = [
                sa.Column("chunk_count", sa.Integer, server_default="0"),
                sa.Column("embedding_model", sa.String(255)),
            ]
        elif table_name == "graph_run":
            extra_cols = [
                sa.Column("nodes_created", sa.Integer, server_default="0"),
                sa.Column("edges_created", sa.Integer, server_default="0"),
            ]
        op.create_table(
            table_name,
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("document_id", UUID(as_uuid=True),
                      sa.ForeignKey("document_registry.id", ondelete="CASCADE")),
            sa.Column("status", run_status, server_default="PENDING"),
            *extra_cols,
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("error_message", sa.Text),
            sa.Column("metadata", JSONB),
        )

    # ── knowledge_summary ─────────────────────────────────────────────────────
    op.create_table(
        "knowledge_summary",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True),
                  sa.ForeignKey("document_registry.id", ondelete="CASCADE"), unique=True),
        sa.Column("summary_text", sa.Text, nullable=False),
        sa.Column("model_used", sa.String(255)),
        sa.Column("prompt_version", sa.String(50)),
        sa.Column("confidence_score", sa.Float),
        sa.Column("validation_status", validation_status, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── knowledge_chunk ───────────────────────────────────────────────────────
    op.create_table(
        "knowledge_chunk",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("document_registry.id", ondelete="CASCADE")),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer),
        sa.Column("framework", framework),
        sa.Column("topics", ARRAY(sa.Text)),
        sa.Column("qdrant_point_id", UUID(as_uuid=True)),
        sa.Column("embedding_model", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_chunk_document_id", "knowledge_chunk", ["document_id"])

    # ── knowledge_fact ────────────────────────────────────────────────────────
    op.create_table(
        "knowledge_fact",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("document_registry.id", ondelete="CASCADE")),
        sa.Column("fact_type", sa.String(100)),
        sa.Column("fact_text", sa.Text, nullable=False),
        sa.Column("subject", sa.Text),
        sa.Column("predicate", sa.Text),
        sa.Column("object", sa.Text),
        sa.Column("confidence", sa.Float),
        sa.Column("source_span", sa.Text),
        sa.Column("validation_status", validation_status, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── knowledge_tag ─────────────────────────────────────────────────────────
    op.create_table(
        "knowledge_tag",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("document_registry.id", ondelete="CASCADE")),
        sa.Column("tag_type", tag_type, nullable=False),
        sa.Column("tag_value", sa.Text, nullable=False),
        sa.Column("is_primary", sa.Boolean, server_default="false"),
        sa.Column("assigned_by", assigned_by, server_default="MODEL"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_tag_document_id", "knowledge_tag", ["document_id"])

    # ── graph_node ────────────────────────────────────────────────────────────
    op.create_table(
        "graph_node",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("node_type", graph_node_type, nullable=False),
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("properties", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_graph_node_type_external", "graph_node", ["node_type", "external_id"], unique=True)

    # ── graph_edge ────────────────────────────────────────────────────────────
    op.create_table(
        "graph_edge",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("from_node_id", UUID(as_uuid=True), sa.ForeignKey("graph_node.id", ondelete="CASCADE")),
        sa.Column("to_node_id", UUID(as_uuid=True), sa.ForeignKey("graph_node.id", ondelete="CASCADE")),
        sa.Column("edge_type", graph_edge_type, nullable=False),
        sa.Column("weight", sa.Float, server_default="1.0"),
        sa.Column("provenance", graph_provenance, server_default="ENRICHMENT"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_graph_edge_from_to", "graph_edge", ["from_node_id", "to_node_id", "edge_type"])

    # ── workflow_run ──────────────────────────────────────────────────────────
    op.create_table(
        "workflow_run",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_type", sa.String(100), nullable=False),
        sa.Column("temporal_workflow_id", sa.String(255)),
        sa.Column("source_id", UUID(as_uuid=True),
                  sa.ForeignKey("source_registry.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_id", UUID(as_uuid=True),
                  sa.ForeignKey("document_registry.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", workflow_status, server_default="RUNNING"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text),
        sa.Column("metadata", JSONB),
    )
    op.create_index("ix_workflow_run_status", "workflow_run", ["status"])

    # ── review_queue ──────────────────────────────────────────────────────────
    op.create_table(
        "review_queue",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", review_entity_type, nullable=False),
        sa.Column("entity_id", sa.Text, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("priority", sa.Integer, server_default="5"),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("assigned_to", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )

    # ── job_error ─────────────────────────────────────────────────────────────
    op.create_table(
        "job_error",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_run_id", UUID(as_uuid=True),
                  sa.ForeignKey("workflow_run.id", ondelete="CASCADE")),
        sa.Column("activity_name", sa.String(255)),
        sa.Column("error_type", sa.String(255)),
        sa.Column("error_message", sa.Text),
        sa.Column("stack_trace", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── admin_audit_log ───────────────────────────────────────────────────────
    op.create_table(
        "admin_audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("entity_type", sa.String(100)),
        sa.Column("entity_id", sa.Text),
        sa.Column("before_state", JSONB),
        sa.Column("after_state", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_admin_audit_log_entity", "admin_audit_log", ["entity_type", "entity_id"])


def downgrade() -> None:
    tables = [
        "admin_audit_log", "job_error", "review_queue", "workflow_run",
        "graph_edge", "graph_node", "knowledge_tag", "knowledge_fact",
        "knowledge_chunk", "knowledge_summary",
        "graph_run", "chunk_run", "enrichment_run", "extraction_run", "fetch_run",
        "candidate_document_evaluation", "candidate_discovery_run",
        "document_version", "document_registry", "discovery_filter_profile",
        "source_review", "source_framework_map", "source_policy", "source_registry",
    ]
    for t in tables:
        op.drop_table(t)

    enums = [
        "sourceapprovalstatus", "sourcetype", "framework", "documentstatus",
        "doctype", "discoverymode", "discoverydecision", "reviewdecision",
        "workflowstatus", "runstatus", "extractionquality", "validationstatus",
        "tagtype", "assignedby", "graphnodetype", "graphedgetype",
        "graphprovenance", "reviewentitytype",
    ]
    for e in enums:
        sa.Enum(name=e).drop(op.get_bind())
