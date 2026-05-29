import sys
import os
import uuid
import asyncio
import json
import logging
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Configure paths
sys.path.append("/app")
sys.path.append("/app/src")

from apps.api.database import AsyncSessionFactory
from ks.domain.models import DocumentRegistry, KnowledgeFact, KnowledgeTag, SourceRegistry
from ks.domain.enums import TagType
from ks.common.llm_gateway import complete as gateway_complete
from ks.config.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("BackfillJob")


async def backfill_clinical_quality():
    settings = get_settings()
    logger.info("Starting Clinical Quality Backfill & Upgrade Job...")
    
    async with AsyncSessionFactory() as session:
        # 1. Query all documents with their sources and tags
        stmt = (
            select(DocumentRegistry)
            .options(
                selectinload(DocumentRegistry.source),
                selectinload(DocumentRegistry.tags),
                selectinload(DocumentRegistry.facts),
                selectinload(DocumentRegistry.summary)
            )
        )
        res = await session.execute(stmt)
        docs = res.scalars().all()
        
        logger.info(f"Retrieved {len(docs)} documents from PostgreSQL.")
        
        updated_docs_count = 0
        updated_facts_count = 0
        
        for i, doc in enumerate(docs):
            doc_id = doc.id
            logger.info(f"[{i+1}/{len(docs)}] Auditing document: {doc.title or 'N/A'} (ID: {doc_id})")
            
            # A. Dynamic Evidence Auditing via LLM Gateway
            # If not audited yet (or defaults to unclassified), run LLM audit
            if not doc.evidence_grade or doc.evidence_grade == "GRADE_D":
                # Hydrate text from MinIO or fallback to title/summary
                text = ""
                if doc.extracted_text_key:
                    try:
                        from minio import Minio
                        minio_client = Minio(
                            settings.minio.endpoint,
                            access_key=settings.minio.access_key,
                            secret_key=settings.minio.secret_key,
                            secure=settings.minio.secure
                        )
                        bucket = settings.minio.bucket_extracted
                        resp = minio_client.get_object(bucket, doc.extracted_text_key)
                        text = resp.read().decode("utf-8")[:12000]
                        resp.close()
                        resp.release_conn()
                    except Exception as minio_err:
                        logger.warning(f"Failed to fetch text from MinIO for {doc_id}: {minio_err}")
                
                if not text:
                    text = f"Title: {doc.title or 'N/A'}\n"
                    if doc.summary and doc.summary.summary_text:
                        text += f"Summary: {doc.summary.summary_text}"
                
                source_type = doc.source.source_type.value if doc.source else "GENERAL_HEALTH"
                
                try:
                    logger.info("Executing dynamic LoE audit...")
                    resp = await gateway_complete(
                        "enrichment.evidence_audit.v1",
                        {"title": doc.title or "N/A", "source_type": source_type, "text": text},
                        stage="enrichment",
                        document_id=str(doc_id)
                    )
                    
                    if resp.status in ("success", "cached"):
                        output = json.loads(resp.content)
                        doc.evidence_grade = output.get("evidence_grade", "GRADE_D")
                        doc.study_type = output.get("study_type", "Unclassified Study")
                        doc.methodology_critique = output.get("methodology_critique", "")
                        logger.info(f"  -> Audited LoE Grade: {doc.evidence_grade} ({doc.study_type})")
                        updated_docs_count += 1
                    else:
                        logger.warning(f"  -> Audit failed with gateway status: {resp.status}")
                except Exception as audit_err:
                    logger.error(f"  -> Audit exception occurred: {audit_err}")
            else:
                logger.info(f"  -> Skipping LoE audit: Document already graded as {doc.evidence_grade}")
            
            # B. Fact Entity Tagging
            # Pull extraction tags to help map types
            interventions = [t.tag_value for t in doc.tags if t.tag_type == TagType.INTERVENTION]
            conditions = [t.tag_value for t in doc.tags if t.tag_type == TagType.CONDITION]
            symptoms = [t.tag_value for t in doc.tags if t.tag_type == TagType.SYMPTOM]
            nutrients = [t.tag_value for t in doc.tags if t.tag_type == TagType.NUTRIENT]
            
            def get_entity_type(name: str) -> str | None:
                if not name:
                    return "OTHER"
                name_lower = name.lower().strip()
                if any(x.lower().strip() in name_lower or name_lower in x.lower().strip() for x in interventions):
                    return "INTERVENTION"
                if any(x.lower().strip() in name_lower or name_lower in x.lower().strip() for x in conditions):
                    return "CONDITION"
                if any(x.lower().strip() in name_lower or name_lower in x.lower().strip() for x in symptoms):
                    return "SYMPTOM"
                if any(x.lower().strip() in name_lower or name_lower in x.lower().strip() for x in nutrients):
                    return "INTERVENTION"
                # Heuristics
                if any(keyword in name_lower for keyword in ["insulin", "testosterone", "cortisol", "lh", "fsh", "hba1c", "glucose", "shbg", "progesterone", "estrogen", "tsh", "crp", "lipid"]):
                    return "BIOMARKER"
                if any(keyword in name_lower for keyword in ["metformin", "inositol", "spironolactone", "spearmint", "diet", "exercise", "training", "supplement", "vitamin", "dose", "mg"]):
                    return "INTERVENTION"
                return "OTHER"
            
            # Map types for all facts
            for fact in doc.facts:
                if not fact.subject_type or not fact.object_type:
                    fact.subject_type = get_entity_type(fact.subject)
                    fact.object_type = get_entity_type(fact.object_)
                    updated_facts_count += 1
            
            # Commit in batches of 5 documents to keep transactions quick
            if (i + 1) % 5 == 0 or (i + 1) == len(docs):
                await session.commit()
                logger.info(f"--- BATCH COMMITTED (Upgraded {updated_docs_count} docs, {updated_facts_count} facts so far) ---")
        
        logger.info("====================================================")
        logger.info("🏁 BACKFILL JOB COMPLETED SUCCESSFULLY!")
        logger.info(f"Total Upgraded Documents: {updated_docs_count}")
        logger.info(f"Total Upgraded Facts: {updated_facts_count}")
        logger.info("====================================================")

if __name__ == "__main__":
    asyncio.run(backfill_clinical_quality())
