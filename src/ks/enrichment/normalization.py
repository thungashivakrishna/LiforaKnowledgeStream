"""Normalization service — standardizes clinical entities for the knowledge graph."""
import logging
import json
import litellm
from ks.config.settings import get_settings

logger = logging.getLogger(__name__)

class EntityNormalizer:
    def __init__(self):
        self.settings = get_settings()
        # In a production system, this might also query a local dictionary (MeSH, UMLS)
        # for high-speed lookups before falling back to an LLM.

    async def normalize_entity(self, entity_name: str, entity_type: str = "GENERAL") -> str:
        """
        Maps a potentially noisy or synonymous entity name to a canonical form.
        Example: "Vitamin B12" -> "Cobalamin"
        """
        if not entity_name or len(entity_name) < 2:
            return entity_name

        prompt = f"""
        You are a clinical ontology expert. Map the following clinical entity to its canonical, scientific name.
        If it is already canonical or you are unsure, return the original name.
        
        Entity: "{entity_name}"
        Type Context: {entity_type}
        
        Return valid JSON: {{"canonical_name": "Standard Name"}}
        """

        try:
            resp = litellm.completion(
                model=self.settings.model.secondary_model, # Use a faster/cheaper model for normalization
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                api_key=self.settings.model.primary_api_key, # Assuming same provider or key
                temperature=0
            )
            output = json.loads(resp.choices[0].message.content)
            canonical = output.get("canonical_name", entity_name)
            
            if canonical != entity_name:
                logger.info(f"Normalized entity: '{entity_name}' -> '{canonical}'")
            
            return canonical
        except Exception as e:
            logger.warning(f"Normalization failed for '{entity_name}': {e}")
            return entity_name

    async def normalize_triple(self, subject: str, predicate: str, object_value: str) -> tuple:
        """Standardizes all parts of a S-P-O triple."""
        norm_subject = await self.normalize_entity(subject, "SUBJECT")
        norm_object = await self.normalize_entity(object_value, "OBJECT")
        # Predicates could also be normalized to a standard set (e.g., "treats", "causes", "dosage_is")
        return norm_subject, predicate, norm_object
