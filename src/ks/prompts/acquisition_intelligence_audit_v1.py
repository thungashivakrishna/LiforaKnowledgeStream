PROMPT_ID = "acquisition.intelligence_audit.v1"
MODEL_GROUP = "fast"
MAX_INPUT_CHARS = 5_000
RESPONSE_FORMAT = {"type": "json_object"}

_TEMPLATE = """You are a Health Intelligence Auditor. Analyze the content from {url} to determine if it's high-value medical knowledge.

Criteria:
- HIGH VALUE: Detailed clinical guidelines, specific medication dosages (e.g., 500mg), nutrient stats, symptoms, or treatment protocols.
- LOW VALUE / INDEX: Lists of links, search results, directory pages, or shallow boilerplate.
- ENGLISH ONLY: Reject immediately if the primary content language is not English.

Task:
1. Decide if high_value (bool). MUST be false if the content is not in English.
2. Provide reason (string). Mention 'Non-English Content' if rejected for language.
3. If LOW VALUE but has promising links, list up to 5 absolute URLs to follow.
4. If HIGH VALUE, extract top 3 key facts as S-P-O triples (subject, predicate, object).

Content (first 5000 chars):
{content}"""


def render(variables: dict) -> str:
    return _TEMPLATE.format(
        url=variables.get("url", ""),
        content=variables.get("content", "")[:MAX_INPUT_CHARS],
    )
