"""Fire a batch of concurrent requests at a running service and report on them.

    python scripts/load_probe.py --requests 20 --concurrency 5

Requests are drawn from data/sample_tickets.json, which contains exact repeats
and paraphrases on purpose. Run it against the baseline first and keep the
numbers — every later claim about an improvement is measured against them.
"""

import argparse
import asyncio
import json
import random
import statistics
import time
from pathlib import Path

import httpx

TICKETS_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_tickets.json"


async def one_request(client: httpx.AsyncClient, url: str, ticket: dict, semaphore: asyncio.Semaphore) -> dict:
    payload = {"ticket_text": ticket["ticket_text"]}
    if ticket.get("account_id"):
        payload["account_id"] = ticket["account_id"]

    async with semaphore:
        started = time.perf_counter()
        try:
            response = await client.post(url, json=payload, timeout=120.0)
            elapsed_ms = (time.perf_counter() - started) * 1000
            body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            return {
                "ticket": ticket["id"],
                "status": response.status_code,
                "latency_ms": elapsed_ms,
                "cost_eur": body.get("cost_eur", 0.0),
            }
        except Exception as exc:  # noqa: BLE001 - the probe reports failures, it does not handle them
            return {
                "ticket": ticket["id"],
                "status": 0,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "cost_eur": 0.0,
                "error": type(exc).__name__,
            }


async def run(url: str, total: int, concurrency: int, seed: int) -> None:
    tickets = json.loads(TICKETS_PATH.read_text(encoding="utf-8"))
    random.seed(seed)
    selection = [random.choice(tickets) for _ in range(total)]

    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient() as client:
        wall_start = time.perf_counter()
        results = await asyncio.gather(*(one_request(client, url, t, semaphore) for t in selection))
        wall = time.perf_counter() - wall_start

    latencies = sorted(r["latency_ms"] for r in results)
    ok = [r for r in results if r["status"] == 200]
    failed = [r for r in results if r["status"] != 200]

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        index = min(len(latencies) - 1, int(round(p / 100 * len(latencies))) - 1)
        return latencies[max(index, 0)]

    print(f"\nrequests        {total} at concurrency {concurrency}")
    print(f"wall clock      {wall:.2f} s")
    print(f"throughput      {total / wall:.2f} req/s")
    print(f"success         {len(ok)}   failed {len(failed)}")
    if latencies:
        print(f"latency p50     {statistics.median(latencies):.0f} ms")
        print(f"latency p95     {pct(95):.0f} ms")
        print(f"latency max     {latencies[-1]:.0f} ms")
    print(f"cost total      EUR {sum(r['cost_eur'] for r in results):.4f}")
    if ok:
        print(f"cost per req    EUR {sum(r['cost_eur'] for r in ok) / len(ok):.5f}")
    if failed:
        codes = {}
        for r in failed:
            key = r.get("error") or r["status"]
            codes[key] = codes.get(key, 0) + 1
        print(f"failures        {codes}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/v1/triage")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--seed", type=int, default=7, help="Same seed means the same request mix.")
    args = parser.parse_args()
    asyncio.run(run(args.url, args.requests, args.concurrency, args.seed))


if __name__ == "__main__":
    main()
