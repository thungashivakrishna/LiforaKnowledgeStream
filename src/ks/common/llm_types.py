"""LLM response and error types used by the gateway."""
from dataclasses import dataclass, field


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    fallback_depth: int = 0
    cache_hit: bool = False


@dataclass
class LLMResponse:
    content: str
    model_used: str
    model_requested: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    skipped: bool = False
    # success | failed | refusal | budget_exceeded | cached | blocked
    status: str = "success"


class LLMBudgetExceeded(Exception):
    pass
