PROMPT_ID = "discovery.source_authority.v1"
MODEL_GROUP = "fast"
MAX_INPUT_CHARS = 2_000
RESPONSE_FORMAT = {"type": "json_object"}

_TEMPLATE = """Evaluate the following web domain for clinical and medical authority.
Domain: {domain}
Sample Context: {snippet}

Is this a reputable academic, public health, government, or recognized clinical site?
Return a JSON object with:
- is_reputable (bool)
- trust_score (0.0 to 1.0)
- reason (string)
- source_type (e.g. ACADEMIC, GOVERNMENT, COMMERCIAL_WELLNESS, SPAM)"""


def render(variables: dict) -> str:
    return _TEMPLATE.format(
        domain=variables.get("domain", ""),
        snippet=variables.get("snippet", "")[:MAX_INPUT_CHARS],
    )
