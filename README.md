# Alton Energy — Support Triage Service

**Baseline project for Production Engineering for AI/ML, Module A.**

Alton Energy is a German energy retailer with roughly 400,000 residential customers. Its support inbox takes about 2,000 messages a day: duplicate direct debits, meter readings that look wrong, moves, outages. An internal team built this service so agents open a ticket and already see an urgency label, a drafted answer, and the help-centre articles the answer came from.

It works. It is also slow, expensive, and falls over whenever one of its dependencies has a bad day. You will spend the next four sprints fixing that.

---

## What the service does

One endpoint, `POST /v1/triage`. Per request it runs four steps in order:

| Step | Dependency | Roughly |
|---|---|---|
| Classify urgency | model provider | 60 ms |
| Look up the account | billing system (external) | 250 ms — only if `account_id` was sent |
| Retrieve help articles | embeddings + similarity | 420 ms |
| Draft the answer | model provider | 780 ms |

About 1.5 seconds on the mock provider when nothing else is happening. Considerably worse when something else is happening, and different again against real models — see below.

---

## Running it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

In Cursor, open the folder and select `.venv` as the interpreter. `.cursor/rules/project.mdc`
tells the assistant how this repo is meant to be worked in — read it, it is short.

Interactive docs at `http://127.0.0.1:8000/docs`. A first request:

```bash
curl -X POST http://127.0.0.1:8000/v1/triage \
  -H "content-type: application/json" \
  -d '{"ticket_text": "My direct debit was taken twice this month. Can you refund one of them?", "account_id": "ALT-10023"}'
```

The response carries `processing_ms`, `cost_eur`, and a `steps_ms` breakdown, so every request tells you what it took and what it cost.

Tests:

```bash
pytest
```

---

## Measuring it

Two scripts. You will use them in every sprint.

```bash
python scripts/load_probe.py --requests 20 --concurrency 5   # send traffic
python scripts/analyze_logs.py                                # summarise what happened
```

`load_probe.py` draws from `data/sample_tickets.json` and reports throughput, latency percentiles, and total cost. `analyze_logs.py` reads `logs/service.jsonl` and adds the per-step breakdown.

**Do this before you change anything.** Run the probe against the untouched baseline and save the output:

```bash
python scripts/load_probe.py --requests 20 --concurrency 5 | tee baseline-run.txt
cp logs/service.jsonl logs/baseline.jsonl
```

Every improvement you claim for the rest of the module is measured against those numbers.

---

## Layout

```
app/
  main.py                    FastAPI app, the endpoint, request logging middleware
  config.py                  settings and fault-injection knobs, all from env vars
  schemas.py                 request and response models
  logging_conf.py            JSON logging to stdout and logs/service.jsonl
  metrics.py                 per-request latency and cost accounting
  services/
    triage.py                the pipeline — the four steps, assembled
    model_client.py          the one way to call a model: classify, embed, generate
    providers/
      mock_provider.py       offline stand-in
      openrouter_provider.py real calls to OpenRouter
    retrieval.py             help-centre search
    account_tool.py          the external billing-system call
    errors.py                dependency failure types
data/
  help_center.jsonl          22 help-centre articles
  accounts.json              8 customer accounts
  sample_tickets.json        24 tickets, with repeats and paraphrases
scripts/
  load_probe.py              send concurrent traffic
  analyze_logs.py            latency, cost, and per-step summary
  check_provider.py          verify your OpenRouter key and models
tests/
  test_smoke.py              the service still works
  test_openrouter_provider.py the real-provider path, with HTTP stubbed
```

---

## Two model providers, one switch

`MODEL_PROVIDER` decides who answers the model calls.

| | `mock` (default) | `openrouter` |
|---|---|---|
| Runs | offline, no key | real models over the OpenRouter API |
| Cost | nothing | your credits |
| Same input, same output? | yes | no |
| Use it for | load tests, benchmarks, anything you compare | seeing how a real model actually behaves |

```bash
# real models
MODEL_PROVIDER=openrouter uvicorn app.main:app --reload

# check your key and models work before you need them
MODEL_PROVIDER=openrouter python scripts/check_provider.py
```

Put your key in `.env`:

```bash
MODEL_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
CHAT_MODEL=openai/gpt-4o-mini
EMBEDDING_MODEL=openai/text-embedding-3-small
```

`.env` is gitignored. Do not commit a key, and do not paste one into a chat window.

**Benchmark on the mock.** This is the one rule to hold to. A real model's latency moves with provider load and its output moves with temperature, so a before-and-after against a real model tells you very little about your change and costs money to learn it. Develop against `openrouter` when the model's actual behaviour matters — does the classifier get this ticket right, is the answer any good — and switch to `mock` whenever you are measuring.

Everything in the service calls the three functions in `app/services/model_client.py` and never a provider directly. That indirection is why the switch is a single environment variable, and it is worth noticing as a pattern: it is the same reason production services wrap their model vendors.
