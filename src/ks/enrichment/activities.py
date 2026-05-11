"""Enrichment activities — worker tasks for analyzing text and extracting structured knowledge."""
import json
import logging
import uuid
from datetime import datetime

import litellm
from minio import Minio
from temporalio import activity

from ks.config.settings import get_settings
from ks.domain.enums import RunStatus, Framework, TagType, AssignedBy, ValidationStatus
from ks.domain.models import EnrichmentRun, KnowledgeSummary, KnowledgeTag, KnowledgeFact
from ks.enrichment.schemas import LLMEnrichmentOutput


logger = logging.getLogger(__name__)


class EnrichmentActivities:
    def __init__(self, minio_client: Minio):
        self.minio_client = minio_client
        self.settings = get_settings()

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
    async def run_llm_enrichment(self, payload: dict) -> dict:
        """
        Calls litellm to parse the text and return structured JSON based on LLMEnrichmentOutput schema.
        Payload keys: text, model
        """
        text = payload["text"]
        model = payload.get("model", "gpt-3.5-turbo")
        
        # Truncate text to avoid overloading prompt context
        truncated_text = text[:25000]
        
        # Truncate text if it's exceptionally long for Phase 1 context window constraints
        # Real implementation would chunk or map-reduce this
        source_type = payload.get("source_type", "GENERAL_HEALTH")
        
        is_clinical = source_type in ["PRESCRIPTION_SOURCE", "CLINICAL_REPORT_SOURCE"]
        
        clinical_context = ""
        if is_clinical:
            clinical_context = """
            SPECIALIZED CLINICAL MODE ENABLED:
            - Focus on RX IDENTIFIERS: Active ingredients, Brand names, and Medication Classes.
            - Focus on CLINICAL MARKERS: Reference ranges (e.g., "Normal: 70-100 mg/dL"), units of measure, and test names.
            - Precise DOSAGE extraction: Capture frequency (BID, QD), strength, and administration route.
            - CONTRADICTIONS: Be extremely granular about drug-drug or drug-condition interactions.
            """

        prompt = f"""
        You are a world-class health knowledge graph extractor. Your goal is to convert medical text into high-fidelity structured intelligence.
        {clinical_context}
        
        Extract the following attributes if present in the text:
        - CONDITIONS & SYMPTOMS: Medical conditions, diseases, and their associated symptoms.
        - INTERVENTIONS: Medications, procedures, or lifestyle changes.
        - DOSAGE & DURATION: Specific amounts (e.g., "500mg") and timeframes (e.g., "for 10 days").
        - FOOD & NUTRIENTS: Specific foods, diets, or nutritional markers (e.g., "Vitamin B12").
        - POPULATION APPLICABILITY: Who is this for? (e.g., "Adults", "Pregnant women", "Athletes").
        - BENEFITS & CAUTIONS: Positive outcomes and potential risks or side effects.
        - EVIDENCE CATEGORY: Clinical evidence levels (e.g., "Systematic Review", "Expert Opinion").
        - CONTRAINDICATION MARKERS: When should this NOT be used?
        
        Guidelines for Facts:
        - Format every insight as a Subject-Predicate-Object (S-P-O) triple.
        - Subject: The main entity (e.g., "Lisinopril").
        - Predicate: The relationship (e.g., "prescribed for", "dosage is", "should be avoided in").
        - Object: The value or target (e.g., "Hypertension", "10mg daily", "Kidney disease").
        
        Text:
        {truncated_text}
        """
        
        try:
            logger.info(f"Running LLM enrichment using model: {model}")
            
            # Route the correct API key based on the model being called
            m = model.lower()
            if "deepseek" in m:
                api_key = self.settings.model.primary_api_key
                api_base = self.settings.model.primary_api_base
                # DeepSeek supports JSON mode but not JSON Schema response_format
                # Inject schema instructions into the prompt
                schema_hint = (
                    '\n\nReturn ONLY valid JSON matching this schema (no markdown, no explanation):\n'
                    '{"summary": "string", "primary_framework": "one of NUTRITION|EXERCISE|SLEEP|STRESS|HYDRATION|SUPPLEMENTATION|RECOVERY|GENERAL|PREVENTIVE_MEDICINE", '
                    '"secondary_frameworks": ["..."], "topics": ["..."], '
                    '"conditions": ["..."], "symptoms": ["..."], "interventions": ["..."], "nutrients": ["..."], "populations": ["..."], '
                    '"facts": [{"fact_text": "...", "subject": "...", "predicate": "...", "object_value": "...", "confidence": 0.9, "source_span": "..."}]}'
                )
                full_prompt = prompt + schema_hint
                call_kwargs = dict(
                    model=model,
                    messages=[{"role": "user", "content": full_prompt}],
                    response_format={"type": "json_object"},
                    api_key=api_key,
                    api_base=api_base
                )
            elif "gpt" in m or "openai" in m:
                api_key = self.settings.model.secondary_api_key
                # OpenAI gpt-4o-mini supports full structured output with Pydantic class
                call_kwargs = dict(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format=LLMEnrichmentOutput,
                    api_key=api_key
                )
            else:
                api_key = self.settings.model.primary_api_key
                call_kwargs = dict(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    api_key=api_key
                )
            
            response = litellm.completion(**call_kwargs)
            
            # Litellm parses it back if using structured output, otherwise we parse JSON
            output_json = response.choices[0].message.content
            
            try:
                # Some models return pure JSON strings, others return objects depending on litellm version
                if isinstance(output_json, str):
                    parsed_output = json.loads(output_json)
                else:
                    parsed_output = output_json
                    
                # Extract token usage
                usage = getattr(response, "usage", None)
                usage_data = {}
                if usage:
                    usage_data = {
                        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(usage, "completion_tokens", 0),
                        "total_tokens": getattr(usage, "total_tokens", 0)
                    }
                    
                return {"success": True, "enrichment": parsed_output, **usage_data}
                
            except json.JSONDecodeError as e:
                logger.error(f"LLM returned invalid JSON: {output_json}")
                return {"success": False, "error": f"Invalid JSON returned by LLM: {e}"}
                
        except Exception as e:
            logger.error(f"Failed to run LLM enrichment: {e}")
            return {"success": False, "error": str(e)}

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
        
        async with SessionLocal() as session:
            try:
                from sqlalchemy import select as sa_select
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
                primary_fw = enrichment.get("primary_framework")
                if primary_fw:
                    tag = KnowledgeTag(
                        document_id=doc_id,
                        tag_type=TagType.FRAMEWORK,
                        tag_value=primary_fw,
                        is_primary=True,
                        assigned_by=AssignedBy.MODEL
                    )
                    session.add(tag)
                    
                for fw in enrichment.get("secondary_frameworks", []):
                    tag = KnowledgeTag(
                        document_id=doc_id,
                        tag_type=TagType.FRAMEWORK,
                        tag_value=fw,
                        is_primary=False,
                        assigned_by=AssignedBy.MODEL
                    )
                    session.add(tag)
                    
                for topic in enrichment.get("topics", []):
                    tag = KnowledgeTag(
                        document_id=doc_id,
                        tag_type=TagType.TOPIC,
                        tag_value=topic,
                        is_primary=False,
                        assigned_by=AssignedBy.MODEL
                    )
                    session.add(tag)
                
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
                        tag = KnowledgeTag(
                            document_id=doc_id,
                            tag_type=t_type,
                            tag_value=val,
                            is_primary=False,
                            assigned_by=AssignedBy.MODEL
                        )
                        session.add(tag)
                    
                # 3. Save Facts
                for fact_data in enrichment.get("facts", []):
                    fact = KnowledgeFact(
                        document_id=doc_id,
                        fact_text=fact_data.get("fact_text", ""),
                        subject=fact_data.get("subject"),
                        predicate=fact_data.get("predicate"),
                        object_=fact_data.get("object_value"),
                        confidence=fact_data.get("confidence"),
                        source_span=fact_data.get("source_span"),
                        validation_status=ValidationStatus.PENDING
                    )
                    session.add(fact)
                    
                await session.commit()
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
                if prompt_tokens is not None:
                    run.prompt_tokens = prompt_tokens
                if completion_tokens is not None:
                    run.completion_tokens = completion_tokens
                if total_tokens is not None:
                    run.total_tokens = total_tokens
                if error_msg:
                    run.error_message = error_msg
            
            await session.commit()
