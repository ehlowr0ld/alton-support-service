"""Alton Energy — support triage service.

One endpoint: POST /v1/triage. Send a customer message, get back an urgency
label, a drafted answer, and the help-centre articles it was based on.

Read app/services/triage.py to see what actually happens per request.
"""

import logging
import time
import uuid

from fastapi import FastAPI, Request

from .config import settings
from .logging_conf import configure_logging
from .metrics import RequestMetrics, current, set_current
from .schemas import TriageRequest, TriageResponse
from .services.triage import triage_ticket

configure_logging()
logger = logging.getLogger("alton.api")

app = FastAPI(
    title="Alton Energy Support Triage",
    version=settings.version,
    description="Baseline service for the Production Engineering module.",
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id, time the request, and log one line per request."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    set_current(RequestMetrics(request_id=request_id))
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            "request failed",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "status": 500,
                "duration_ms": duration_ms,
                **(current().as_log_fields() if current() else {}),
            },
        )
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["x-request-id"] = request_id
    logger.info(
        "request completed",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "status": response.status_code,
            "duration_ms": duration_ms,
            **(current().as_log_fields() if current() else {}),
        },
    )
    return response


# The endpoint is declared async but every call inside it is blocking.
# Watch what that does to throughput when more than one request arrives at once.
@app.post("/v1/triage", response_model=TriageResponse)
async def triage(payload: TriageRequest) -> TriageResponse:
    metrics = current()
    result = triage_ticket(
        ticket_text=payload.ticket_text,
        account_id=payload.account_id,
        top_k=payload.top_k,
    )
    return TriageResponse(
        request_id=metrics.request_id if metrics else "unknown",
        cost_eur=metrics.cost_eur if metrics else 0.0,
        steps_ms=metrics.steps_ms if metrics else {},
        **result,
    )
