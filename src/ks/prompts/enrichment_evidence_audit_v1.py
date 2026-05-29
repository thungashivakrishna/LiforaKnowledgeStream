PROMPT_ID = "enrichment.evidence_audit.v1"
MODEL_GROUP = "fast"
MAX_INPUT_CHARS = 12_000
RESPONSE_FORMAT = {"type": "json_object"}

_TEMPLATE = """Analyze the following document title, source, and text content (abstract, methodology, or full text) to audit its clinical evidence quality and study design.

Determine the Level of Evidence (LoE) Grade (A, B, C, or D) based on these strict medical research standards:
- **GRADE_A:** High-authority evidence. Randomized Controlled Trials (RCTs), Meta-analyses, Systematic Reviews, or Official Multi-center Guidelines (e.g. WHO, NICE, CDC).
- **GRADE_B:** Good-quality evidence. Cohort Studies, Case-Control Trials, or large clinical trials without full randomization.
- **GRADE_C:** Fair-quality evidence. Cross-sectional studies, observational clinical trials, case series, or peer-reviewed journal review articles.
- **GRADE_D:** Weak or General consensus. Expert opinions, general web health articles, patient surveys, consensus statements, or anecdotal/unverified guidelines.

Title: {title}
Source Type: {source_type}

Text Content:
{text}

Return a JSON object in this strict format:
{{
  "evidence_grade": "GRADE_A" | "GRADE_B" | "GRADE_C" | "GRADE_D",
  "study_type": "string describing the study design, e.g. 'Randomized Double-Blind Placebo-Controlled Trial' or 'Literature Review' or 'Web Consensus Article'",
  "methodology_critique": "brief string analyzing the methods, sample size, controls, or potential biases detected in the text"
}}"""


def render(variables: dict) -> str:
    return _TEMPLATE.format(
        title=variables.get("title", "Unknown Title"),
        source_type=variables.get("source_type", "GENERAL_HEALTH"),
        text=variables.get("text", "")[:MAX_INPUT_CHARS],
    )
