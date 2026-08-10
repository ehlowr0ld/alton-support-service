"""Summarise logs/service.jsonl: latency percentiles, cost, and time per step.

    python scripts/analyze_logs.py
    python scripts/analyze_logs.py --log logs/baseline.jsonl

Copy the log file aside before you change the service, then compare runs.
"""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

DEFAULT_LOG = Path(__file__).resolve().parent.parent / "logs" / "service.jsonl"


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(p / 100 * len(ordered))) - 1))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--path", default="/v1/triage", help="Only count requests to this path.")
    args = parser.parse_args()

    if not args.log.exists():
        print(f"No log file at {args.log}. Start the service and send a request first.")
        return

    durations: list[float] = []
    costs: list[float] = []
    statuses: dict[int, int] = defaultdict(int)
    step_totals: dict[str, float] = defaultdict(float)
    step_calls: dict[str, int] = defaultdict(int)

    for line in args.log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("path") != args.path or "duration_ms" not in entry:
            continue

        durations.append(entry["duration_ms"])
        costs.append(entry.get("cost_eur", 0.0))
        statuses[entry.get("status", 0)] += 1
        for step, ms in (entry.get("steps_ms") or {}).items():
            step_totals[step] += ms
        for step, count in (entry.get("calls") or {}).items():
            step_calls[step] += count

    if not durations:
        print(f"No requests to {args.path} found in {args.log}.")
        return

    n = len(durations)
    print(f"\nlog             {args.log}")
    print(f"requests        {n}")
    print(f"status codes    {dict(statuses)}")
    print(f"latency p50     {statistics.median(durations):.0f} ms")
    print(f"latency p95     {percentile(durations, 95):.0f} ms")
    print(f"latency p99     {percentile(durations, 99):.0f} ms")
    print(f"cost total      EUR {sum(costs):.4f}")
    print(f"cost per req    EUR {sum(costs) / n:.5f}")
    print("\nper request, on average:")
    for step in sorted(step_totals, key=lambda s: -step_totals[s]):
        print(f"  {step:<16} {step_totals[step] / n:8.1f} ms   {step_calls[step] / n:5.2f} calls")
    print()


if __name__ == "__main__":
    main()
