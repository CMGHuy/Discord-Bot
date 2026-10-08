# v142 — Partials analytics tab: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part file whole** — pull one task: `grep -rn "^### Task V142-5" -A 400 docs/superpowers/plans/2026-10-08-v142-partials-analytics-tab_*.md`.

**Bump:** ui minor · bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-08-v142-partials-analytics-tab-design.md`](../specs/2026-10-08-v142-partials-analytics-tab-design.md)

**Goal:** A seventh Analytics tab, **Partials**, that shows whether the runner earns its keep (TP1→TP2 conversion, runner-beat-all-out, the four counterfactuals, hold times, breakdowns) from the live book. Plans gain a `runner_path` stamp at runner close, and a one-off backfill stamps closed history from the disk cache.

**Architecture:** One pure helper, `swingbot/core/analytics/runner_path.py:compute_runner_path(plan, bars, *, source)`, turns daily bars into the stamp. `stamp_runner_path` wraps it: it never raises and it logs a miss. `cached_daily_bars` is the only bar source, and it reads the live scan's disk cache only. Three writers use it. `PlanManager._close_runner` covers every automated runner close. `trade_commands._close_plan` covers the manual close of a PARTIAL plan. `scripts/data/backfill_runner_path.py` covers history. `swingbot/core/analytics/partials.py` turns scoped plan records into the report. `GET /api/v1/analytics/partials` serialises it. The SPA gets a `partials` store slice and `tabs/partials.ts`, built only from existing `ui/` primitives.

**Tech Stack:** Python 3.11, pandas/numpy, Flask, pytest (Postgres `db-test`); Angular (signals, `@ngrx/signals`), Vitest via `ng test`.

## Spec resolutions (the code forced a choice; the plan follows the code)

1. **A manual close records no runner leg on the plan.** `trade_commands._close_plan` only records the transition. `TradeLog.close_trade_manual` realises the runner as a leg on the **trade** (`performance.py:_apply_exit_price`). Production on 2026-10-08 held 16 such plans out of 189 closed partials. `partials.build_report(plans, manual_exits=...)` takes `{plan_id: linked trade exit_price}`, and the endpoint builds that map from the trades table (still DB-only). A manual runner whose trade has no price is still a closed runner. It is counted in a new visible `counterfactuals.runner_r_unavailable` figure, beside `path_unavailable`, and never dropped silently.
2. **The live stamp cannot have a finished exit-session bar.** The close happens intraday. The no-network source is the scan's disk cache (`data_store.load_normalized(ticker, "daily")`), and it holds at most a forming bar for today. So "the bars cover the window" means **every NYSE session from the TP1 session up to the day before the exit session**. The exit-session bar is used when present (a forming bar's extremes are real prints). The runner's own fills always count as points: the TP1 leg on its session and the runner leg on the exit session. So a TP2 exit still touches the levels up to TP2. A stop/floor/trail exit session contributes only its fill, as the spec's conservative rule already requires.
3. **What the TP1 session counts.** Only its **favourable** extreme counts. The adverse extreme may predate TP1, so the TP1 session adds the TP1 fill R to MAE and nothing else. Ladder levels at or below the TP1 fill R count as touched on the TP1 session (the fill crossed them). This is consistent with "MFE floored at the TP1 R".
4. **Signature.** `compute_runner_path(plan, bars, *, source="live")` adds the keyword the stamp's `source` field needs. The spec's two positional arguments are unchanged.
5. **Scope on plans.** `BookScope` filters trades. `partials.select_plans` applies the same fields to plans: fill date (ET date of the first `ACTIVE` transition) for `from`/`to`, `plan.ledger`, `plan.strategy`, `plan.horizon_key` and `plan.direction`. The endpoint echoes `n` = filled plans in scope.
6. **The scope bar's `N=… closed` is not fed by this tab.** That label counts closed trades. A filled-plan count would mislabel it, so `scopeN` ignores the Partials payload. The tab shows its own population (funnel header, footer).
7. **An open runner on a plan with no TP2 is `open`, not `no_tp2`.** The spec's edge-case table keeps open runners out of every counterfactual. A close reason the code does not know goes to an `other` bucket. That bucket is only reported when it is non-empty (the `exit_reason_split` lesson), so "each partial trade in exactly one bucket" holds.
8. **Units.** Rates and shares are percentages 0–100, rounded to 1 dp. R is rounded to 4 dp. Leg R and blended R go through `metrics.r_multiple`, which rounds to 2 dp. Hold times are NYSE sessions (`session.nyse_calendar`), where the same session counts as 0.
9. **The TP2 ladder is a bar list** (partner decision, 2026-10-08, replacing a `LineChart` with synthetic dates). `ladderRows` gives one `BarList` row per level: label `TP2 at X.XR`, value = counterfactual ExpR, `n`. The actual setup is a final `Actual` row carrying the actual ExpR on the same signed axis. `BarList` draws its `reference` marker only in `rate` mode and has no secondary-figure column, so it cannot mark the actual setup any other way. The touch rate per level is a second `BarList` (`touchRows`, `rate` mode) under it. V142-8 (`LineChart.xLabel`) is retired; its id stays.
10. **Which cache production holds (checked read-only on 2026-10-08).** `market_data/daily/` has a file for **48 of 48** tickers with a partial plan (ADBE runs 1986-08-13 → 2026-10-08). `data/backtest_cache/` has 7 files and covers 4 of them. The backfill therefore reads `market_data/daily` through `runner_path.cached_daily_bars`, the same reader the live stamp uses, and not `fetch_backtest_data.load_cached` (backtest_cache). V142-0 re-runs the check before anything is built. V142-11 re-runs it before `--apply`.
11. **Breakdown "month"** is the month of the TP1 hit, so it has no TP1-rate denominator: `tp1_rate` is `null` on month rows. A strategy, horizon or side key with filled plans but no partial still shows, with `n = 0`.

## Global Constraints

- Work in the worktree `.claude/worktrees/2026-10-08-v142-partials-analytics-tab` on branch `2026-10-08-v142-partials-analytics-tab`. **Every dispatch names this worktree.** Never edit the main tree (another session has an untracked v140 spec there). Never `cd` in Bash; use paths relative to the worktree root, or `git -C`.
- `runner_path` shape, exactly: `{"mfe_r": float, "mae_r": float, "ladder": {"1.5"|"2.0"|"2.5"|"3.0"|"4.0": "YYYY-MM-DD" | null}, "sessions_after_tp1": int, "source": "live" | "backfill"}`. `LADDER_R = (1.5, 2.0, 2.5, 3.0, 4.0)`.
- R is measured against the plan's **initial** risk `abs(entry_price - stop_loss)`, the `metrics.r_multiple` basis.
- The stamp **never triggers a network fetch and never blocks a close**. Its only bar source is `runner_path.cached_daily_bars` (`data_store.load_normalized(ticker, "daily")`).
- `TradePlanV2.runner_path` rides in `plans.doc` (schema-evolution "add": default `None`, readers never infer it, the backfill writes it). No Alembic revision.
- Buckets: `tp2`, `trail` (`tp1_runner_trail`), `floor` (`tp1_runner_be`), `stall` (`tp1_runner_progress_stall`), `time` (`time_exit`), `manual`, `no_tp2`, `open` (+ `other` only when non-empty). `THIN_N = 10`. `SPLIT_FRACTIONS = (0.33, 0.5, 0.67)`.
- Exits and thresholds are untouched. No exit parameter changes. The page is never a gate, and its footer says "live book only — not a gate".
- Frontend: only existing `frontend/src/app/ui/` components; no new chart library. Media queries use the declared breakpoints only (639/1023/1439/1919 and their +1).
- Every function written or changed ends at cyclomatic complexity **< 15** (`python -m radon cc -s -n C <files>`). Legacy functions ≥ 15 in touched files (`analytics.py`, `plan_manager.py`) are not edited.
- Every `except` that logs uses `exc_info=True` (`tests/infra/test_log_tracebacks.py` enforces it).
- Per-task checks: `python scripts/dev/testrun.py file <test>` and `cd frontend && npx ng test --include <spec>`. **DB tests need `db-test` reachable.** If a DB test reports SKIPPED, start it (`docker compose --profile test up -d db-test`) or point `TEST_DATABASE_URL` at the running container's port (`docker port swing-db-test`). A skipped DB test is not a pass. The full suites run **once**, at V142-10.
- Do not commit plan or spec documents from the worktree. Commit code per task on the branch.

## Review Focus

1. **A manual runner close.** The plan carries only the TP1 leg. Its R must come from the linked trade, or it must be counted unpriced, never dropped. Pinned by `test_a_manual_close_without_a_trade_price_is_counted_not_dropped` (V142-5) and `test_without_the_linked_trade_the_manual_runner_is_counted_unpriced` (V142-6).
2. **An intraday live close with today's bar still forming or absent.** The stamp must still compute from the fills. Pinned by `test_a_still_forming_exit_session_bar_is_optional` (V142-1).
3. **The stamp failing for any reason.** A missing file, an unreadable CSV or an exception must close the plan anyway, with `runner_path: null` and one log line. Pinned by `test_a_failing_bar_source_never_blocks_the_close` and `test_missing_bars_close_the_plan_with_a_null_stamp` (V142-2), `test_a_null_stamp_still_closes` (V142-3) and `test_stamp_never_raises` (V142-1).
4. **Running the backfill twice, or after live stamps exist.** A second run must stamp nothing new and must never overwrite a live stamp. Pinned by `test_apply_twice_stamps_once` (V142-4).
5. **A scope with zero partial trades.** The API answers with zeros and nulls (no 500), and the tab shows the empty state instead of NaN tiles. Pinned by `test_empty_scope_is_all_zeros_and_nones` (V142-5), `test_an_empty_scope_answers_with_zeros` (V142-6) and `shows the empty state when the scope holds no partial trade` (V142-9).

## Parts

| Part | File | Tasks |
|---|---|---|
| 1 | `2026-10-08-v142-partials-analytics-tab_1-contract-stamps.md` | V142-0 .. V142-3 (Phase 0 production check, Phase 1 contract, Phase 2 live + manual stamps) |
| 2 | `2026-10-08-v142-partials-analytics-tab_2-backfill-metrics-api.md` | V142-4 .. V142-6 (Phase 2 continued: backfill, metrics; Phase 3 API) |
| 3 | `2026-10-08-v142-partials-analytics-tab_3-frontend-and-release.md` | V142-7 .. V142-11 (Phase 4 SPA; Phase 5 full suites, merge, production backfill) |

## Parallelisation

Mirrors the spec's groups, per phase.

- **Phase 0 — sequential:** V142-0 creates the worktree and re-checks production's cache. Everything else runs inside that worktree, and the backfill's bar source depends on the answer.
- **Phase 1 — sequential:** V142-1 alone. It introduces `TradePlanV2.runner_path` and the whole `runner_path` module (`compute_runner_path`, `stamp_runner_path`, `cached_daily_bars`, `transition_day`, `session_span`, `tp1_leg`, `runner_leg`, `close_reason`, `LADDER_R`). Every later Python task consumes those symbols. Its test helpers (`_closed`, `LONG_BARS`, `FILL`/`MON`/`WED`) are imported by V142-2 and V142-4.
- **Phase 2 — Group A (parallel, after V142-1):** V142-2, V142-3, V142-4, V142-5. Disjoint files:
  - V142-2: `swingbot/core/planning/plan_manager.py`, `tests/planning/test_plan_manager_runner_path.py`.
  - V142-3: `swingbot/admin/api_v1/trade_commands.py`, `tests/admin/test_trade_commands_runner_path.py`.
  - V142-4: `scripts/data/backfill_runner_path.py`, `tests/scripts/test_backfill_runner_path.py`.
  - V142-5: `swingbot/core/analytics/partials.py`, `tests/analytics/test_partials.py`.
  Each consumes only V142-1's symbols. V142-3 is the manual-close half of the spec's "live stamping". It is split from V142-2 because it is a different file in a different process (admin). That split does not change the group.
- **Phase 3 — sequential:** V142-6 after V142-5. The endpoint serialises `build_report`/`select_plans`, and its test imports V142-5's `_book()`.
- **Phase 4 — sequential:** V142-7, then V142-9. V142-9 consumes `AnalyticsPartials`, `store.partials` and `PARTIALS_FIXTURE` from V142-7. V142-8 is retired (index item 9): no code, nothing to schedule.
- **Phase 5 — sequential:** V142-10 (one full Python run, one full `npm test`) after everything. V142-11 (merge, deploy, production backfill) after V142-10. The backfill `--apply` runs only once the branch is deployed, so the live stamp and the backfill write the same shape.
