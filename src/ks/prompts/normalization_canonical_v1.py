PROMPT_ID = "normalization.canonical.v1"
MODEL_GROUP = "fast"
MAX_INPUT_CHARS = 500
RESPONSE_FORMAT = {"type": "json_object"}

_TEMPLATE = """You are a clinical ontology expert. Map the following clinical entity to its canonical, scientific name.
If it is already canonical or you are unsure, return the original name.

Entity: "{entity_name}"
Type Context: {entity_type}

Return valid JSON: {{"canonical_name": "Standard Name"}}"""


def render(variables: dict) -> str:
    return _TEMPLATE.format(
        entity_name=variables.get("entity_name", "")[:MAX_INPUT_CHARS],
        entity_type=variables.get("entity_type", "GENERAL"),
    )
