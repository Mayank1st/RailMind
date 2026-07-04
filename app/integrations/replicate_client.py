import asyncio
import logging

import httpx

from functools import lru_cache
from typing import Any, Optional

from app.config import settings
from app.integrations.replicate_models import REPLICATE_MODELS

logger = logging.getLogger(__name__)

REPLICATE_API_BASE_URL = "https://api.replicate.com/v1"

MAX_TOKENS_PARAM_DEFAULT = "max_tokens"  # override per call if a model uses another key

PREDICTION_WAIT_SECONDS = 60  # server-side sync hold (Prefer: wait) — 60 is the max
POLL_INTERVAL_SECONDS = 2
POLL_TIMEOUT_SECONDS = 180
HTTP_TIMEOUT_SECONDS = 90  # must stay above PREDICTION_WAIT_SECONDS

STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELED = "canceled"
TERMINAL_STATUSES = {STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELED}

HTTP_STATUS_BAD_REQUEST = 400
HTTP_STATUS_NOT_FOUND = 404
HTTP_STATUS_UNPROCESSABLE = 422
HTTP_STATUS_RATE_LIMITED = 429

LOG_VALUE_MAX_CHARS = (
    120  # long input values (prompts, base64 images) truncated in logs
)


# ─────────────────────────────────────────────
# Custom Exceptions
# ─────────────────────────────────────────────


class ReplicateRateLimitError(Exception):
    """429 — Quota / rate limit exhausted."""


class ReplicateInvalidRequestError(Exception):
    """400 / 404 / 422 — Bad model slug, prompt, or parameters."""


class ReplicateInferenceError(Exception):
    """Any other Replicate API / model failure."""


class ReplicateUnsupportedModelError(Exception):
    """Model key passed is not registered in replicate_models.py."""


# ─────────────────────────────────────────────
# Internal Connection (singleton)
# ─────────────────────────────────────────────


class _ReplicateConnection:
    def __init__(self) -> None:
        if not settings.REPLICATE_API_TOKEN:
            raise ValueError(
                "REPLICATE_API_TOKEN is missing. Add it to your .env file."
            )

        self.headers: dict[str, str] = {
            "Authorization": f"Bearer {settings.REPLICATE_API_TOKEN}",
            "Content-Type": "application/json",
        }

        logger.info("ReplicateConnection initialised")


@lru_cache(maxsize=1)
def get_connection() -> _ReplicateConnection:
    """Returns the module-level singleton. Thread-safe via lru_cache."""
    return _ReplicateConnection()


# ─────────────────────────────────────────────
# Model resolution — registry key ("MODEL1") or raw slug ("owner/name")
# ─────────────────────────────────────────────


def _resolve_model(model: str) -> str:
    if "/" in model:
        return model

    slug = REPLICATE_MODELS.get(model.strip().upper())
    if slug is None:
        raise ReplicateUnsupportedModelError(
            f"Model '{model}' is not registered in replicate_models.py. "
            f"Available: {sorted(REPLICATE_MODELS)}"
        )
    return slug


# ─────────────────────────────────────────────
# Logging helpers
# ─────────────────────────────────────────────


def _loggable_value(value: Any) -> Any:
    if isinstance(value, str) and len(value) > LOG_VALUE_MAX_CHARS:
        return f"{value[:LOG_VALUE_MAX_CHARS]}… <len={len(value)}>"
    if isinstance(value, (bytes, bytearray)):
        return f"<bytes len={len(value)}>"
    if isinstance(value, list):
        return [_loggable_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _loggable_value(item) for key, item in value.items()}
    return value


def _loggable_input(model_input: dict[str, Any]) -> dict[str, Any]:
    """Compact copy of the input for logs — every param stays visible
    (resolution, aspect_ratio, ...), long values are truncated."""
    return {key: _loggable_value(value) for key, value in model_input.items()}


# ─────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < HTTP_STATUS_BAD_REQUEST:
        return

    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text

    if response.status_code == HTTP_STATUS_RATE_LIMITED:
        logger.warning("Replicate rate limit: %s", detail)
        raise ReplicateRateLimitError(
            "Replicate quota exhausted. Retry after a moment."
        )

    if response.status_code == HTTP_STATUS_NOT_FOUND:
        logger.error("Replicate model not found: %s", detail)
        raise ReplicateInvalidRequestError(f"Model not found on Replicate: {detail}")

    if response.status_code in (HTTP_STATUS_BAD_REQUEST, HTTP_STATUS_UNPROCESSABLE):
        logger.error("Replicate invalid request: %s", detail)
        raise ReplicateInvalidRequestError(str(detail))

    logger.error("Replicate API error %s: %s", response.status_code, detail)
    raise ReplicateInferenceError(
        f"Replicate API returned {response.status_code}: {detail}"
    )


async def _wait_for_prediction(
    client: httpx.AsyncClient, prediction: dict[str, Any]
) -> dict[str, Any]:
    """Polls the prediction until it reaches a terminal status."""
    elapsed_seconds = 0

    while prediction.get("status") not in TERMINAL_STATUSES:
        if elapsed_seconds >= POLL_TIMEOUT_SECONDS:
            raise ReplicateInferenceError(
                f"Prediction {prediction.get('id')} did not finish within "
                f"{POLL_TIMEOUT_SECONDS}s."
            )

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        elapsed_seconds += POLL_INTERVAL_SECONDS

        response = await client.get(
            f"{REPLICATE_API_BASE_URL}/predictions/{prediction['id']}"
        )
        _raise_for_status(response)
        prediction = response.json()
        logger.debug(
            "replicate polling | prediction_id=%s status=%s elapsed=%ss",
            prediction.get("id"),
            prediction.get("status"),
            elapsed_seconds,
        )

    return prediction


def _join_output(output: Any) -> str:
    """Replicate LLMs return their text as a list of string chunks."""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        return "".join(str(chunk) for chunk in output)
    return str(output)


# ─────────────────────────────────────────────
# Generic Runner — any Replicate model, raw input/output
# ─────────────────────────────────────────────


async def run_replicate_model(model: str, model_input: dict[str, Any]) -> Any:
    """
    Runs any Replicate model with a raw input dict and returns the raw
    prediction output. `model` is a registry key ("MODEL1") from
    replicate_models.py or a direct "owner/name" slug.
    """
    connection = get_connection()
    slug = _resolve_model(model)

    logger.info(
        "replicate call | model=%s input=%s", slug, _loggable_input(model_input)
    )

    try:
        async with httpx.AsyncClient(
            headers=connection.headers, timeout=HTTP_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(
                f"{REPLICATE_API_BASE_URL}/models/{slug}/predictions",
                json={"input": model_input},
                headers={"Prefer": f"wait={PREDICTION_WAIT_SECONDS}"},
            )
            _raise_for_status(response)
            prediction = await _wait_for_prediction(client, response.json())

    except httpx.HTTPError as e:
        logger.exception("Replicate network error: %s", e)
        raise ReplicateInferenceError(f"Replicate request failed: {e}") from e

    if prediction.get("status") != STATUS_SUCCEEDED:
        logger.error(
            "replicate failed | model=%s prediction_id=%s status=%s error=%s",
            slug,
            prediction.get("id"),
            prediction.get("status"),
            prediction.get("error"),
        )
        raise ReplicateInferenceError(
            f"Prediction {prediction.get('status')}: {prediction.get('error')}"
        )

    output = prediction.get("output")
    logger.info(
        "replicate done | model=%s prediction_id=%s status=%s metrics=%s output=%s",
        slug,
        prediction.get("id"),
        prediction.get("status"),
        prediction.get("metrics"),
        _loggable_value(output),
    )
    return output


# ─────────────────────────────────────────────
# Public LLM Client — use this everywhere; pass the model per call
# ─────────────────────────────────────────────


async def replicate_client(
    prompt: str,
    model: str,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    max_tokens_param: str = MAX_TOKENS_PARAM_DEFAULT,
    extra_input: Optional[dict[str, Any]] = None,
) -> str:
    """
    Common text-generation client for any Replicate-hosted LLM.
    `model` is a registry key ("MODEL1") from replicate_models.py or a
    direct "owner/name" slug — FE payload can send the key as-is.
    `extra_input` merges last, so model-specific params can be added/overridden.
    """
    payload: dict[str, Any] = {
        "prompt": prompt,
        "temperature": (
            temperature if temperature is not None else settings.REPLICATE_TEMPERATURE
        ),
        max_tokens_param: (
            max_tokens if max_tokens is not None else settings.REPLICATE_MAX_TOKENS
        ),
    }
    if system_prompt is not None:
        payload["system_prompt"] = system_prompt
    if extra_input:
        payload.update(extra_input)

    output = await run_replicate_model(model=model, model_input=payload)
    text = _join_output(output)

    logger.debug("replicate ok | model=%s chars=%s", model, len(text))
    return text
