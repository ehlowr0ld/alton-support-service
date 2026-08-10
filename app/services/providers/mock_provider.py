"""Offline provider. No network, no key, no bill.

Emulates three capabilities — classification, embedding, generation — with
realistic latency and stable output. Used for load testing and for any lesson
where a hundred identical runs need to produce comparable numbers.

Every call returns (result, tokens). The facade in model_client.py handles
pricing, metrics, and fault injection.
"""

import hashlib
import math
import time
from typing import List, Sequence, Tuple

from ...config import settings

EMBEDDING_DIM = 64

_URGENCY_HINTS = {
    "high": ("no power", "outage", "no heating", "emergency", "leak", "cut off", "disconnect", "smell of gas"),
    "medium": ("overcharged", "wrong bill", "refund", "double charged", "meter reading wrong", "complaint"),
}


def estimate_tokens(text: str) -> int:
    """Crude token estimate: good enough to price a call, and stable."""
    return max(1, len(text) // 4)


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def classify(text: str) -> Tuple[str, float, int]:
    _sleep(settings.classify_latency)

    lowered = text.lower()
    label, confidence = "low", 0.62
    for candidate, hints in _URGENCY_HINTS.items():
        if any(hint in lowered for hint in hints):
            label = candidate
            confidence = 0.94 if candidate == "high" else 0.81
            break
    return label, confidence, estimate_tokens(text)


def embed(texts: Sequence[str]) -> Tuple[List[List[float]], int]:
    """Hashed vectors, not learned ones.

    Similarity works through shared tokens only. Enough to make retrieval
    behave sensibly and cache hits easy to reason about; it is not a semantic
    model. Switch to the openrouter provider when a lesson needs real semantics.
    """
    _sleep(len(texts) * settings.embed_latency_per_item)
    vectors = [_hash_embed(text) for text in texts]
    return vectors, sum(estimate_tokens(text) for text in texts)


def generate(prompt: str, *, max_tokens: int = 220) -> Tuple[str, int]:
    prompt_tokens = estimate_tokens(prompt)
    # Longer prompts take longer, as they would with a real provider.
    _sleep(settings.generate_base_latency + min(prompt_tokens, 1200) * 0.00035)

    answer = _compose_answer(prompt)
    return answer, prompt_tokens + min(max_tokens, estimate_tokens(answer))


# --- internals -------------------------------------------------------------


def _hash_embed(text: str) -> List[float]:
    vector = [0.0] * EMBEDDING_DIM
    for word in _words(text):
        digest = hashlib.md5(word.encode("utf-8")).digest()
        index = digest[0] % EMBEDDING_DIM
        sign = 1.0 if digest[1] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _words(text: str) -> List[str]:
    return [word for word in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(word) > 2]


def _compose_answer(prompt: str) -> str:
    """Stitch an answer out of the context the prompt carries.

    A real provider writes this text. Here it is assembled so the response is
    stable and inspectable, which makes cache hits easy to verify.
    """
    context_lines = [line.strip("- ").strip() for line in prompt.splitlines() if line.strip().startswith("-")]
    if not context_lines:
        return (
            "I could not find a help-centre article covering this. A support agent "
            "will follow up within one working day."
        )
    body = " ".join(context_lines[:2])
    return (
        f"Here is what applies to your case. {body} "
        "If this does not resolve the issue, reply to this message and an agent will pick it up."
    )
