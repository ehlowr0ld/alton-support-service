"""The service's view of a model provider.

Three functions — classify_urgency, embed, generate — and one decision behind
them: which provider actually runs. Set MODEL_PROVIDER in the environment.

    mock        offline, deterministic, free           (default)
    openrouter  real models over the OpenRouter API

Everything else in the service calls these three functions and does not care
which provider answered. Keeping the choice in one place is what makes it
possible to develop against real models and load-test against the mock.

This module also owns three cross-cutting concerns, so they behave the same
whichever provider is in use:

    - metrics: every call records its own latency, tokens, and cost
    - pricing: reported spend where the provider gives it, config prices otherwise
    - fault injection: the FAULT_* settings, so Sprint 3 works in either mode
"""

import random
import time
from typing import List, Optional, Sequence, Tuple

from ..config import settings
from ..metrics import record
from .errors import ModelUnavailable
from .providers import mock_provider


def _using_openrouter() -> bool:
    return settings.model_provider == "openrouter"


def _maybe_fail(error_rate: float, message: str) -> None:
    if error_rate > 0 and random.random() < error_rate:
        raise ModelUnavailable(message)


def _inject_latency() -> None:
    if settings.fault_model_extra_latency > 0:
        time.sleep(settings.fault_model_extra_latency)


def _price(tokens: int, per_1k: float, reported_cost: Optional[float]) -> float:
    """Reported spend wins; otherwise price the tokens ourselves."""
    return reported_cost if reported_cost is not None else tokens / 1000 * per_1k


def classify_urgency(text: str) -> Tuple[str, float]:
    """Return (label, confidence) for a support ticket."""
    started = time.perf_counter()
    _maybe_fail(settings.fault_model_error_rate, "classifier returned 503")
    _inject_latency()

    if _using_openrouter():
        from .providers import openrouter_provider

        label, confidence, tokens, cost = openrouter_provider.classify(text)
    else:
        label, confidence, tokens = mock_provider.classify(text)
        cost = None

    record(
        "classify",
        time.perf_counter() - started,
        tokens=tokens,
        cost_usd=_price(tokens, settings.price_classify_usd_per_1k, cost),
    )
    return label, confidence


def embed(texts: Sequence[str]) -> List[List[float]]:
    """Embed a batch of strings. Vectors come back unit length."""
    started = time.perf_counter()
    _maybe_fail(settings.fault_model_error_rate, "embedding endpoint returned 503")
    _inject_latency()

    if _using_openrouter():
        from .providers import openrouter_provider

        vectors, tokens, cost = openrouter_provider.embed(texts)
    else:
        vectors, tokens = mock_provider.embed(texts)
        cost = None

    record(
        "embed",
        time.perf_counter() - started,
        tokens=tokens,
        cost_usd=_price(tokens, settings.price_embed_usd_per_1k, cost),
    )
    return vectors


def generate(prompt: str, *, max_tokens: int = 400) -> str:
    """Generate an answer for a prompt."""
    started = time.perf_counter()
    _maybe_fail(settings.fault_model_error_rate, "generation endpoint returned 503")
    _inject_latency()

    if _using_openrouter():
        from .providers import openrouter_provider

        answer, tokens, cost = openrouter_provider.generate(prompt, max_tokens=max_tokens)
    else:
        answer, tokens = mock_provider.generate(prompt, max_tokens=max_tokens)
        cost = None

    record(
        "generate",
        time.perf_counter() - started,
        tokens=tokens,
        cost_usd=_price(tokens, settings.price_generate_usd_per_1k, cost),
    )
    return answer
