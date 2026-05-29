"""Enrichment activities — worker tasks for analyzing text and extracting structured knowledge."""
import hashlib
import json
import logging
import uuid
from datetime import datetime

from minio import Minio
from temporalio import activity

from ks.common import redis_client
from ks.common.llm_gateway import complete as gateway_complete
from ks.common.llm_types import LLMBudgetExceeded
from ks.config.settings import get_settings
from ks.domain.enums import RunStatus, Framework, TagType, AssignedBy, ValidationStatus
from ks.domain.models import EnrichmentRun, KnowledgeSummary, KnowledgeTag, KnowledgeFact
from ks.enrichment.schemas import LLMEnrichmentOutput
from ks.enrichment.normalization import EntityNormalizer


logger = logging.getLogger(__name__)


class EnrichmentActivities:
    def __init__(self, minio_client: Minio):
        self.minio_client = minio_client
        self.settings = get_settings()
        self.normalizer = EntityNormalizer()

    def _fetch_text_from_payload(self, payload: dict) -> str:
        """Internal helper to fetch text from local memory or directly from MinIO."""
        if "text" in payload and payload["text"]:
            return payload["text"]

        if "extracted_text_key" in payload:
            key = payload["extracted_text_key"]
            bucket = self.settings.minio.bucket_extracted
            logger.info(f"JIT Hydration: Fetching text from MinIO: {bucket}/{key}")
            try:
                resp = self.minio_client.get_object(bucket, key)
                text = resp.read().decode("utf-8")
                resp.close()
                resp.release_conn()
                return text
            except Exception as e:
                logger.error(f"JIT Hydration failed for {key}: {e}")
                raise ValueError(f"Failed to load extracted text artifact: {str(e)}")

        raise ValueError("Neither 'text' nor 'extracted_text_key' present in enrichment payload.")

    @activity.defn
    async def fetch_extracted_text(self, payload: dict) -> dict:
        """
        Fetches the clean text artifact from MinIO.
        Payload keys: extracted_object_key
        """
        object_key = payload["extracted_object_key"]
        bucket = self.settings.minio.bucket_extracted

        logger.info(f"Fetching extracted text from MinIO: {bucket}/{object_key}")

        try:
            response = self.minio_client.get_object(bucket, object_key)
            content_bytes = response.read()
            text = content_bytes.decode("utf-8")
            response.close()
            response.release_conn()

            return {
                "object_key": object_key,
                "text": text,
                "success": True
            }
        except Exception as e:
            logger.error(f"Failed to fetch extracted text {object_key}: {e}")
            return {"success": False, "error": str(e)}

    @activity.defn
    async def detect_relevant_frameworks(self, payload: dict) -> dict:
        """
        Identifies which high-level scientific frameworks are present in the content.
        Payload: text OR extracted_text_key, model
        """
        extracted_text_key = payload.get("extracted_text_key", "")
        doc_id_prefix = extracted_text_key.split("/")[0] if extracted_text_key else None
        fw_cache_key = f"cache:frameworks:{doc_id_prefix}" if doc_id_prefix else None

        if fw_cache_key:
            cached = await redis_client.get_cache(fw_cache_key)
            if cached is not None:
                logger.info(f"Cache hit for framework detection: {fw_cache_key}")
                return cached

        try:
            raw_text = self._fetch_text_from_payload(payload)
            text = raw_text[:10000]
        except Exception as e:
            return {"success": False, "frameworks": ["PREVENTIVE_MEDICINE"], "error": f"Text fetch failed: {e}"}

        model = payload.get("model", self.settings.model.primary_model)

        prompt = f"""
        Categorize the content below into one or more of the following high-level Frameworks:
        - EVIDENCE_BASED_WESTERN_MEDICINE (Standard protocols, pharmaceuticals, surgeries)
        - NUTRITION_SCIENCE (Diet, foods, fasting, micronutrients, cooking)
        - PHYSICAL_ACTIVITY_SCIENCE (Exercise, biomechanics, gym, recovery, cardio)
        - HOLISTIC_TRADITIONAL_SYSTEMS (Herbs, TCM, Ayurveda, adaptogens, traditional systems)
        - PREVENTIVE_MEDICINE (Screening, lab benchmarks, disease avoidance)
        - DIAGNOSTICS_AND_LABS (Blood tests, biomarkers, reference ranges, clinical imaging)
        - PHARMACOLOGY_MEDICINE (Prescription drugs, dosages, mechanisms, side effects, drug-drug interactions)

        Return valid JSON in this strict format:
        {{"frameworks": ["FRAMEWORK_NAME_1", "FRAMEWORK_NAME_2"]}}

        Text Sample: {text}
        """

        try:
            resp = await gateway_complete(
                "enrichment.framework_detection.v1",
                {"text": text},
                stage="enrichment",
                run_id=payload.get("run_id"),
                document_id=payload.get("document_id"),
            )
            if resp.status != "success":
                return {"success": False, "frameworks": ["PREVENTIVE_MEDICINE"], "error": resp.status}

            output = json.loads(resp.content)
            frameworks = output.get("frameworks", ["PREVENTIVE_MEDICINE"]) or ["PREVENTIVE_MEDICINE"]

            result = {"success": True, "frameworks": frameworks}
            if fw_cache_key:
                await redis_client.set_cache(fw_cache_key, result, ttl=redis_client.DEDUP_TTL)
            return result
        except Exception as e:
            logger.error(f"Framework detection failed: {e}")
            return {"success": False, "frameworks": ["PREVENTIVE_MEDICINE"], "error": str(e)}

    @activity.defn
    async def audit_clinical_evidence(self, payload: dict) -> dict:
        """
        Audits the document methodology and abstract to determine Level of Evidence (LoE) grade.
        Payload: text OR extracted_text_key, document_id, run_id
        """
        from apps.api.database import SessionLocal
        from ks.domain.models import DocumentRegistry
        from sqlalchemy import select as sa_select

        doc_id = uuid.UUID(payload["document_id"])
        
        try:
            async with SessionLocal() as session:
                # Hydrate title and source type from PostgreSQL dynamically
                stmt = sa_select(DocumentRegistry).where(DocumentRegistry.id == doc_id).join(DocumentRegistry.source)
                res = await session.execute(stmt)
                doc = res.scalar_one_or_none()
                if doc:
                    title = doc.title or "Unknown Title"
                    source_type = doc.source.source_type.value if doc.source else "GENERAL_HEALTH"
                else:
                    title = "Unknown Title"
                    source_type = "GENERAL_HEALTH"
        except Exception as e:
            logger.warning(f"Database query failed for document {doc_id}: {e}")
            title = "Unknown Title"
            source_type = "GENERAL_HEALTH"
        
        try:
            raw_text = self._fetch_text_from_payload(payload)
            # Use first 12,000 characters for abstract / methodology
            text = raw_text[:12000]
        except Exception as e:
            return {
                "success": False, 
                "evidence_grade": "GRADE_D", 
                "study_type": "Unknown Methodology", 
                "methodology_critique": f"Text fetch failed: {e}"
            }

        try:
            logger.info("Running dynamic Level of Evidence (LoE) audit via gateway")
            resp = await gateway_complete(
                "enrichment.evidence_audit.v1",
                {"title": title, "source_type": source_type, "text": text},
                stage="enrichment",
                run_id=payload.get("run_id"),
                document_id=payload.get("document_id"),
            )
            if resp.status not in ("success", "cached"):
                return {
                    "success": False, 
                    "evidence_grade": "GRADE_D", 
                    "study_type": "Unclassified Study", 
                    "methodology_critique": f"LLM Gateway status: {resp.status}"
                }

            output = json.loads(resp.content)
            return {
                "success": True,
                "evidence_grade": output.get("evidence_grade", "GRADE_D"),
                "study_type": output.get("study_type", "Unclassified Study"),
                "methodology_critique": output.get("methodology_critique", "")
            }
        except Exception as e:
            logger.error(f"Clinical evidence audit failed: {e}")
            return {
                "success": False, 
                "evidence_grade": "GRADE_D", 
                "study_type": "Unclassified Study", 
                "methodology_critique": str(e)
            }

    @activity.defn
    async def run_llm_enrichment(self, payload: dict) -> dict:
        """
        Calls litellm to parse the text and return structured JSON based on LLMEnrichmentOutput schema.
        Payload keys: text OR extracted_text_key, model, framework
        """
        extracted_text_key = payload.get("extracted_text_key", "")
        doc_id_prefix = extracted_text_key.split("/")[0] if extracted_text_key else "unknown"
        framework = payload.get("framework", "general")
        lock_key = f"lock:enrichment:{doc_id_prefix}:{framework}"

        if not await redis_client.acquire_lock(lock_key, ttl=redis_client.LOCK_ENRICHMENT):
            from temporalio.exceptions import ApplicationError
            raise ApplicationError(f"Enrichment lock held for {lock_key}", non_retryable=False)

        try:
            try:
                text = self._fetch_text_from_payload(payload)
            except Exception as e:
                return {"success": False, "error": f"Payload hydration failed: {e}"}

            source_type = payload.get("source_type", "GENERAL_HEALTH")
            framework = payload.get("framework")

            try:
                logger.info("Running LLM enrichment via gateway")

                response = await gateway_complete(
                    "enrichment.extraction.v1",
                    {
                        "text": text,
                        "framework": framework,
                        "source_type": source_type,
                    },
                    stage="enrichment",
                    run_id=payload.get("run_id"),
                    document_id=payload.get("document_id"),
                )

                if response.status not in ("success", "cached"):
                    return {"success": False, "error": response.status}

                output_json = response.content
                try:
                    parsed_output = json.loads(output_json) if isinstance(output_json, str) else output_json
                    return {
                        "success": True,
                        "enrichment": parsed_output,
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    }
                except json.JSONDecodeError as e:
                    logger.error(f"LLM returned invalid JSON: {output_json}")
                    return {"success": False, "error": f"Invalid JSON returned by LLM: {e}"}

            except Exception as e:
                logger.error(f"Failed to run LLM enrichment: {e}")
                return {"success": False, "error": str(e)}
        finally:
            await redis_client.release_lock(lock_key)

    @activity.defn
    async def persist_enrichment_results(self, payload: dict) -> dict:
        """
        Saves the structured LLM output to the PostgreSQL database.
        Payload keys: run_id, document_id, enrichment (dict), model
        """
        from apps.api.database import SessionLocal

        doc_id = uuid.UUID(payload["document_id"])
        enrichment = payload["enrichment"]
        model = payload["model"]
        verification_report = payload.get("verification_report", [])

        # Index verification report by fact index for fast lookup
        v_map = {v.get("fact_index"): v for v in verification_report}

        redis_keys_to_mark: list[str] = []

        async with SessionLocal() as session:
            try:
                from sqlalchemy import select as sa_select
                from ks.domain.models import DocumentRegistry
                # Update Document level clinical quality metadata
                existing_doc = (await session.execute(
                    sa_select(DocumentRegistry).where(DocumentRegistry.id == doc_id)
                )).scalar_one_or_none()
                if existing_doc:
                    existing_doc.evidence_grade = payload.get("evidence_grade", "GRADE_D")
                    existing_doc.study_type = payload.get("study_type")
                    existing_doc.methodology_critique = payload.get("methodology_critique")

                # 1. Upsert Summary — update if exists, create if not
                existing_summary = (await session.execute(
                    sa_select(KnowledgeSummary).where(KnowledgeSummary.document_id == doc_id)
                )).scalar_one_or_none()

                if existing_summary:
                    existing_summary.summary_text = enrichment.get("summary", "")
                    existing_summary.model_used = model
                    existing_summary.prompt_version = "v1"
                    existing_summary.validation_status = ValidationStatus.PENDING
                else:
                    summary = KnowledgeSummary(
                        document_id=doc_id,
                        summary_text=enrichment.get("summary", ""),
                        model_used=model,
                        prompt_version="v1",
                        validation_status=ValidationStatus.PENDING
                    )
                    session.add(summary)

                # 2. Save Tags (Frameworks and Topics)
                async def add_tag_if_new(doc_id, t_type, t_value, is_primary=False):
                    tag_key = f"dedup:tag:{redis_client.sha256(f'{doc_id}{t_type}{t_value}')}"
                    if await redis_client.check_dedup(tag_key):
                        return
                    stmt = sa_select(KnowledgeTag).where(
                        KnowledgeTag.document_id == doc_id,
                        KnowledgeTag.tag_type == t_type,
                        KnowledgeTag.tag_value == t_value
                    )
                    existing = await session.execute(stmt)
                    if not existing.scalar_one_or_none():
                        tag = KnowledgeTag(
                            document_id=doc_id,
                            tag_type=t_type,
                            tag_value=t_value,
                            is_primary=is_primary,
                            assigned_by=AssignedBy.MODEL
                        )
                        session.add(tag)
                        redis_keys_to_mark.append(tag_key)

                primary_fw = enrichment.get("primary_framework")
                if primary_fw:
                    await add_tag_if_new(doc_id, TagType.FRAMEWORK, primary_fw, is_primary=True)

                for fw in enrichment.get("secondary_frameworks", []):
                    await add_tag_if_new(doc_id, TagType.FRAMEWORK, fw)

                for topic in enrichment.get("topics", []):
                    await add_tag_if_new(doc_id, TagType.TOPIC, topic)


                # Granular Health Tags
                tag_mapping = {
                    "conditions": TagType.CONDITION,
                    "symptoms": TagType.SYMPTOM,
                    "interventions": TagType.INTERVENTION,
                    "nutrients": TagType.NUTRIENT,
                    "populations": TagType.POPULATION
                }

                for key, t_type in tag_mapping.items():
                    for val in enrichment.get(key, []):
                        if val:
                            await add_tag_if_new(doc_id, t_type, val)

                # 3. Save Facts
                for fact_data in enrichment.get("facts", []):
                    # NORMALIZE ENTITIES before dedup check and persistence
                    raw_subject = fact_data.get("subject")
                    raw_object = fact_data.get("object_value")

                    norm_subject, _, norm_object = await self.normalizer.normalize_triple(
                        raw_subject, "", raw_object
                    )

                    # Redis dedup — fast path before DB SELECT
                    predicate = fact_data.get("predicate")
                    fact_key = f"dedup:fact:{redis_client.sha256(f'{doc_id}{norm_subject}{predicate}{norm_object}')}"
                    if await redis_client.check_dedup(fact_key):
                        continue

                    # DB dedup fallback
                    stmt = sa_select(KnowledgeFact).where(
                        KnowledgeFact.document_id == doc_id,
                        KnowledgeFact.subject == norm_subject,
                        KnowledgeFact.predicate == predicate,
                        KnowledgeFact.object_ == norm_object
                    )
                    existing_fact = await session.execute(stmt)
                    if existing_fact.scalar_one_or_none():
                        continue

                    # AUTO-VALIDATION: If confidence is high (> 0.9), mark as VALIDATED immediately.
                    # This reduces the manual bottleneck for high-fidelity sources.
                    confidence = fact_data.get("confidence", 0.8)
                    status = ValidationStatus.VALIDATED if confidence > 0.9 else ValidationStatus.PENDING

                    # Apply verification results if available
                    v_result = v_map.get(enrichment.get("facts", []).index(fact_data))
                    is_hallucination = False
                    critique = None
                    if v_result:
                        is_hallucination = v_result.get("is_hallucination", False)
                        critique = v_result.get("critique")
                        if is_hallucination:
                            status = ValidationStatus.PENDING # Force human review

                    # Determine subject type and object type based on extraction tags & medical keywords
                    def get_entity_type(name: str) -> str | None:
                        if not name:
                            return "OTHER"
                        name_lower = name.lower().strip()
                        if any(x.lower().strip() in name_lower or name_lower in x.lower().strip() for x in enrichment.get("interventions", [])):
                            return "INTERVENTION"
                        if any(x.lower().strip() in name_lower or name_lower in x.lower().strip() for x in enrichment.get("conditions", [])):
                            return "CONDITION"
                        if any(x.lower().strip() in name_lower or name_lower in x.lower().strip() for x in enrichment.get("symptoms", [])):
                            return "SYMPTOM"
                        if any(x.lower().strip() in name_lower or name_lower in x.lower().strip() for x in enrichment.get("nutrients", [])):
                            return "INTERVENTION"
                        # Heuristic checks
                        if any(keyword in name_lower for keyword in ["insulin", "testosterone", "cortisol", "lh", "fsh", "hba1c", "glucose", "shbg", "progesterone", "estrogen", "tsh", "crp", "lipid"]):
                            return "BIOMARKER"
                        if any(keyword in name_lower for keyword in ["metformin", "inositol", "spironolactone", "spearmint", "diet", "exercise", "training", "supplement", "vitamin", "dose", "mg"]):
                            return "INTERVENTION"
                        return "OTHER"

                    fact = KnowledgeFact(
                        document_id=doc_id,
                        fact_text=fact_data.get("fact_text", ""),
                        subject=norm_subject,
                        predicate=fact_data.get("predicate"),
                        object_=norm_object,
                        confidence=confidence,
                        source_span=fact_data.get("source_span"),
                        validation_status=status,
                        is_hallucination=is_hallucination,
                        critique=critique,
                        subject_type=get_entity_type(norm_subject),
                        object_type=get_entity_type(norm_object)
                    )
                    session.add(fact)
                    redis_keys_to_mark.append(fact_key)

                await session.commit()
                for key in redis_keys_to_mark:
                    await redis_client.mark_seen(key)
                return {"success": True}

            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to persist enrichment results to DB: {e}")
                return {"success": False, "error": str(e)}

    @activity.defn
    async def update_enrichment_status(self, payload: dict) -> None:
        """
        Updates the EnrichmentRun status in the DB.
        """
        from apps.api.database import SessionLocal
        from sqlalchemy import select

        run_id = uuid.UUID(payload["run_id"])
        status = RunStatus(payload["status"])
        error_msg = payload.get("error_message")
        prompt_tokens = payload.get("prompt_tokens")
        completion_tokens = payload.get("completion_tokens")
        total_tokens = payload.get("total_tokens")

        async with SessionLocal() as session:
            res = await session.execute(select(EnrichmentRun).where(EnrichmentRun.id == run_id))
            run = res.scalar_one_or_none()
            if run:
                run.status = status
                run.completed_at = datetime.now()

                # Update model used if passed (handles fallbacks)
                model_used = payload.get("model_used")
                if model_used:
                    run.model_used = model_used

                if prompt_tokens is not None:
                    run.prompt_tokens = prompt_tokens
                if completion_tokens is not None:
                    run.completion_tokens = completion_tokens
                if total_tokens is not None:
                    run.total_tokens = total_tokens
                if error_msg:
                    run.error_message = error_msg

                # CRITICAL STATE PROPAGATION
                if status == RunStatus.COMPLETED:
                    from ks.domain.models import DocumentRegistry
                    from ks.domain.enums import DocumentStatus
                    doc_res = await session.execute(select(DocumentRegistry).where(DocumentRegistry.id == run.document_id))
                    doc = doc_res.scalar_one_or_none()
                    if doc:
                        doc.status = DocumentStatus.ENRICHED

            await session.commit()

    @activity.defn
    async def verify_extraction_activity(self, payload: dict) -> dict:
        """
        Critic Agent: Reviews extracted facts against the source text to identify hallucinations.
        """
        facts = payload["facts"] # List of extracted facts
        source_text = payload["source_text"]

        prompt = (
            "You are a clinical integrity auditor. Your job is to verify if the following extracted facts are accurately supported by the provided source text.\n\n"
            "SOURCE TEXT:\n"
            f"{source_text[:12000]}\n\n"
            "EXTRACTED FACTS:\n"
            f"{json.dumps(facts, indent=2)}\n\n"
            "For each fact, determine if it is a hallucination or inaccurate. Provide a critique and suggested fix if needed.\n"
            "Return valid JSON: {\"verifications\": [{\"fact_index\": 0, \"is_hallucination\": false, \"confidence_score\": 0.95, \"critique\": \"...\", \"suggested_fix\": \"...\"}]}"
        )

        try:
            resp = await gateway_complete(
                "enrichment.verification.v1",
                {"source_text": source_text, "facts": facts},
                stage="enrichment",
                cache=False,
            )
            if resp.status not in ("success", "cached"):
                return {"success": False, "error": resp.status}
            report = json.loads(resp.content)
            return {"success": True, "report": report.get("verifications", [])}
        except Exception as e:
            logger.error(f"Verification activity failed: {e}")
            return {"success": False, "error": str(e)}
