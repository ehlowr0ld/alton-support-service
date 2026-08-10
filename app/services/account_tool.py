"""Account lookup — the service's third-party dependency.

Stands in for Alton's billing system: an HTTP call to a system owned by another
team, with its own latency and its own outages. It is slower than it looks like
it should be, and it is the easiest dependency to lose.
"""

import json
import random
import time
from typing import Dict, Optional

from ..config import DATA_DIR, settings
from ..metrics import record
from .errors import ToolUnavailable

ACCOUNTS_PATH = DATA_DIR / "accounts.json"


def lookup_account(account_id: str) -> Optional[Dict]:
    """Fetch account and tariff details. Returns None if the account is unknown."""
    started = time.perf_counter()

    if settings.fault_tool_error_rate > 0 and random.random() < settings.fault_tool_error_rate:
        raise ToolUnavailable("billing system returned 502")

    time.sleep(settings.tool_latency + settings.fault_tool_extra_latency)

    with ACCOUNTS_PATH.open(encoding="utf-8") as handle:
        accounts = json.load(handle)

    record("account_lookup", time.perf_counter() - started)
    return accounts.get(account_id)
