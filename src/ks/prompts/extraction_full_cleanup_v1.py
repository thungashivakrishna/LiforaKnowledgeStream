PROMPT_ID = "extraction.full_cleanup.v1"
MODEL_GROUP = "fast"
MAX_INPUT_CHARS = 3_000
RESPONSE_FORMAT = None

_TEMPLATE = """Read this raw text and convert into clean markdown with headers.

Raw Text:
{text}"""


def render(variables: dict) -> str:
    return _TEMPLATE.format(text=variables.get("text", "")[:MAX_INPUT_CHARS])
