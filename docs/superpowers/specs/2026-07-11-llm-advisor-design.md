# LLM Trading Advisor — Design Spec

Date: 2026-07-11. Status: approved direction (hybrid), pending user review of this document.

## 1. Goal

Add an LLM "advisor" layer that reads the bot's own evidence — trades.json, the lessons journal, the analytics snapshot, calibration/drift tables, the validation registry — and turns it into: (a) a nightly narrative performance analysis, (b) weekly tuning hypotheses for the TRAIN-only harness to test, (c) a per-alert second opinion on each trade plan, and (d) a `!ask` command that answers questions about the user's own trading history.

**Honest framing (binding for every prompt this system ships):** a 100% win rate does not exist and the advisor must never suggest otherwise. The bot's own out-of-sample validation shows the best strategies hold 81–87% WR and that train-window edges can collapse out-of-sample (RSI: 85.2% → 68.4%). The advisor's job is to push win rate and expectancy up *honestly*: explain failures, surface decay early, generate testable hypotheses, and talk the user out of low-quality plans. Every advisor claim must cite the data it was given (trade IDs, table rows); every tuning idea is a *proposal* to be verified by the existing backtest discipline, never an applied change.

## 2. Constraints & context this design builds on

- **Hosting:** bot + admin UI run in Docker on a Hetzner CX23 (4 shared vCPU, 8GB RAM) — too weak for meaningful local inference and needed for the bot itself.
- **Laptop:** i7-1255U (2P+8E cores), 32GB RAM, **no dedicated GPU**, Windows 11. CPU inference only: 8B-class models at ~4–8 tok/s, 14B at ~2–3 tok/s. Fine for unattended batch jobs; unusable for interactive chat. Behind home NAT, online irregularly.
- **User has no LLM experience** — the plan derived from this spec must include setup/primer steps (Ollama install, API key creation, first smoke tests) and the system must degrade gracefully (advisor down ≠ bot down).
- **Budget:** hybrid approved. Cloud = Anthropic **`claude-haiku-4-5`** ($1/MTok in, $5/MTok out, 200K context); expected spend $2–8/month with prompt caching; hard monthly cap enforced in code.
- **Transports:** SSH (existing server key) primary; token-authenticated HTTPS endpoints on the existing Flask admin app as backup. Nothing new exposed by default.
- **Prerequisites:** plan-engine-v2 merged; **Plan A (analytics core) merged** — the advisor consumes `analytics_snapshot.json`, `journal.json`, calibration/drift, `rank.follow_score`. Plan C's tuning `JobManager` is *related but separate* (it runs backtest subprocesses; the advisor queue runs LLM jobs). If Plan C is unmerged, the tuning-hypothesis output still works (it writes proposal files); only the "one-click grid launch" cross-link degrades to a CLI instruction.
- **No new heavy dependencies on the server:** `anthropic` SDK + `jsonschema` only. The laptop worker additionally uses `paramiko` (SFTP) and `requests` (Ollama REST + HTTPS fallback); Ollama itself is a native install on the laptop, never on the server.

## 3. Architecture overview

```
┌─ Hetzner CX23 ──────────────────────────────────────────────┐
│  swingbot (Discord bot)                                     │
│   swingbot/core/advisor/                                    │
│    ├ queue.py        job files in data/llm_jobs/            │
│    ├ producers.py    nightly / weekly / plan_review / ask   │
│    ├ consumer.py     ingest results → Discord + admin       │
│    ├ cloud.py        Claude Haiku (anthropic SDK) inline    │
│    ├ schemas.py      JSON Schemas for every job kind        │
│    ├ prompts/        system + task prompt templates (.md)   │
│    └ budget.py       token ledger + monthly cap             │
│  swingbot/admin: /advisor page + /api/llm/* (token auth)    │
└───────────────▲──────────────────────────▲──────────────────┘
        SSH/SFTP │ (primary)        HTTPS │ (backup)
                 │                        │
┌─ Laptop (when open) ────────────────────┴───────────────────┐
│  llm_worker/  poll → lease job → build prompt → Ollama      │
│               (qwen3:8b default) → validate JSON → push     │
└──────────────────────────────────────────────────────────────┘
```

Two execution paths, one contract:
- **Inline cloud path** (bot process, seconds): `plan_review` and `ask` jobs run immediately against Claude Haiku when `ADVISOR_CLOUD_ENABLED` and the budget allows; otherwise they fall back into the queue.
- **Queued local path** (laptop, minutes–hours): `nightly_analysis` and `tuning_hypotheses` always queue; the worker processes them whenever the laptop is on. Cloud never runs these by default (they're big-context, latency-insensitive — exactly what free local compute is for). An operator override (`model_hint: "cloud"` set from the admin page) can force a stuck job to the cloud via the Batches API (50% price).

Both paths use the **same prompt templates and the same JSON Schemas**; only the provider differs. The worker gets prompts/schemas from its own checkout of this repo (git pull is a documented worker-update step).

## 4. Job model and queue protocol

One JSON file per job: `data/llm_jobs/{job_id}.json`, written atomically via `jsonio.atomic_write_json` (Plan A). Results: `data/llm_results/{job_id}.json`. Completed job+result pairs are archived to `data/advisor/archive/YYYY-MM/` by the consumer after ingestion.

Job schema (exact keys):

```json
{
  "id": "j_20260711_a1b2c3",
  "kind": "nightly_analysis | tuning_hypotheses | plan_review | ask",
  "created_at": "ISO-8601",
  "priority": 1,
  "model_hint": "local | cloud | any",
  "status": "pending | leased | done | failed",
  "lease": {"worker": "laptop-hostname", "expires": "ISO-8601"} ,
  "attempts": 0,
  "payload": { "...kind-specific, see §6..." }
}
```

Protocol (worker side):
1. List `data/llm_jobs/*.json`, pick oldest `pending` (or `leased` with expired lease — crash recovery) matching its capabilities.
2. Lease: rewrite the file with `status="leased"`, `lease.expires = now + MAX_JOB_MINUTES` (default 45), `attempts += 1`. SFTP rename-based write keeps this atomic enough for a single worker; the design assumes **one worker** (documented; a second laptop later would need a lease-token check the consumer already tolerates).
3. Run the job; write `data/llm_results/{job_id}.json` `{job_id, produced_at, provider: "ollama:qwen3:8b", duration_s, output: {…schema-valid…}}`; rewrite job `status="done"`.
4. On failure: `status="failed"` with `error` string. Consumer re-queues once (attempts ≤ 2), then surfaces the failure on the admin page.

Consumer (bot side, piggybacks on the existing 60s monitor loop): scan `data/llm_results/`, validate against schema again (defense in depth — a worker bug must not post garbage to Discord), dispatch per kind (§6), archive.

## 5. Transports

**SSH/SFTP (primary).** The worker connects with the user's existing Hetzner key (`paramiko.SFTPClient`), working directly on the bot's bind-mounted `data/` directory. No server-side changes at all. Config: `SSH_HOST`, `SSH_USER`, `SSH_KEY_PATH`, `REMOTE_DATA_DIR` in `llm_worker/worker.env`.

**HTTPS (backup).** Three endpoints on the existing Flask admin app, auth by `X-Advisor-Token` header (constant-time compare against config `ADVISOR_WORKER_TOKEN`, a generated 32-byte secret, independent of admin basic-auth):
- `GET  /api/llm/jobs?status=pending` → job list
- `POST /api/llm/jobs/<id>/lease` → lease (409 if already leased)
- `POST /api/llm/results/<id>` → submit result (validated server-side before write)

The worker tries SSH first; on connect failure it retries via HTTPS if `HTTP_FALLBACK_URL` is configured. Both transports implement one tiny `Transport` interface (`list_jobs`, `lease`, `put_result`) so the worker logic is transport-blind. Rationale for having both: SSH needs zero exposure but breaks if the key/network setup changes; HTTPS works from networks where outbound 22 is blocked, but requires the admin port to be internet-reachable behind HTTPS (documented as opt-in with a strong token).

## 6. The four capabilities

Common rules baked into every system prompt: *use only the data provided; cite trade IDs / table rows for every claim; state sample sizes; never promise or imply guaranteed outcomes; a claim without evidence in the payload is forbidden; answer in the JSON schema given.* All outputs are validated with `jsonschema`; invalid output → one retry with the validation error appended → fail.

### 6.1 Plan reviewer (cloud, inline, per alert)

- **Trigger:** after a scan alert's plan is built, if `ADVISOR_PLAN_REVIEW_ENABLED` (default off) and budget OK. Runs in the scan's background thread; a failure or >10s timeout silently skips (alerts must never block on the advisor).
- **Payload:** the TradePlanV2 dict, its follow-score breakdown, badge stats, the strategy's live-vs-OOS drift row, last 5 journal entries for that ticker, regime state, days-to-earnings if known.
- **Output schema:** `{"verdict": "follow|caution|skip", "confidence": 0-100, "reasons": [str], "risks": [str], "one_liner": str}`.
- **Surface:** appended field on the alert embed: `🤖 Advisor: CAUTION (62) — earnings in 2 days; RSI Divergence live WR 71% vs 76% OOS.` Full reasons behind the Plan B "Breakdown" button and on the admin plan-detail page. The verdict is advice — it never suppresses or reorders alerts (follow_score stays the only ranking).

### 6.2 Nightly analyst (local, queued)

- **Trigger:** produced right after the daily retrospective posts (same session-end hook), so it runs on tonight's data whenever the laptop next opens.
- **Payload:** analytics snapshot (overall, by-dimension tables, calibration, drift), today's + trailing-7-day journal entries, retrospective text, open plan list.
- **Output schema:** `{"headline": str, "findings": [{"topic": str, "detail": str, "evidence": [str]}], "concerns": [str], "focus_tomorrow": [str], "discord_summary": str}` (`discord_summary` ≤ 1500 chars).
- **Surface:** `discord_summary` posted to the retrospective channel as `🤖 AI Analyst — {date}`; full report browsable on the admin Advisor page and via `!analyst` (latest report).

### 6.3 Tuning hypothesist (local, queued, weekly)

- **Trigger:** weekly (Sunday), and on demand from the admin Advisor page.
- **Payload:** full snapshot + drift report, per-strategy grid of current `DEFAULT_PARAMS`/`STRATEGY_GATES`/`STRATEGY_RR_OVERRIDE` with their provenance, the tunable-parameter catalog with allowed ranges (mirrors `scripts/tune_strategy.py`), round-1/round-2 results-doc summaries, and the list of hypotheses already tested (to avoid repeats).
- **Output schema:** `{"hypotheses": [{"strategy": str, "param_changes": {name: value}, "rationale": str, "expected_effect": str, "priority": 1-3}]}` — max 5, each param must be in the allowed catalog (validated).
- **Surface & handoff (the safety-critical part):** each hypothesis is written to `data/tuning_proposals/` in the same shape Plan C's workbench uses, flagged `source: "llm"` and `status: "untested"`. The human reviews it and runs the **TRAIN-only** grid (Plan C UI or CLI). The LLM cannot execute backtests, cannot touch the 2024–25 validation window (the TRAIN-only guardrail sits below it), and cannot change code. A hypothesis that fails TRAIN is recorded back into the "already tested" list so it's never re-proposed.

### 6.4 `!ask` (cloud, inline)

- **Trigger:** `!ask <question>` Discord command (and `/ask`).
- **Context assembly (no vector DB in v1):** keyword match over journal entries + snapshot tables; ticker/strategy names in the question select their journal entries and stat rows; cap context at ~30 entries. This is deliberately simple — real RAG with local embeddings is a future-machine feature (§9).
- **Output schema:** `{"answer": str, "evidence": [str], "caveats": [str]}` → rendered as an embed with an evidence footnote.
- **Budget:** counts against the monthly cap; over cap → `"Advisor budget spent for this month — question queued for the local worker"` (job with `model_hint: "local"`).

## 7. Providers

**Cloud (`cloud.py`).** Official `anthropic` SDK, model `claude-haiku-4-5`, `client.messages.create` with `output_config={"format": {"type": "json_schema", "schema": …}}` (Haiku 4.5 supports structured outputs), `max_tokens=2048` (plan review / ask) — nightly-sized jobs use the **Batches API** at 50% price when operator-forced to cloud. The stable system prompt carries `cache_control: {"type": "ephemeral"}`; volatile payload goes in the user turn — so per-alert reviews mostly pay cache-read prices. Key from config Field `ANTHROPIC_API_KEY` (sensitive). Errors: typed exception chain (RateLimitError → backoff once; anything else → skip/queue); the bot never crashes on advisor errors.

**Local (`llm_worker/ollama_client.py`).** Ollama REST `POST http://localhost:11434/api/chat` with `"format": <json schema>` (Ollama's structured-output mode) and `"options": {"num_ctx": 16384}`. Default model `qwen3:8b` (config `OLLAMA_MODEL`); documented step-up `qwen3:14b` for the weekly job if the user accepts ~2× runtime. Worker checks `GET /api/tags` at startup and pulls the model if missing.

**Budget (`budget.py`).** Every cloud call logs `{ts, kind, input_tokens, output_tokens, cache_read, cost_usd}` to `data/advisor/usage.jsonl`; `spent_this_month()` gates inline calls against `ADVISOR_MONTHLY_BUDGET_USD` (default 5.0). Admin page shows the meter.

## 8. Configuration (new `config.FIELDS`, section "AI Advisor")

| Key | Type | Default | Notes |
|---|---|---|---|
| `ADVISOR_ENABLED` | checkbox | false | master switch (producers + consumer) |
| `ANTHROPIC_API_KEY` | password | "" | sensitive |
| `ADVISOR_CLOUD_MODEL` | select | `claude-haiku-4-5` | options: haiku / sonnet (`claude-sonnet-5`) for users who later want smarter reviews |
| `ADVISOR_MONTHLY_BUDGET_USD` | float | 5.0 | hard cap on cloud spend |
| `ADVISOR_PLAN_REVIEW_ENABLED` | checkbox | false | per-alert reviewer |
| `ADVISOR_WORKER_TOKEN` | password | "" | HTTPS fallback auth; empty disables the endpoints |

Worker-side config lives in `llm_worker/worker.env` (not in the server's FIELDS): `SSH_HOST/SSH_USER/SSH_KEY_PATH/REMOTE_DATA_DIR`, `HTTP_FALLBACK_URL`, `ADVISOR_WORKER_TOKEN`, `OLLAMA_MODEL=qwen3:8b`, `POLL_SECONDS=120`, `MAX_JOB_MINUTES=45`.

## 9. Hardware tiers & the future-machine playbook

| Tier | Hardware | Model class | What changes |
|---|---|---|---|
| **Now** | i7-1255U, 32GB, CPU-only | Qwen3 8B Q4 (14B for weekly) | Batch-only, laptop-when-open, this spec |
| **Next** | Any desktop w/ 16GB-VRAM GPU (e.g. RTX 4060 Ti 16GB) | 14B fast / 32B Q4 usable | Worker moves to it, runs 24/7; nightly report ready at market open; `!ask` can go local-first |
| **Strong** | 24GB+ VRAM (RTX 4090/5090) | 32B-class comfortably; 70B Q4 marginal | Add: local embeddings (`nomic-embed-text` via Ollama) + a small vector index over the full journal → real RAG for `!ask`; optional **QLoRA fine-tune** of an 8B model on the journal (teach it the house vocabulary and failure taxonomy) — a weekend project, not a research program |

Explicit expectation-setting for the plan's docs: **nobody trains an LLM from scratch** (that is a multi-million-dollar exercise); "building the stronger LLM" means bigger open-weights base models + your own data via retrieval and light fine-tuning. The architecture above is deliberately tier-portable: the worker is a folder + an env file; moving it to a stronger machine is `git clone`, install Ollama, copy `worker.env`.

## 10. External services worth adding (and not)

- **Finnhub free tier** (news + earnings calendar, 60 req/min): feed days-to-earnings and headline sentiment into the plan-review payload and as a quality-score context line. Config `FINNHUB_API_KEY` (optional; absent = feature silently off).
- **Economic calendar** (CPI/FOMC/NFP dates — Finnhub covers this too): flag plans whose entry window straddles a macro event; the reviewer cites it as a risk.
- **Deliberately excluded:** paid signal/sentiment subscriptions, social-sentiment feeds, and anything marketed with win-rate promises — they add correlated noise on top of an edge you've actually validated, and none survive the same out-of-sample bar your own strategies are held to.

## 11. Error handling

- Advisor failures never block or degrade core bot behavior: every producer/consumer call is wrapped, logged to the bot log with an `advisor:` prefix, and dropped.
- Worker: per-job try/except → `failed` status with the traceback string; connectivity loss mid-job → lease expiry handles it; Ollama OOM/timeout (> `MAX_JOB_MINUTES`) → fail with a hint to reduce model size.
- Schema-invalid LLM output: one retry with the validator error included in the prompt, then fail. The consumer re-validates before posting anything.
- Cloud: SDK typed-exception chain; 429 → single backoff retry; budget exceeded → queue-for-local; missing API key with cloud features on → one warning at startup, features off.

## 12. Testing & verification

- **Unit:** queue lease/expiry/recovery over tmp dirs; schema validation for all four kinds (valid + invalid fixtures); budget ledger math and cap gating; transports against a local directory (SFTP mocked via the `Transport` interface); prompt assembly (payload → prompt string) golden tests; consumer dispatch with fake results.
- **Provider fakes:** `FakeProvider` returning canned schema-valid/invalid outputs powers all bot-side tests; no network in the test suite.
- **Eval script (`scripts/eval_advisor.py`):** runs fixture snapshots/journals through a real provider (Ollama or cloud, flag-selected), asserts schema validity and prints outputs for human review — the "did the prompt regress" check after any prompt edit.
- **Live smoke (documented per phase):** hello-world Ollama call on the laptop; one real Haiku plan review in a test channel; one full nightly cycle (produce job → worker → Discord post).

## 13. Risks

- **Laptop absence:** nightly/weekly jobs simply wait (queue is durable). Mitigation: admin page shows queue age; operator can force-to-cloud via Batches.
- **8B model quality:** small models can produce shallow or subtly wrong analysis. Mitigations: schemas force evidence fields; consumer re-validation; the nightly report is labelled as AI-generated advice; tuning ideas are worthless until TRAIN-verified by construction.
- **Prompt-injection via data:** journal notes are user-authored; ticker names are external. Payloads are serialized as fenced JSON data blocks with an explicit "data, not instructions" frame; the advisor has no tools and no write access — worst case is a bad paragraph, never a bad action.
- **Cost runaway:** hard budget cap in code + per-call logging; plan review is off by default.
- **Windows worker quirks (paramiko/Ollama on Windows):** both are well-supported; the plan includes a smoke-test step before any queue code.
