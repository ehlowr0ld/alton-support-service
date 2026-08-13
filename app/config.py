"""Service configuration.

Everything is read from environment variables so behaviour can be changed
without touching code. The FAULT_* settings exist so a dependency can be made
to fail or slow down on demand — you will need them from Sprint 3 onwards.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # --- service ---
    service_name: str = "alton-support-service"
    version: str = "0.1.0"
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_file: Path = field(default_factory=lambda: LOG_DIR / "service.jsonl")
    
    # --- currency ---
    # Providers bill in USD. Converted to EUR once, in metrics.py.
    # A pinned assumption, not a live rate — change it deliberately.
    eur_per_usd: float = field(default_factory=lambda: _env_float("EUR_PER_USD", 0.92))

    # --- model provider ---
    # "mock"       offline, deterministic, free — the default, and what load tests use
    # "openrouter" real models over the OpenRouter API
    model_provider: str = field(
        default_factory=lambda: os.getenv("MODEL_PROVIDER", "mock").strip().lower()
    )
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_base_url: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )
    openrouter_timeout: float = field(default_factory=lambda: _env_float("OPENROUTER_TIMEOUT", 30.0))
    openrouter_referer: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_REFERER", "https://masterschool.com")
    )
    openrouter_title: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_TITLE", "Alton Support Triage")
    )
    chat_model: str = field(
        default_factory=lambda: os.getenv("CHAT_MODEL", "openai/gpt-4o-mini")
    )
    classifier_model: str = field(
        default_factory=lambda: os.getenv("CLASSIFIER_MODEL", os.getenv("CHAT_MODEL", "openai/gpt-4o-mini"))
    )
    embedding_model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
    )

    # --- simulated provider latency (seconds) ---
    # Mock provider only. The openrouter provider has whatever latency the
    # network and the model give it.
    # These emulate a hosted model / embedding / tool API. They are the reason
    # the service is slow. Do not "optimise" by lowering them.
    classify_latency: float = field(default_factory=lambda: _env_float("CLASSIFY_LATENCY", 0.06))
    embed_latency_per_item: float = field(default_factory=lambda: _env_float("EMBED_LATENCY_PER_ITEM", 0.018))
    generate_base_latency: float = field(default_factory=lambda: _env_float("GENERATE_BASE_LATENCY", 0.70))
    tool_latency: float = field(default_factory=lambda: _env_float("TOOL_LATENCY", 0.25))

    # --- simulated pricing (USD per 1k tokens) ---
    # Deliberately round numbers, not a copy of any vendor's price list.
    # They are the module's cost model: on mock, every cost figure comes
    # from here. Converted to EUR in metrics.py.
    price_generate_usd_per_1k: float = field(default_factory=lambda: _env_float("PRICE_GENERATE_USD_PER_1K", 0.0150))
    price_classify_usd_per_1k: float = field(default_factory=lambda: _env_float("PRICE_CLASSIFY_USD_PER_1K", 0.0004))
    price_embed_usd_per_1k: float = field(default_factory=lambda: _env_float("PRICE_EMBED_USD_PER_1K", 0.0002))

    # --- retrieval ---
    retrieval_top_k: int = field(default_factory=lambda: _env_int("RETRIEVAL_TOP_K", 3))

    # --- fault injection (Sprint 3) ---
    fault_model_error_rate: float = field(default_factory=lambda: _env_float("FAULT_MODEL_ERROR_RATE", 0.0))
    fault_model_extra_latency: float = field(default_factory=lambda: _env_float("FAULT_MODEL_EXTRA_LATENCY", 0.0))
    fault_retrieval_down: bool = field(default_factory=lambda: _env_bool("FAULT_RETRIEVAL_DOWN"))
    fault_tool_error_rate: float = field(default_factory=lambda: _env_float("FAULT_TOOL_ERROR_RATE", 0.0))
    fault_tool_extra_latency: float = field(default_factory=lambda: _env_float("FAULT_TOOL_EXTRA_LATENCY", 0.0))


settings = Settings()
