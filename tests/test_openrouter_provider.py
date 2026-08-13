"""The OpenRouter path, exercised without spending anything.

The HTTP call is stubbed, so these run in CI and offline. They check the parts
that break in practice: parsing the response, reading reported cost, coping
with a model that ignores the output format, and turning an HTTP error into a
dependency failure.

For a real end-to-end check against OpenRouter, see scripts/check_provider.py.
"""

from dataclasses import replace

import pytest

from app.services import model_client
from app.services.errors import ModelUnavailable
from app.services.providers import openrouter_provider as orp
from app.config import settings


@pytest.fixture
def openrouter_mode(monkeypatch):
    """Settings are frozen, so flip the provider check rather than the value."""
    monkeypatch.setattr(model_client, "_using_openrouter", lambda: True)
    yield


def _chat_body(content: str, cost: float | None = 0.00021) -> dict:
    usage = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
    if cost is not None:
        usage["cost"] = cost
    return {"choices": [{"message": {"content": content}}], "usage": usage}


def test_classification_parses_the_models_json(monkeypatch, openrouter_mode):
    monkeypatch.setattr(orp, "_post", lambda path, payload: _chat_body('{"urgency": "high", "confidence": 0.91}'))
    label, confidence = model_client.classify_urgency("No power since this morning.")
    assert (label, confidence) == ("high", 0.91)


def test_classification_survives_a_model_that_ignores_the_format(monkeypatch, openrouter_mode):
    monkeypatch.setattr(orp, "_post", lambda path, payload: _chat_body("This looks like a MEDIUM urgency ticket."))
    label, _ = model_client.classify_urgency("You charged me twice.")
    assert label == "medium"


def test_reported_cost_is_used_instead_of_the_fallback_price(monkeypatch, openrouter_mode):
    from app.metrics import RequestMetrics, set_current

    metrics = RequestMetrics(request_id="test")
    set_current(metrics)
    monkeypatch.setattr(orp, "_post", lambda path, payload: _chat_body("an answer", cost=0.0075))
    model_client.generate("some prompt")
    assert metrics.cost_eur == pytest.approx(0.0075 * settings.eur_per_usd)


def test_embeddings_come_back_in_order_and_unit_length(monkeypatch, openrouter_mode):
    monkeypatch.setattr(
        orp,
        "_post",
        lambda path, payload: {
            "data": [
                {"index": 1, "embedding": [0.0, 3.0, 4.0]},
                {"index": 0, "embedding": [3.0, 4.0, 0.0]},
            ],
            "usage": {"total_tokens": 40},
        },
    )
    vectors = model_client.embed(["first", "second"])
    assert vectors[0] == pytest.approx([0.6, 0.8, 0.0])
    assert vectors[1] == pytest.approx([0.0, 0.6, 0.8])


def test_a_missing_key_is_a_dependency_failure_not_a_crash(monkeypatch, openrouter_mode):
    monkeypatch.setattr(orp, "_client", None, raising=False)
    monkeypatch.setattr(orp, "settings", replace(orp.settings, openrouter_api_key=""))
    with pytest.raises(ModelUnavailable):
        model_client.generate("some prompt")
