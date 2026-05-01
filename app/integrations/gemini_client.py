import asyncio
import logging
from functools import lru_cache
from typing import Optional

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

MODEL_1 = "gemini-2.5-flash"
# MODEL_2 = "gemini-2.5-pro"


# ─────────────────────────────────────────────
# Custom Exceptions
# ─────────────────────────────────────────────


class GeminiRateLimitError(Exception):
    """429 — Quota exhausted."""


class GeminiInvalidRequestError(Exception):
    """400 — Bad prompt or parameters."""


class GeminiInferenceError(Exception):
    """Any other Gemini/Google API failure."""


class GeminiUnsupportedModelError(Exception):
    """model_id passed does not match any registered model."""


# ─────────────────────────────────────────────
# Internal Connection (singleton)
# ─────────────────────────────────────────────


class _GeminiConnection:
    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is missing. Add it to your .env file.")

        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

        self._model_map: dict[int, str] = {
            1: MODEL_1,
            # 2: MODEL_2    ← Phase 3 mein add hoga
        }

        logger.info("GeminiConnection initialised | models=%s", self._model_map)

    def get_model_name(self, model_id: int) -> str:
        name = self._model_map.get(model_id)
        if name is None:
            raise GeminiUnsupportedModelError(
                f"model_id={model_id} is not registered. "
                f"Available: {list(self._model_map.keys())}"
            )
        return name


@lru_cache(maxsize=1)
def get_connection() -> _GeminiConnection:
    """Returns the module-level singleton. Thread-safe via lru_cache."""
    return _GeminiConnection()


# ─────────────────────────────────────────────
# Model-Specific Function
# ─────────────────────────────────────────────


async def use_gemini_25_flash(
    prompt: str,
    system_instruction: Optional[str] = None,
    temperature: Optional[float] = None,
) -> str:
    """
    Runs inference on gemini-2.5-flash.
    Called internally by gemini_client() when model_id == 1.
    """
    connection = get_connection()
    model_name = connection.get_model_name(1)

    config = types.GenerateContentConfig(
        temperature=(
            temperature if temperature is not None else settings.GEMINI_TEMPERATURE
        ),
        max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
        system_instruction=system_instruction,  # new SDK supports this natively
    )

    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: connection.client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            ),
        )

        logger.debug(
            "gemini-2.5-flash ok | tokens=%s",
            getattr(response.usage_metadata, "total_token_count", "N/A"),
        )
        return response.text

    except Exception as e:
        error_str = str(e).lower()

        if "quota" in error_str or "429" in error_str or "rate" in error_str:
            logger.warning("Gemini rate limit: %s", e)
            raise GeminiRateLimitError(
                "Gemini quota exhausted. Retry after a moment."
            ) from e

        if "invalid" in error_str or "400" in error_str:
            logger.error("Gemini invalid request: %s", e)
            raise GeminiInvalidRequestError(str(e)) from e

        logger.exception("Gemini inference error: %s", e)
        raise GeminiInferenceError(str(e)) from e


# ─────────────────────────────────────────────
# Public Dispatcher — use this everywhere
# ─────────────────────────────────────────────


async def gemini_client(
    prompt: str,
    model_id: int = 1,
    system_instruction: Optional[str] = None,
    temperature: Optional[float] = None,
) -> str:
    if model_id == 1:
        return await use_gemini_25_flash(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=temperature,
        )

    # if model_id == 2:
    #     return await use_gemini_25_pro(...)

    raise GeminiUnsupportedModelError(f"model_id={model_id} is not registered.")
