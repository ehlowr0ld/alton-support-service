"""Ticket triage pipeline.

Four steps, run one after another:

    1. classify urgency          (model)
    2. look up the account       (external tool, only if an account id was sent)
    3. retrieve help articles    (embeddings + similarity)
    4. draft an answer           (model)

Everything is sequential and blocking, nothing is cached, and no failure is
handled. That is the baseline. Each sprint changes part of this file.
"""

import logging
import time
from typing import Dict, List, Optional

from ..config import settings
from . import account_tool, model_client, retrieval

logger = logging.getLogger(__name__)


def triage_ticket(
    ticket_text: str,
    account_id: Optional[str] = None,
    top_k: Optional[int] = None,
) -> Dict:
    started = time.perf_counter()

    urgency, confidence = model_client.classify_urgency(ticket_text)
    logger.debug("classified ticket", extra={"urgency": urgency, "confidence": confidence})

    account = account_tool.lookup_account(account_id) if account_id else None

    articles = retrieval.search(ticket_text, top_k=top_k or settings.retrieval_top_k)

    prompt = _build_prompt(ticket_text, articles, account)
    answer = model_client.generate(prompt)

    return {
        "urgency": urgency,
        "urgency_confidence": confidence,
        "answer": answer,
        "sources": [
            {"id": article["id"], "title": article["title"], "score": article["score"]}
            for article in articles
        ],
        "account": account,
        "processing_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def _build_prompt(ticket_text: str, articles: List[Dict], account: Optional[Dict]) -> str:
    lines = [
        "You are a support assistant for Alton Energy, a German energy retailer.",
        "Answer the customer using only the help-centre extracts below.",
        "",
        f"Customer message: {ticket_text}",
        "",
    ]
    if account:
        lines += [
            f"Account tariff: {account['tariff']} | status: {account['status']} "
            f"| last invoice: EUR {account['last_invoice_eur']}",
            "",
        ]
    lines.append("Help-centre extracts:")
    lines += [f"- {article['body']}" for article in articles]
    return "\n".join(lines)
