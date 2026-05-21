import json

PROMPT_ID = "enrichment.verification.v1"
MODEL_GROUP = "default"
MAX_INPUT_CHARS = 12_000
RESPONSE_FORMAT = {"type": "json_object"}

_TEMPLATE = """You are a clinical integrity auditor. Your job is to verify if the following extracted facts are accurately supported by the provided source text.

SOURCE TEXT:
{source_text}

EXTRACTED FACTS:
{facts_json}

For each fact, determine if it is a hallucination or inaccurate. Provide a critique and suggested fix if needed.
Return valid JSON: {{"verifications": [{{"fact_index": 0, "is_hallucination": false, "confidence_score": 0.95, "critique": "...", "suggested_fix": "..."}}]}}"""


def render(variables: dict) -> str:
    source_text = variables.get("source_text", "")[:MAX_INPUT_CHARS]
    facts = variables.get("facts", [])
    return _TEMPLATE.format(
        source_text=source_text,
        facts_json=json.dumps(facts, indent=2),
    )
