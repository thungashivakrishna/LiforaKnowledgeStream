"""Safety guards for LLM inputs/outputs: PII redaction, injection detection, refusal detection."""
import re
import logging

logger = logging.getLogger(__name__)

_PII_PATTERNS = [
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'), "[REDACTED_EMAIL]"),
    (re.compile(r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b'), "[REDACTED_SSN]"),
    (re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'), "[REDACTED_PHONE]"),
    (re.compile(r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b'), "[REDACTED_CC]"),
]

_INJECTION_MARKERS = [
    "<|im_start|>",
    "<|im_end|>",
    "### system:",
    "ignore previous instructions",
    "ignore all previous",
    "disregard previous",
    "forget your instructions",
]

_REFUSAL_PREFIXES = (
    "i can't help",
    "i'm unable to",
    "as an ai",
    "i cannot assist",
    "i'm not able to",
)


def redact_pii(text: str) -> str:
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def check_injection(text: str) -> bool:
    """Returns True if a prompt-injection attempt is detected."""
    lower = text.lower()
    return any(marker.lower() in lower for marker in _INJECTION_MARKERS)


def detect_refusal(text: str) -> bool:
    """Returns True if the model output appears to be a refusal."""
    lower = text.strip().lower()
    return any(lower.startswith(prefix) for prefix in _REFUSAL_PREFIXES)
