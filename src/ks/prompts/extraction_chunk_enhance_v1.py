PROMPT_ID = "extraction.chunk_enhance.v1"
MODEL_GROUP = "default"
MAX_INPUT_CHARS = 15_000
RESPONSE_FORMAT = None

_TEMPLATE = """You are a medical data architect. Convert the following raw OCR/Text chunk into clean, structured markdown. Preserve all clinical values, dosages, and medical terms exactly. Do not summarize; just reformat and clean noise.

Raw Chunk:
{chunk_text}"""


def render(variables: dict) -> str:
    return _TEMPLATE.format(chunk_text=variables.get("chunk_text", "")[:MAX_INPUT_CHARS])
