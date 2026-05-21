PROMPT_ID = "enrichment.framework_detection.v1"
MODEL_GROUP = "fast"
MAX_INPUT_CHARS = 10_000
RESPONSE_FORMAT = {"type": "json_object"}

_TEMPLATE = """Categorize the content below into one or more of the following high-level Frameworks:
- EVIDENCE_BASED_WESTERN_MEDICINE (Standard protocols, pharmaceuticals, surgeries)
- NUTRITION_SCIENCE (Diet, foods, fasting, micronutrients, cooking)
- PHYSICAL_ACTIVITY_SCIENCE (Exercise, biomechanics, gym, recovery, cardio)
- HOLISTIC_TRADITIONAL_SYSTEMS (Herbs, TCM, Ayurveda, adaptogens, traditional systems)
- PREVENTIVE_MEDICINE (Screening, lab benchmarks, disease avoidance)
- DIAGNOSTICS_AND_LABS (Blood tests, biomarkers, reference ranges, clinical imaging)
- PHARMACOLOGY_MEDICINE (Prescription drugs, dosages, mechanisms, side effects, drug-drug interactions)

Return valid JSON in this strict format:
{{"frameworks": ["FRAMEWORK_NAME_1", "FRAMEWORK_NAME_2"]}}

Text Sample: {text}"""


def render(variables: dict) -> str:
    text = variables.get("text", "")[:MAX_INPUT_CHARS]
    return _TEMPLATE.format(text=text)
