"""Source policy — trust scoring and tier recommendation."""


DIMENSION_WEIGHTS: dict[str, float] = {
    "authority": 0.25,
    "evidence_orientation": 0.20,
    "transparency": 0.15,
    "stability": 0.10,
    "relevance": 0.15,
    "extraction_feasibility": 0.05,
    "safety_risk": 0.05,       # inverted — high risk = lower score
    "policy_compliance": 0.05,
}

TIER_THRESHOLDS: list[tuple[float, int]] = [
    (0.85, 1),
    (0.70, 2),
    (0.55, 3),
    (0.40, 4),
    (0.0, 5),
]


def compute_composite_score(dimensions: dict[str, float]) -> float:
    """Weighted composite score in [0, 1]. safety_risk is inverted."""
    score = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        raw = dimensions.get(dim, 0.5)
        value = (1.0 - raw) if dim == "safety_risk" else raw
        score += weight * value
    return round(score, 4)


def recommend_trust_tier(composite_score: float) -> int:
    for threshold, tier in TIER_THRESHOLDS:
        if composite_score >= threshold:
            return tier
    return 5


def evaluate_policy(dimensions: dict[str, float]) -> dict:
    """Full policy evaluation — returns composite score + recommended tier."""
    composite = compute_composite_score(dimensions)
    tier = recommend_trust_tier(composite)
    return {
        "composite_score": composite,
        "recommended_tier": tier,
        "dimensions": dimensions,
    }


def get_default_dimensions_for_tier(trust_tier: int) -> dict[str, float]:
    """Sensible default dimension scores for a given manually-assigned tier."""
    base = {1: 0.9, 2: 0.75, 3: 0.6, 4: 0.45, 5: 0.2}.get(trust_tier, 0.5)
    return {dim: base for dim in DIMENSION_WEIGHTS}
