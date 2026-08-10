"""Smoke tests for the baseline.

These check that the scaffold works, not that it is good. Keep them passing as
you change the service — if a refactor breaks one, you changed the contract.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

TICKET = "My direct debit was taken twice this month. Can you refund one of them?"


def test_triage_returns_a_complete_answer():
    response = client.post("/v1/triage", json={"ticket_text": TICKET})
    assert response.status_code == 200

    body = response.json()
    assert body["urgency"] in {"low", "medium", "high"}
    assert body["answer"]
    assert len(body["sources"]) == 3
    assert body["cost_eur"] > 0
    assert {"classify", "embed", "generate"} <= set(body["steps_ms"])


def test_account_lookup_runs_only_when_an_account_id_is_sent():
    without = client.post("/v1/triage", json={"ticket_text": TICKET}).json()
    assert without["account"] is None
    assert "account_lookup" not in without["steps_ms"]

    with_account = client.post(
        "/v1/triage", json={"ticket_text": TICKET, "account_id": "ALT-10023"}
    ).json()
    assert with_account["account"]["tariff"] == "Alton Fix 24"
    assert "account_lookup" in with_account["steps_ms"]


def test_urgency_classification_separates_an_outage_from_a_billing_question():
    outage = client.post(
        "/v1/triage", json={"ticket_text": "There is no power in my flat since this morning."}
    ).json()
    assert outage["urgency"] == "high"


def test_short_input_is_rejected():
    assert client.post("/v1/triage", json={"ticket_text": "hi"}).status_code == 422


@pytest.mark.parametrize("top_k", [1, 5])
def test_top_k_controls_how_many_articles_come_back(top_k):
    body = client.post("/v1/triage", json={"ticket_text": TICKET, "top_k": top_k}).json()
    assert len(body["sources"]) == top_k
