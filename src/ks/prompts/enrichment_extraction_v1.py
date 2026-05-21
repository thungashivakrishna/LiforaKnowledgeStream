PROMPT_ID = "enrichment.extraction.v1"
MODEL_GROUP = "default"
MAX_INPUT_CHARS = 25_000
RESPONSE_FORMAT = {"type": "json_object"}

_FRAMEWORK_CONTEXTS = {
    "NUTRITION_SCIENCE": """
SPECIALIZED NUTRITION AGENT ACTIVE:
Focus on:
- MACROS & MICROS: Precise numeric components (e.g., "Fiber: 10g").
- GLYCEMIC IMPACT: Insulogenic load, metabolic response.
- PREPARATION METHOD: How cooking/raw state impacts bioavailability.
- COMBINATION SYNERGY: Food pairing benefits (e.g., "Turmeric + Black pepper").
""",
    "PHYSICAL_ACTIVITY_SCIENCE": """
SPECIALIZED MOVEMENT AGENT ACTIVE:
Focus on:
- EXERTION INTENSITY: Heart rate zones, VO2 max impact, RPE.
- MODALITY: Aerobic vs Anaerobic mechanics.
- RECOVERY: Hypertrophy markers, rest cycles, cortisol impact.
- BIOMECHANICS: Kinematic safety cues and postural adaptations.
""",
    "PREVENTIVE_MEDICINE": """
SPECIALIZED DIAGNOSTIC AGENT ACTIVE:
Focus on:
- BIOMARKERS: LDL, HbA1c, CRP, fasting glucose benchmarks.
- SCREENING GUIDELINES: Age/risk thresholds for intervention.
- PROPHYLAXIS: Preventative thresholds and risk reduction ratios.
""",
    "HOLISTIC_TRADITIONAL_SYSTEMS": """
SPECIALIZED TRADITIONAL SYSTEMS AGENT ACTIVE:
Focus on:
- ADAPTOGENS & HERBS: Herbal classification, tonic effects.
- GUT-BRAIN AXIS: Microbiome, digestive fire, or systemic connection.
- CONSTITUTIONAL EFFECTS: Warming/cooling properties or systemic balance impacts.
""",
    "DIAGNOSTICS_AND_LABS": """
SPECIALIZED DIAGNOSTIC & LAB AGENT ACTIVE:
Focus on:
- REFERENCE INTERVALS: Normal bounds, optimal vs sub-optimal tiers, and panic values.
- TEST METHODOLOGY: Fasting required, imaging modalities (MRI, CT, Ultrasound), measurement units.
- CLINICAL SIGNIFICANCE: What elevated/suppressed levels indicate (e.g., High TSH = Hypothyroidism).
""",
    "PHARMACOLOGY_MEDICINE": """
SPECIALIZED PHARMACOLOGICAL AGENT ACTIVE:
Focus on:
- MECHANISM OF ACTION: Agonist/Antagonist relationships, biological pathways.
- THERAPEUTIC INDEX: Dosage safety margin, half-life, pharmacokinetics.
- ADVERSE REACTIONS: Common side effects versus severe toxicity warnings.
- CONTRAINDICATIONS: Absolute and relative restrictions based on comorbidities.
""",
}

_CLINICAL_SOURCE_CONTEXT = """
SPECIALIZED CLINICAL MODE ENABLED:
- Focus on RX IDENTIFIERS: Active ingredients, Brand names, and Medication Classes.
- Focus on CLINICAL MARKERS: Reference ranges (e.g., "Normal: 70-100 mg/dL"), units of measure, and test names.
- Precise DOSAGE extraction: Capture frequency (BID, QD), strength, and administration route.
- CONTRADICTIONS: Be extremely granular about drug-drug or drug-condition interactions.
"""

_SCHEMA_HINT = """

Return ONLY valid JSON matching this schema (no markdown, no explanation):
{"summary": "string", "primary_framework": "one of NUTRITION|EXERCISE|SLEEP|STRESS|HYDRATION|SUPPLEMENTATION|RECOVERY|GENERAL|PREVENTIVE_MEDICINE", "secondary_frameworks": ["..."], "topics": ["..."], "conditions": ["..."], "symptoms": ["..."], "interventions": ["..."], "nutrients": ["..."], "populations": ["..."], "facts": [{"fact_text": "...", "subject": "...", "predicate": "...", "object_value": "...", "confidence": 0.9, "source_span": "..."}]}"""

_TEMPLATE = """You are a world-class health knowledge graph extractor. Your goal is to convert medical text into high-fidelity structured intelligence.
{clinical_context}{framework_context}
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
{text}{schema_hint}"""


def render(variables: dict) -> str:
    text = variables.get("text", "")[:MAX_INPUT_CHARS]
    framework = variables.get("framework", "")
    source_type = variables.get("source_type", "")

    is_clinical = source_type in ("PRESCRIPTION_SOURCE", "CLINICAL_REPORT_SOURCE")
    clinical_context = _CLINICAL_SOURCE_CONTEXT if is_clinical else ""
    framework_context = _FRAMEWORK_CONTEXTS.get(framework, "")

    return _TEMPLATE.format(
        clinical_context=clinical_context,
        framework_context=framework_context,
        text=text,
        schema_hint=_SCHEMA_HINT,
    )
