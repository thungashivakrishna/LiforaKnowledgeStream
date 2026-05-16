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
            api_key = self.settings.model.primary_api_key
            resp = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                api_key=api_key,
                temperature=0
            )
            
            output = json.loads(resp.choices[0].message.content)
            # Default to at least one if empty
            frameworks = output.get("frameworks", ["PREVENTIVE_MEDICINE"])
            if not frameworks:
                 frameworks = ["PREVENTIVE_MEDICINE"]
                 
            return {"success": True, "frameworks": frameworks}
        except Exception as e:
            logger.error(f"Framework detection failed: {e}")
            return {"success": False, "frameworks": ["PREVENTIVE_MEDICINE"], "error": str(e)}

    @activity.defn
    async def run_llm_enrichment(self, payload: dict) -> dict:
        """
        Calls litellm to parse the text and return structured JSON based on LLMEnrichmentOutput schema.
        Payload keys: text OR extracted_text_key, model, framework
        """
        try:
            text = self._fetch_text_from_payload(payload)
        except Exception as e:
            return {"success": False, "error": f"Payload hydration failed: {e}"}
            
        model = payload.get("model", self.settings.model.primary_model)
        
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

        # Framework-Specific Agent Personalities
        framework = payload.get("framework")
        framework_context = ""
        
        if framework == "NUTRITION_SCIENCE":
            framework_context = """
            SPECIALIZED NUTRITION AGENT ACTIVE:
            Focus on: 
            - MACROS & MICROS: Precise numeric components (e.g., "Fiber: 10g").
            - GLYCEMIC IMPACT: Insulogenic load, metabolic response.
            - PREPARATION METHOD: How cooking/raw state impacts bioavailability.
            - COMBINATION SYNERGY: Food pairing benefits (e.g., "Turmeric + Black pepper").
            """
        elif framework == "PHYSICAL_ACTIVITY_SCIENCE":
            framework_context = """
            SPECIALIZED MOVEMENT AGENT ACTIVE:
            Focus on:
            - EXERTION INTENSITY: Heart rate zones, VO2 max impact, RPE.
            - MODALITY: Aerobic vs Anaerobic mechanics.
            - RECOVERY: Hypertrophy markers, rest cycles, cortisol impact.
            - BIOMECHANICS: Kinematic safety cues and postural adaptations.
            """
        elif framework == "PREVENTIVE_MEDICINE":
            framework_context = """
            SPECIALIZED DIAGNOSTIC AGENT ACTIVE:
            Focus on:
            - BIOMARKERS: LDL, HbA1c, CRP, fasting glucose benchmarks.
            - SCREENING GUIDELINES: Age/risk thresholds for intervention.
            - PROPHYLAXIS: Preventative thresholds and risk reduction ratios.
            """
        elif framework == "HOLISTIC_TRADITIONAL_SYSTEMS":
            framework_context = """
            SPECIALIZED TRADITIONAL SYSTEMS AGENT ACTIVE:
            Focus on:
            - ADAPTOGENS & HERBS: Herbal classification, tonic effects.
            - GUT-BRAIN AXIS: Microbiome, digestive fire, or systemic connection.
            - CONSTITUTIONAL EFFECTS: Warming/cooling properties or systemic balance impacts.
            """
        elif framework == "DIAGNOSTICS_AND_LABS":
            framework_context = """
            SPECIALIZED DIAGNOSTIC & LAB AGENT ACTIVE:
            Focus on:
            - REFERENCE INTERVALS: Normal bounds, optimal vs sub-optimal tiers, and panic values.
            - TEST METHODOLOGY: Fasting required, imaging modalities (MRI, CT, Ultrasound), measurement units.
            - CLINICAL SIGNIFICANCE: What elevated/suppressed levels indicate (e.g., High TSH = Hypothyroidism).
            """
        elif framework == "PHARMACOLOGY_MEDICINE":
            framework_context = """
            SPECIALIZED PHARMACOLOGICAL AGENT ACTIVE:
            Focus on:
            - MECHANISM OF ACTION: Agonist/Antagonist relationships, biological pathways.
            - THERAPEUTIC INDEX: Dosage safety margin, half-life, pharmacokinetics.
            - ADVERSE REACTIONS: Common side effects versus severe toxicity warnings.
            - CONTRAINDICATIONS: Absolute and relative restrictions based on comorbidities.
            """

        prompt = f"""
        You are a world-class health knowledge graph extractor. Your goal is to convert medical text into high-fidelity structured intelligence.
        {clinical_context}
        {framework_context}
        
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
                api_key = self.settings.model.tertiary_api_key
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
        verification_report = payload.get("verification_report", [])
        
        # Index verification report by fact index for fast lookup
        v_map = {v.get("fact_index"): v for v in verification_report}
        
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
                async def add_tag_if_new(doc_id, t_type, t_value, is_primary=False):
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

                    # Dedup Check with normalized values
                    stmt = sa_select(KnowledgeFact).where(
                        KnowledgeFact.document_id == doc_id,
                        KnowledgeFact.subject == norm_subject,
                        KnowledgeFact.predicate == fact_data.get("predicate"),
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
                        critique=critique
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
            resp = litellm.completion(
                model="deepseek/deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                api_key=self.settings.model.primary_api_key
            )
            report = json.loads(resp.choices[0].message.content)
            return {"success": True, "report": report.get("verifications", [])}
        except Exception as e:
            logger.error(f"Verification activity failed: {e}")
            return {"success": False, "error": str(e)}
