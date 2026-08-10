"""OpenRouter provider — real model calls over HTTP.

OpenRouter exposes an OpenAI-shaped API behind one key and one base URL:

    POST {base_url}/chat/completions   -> classification and generation
    POST {base_url}/embeddings         -> retrieval vectors

Set OPENROUTER_API_KEY and MODEL_PROVIDER=openrouter to use it. Same three
functions as the mock, same (result, tokens) shape, so nothing else in the
service changes.

Cost: we ask OpenRouter to report actual spend per call (`usage.include`) and
use that when it comes back. Where it does not, the facade falls back to the
per-1k prices in config.

These calls are blocking on purpose, exactly like the mock. Sprint 1 is about
what to do with blocking calls, not about hiding them.
"""

import json
import math
from typing import List, Optional, Sequence, Tuple

import httpx

from ...config import settings
from ..errors import ModelUnavailable

_client: Optional[httpx.Client] = None

CLASSIFY_SYSTEM = (
    "You triage customer support tickets for a German energy retailer. "
    "Classify urgency as high, medium, or low. "
    "high = safety or loss of supply. medium = money already taken or wrongly billed. "
    "low = everything else. "
    'Reply with JSON only, no prose: {"urgency": "...", "confidence": 0.0}'
)


def _http() -> httpx.Client:
    global _client
    if _client is None:
        if not settings.openrouter_api_key:
            raise ModelUnavailable(
                "OPENROUTER_API_KEY is not set. Put it in .env, or run with MODEL_PROVIDER=mock."
            )
        _client = httpx.Client(
            base_url=settings.openrouter_base_url,
            timeout=settings.openrouter_timeout,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": settings.openrouter_referer,
                "X-Title": settings.openrouter_title,
            },
        )
    return _client


def _post(path: str, payload: dict) -> dict:
    """POST and turn every failure into a ModelUnavailable.

    Note what is *not* here: no retry, no backoff, no circuit breaker. A 429 or
    a 529 from an overloaded provider goes straight to the customer as a 500.
    That is Sprint 3's problem to solve.
    """
    try:
        response = _http().post(path, json=payload)
    except httpx.HTTPError as exc:
        raise ModelUnavailable(f"OpenRouter request failed: {type(exc).__name__}") from exc

    if response.status_code >= 400:
        detail = response.text[:200]
        raise ModelUnavailable(f"OpenRouter returned {response.status_code}: {detail}")
    return response.json()


def _usage(body: dict) -> Tuple[int, Optional[float]]:
    """Return (total tokens, reported cost in USD if available)."""
    usage = body.get("usage") or {}
    tokens = usage.get("total_tokens") or (
        usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
    )
    cost = usage.get("cost")
    return int(tokens or 0), (float(cost) if cost is not None else None)


def classify(text: str) -> Tuple[str, float, int, Optional[float]]:
    body = _post(
        "/chat/completions",
        {
            "model": settings.classifier_model,
            "messages": [
                {"role": "system", "content": CLASSIFY_SYSTEM},
                {"role": "user", "content": text},
            ],
            "temperature": 0,
            "max_tokens": 40,
            "usage": {"include": True},
        },
    )
    tokens, cost = _usage(body)
    content = body["choices"][0]["message"]["content"].strip()

    label, confidence = "low", 0.5
    try:
        parsed = json.loads(content.removeprefix("```json").removesuffix("```").strip())
        label = str(parsed.get("urgency", "low")).lower()
        confidence = float(parsed.get("confidence", 0.5))
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        # A model that ignores the output format is a real failure mode.
        # The baseline shrugs and defaults; discuss whether that is acceptable.
        lowered = content.lower()
        label = next((candidate for candidate in ("high", "medium", "low") if candidate in lowered), "low")

    if label not in {"high", "medium", "low"}:
        label = "low"
    return label, round(min(max(confidence, 0.0), 1.0), 2), tokens, cost


def embed(texts: Sequence[str]) -> Tuple[List[List[float]], int, Optional[float]]:
    body = _post(
        "/embeddings",
        {
            "model": settings.embedding_model,
            "input": list(texts),
            "encoding_format": "float",
            "usage": {"include": True},
        },
    )
    tokens, cost = _usage(body)
    ordered = sorted(body["data"], key=lambda item: item.get("index", 0))
    return [_normalise(item["embedding"]) for item in ordered], tokens, cost


def generate(prompt: str, *, max_tokens: int = 400) -> Tuple[str, int, Optional[float]]:
    body = _post(
        "/chat/completions",
        {
            "model": settings.chat_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "usage": {"include": True},
        },
    )
    tokens, cost = _usage(body)
    return body["choices"][0]["message"]["content"].strip(), tokens, cost


def _normalise(vector: List[float]) -> List[float]:
    """Retrieval uses a dot product, so vectors have to arrive unit length."""
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]
