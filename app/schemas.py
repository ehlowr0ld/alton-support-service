"""Request and response models for the public API."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TriageRequest(BaseModel):
    ticket_text: str = Field(..., min_length=5, max_length=4000, description="The customer's message.")
    account_id: Optional[str] = Field(
        None, description="Alton account id, e.g. ALT-10023. Triggers a billing-system lookup."
    )
    top_k: Optional[int] = Field(None, ge=1, le=10, description="How many help-centre articles to retrieve.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ticket_text": "My direct debit was taken twice this month. Can you refund one of them?",
                    "account_id": "ALT-10023",
                }
            ]
        }
    }


class Source(BaseModel):
    id: str
    title: str
    score: float


class Account(BaseModel):
    tariff: str
    status: str
    last_invoice_eur: float
    region: str


class TriageResponse(BaseModel):
    request_id: str
    urgency: str
    urgency_confidence: float
    answer: str
    sources: List[Source]
    account: Optional[Account] = None
    processing_ms: float
    cost_eur: float
    steps_ms: Dict[str, float]
