"""Per-request latency and cost accounting.

Every provider call reports what it took and what it cost into the
RequestMetrics object for the current request. The middleware logs the result.

This is the measurement instrument for the whole module: when a lesson asks you
to show that caching reduced cost, you show it from here.
"""

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Dict, Optional
from .config import settings

_current: ContextVar[Optional["RequestMetrics"]] = ContextVar("request_metrics", default=None)


@dataclass
class RequestMetrics:
    request_id: str
    steps_ms: Dict[str, float] = field(default_factory=dict)
    calls: Dict[str, int] = field(default_factory=dict)
    tokens: int = 0
    cost_eur: float = 0.0

    def record(self, step: str, duration_s: float, *, tokens: int = 0, cost_usd: float = 0.0) -> None:
        self.steps_ms[step] = round(self.steps_ms.get(step, 0.0) + duration_s * 1000, 2)
        self.calls[step] = self.calls.get(step, 0) + 1
        self.tokens += tokens
        self.cost_eur = round(self.cost_eur + cost_usd * settings.eur_per_usd, 6)

    def as_log_fields(self) -> dict:
        return {
            "steps_ms": self.steps_ms,
            "calls": self.calls,
            "tokens": self.tokens,
            "cost_eur": self.cost_eur,
        }


def set_current(metrics: RequestMetrics) -> None:
    _current.set(metrics)


def current() -> Optional[RequestMetrics]:
    return _current.get()


def record(step: str, duration_s: float, *, tokens: int = 0, cost_usd: float = 0.0) -> None:
    metrics = current()
    if metrics is not None:
        metrics.record(step, duration_s, tokens=tokens, cost_usd=cost_usd)
