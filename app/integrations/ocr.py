import json
import logging
import re

from app.ai.prompts.kyc_ocr_prompts import kyc_ocr_prompt
from app.domain.kyc.constants.kyc import (
    COMPACT_FIELDS,
    DOCUMENT_FIELDS,
    FIELD_SEPARATORS,
    OCR_MAX_ATTEMPTS,
    OCR_MAX_TOKENS,
    OCR_MAX_TOKENS_PARAM,
    OCR_TEMPERATURE,
    UPPERCASE_FIELDS,
)
from app.integrations.replicate_client import replicate_client
from app.integrations.replicate_models import MODEL3

logger = logging.getLogger(__name__)

CODE_FENCE_RE = re.compile(r"```(?:json)?", re.IGNORECASE)

# Values a model reaches for instead of a real null.
NULL_LIKE_VALUES = frozenset({"", "null", "none", "n/a", "na", "not visible", "-"})


class OcrExtractionError(Exception):
    """The vision model failed, or returned nothing parseable as JSON."""


def _extract_json(text: str) -> dict:
    """Pull the JSON object out of a model reply, tolerating fences and prose."""
    cleaned = CODE_FENCE_RE.sub("", text or "").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise OcrExtractionError("no JSON object in the model response")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as e:
        raise OcrExtractionError(f"malformed JSON in the model response: {e}") from e
    if not isinstance(parsed, dict):
        raise OcrExtractionError("model returned JSON that is not an object")
    return parsed


def _clean_value(field: str, value: object) -> str | None:
    """Normalise one extracted field — null-like strings collapse to None, and
    ID numbers lose their separators so the stored form is canonical."""
    if value is None:
        return None
    text = " ".join(str(value).split())
    if text.casefold() in NULL_LIKE_VALUES:
        return None
    if field in COMPACT_FIELDS:
        text = text.translate({ord(c): None for c in FIELD_SEPARATORS})
    if field in UPPERCASE_FIELDS:
        text = text.upper()
    return text or None


async def extract_document_fields(image_url: str, document_type: str) -> dict:
    """
    Read an identity document with the vision model and return
    `{field: value | None}` for exactly the fields that document defines.

    `image_url` is a short-lived signed URL into the private KYC bucket.
    Raises OcrExtractionError on any model or parsing failure — the caller must
    surface that, never present an empty result as a successful read.

    Nothing here logs a field value: an Aadhaar/PAN number must not reach the logs.
    """
    parsed: dict | None = None
    for attempt in range(1, OCR_MAX_ATTEMPTS + 1):
        try:
            raw = await replicate_client(
                prompt=kyc_ocr_prompt(document_type),
                model=MODEL3,
                temperature=OCR_TEMPERATURE,
                max_tokens=OCR_MAX_TOKENS,
                max_tokens_param=OCR_MAX_TOKENS_PARAM,
                extra_input={"image_input": [image_url]},
            )
            parsed = _extract_json(raw)
            break
        except Exception as e:
            # The reply is never logged — a malformed one still holds the number.
            logger.warning(
                "KYC OCR attempt %s/%s failed | type=%s | %s",
                attempt,
                OCR_MAX_ATTEMPTS,
                document_type,
                type(e).__name__,
            )
            if attempt == OCR_MAX_ATTEMPTS:
                raise OcrExtractionError(str(e)) from e

    fields = {
        field: _clean_value(field, parsed.get(field))
        for field in DOCUMENT_FIELDS[document_type]
    }

    logger.info(
        "KYC OCR done | type=%s read=%s/%s",
        document_type,
        sum(1 for v in fields.values() if v),
        len(fields),
    )
    return fields
