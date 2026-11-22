"""Gemini model chain: preferred model first, then fallbacks.

Preview models can be capacity-limited (503) or quota-limited (429). The chain keeps the
email panel responsive: each model gets a short timeout and one quick retry before moving on.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

from app.config import Settings

log = logging.getLogger(__name__)
T = TypeVar("T")
# Gemini + Anthropic transient failures (and refusals, which move to the next model in the chain)
RETRYABLE = ("503", "529", "429", "500", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE", "timed out", "Timeout",
             "RateLimitError", "InternalServerError", "OverloadedError", "APIConnectionError", "APITimeoutError",
             "RefusalError")


def model_chain(settings: Settings) -> list[str]:
    chain = [settings.gemini_model] + [m for m in settings.gemini_fallback_models if m != settings.gemini_model]
    return chain


def is_retryable(exc: Exception) -> bool:
    msg = f"{type(exc).__name__} {exc}"
    return any(k in msg for k in RETRYABLE)


def call_with_chain(models: list[str], fn: Callable[[str], T], attempts_per_model: int = 2) -> tuple[T, str]:
    """Run fn(model) down the chain. Returns (result, model_used). Raises the last error."""
    last: Exception | None = None
    for model in models:
        for attempt in range(attempts_per_model):
            try:
                return fn(model), model
            except Exception as exc:  # noqa: BLE001
                last = exc
                if not is_retryable(exc):
                    log.warning("LLM %s failed (not retryable): %s", model, str(exc)[:160])
                    break
                log.info("LLM %s busy (%s); attempt %d", model, str(exc)[:60], attempt + 1)
                time.sleep(0.8 * (attempt + 1))
    raise last or RuntimeError("No model in the chain responded")


def resolve_available(settings: Settings, timeout_ms: int = 12000) -> str | None:
    """Pick the first model in the chain that answers a tiny probe (used for the CrewAI LLM)."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(timeout=timeout_ms))
    try:
        _, model = call_with_chain(model_chain(settings),
                                   lambda m: client.models.generate_content(model=m, contents="Reply OK."),
                                   attempts_per_model=1)
        return model
    except Exception as exc:  # noqa: BLE001
        log.warning("No Gemini model responded to the probe: %s", str(exc)[:160])
        return None
