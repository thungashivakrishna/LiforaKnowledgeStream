"""Normalization service — standardizes clinical entities for the knowledge graph."""
import json
import logging

from ks.common.llm_gateway import complete as gateway_complete

logger = logging.getLogger(__name__)

class EntityNormalizer:

    async def normalize_entity(self, entity_name: str, entity_type: str = "GENERAL") -> str:
        """
        Maps a potentially noisy or synonymous entity name to a canonical form.
        Example: "Vitamin B12" -> "Cobalamin"
        """
        if not entity_name or len(entity_name) < 2:
            return entity_name

        try:
            resp = await gateway_complete(
                "normalization.canonical.v1",
                {"entity_name": entity_name, "entity_type": entity_type},
                stage="enrichment",
            )
            if resp.status not in ("success", "cached"):
                return entity_name
            output = json.loads(resp.content)
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
