"""Show circuit breaker state transitions from the service log.

    python scripts/show_circuit.py
    python scripts/show_circuit.py --log logs/baseline.jsonl

Prints one line per transition, with the gap since the previous one. The gap
between 'circuit open' and 'circuit half-open' is your recovery timeout.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

DEFAULT_LOG = Path(__file__).resolve().parent.parent / "logs" / "service.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args()

    if not args.log.exists():
        print(f"No log file at {args.log}. Start the service and send a request first.")
        return

    rows = []
    for line in args.log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "circuit" in entry and str(entry.get("event", "")).startswith("circuit"):
            rows.append(entry)

    if not rows:
        print("No circuit transitions in the log.")
        print("The breaker never opened. Raise FAULT_TOOL_ERROR_RATE, lower your")
        print("failure_threshold, or send more requests — then run this again.")
        return

    print(f"\n{len(rows)} transition(s) in {args.log}\n")
    print(f"{'time':<14}{'state':<20}{'gap':>8}   detail")

    previous = None
    for entry in rows:
        stamp = datetime.fromisoformat(entry["ts"])
        gap = "" if previous is None else f"{(stamp - previous).total_seconds():.1f}s"
        failures = entry.get("consecutive_failures")
        detail = f"after {failures} consecutive failures" if failures else ""
        print(f"{entry['ts'][11:23]:<14}{entry['event']:<20}{gap:>8}   {detail}")
        previous = stamp

    print()


if __name__ == "__main__":
    main()