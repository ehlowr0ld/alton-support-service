"""Load scenario for the Sprint 1 async/background-task checkpoint.

Submit tickets to POST /v1/triage/async, measure 202 acknowledgement latency,
poll GET /v1/triage/{job_id}, and report actual background completion.

Example:
    python scripts/checkpoint_async_probe.py --requests 24 --concurrency 8 --seed 7
"""

import argparse
import asyncio
import json
import random
import statistics
import time
from pathlib import Path
from typing import Any

import httpx

TICKETS_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_tickets.json"


def percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((p / 100) * len(ordered)) - 1))
    return ordered[index]


async def submit_one(
    client: httpx.AsyncClient,
    url: str,
    ticket: dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    payload = {"ticket_text": ticket["ticket_text"]}
    if ticket.get("account_id"):
        payload["account_id"] = ticket["account_id"]

    async with semaphore:
        started = time.perf_counter()
        try:
            response = await client.post(url, json=payload, timeout=30.0)
            latency_ms = (time.perf_counter() - started) * 1000
            body = response.json()
            return {
                "ticket_id": ticket["id"],
                "status_code": response.status_code,
                "ack_latency_ms": latency_ms,
                "job_id": body.get("job_id"),
                "job_status": body.get("status"),
                "submitted_at": started,
            }
        except Exception as exc:  # The probe reports failures; it does not handle them.
            return {
                "ticket_id": ticket["id"],
                "status_code": 0,
                "ack_latency_ms": (time.perf_counter() - started) * 1000,
                "error": type(exc).__name__,
                "submitted_at": started,
            }


async def poll_one(
    client: httpx.AsyncClient,
    lookup_base: str,
    submission: dict[str, Any],
    poll_interval: float,
    timeout: float,
) -> dict[str, Any]:
    job_id = submission["job_id"]
    deadline = time.perf_counter() + timeout

    while time.perf_counter() < deadline:
        try:
            response = await client.get(f"{lookup_base}/{job_id}", timeout=10.0)
            body = response.json()
        except Exception as exc:
            return {**submission, "final_status": "poll_error", "error": type(exc).__name__}

        status = body.get("status")
        if response.status_code != 200:
            return {**submission, "final_status": f"http_{response.status_code}", "body": body}
        if status in {"finished", "failed"}:
            completed_ms = (time.perf_counter() - submission["submitted_at"]) * 1000
            result = body.get("result") if isinstance(body.get("result"), dict) else body
            return {
                **submission,
                "final_status": status,
                "completion_latency_ms": completed_ms,
                "cost_eur": float(result.get("cost_eur", 0.0)),
            }

        await asyncio.sleep(poll_interval)

    return {**submission, "final_status": "timeout"}


async def run(args: argparse.Namespace) -> None:
    tickets = json.loads(TICKETS_PATH.read_text(encoding="utf-8"))
    random.seed(args.seed)
    selection = [random.choice(tickets) for _ in range(args.requests)]
    semaphore = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient() as client:
        scenario_started = time.perf_counter()
        submissions = await asyncio.gather(
            *(submit_one(client, args.intake_url, ticket, semaphore) for ticket in selection)
        )
        acknowledgement_wall_s = time.perf_counter() - scenario_started

        accepted = [item for item in submissions if item.get("status_code") == 202 and item.get("job_id")]
        rejected = [item for item in submissions if item not in accepted]

        completions = await asyncio.gather(
            *(
                poll_one(
                    client,
                    args.lookup_base,
                    submission,
                    args.poll_interval,
                    args.timeout,
                )
                for submission in accepted
            )
        )
        total_wall_s = time.perf_counter() - scenario_started

    ack_latencies = [item["ack_latency_ms"] for item in accepted]
    finished = [item for item in completions if item.get("final_status") == "finished"]
    failed = [item for item in completions if item.get("final_status") == "failed"]
    incomplete = [
        item for item in completions if item.get("final_status") not in {"finished", "failed"}
    ]
    completion_latencies = [item["completion_latency_ms"] for item in finished]

    print(f"\nscenario         {args.requests} tickets at concurrency {args.concurrency}")
    print(f"acknowledged     {len(accepted)}   rejected {len(rejected)}")
    print(f"ack wall clock   {acknowledgement_wall_s:.2f} s")
    if ack_latencies:
        print(f"ack throughput   {len(accepted) / acknowledgement_wall_s:.2f} req/s")
        print(f"ack latency p50  {statistics.median(ack_latencies):.0f} ms")
        print(f"ack latency p95  {percentile(ack_latencies, 95):.0f} ms")
    print(f"jobs finished    {len(finished)}   failed {len(failed)}   incomplete {len(incomplete)}")
    print(f"all-jobs wall    {total_wall_s:.2f} s")
    if completion_latencies:
        print(f"complete p50     {statistics.median(completion_latencies):.0f} ms")
        print(f"complete p95     {percentile(completion_latencies, 95):.0f} ms")
    print(f"cost total       EUR {sum(item.get('cost_eur', 0.0) for item in finished):.4f}")

    problems = rejected + failed + incomplete
    if problems:
        counts: dict[str, int] = {}
        for item in problems:
            key = str(item.get("error") or item.get("final_status") or item.get("status_code"))
            counts[key] = counts.get(key, 0) + 1
        print(f"problems         {counts}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--intake-url",
        default="http://127.0.0.1:8000/v1/triage/async",
    )
    parser.add_argument(
        "--lookup-base",
        default="http://127.0.0.1:8000/v1/triage",
    )
    parser.add_argument("--requests", type=int, default=24)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--poll-interval", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
