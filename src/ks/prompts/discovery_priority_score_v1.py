import json

PROMPT_ID = "discovery.priority_score.v1"
MODEL_GROUP = "fast"
MAX_INPUT_CHARS = 5_000
RESPONSE_FORMAT = {"type": "json_object"}

_TEMPLATE = """You are an advanced Clinical Triage AI. Your job is to prioritize a discovered web document before we spend resources fully extracting it.

URL: {url}
Target Focus / Topics: {topics}
Source Trust Score: {source_trust}

Metadata:
{metadata_json}

Evaluate the document based on the metadata and return a JSON score object matching the specified output schema.
- clinical_relevance (0.0 to 1.0)
- intent_match (0.0 to 1.0): Does it match {topics}?
- evidence_likelihood (0.0 to 1.0): Does it look like a study, protocol, or guideline?
- actionability (0.0 to 1.0)
- safety_value (0.0 to 1.0)
- freshness (0.0 to 1.0)
- commercial_bias_risk (0.0 to 1.0): Does it look like SEO spam or a product sales page?
- source_trust_multiplier (0.5 to 1.5): Based on Source Trust Score provided.

Calculate the overall_priority_score (0 to 100):
Score = ((clinical_relevance * 0.2) + (intent_match * 0.2) + (evidence_likelihood * 0.15) +
        (actionability * 0.1) + (safety_value * 0.15) + (freshness * 0.1) -
        (commercial_bias_risk * 0.3)) * source_trust_multiplier * 100
Clamp final score to 0-100.

Recommended Action logic:
- 85-100: EXTRACT
- 65-84: QUEUE
- 40-64: METADATA_ONLY
- 0-39: REJECT"""


def render(variables: dict) -> str:
    return _TEMPLATE.format(
        url=variables.get("url", ""),
        topics=variables.get("topics", []),
        source_trust=variables.get("source_trust", 1.0),
        metadata_json=json.dumps(variables.get("metadata", {}), indent=2)[:MAX_INPUT_CHARS],
    )
