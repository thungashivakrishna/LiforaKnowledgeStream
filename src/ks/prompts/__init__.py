"""Prompt template registry — all LLM prompts are defined here, versioned, and registered."""
from ks.prompts import (
    acquisition_intelligence_audit_v1,
    discovery_priority_score_v1,
    discovery_source_authority_v1,
    enrichment_extraction_v1,
    enrichment_framework_detection_v1,
    enrichment_verification_v1,
    extraction_chunk_enhance_v1,
    extraction_full_cleanup_v1,
    normalization_canonical_v1,
)

_MODULES = [
    acquisition_intelligence_audit_v1,
    discovery_priority_score_v1,
    discovery_source_authority_v1,
    enrichment_extraction_v1,
    enrichment_framework_detection_v1,
    enrichment_verification_v1,
    extraction_chunk_enhance_v1,
    extraction_full_cleanup_v1,
    normalization_canonical_v1,
]

REGISTRY: dict = {m.PROMPT_ID: m for m in _MODULES}


def render(prompt_id: str, variables: dict) -> tuple[str, str, dict | None]:
    """Returns (rendered_text, model_group, response_format)."""
    module = REGISTRY[prompt_id]
    return module.render(variables), module.MODEL_GROUP, module.RESPONSE_FORMAT
