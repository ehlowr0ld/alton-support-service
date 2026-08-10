"""Check that your OpenRouter key and model choices actually work.

    MODEL_PROVIDER=openrouter python scripts/check_provider.py

Three small calls — classify, embed, generate — and a report of what each cost.
Run this once before Sprint 1 so a broken key is not discovered mid-exercise.
Total spend is well under one cent on the default models.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402
from app.metrics import RequestMetrics, set_current  # noqa: E402
from app.services import model_client  # noqa: E402
from app.services.errors import ModelUnavailable  # noqa: E402


def main() -> int:
    print(f"\nprovider        {settings.model_provider}")
    if settings.model_provider != "openrouter":
        print("Set MODEL_PROVIDER=openrouter to check the real provider.\n")
        return 0

    print(f"base url        {settings.openrouter_base_url}")
    print(f"key             {'set' if settings.openrouter_api_key else 'MISSING'}")
    print(f"chat model      {settings.chat_model}")
    print(f"embedding model {settings.embedding_model}\n")

    metrics = RequestMetrics(request_id="provider-check")
    set_current(metrics)

    try:
        started = time.perf_counter()
        label, confidence = model_client.classify_urgency(
            "There is no power in my flat since this morning."
        )
        print(f"classify   ok   {label} ({confidence})  {(time.perf_counter() - started) * 1000:.0f} ms")

        started = time.perf_counter()
        vectors = model_client.embed(["direct debit taken twice", "how do I submit a meter reading"])
        print(
            f"embed      ok   {len(vectors)} vectors of dim {len(vectors[0])}  "
            f"{(time.perf_counter() - started) * 1000:.0f} ms"
        )

        started = time.perf_counter()
        answer = model_client.generate(
            "Answer in one sentence: a customer was charged twice by direct debit. What happens next?"
        )
        print(f"generate   ok   {(time.perf_counter() - started) * 1000:.0f} ms")
        print(f"\n  {answer[:200]}")
    except ModelUnavailable as exc:
        print(f"\nFAILED: {exc}\n")
        return 1

    print(f"\ntokens          {metrics.tokens}")
    print(f"cost            {metrics.cost_eur:.6f}")
    print("\nProvider is working.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
