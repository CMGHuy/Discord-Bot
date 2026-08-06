# Manual Verification Checklist

Every plan under `docs/superpowers/plans/` has steps that can't be run unattended: live Discord smoke tests, one-shot pre-registered backtests, real API keys, or a human eyeballing a chart. This doc collects all of them across every plan (audited 2026-07-27) and tells you exactly how to run each one.

**Organized by urgency, not by plan**, because most of this backlog isn't actionable yet:
- **A — Do now or soon**: the active plan, `edge-engine-v4`. Its manual steps are the ones you'll actually hit next.
- **B — Blocked on future implementation**: `llm-advisor-v5` and `admin-ui-tradingview-redesign-v8` haven't been built (0 code, no branch, no commits for either — grep/git-log audit 2026-07-27, llm-advisor re-confirmed 2026-07-31). Their manual steps reference scripts that don't exist yet. `gatekeeper-v7` was in this bucket, then was built to 86/90, then had its code **deleted** on 2026-08-06 — its steps are now unrunnable rather than pending; see the ⛔ note in its section below.
- **C — Already done**: `strategy-winrate-redesign` and the bulk of `unified-plan-engine-v2`'s manual steps were already executed to get those plans to "Completed" status. Listed for the record, not as outstanding work.
- **D — Known gaps carried forward**: `unified-plan-engine-v2`'s staged-rollout smoke and `cockpit-v3`'s live-mutation smoke were *skipped by explicit decision*, not completed. These are now tracked as `gatekeeper-v7` Tasks G217/G218 (see the plan reorg below) rather than being re-run ad hoc here.

---

## A. Do now / soon — edge-engine-v4 (active plan)

### Task E56 — Killswitch + risk-page live smoke (currently deferred)
**Why manual:** touches `.env` and a live Discord channel; needs a human watching Discord render in real time.
**How:**
1. Point a test bot token/guild at a dev `.env` (separate from prod).
2. `python bot.py` against that dev config.
3. Open a paper position so `!portfolio` has something to show.
4. In the test channel run: `!portfolio` (verify it lists the open position), `!killswitch status` (verify current state), `!killswitch on` (verify the pause label appears on the next scan/alert), `!killswitch off` (verify it clears).
5. Open the admin UI's `/risk` page in a browser against the same dev DB, confirm the kill-switch toggle reflects what you just set via Discord.
**Record result:** update `.superpowers/sdd/2026-07-11-edge-engine-v4/DEFERRED-MANUAL-VERIFICATION.md` — check off the E56 item with a dated note.

### Task E67 — Plan-engine flag side-by-side smoke
**How:** flip the relevant feature flag in the dev `.env`, trigger one scan cycle in the test channel, then flip it back and trigger another — compare the two alerts by eye for the fields the flag is supposed to change.
**Record result:** note in the E67 section of `.superpowers/sdd/2026-07-11-edge-engine-v4/progress.md`.

### Task E75 — Chart visual QA
**How:**
1. Render the full chart set against real (not synthetic) OHLCV data.
2. Post/open each chart at actual Discord embed size and eyeball for label collisions, overlapping annotations, unreadable shading.
3. Fix anything that fails the eyeball, re-render, recheck.
**Record result:** progress ledger note; no separate doc required.

### Task E76 — Phase E4 checkpoint
**How:** smoke every chart surface (all chart-producing commands) in the test channel in one pass; archive the screenshots into a dated folder under `docs/superpowers/results/` or similar for the record.

### Task E77 — Production universe flip + watch week
**How:**
1. Set `SCAN_UNIVERSE=sp500_top150` in production `.env`.
2. Restart the bot (`make restart` or equivalent).
3. For **7 consecutive days**, record in the plan's Progress block: scan duration, alert count, digest length, memory (RSS) — once per day.
**Record result:** the Progress block of the E77 task itself.

### Task E89 — Full-system walk-forward re-run
**How:** `python scripts/wf_run.py --full --portfolio` (writes `data/replay_result.json` and `data/replay_r_sequence.json` by default via `--json`/`--r-sequence-json` — pass explicit paths if you want to keep multiple runs). This is long-running; consider using a `backtest-runner` subagent so the per-symbol output doesn't flood your context.
**Record result:** render the output into an evidence doc under `docs/superpowers/results/`.

### Task E90 — Full-system permutation test (pre-registered stop rule)
**How:** `python scripts/permutation_test.py --n 200` (also accepts `--component-json` if isolating a component).
**Pre-registered rule — do not skip:** if p > 0.05, **stop** — strip components and re-run until the remaining system's edge is distinguishable from luck. No second attempt at the same hypothesis without stripping something first.
**Record result:** results doc, p-value quoted verbatim.

### Task E91 — 9-way sensitivity table
**How:** run the full system at each of the 9 slippage/risk-assumption combinations the task specifies (see the task body in `edge-engine-v4.md` for the exact 3×3 grid); read off at which assumption the edge stops being positive.
**Record result:** table in the results doc.

### Task E92 — The single 2024-2025 shot (pre-registered, run ONCE)
**How:**
1. **Before running anything**, write the pre-registration paragraph (what "pass" means, quoted verbatim from the task).
2. Run the validation-window backtest exactly once.
3. Write the verdict verbatim — no re-runs, no "adjusted" second attempt, regardless of result.
**This is the highest-stakes manual step in the whole audit** — irreversible once run. Don't run it until E89–E91 are done and reviewed.

### Task E93 — 4-week live paper forward-test
**How:**
1. Turn on the shadow/paper-mode flags in production.
2. Once a week for 4 weeks, post a comparison snapshot to the test channel (paper results vs. backtest expectation).
3. After week 4, write a promotion decision doc: promote, extend, or abandon.

### Task E94 — Promotion + rollback
**How:** flip the promoted flags in production `.env` **one scan-cycle apart** (not all at once), watching the E82 scan-health telemetry between each flip for anomalies before proceeding to the next.

### Task E96 — Quarterly re-validation ritual
**How:** `python scripts/quarterly_revalidation.py` (add `--skip-refresh` if the OHLCV cache is already fresh, `--permutation-n 200` to control the permutation-test sample size). **Deliberately human-run, not cron** — run it the first weekend of Jan/Apr/Jul/Oct, read the PASS/DEGRADED verdict yourself, prune anything degraded.

### Task E99 — One full live trading day review
**How:** pick one full trading day once the system's been live a while; review end-to-end — alerts posted, charts rendered correctly, `!portfolio` accurate, scan telemetry clean, zero ERROR-level log lines.

---

## B. Blocked on future implementation

### gatekeeper-v7 — ⛔ UNRUNNABLE, the code was deleted (2026-08-06, `c84924a`)

**Do not attempt anything in this list.** The header below used to read
"0/219 tasks implemented"; that was already stale (the plan was reorganised to
90 tasks and built to 86/90 by 2026-08-02), and it is now moot:
`swingbot/core/gate/**`, `swingbot/core/macro/**`, `scripts/gate_*.py`,
`scripts/backfill_macro.py` and `scripts/build_event_history.py` were removed
from the repo after plan v8 Task V29's rollback trigger fired. Every script,
command and admin route named below is gone. See the ⛔ banner atop
`docs/superpowers/plans/2026-07-14-gatekeeper-v7_0-index.md` for the full
account.

**Two exceptions that are still real work**, because they audit *other* plans
and never needed the gate: **G217** (unified-plan-engine-v2's staged-rollout
smoke) and **G218** (cockpit-v3's live-mutation smoke) — see section D.

Kept below as the record of what these steps *were*:
- **G29** — visit the Fed's published FOMC calendar and paste the second day of each two-day meeting into the script's `FOMC_DECISION_DAYS` list before it will run; then run it once for real and spot-check the JSON output.
- **G40** — `python scripts/macro_smoke.py` (script doesn't exist yet — created by this task) with real `FRED_API_KEY`/`FINNHUB_API_KEY` in `.env`; paste the printed summary into `docs/superpowers/results/2026-07-macro-smoke.md` with a one-paragraph verdict.
- **G44** — Phase G1 checkpoint requires the G40 evidence doc to already be committed.
- **G97/G98** — `python scripts/gate_fold_run.py --all` (script created by G97) on TRAIN; hand-transcribe the census/frontier numbers.
- **G100** — permutation check on the G97 annotated trades; **pre-registered stop rule: if p ≥ 0.05 pooled, stop the phase and write that down** — same discipline as E90 above.
- **G104/G105** — shadow-mode comparison report once live shadow data exists, then a dated sign-off checklist (14+ days shadow, 15+ would-have-blocked decisions, blocked-cohort WR < passed-cohort WR, zero crashes) before enforce mode may ever be turned on.
- **G166** — live Discord smoke: `!macro`, `!calendar`, `!sectors`, `!sentiment`, `!yields`, `!inflation`, `!checklist NVDA`, `!frontier` all render correctly with real data.
- **G175/G192/G195** — eyeball the yields/curve chart panel and the mobile layout at 375px with real data; full visual QA pass at desktop + mobile widths.
- **G215/G216** — the terminal live ritual: real macro smoke, live Discord commands, enabling `MACRO_ENABLED`+`GATE_ENABLED` on a real scan, `!checklist NVDA` full run, dragging threshold sliders live on `/gate` and watching the next scan's tiers shift, a blackout dry-run, confirming zero blocks in inform mode via live telemetry.
- **G217/G218/G219** (new, added by this audit — see plan reorg below).

### llm-advisor-v5 (implementation status unconfirmed — see G219)
- **L1** — install Ollama, `ollama pull qwen3:8b` (~5GB) on the user's actual laptop, run once and note wall-clock/tokens-per-second baseline.
- **L2** — create a real Anthropic API key at the console, make one real (billed) Haiku call, confirm token counts look sane.
- **L31** — once `scripts/eval_advisor.py` exists, run it against real Ollama on the laptop once per prompt edit; read whether outputs look sensible.
- **L32** — six-part live smoke: real cloud call, trigger a real scan and check the 🤖 field renders, `!ask` with a real evidence-cited answer, physically open the laptop and run `run_worker.ps1`, watch it process a queued job and post the result, check the `/advisor` admin page reflects it, verify the `usage.jsonl` budget meter incremented.

### admin-ui-tradingview-redesign-v8 (not started)
- **U20/U21** — render smoke: load the page in a browser once, confirm a PNG is produced, eyeball it.
- **U36** — final manual QA: all 7 pages at desktop + 380px, one interactive chart with levels, one Discord-style PNG regenerated and eyeballed side-by-side with an old one.

---

## C. Already done (historical reference — no action needed)

- **strategy-winrate-redesign Tasks 18–20**: per-strategy TRAIN grids (`tune_strategy.py`) + one `run_backtest_range.py --validation` run — completed, results in `docs/superpowers/results/2026-07-train-tuning.md`.
- **unified-plan-engine-v2 Task 14 §3**: TRAIN-smoke byte-diff check against a committed table — completed.
- **unified-plan-engine-v2 Task 32**: exit-v2 VALIDATION single run (`run_backtest_range.py --validation --exit-model v2 --scale-out`) — completed.
- **unified-plan-engine-v2 Tasks 39/41**: confluence-gate TRAIN grid (`tune_confluence_gates.py`) + VALIDATION single run — completed.
- **unified-plan-engine-v2 Tasks 96–109**: five rescue-strategy TRAIN grid + VALIDATION pairs (RSI, RSI Divergence, MA Ribbon, Elliott Wave, EMA Crossover) — completed.
- **cockpit-v3 Task C45**: mobile responsive audit at 900/640/480px — completed.

---

## D. Known gaps carried forward into gatekeeper-v7 (not to be re-run here)

- **unified-plan-engine-v2 Tasks 85, 88, 89 §3–4, 90, 91, 94** (staged-rollout live verification) — skipped by explicit user decision 2026-07-18 in favor of deploying straight to production. → tracked as **gatekeeper-v7 Task G217**.
- **cockpit-v3 Tasks B38 §2, C46 §2** (live-mutation admin-UI smoke) — deliberately skipped per their own Progress blocks. → tracked as **gatekeeper-v7 Task G218**.

See "Deliverable 2" of this session's work for the new G217–G219 tasks themselves.
