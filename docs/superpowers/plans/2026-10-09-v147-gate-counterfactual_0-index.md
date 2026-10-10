# v147 Gate counterfactual: Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part whole**: pull one task with `/task-brief V147-4` or `grep -n "^### Task V147-4:" -A 400 docs/superpowers/plans/2026-10-09-v147-gate-counterfactual_*.md`.

**Bump:** bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v147-gate-counterfactual-design.md`](../specs/2026-10-09-v147-gate-counterfactual-design.md)

**Goal:** Record what every candidate thrown away by the RS gate, the plan-rejection gate (`no_qualifying_target`, `risk_cap`) and the compression/earnings gate would have done, on TRAIN (compression, plan-rejected) and live (all three), and report a pre-registered EARNS / COSTS / INCONCLUSIVE / WAITING verdict per gate and population. No gate, threshold or default changes.

**Architecture:** One pure simulator, `simulate_blocked(candidate, bars)` in `swingbot/core/backtesting/gate_counterfactual.py`, walks a blocked candidate through the same `exit_sim.simulate_exit(..., scale_out=True)` call the replays use. TRAIN rows come from two record-only hooks: the confluence scenario replay (`backtest_scenarios.py`, driven by `run_backtest_range.py --scenarios --record-blocked`) records `no_qualifying_target` blocks and a record-only shadow of the plan-time 2% cap; `StrategyEngine` (driven by `measure_arms.py --record-blocked`) records compression rejects where the gate actually runs. Live rows go to a new append-only Postgres table `gate_rejections` through a fail-open `record_rejection(...)` helper called once at each live block point, and a nightly `tasks.loop` resolves expired `pending` rows off the event loop from the live `market_data/` cache. The report (`swingbot/core/analytics/gate_counterfactual_report.py`) collapses distinct setups, computes the week-cluster bootstrap difference blocked − taken, BH across five cells, freezes the verdict of record, and persists `data/reports/gate-counterfactual.json` through a light loader in `swingbot/core/infra/gate_counterfactual_store.py` (no pandas/numpy import) that v150 imports.

**Tech Stack:** Python 3.11, pandas/numpy, SQLAlchemy + Alembic (PostgreSQL), discord.py `tasks.loop`, pytest.

## Global Constraints

- **Measurement only.** No gate decision, threshold, default or `.env` value changes. Every hook records and returns; the gate's own control flow is untouched. A test per hook proves the scan / replay result is identical with the recorder failing or absent.
- **RS is live-only.** No TRAIN RS row is ever written (v34 closed). No new RS threshold anywhere. Do not grep-sweep the closed RS / earnings / dry-up knob names (a PreToolUse hook blocks it); read the RS margin through `rs_gate.rs_margin` (created by V147-9).
- **TRAIN window only:** 2020-01-01..2023-12-31. Both `--record-blocked` entry points refuse `--validation`, any `--from` before 2020-01-01 and any `--to` after 2023-12-31, through `blocked_recorder.require_train_window` (V147-4). TRAIN bars come from the backtest cache (`load_cached` / `backtest_cache`), never the live store.
- **TRAIN compression verdicts are labelled in-sample** (`in_sample: true` on every TRAIN compression row and cell).
- **`risk_cap` TRAIN rows are a record-only shadow** of `analyze.attach_plan_v2`'s plan-time check (`planned_loss_pct(plan.trigger_price, plan.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT + 1e-9`). The replay's own trades, stats and printed table never change. Every `risk_cap` row, TRAIN and live, carries `over_cap: true` in the report and is never presented as tradable. It is unrelated to `exit_sim`'s fill-time `_not_triggered("risk_cap")` cancel; never conflate them.
- **One population rule:** `no-fill` (ExitResult `outcome == "not_triggered"`, whose `r_total` is a placeholder 0.0) and `no-plan` / `no-data` rows never enter an ExpR or win-rate denominator, in either arm. `outcome == "no_trade"` (risk_per_share <= 0) maps to `no-plan` (no valid plan exists).
- **No lookahead.** Plan levels, `level_map`, `quality_inputs` and scan params come from `bars.iloc[:signal_index + 1]`; the outcome reads bars strictly after. Data-driven-stops overrides (`stop_mult`, `tp2_r`, `time_stop_days`) are pinned from the row's stored scan params, never resolved from the live journal at resolution time.
- **Signal bar is an exact date match** on the tz-naive date; bars after `last_session` are dropped first; no match gives `no-data`. Price basis: stored `signal_close` vs cache close drifting more than 0.5% re-anchors every price level by the ratio and sets `reanchored = true`.
- **Live writes are fail-open.** `record_rejection` catches `Exception` around snapshot building *and* the insert, logs one warning, returns `False`, and never raises (`write_failure.is_store_write_failure` would otherwise halt issuance). It is called only from serial code (strategy pass loop, `_sync_run_scan` merge loop, `short_run._qualified_items`), never inside `map_tickers` workers (`_scan_one`) and never inside `qualify.py` (shared with outlook/replay callers). Spot metals (`spot_metals.SPOT_PAIRS`) are skipped.
- **Heat at block time is stored as `null`** (`heat_before`, `heat_cap` keys present, value `None`): heat is computed in `build_decision_context` after a plan exists and is not available at any reject site. The report prints the portfolio-state limitation beside every live verdict. `analyze.py` is not restructured to get heat.
- **Complexity.** Every new/changed function stays < 15 (`python -m radon cc -s -n C <files>`). Into the legacy hot paths (`_sync_run_scan` F(100), `run_backtest_range.main` F(65), `run_scenario_mode` C(19)) add **exactly one helper call per hook and no new branch**. `_scan_one` E(36) and `build_decision_context` D(24) are never touched.
- **Alembic:** the revision `v147_001`'s `down_revision` is whatever `python -m alembic heads` prints at implementation time (today `v144_001`; `v146_001` if v146 merged first). Never hardcode it from this plan; `tests/db/test_migrations.py::test_exactly_one_head` must pass.
- **New table bookkeeping:** `register(...)` in `schema.py`, one `PROMOTION_REASONS` line per promoted column, a `CASES` entry in `tests/db/test_unknown_field_round_trip.py`. **Not** added to `events.TABLE_CHANNELS` (no admin surface reads it; no SSE trigger).
- **Light loader:** `swingbot/core/infra/gate_counterfactual_store.py` imports only stdlib, `swingbot.config` and `swingbot.core.infra.jsonio`; a fresh-interpreter test proves `pandas`, `numpy`, `swingbot.core.backtesting` stay out of `sys.modules`. The analytics report module re-exports its `load_report`.
- **Bootstrap p (partner decision 7):** v146's two-sided +1-corrected formula, `tail = min(#(draws <= 0), #(draws >= 0)) + 1; p = min(1, 2 * tail / (len(draws) + 1))`. At V147-13 time run `git grep -n "2.0 \* tail" -- swingbot`; if v146's copy exists, move it to `swingbot/core/backtesting/instrument/stats.py` as `two_sided_bootstrap_p(draws)` and call it from both; otherwise define `two_sided_bootstrap_p` once in `gate_counterfactual_report.py`. Never two copies.
- **Frozen constants:** `VERDICT_FLOOR = 30` distinct filled setups; `Q_MAX = 0.10`; `BOOTSTRAP_RESAMPLES = 10_000`; `BOOTSTRAP_SEED = 42`; near-miss bands `rs` |margin| <= 5.0, `risk_cap` |margin| <= 0.5, compression none; re-anchor tolerance 0.005; resolver grace 5 sessions.
- Per-task verification is the narrow run (`python scripts/dev/testrun.py file <test>`); one full-suite run as the final task (V147-18). Each task ends with a commit step for the implementer on the plan's worktree branch; the controller reviews.

## Deviations from the spec, found while writing this plan

| Spec says | Plan does | Why |
|---|---|---|
| `down_revision` = `v116_002` | head at implementation time | brief § 0.1; partner decision 1 |
| `load_report()` in `swingbot/core/analytics/gate_counterfactual_report.py` | real loader in `swingbot/core/infra/gate_counterfactual_store.py`, re-exported by the analytics module | `swingbot/core/analytics/__init__` imports pandas/numpy; partner decision 2 |
| `run_backtest_range.py --record-blocked`, one TRAIN run per strategy | `run_backtest_range.py --scenarios --record-blocked` (confluence: `no_qualifying_target` + `risk_cap` shadow) and `measure_arms.py --record-blocked` (StrategyEngine: compression), two TRAIN runs; `run_backtest_range.py --record-blocked` without `--scenarios` exits 2 with a message | compression is refused in `backtest.run_backtest`; the live strategy path has no plan-rejected gate (brief § 0.3, 0.9); partner decision 3 |
| `risk_cap` shadow "on each replayed plan" | only on confluence-scenario plans | the live strategy path never applies the 2% plan-time cap (brief § 0.9), so mirroring live config means confluence only |
| heat from `analyze.py:220-221` | `heat_before`/`heat_cap` stored as `null` | brief § 0.7; partner decision 6 |
| short-lane hook in `qualify.py` | in `short_run._qualified_items` | `qualify_short_item` also serves outlook/replays; partner decision 5 |
| JSONL fields `ticker … win` | adds `population`, `arm` (`blocked`/`taken`), `source`, `entry_date`, `planned_loss_pct`, `dollar_risk`, `expiry_bars`, `in_sample` | the taken arm and the verdict need them; the spec's fields are all present unchanged |
| `no_qualifying_target` rows resolved nightly | inserted with `cf_status = 'no-plan'` and `resolved_at = created_at` | the live constructor already returned `None`; a truncated rebuild is the same call on the same bars |
| fixed-dollar-risk column (formula not given) | `dollar_risk = cf_r * planned_loss_pct / HARD_MAX_PLANNED_LOSS_PCT`: the outcome in units of the 2% dollar cap at the notional a 2%-wide stop would size | the R column assumes 1R sizing; this column shows the money a wider stop risks at cap-sized notional |

## Block-point enumeration (V147-1 verifies from code and records it)

| # | Path | Site | Gate / reason | Covered? |
|---|---|---|---|---|
| L1 | strategy | `strategy_pass._emit_signal` → `_rs_blocked` | `rs` / `rs_blocked` | live |
| L2 | strategy | `strategy_pass._emit_signal` → `_compression_context` reject | `compression` / decide reason (`earnings_*` included) | live |
| L3 | confluence | `scan_run._sync_run_scan` RS block (`config.RS_GATE`) | `rs` / `rs_blocked` | live |
| L4 | confluence | `scan_run._sync_run_scan` `plan_v2_rejected` drop (`PLAN_ENGINE_V2 == "on"` only) | `plan_rejected` / `no_qualifying_target`, `risk_cap` | live |
| L5 | short lane | `qualify_short_item` → `Rejected(stage="rs")`, observed in `short_run._qualified_items` | `rs` / `rs_blocked` | live |
| L6 | short lane | `qualify_short_item` → `Rejected(stage="plan")`, observed in `short_run._qualified_items` | `plan_rejected` / reason | live |
| T1 | TRAIN strategy | `StrategyEngine._candidate_plan` compression reject (decide reasons only; `not_pit_member` is a research universe mask, excluded) | `compression` | TRAIN, in-sample |
| T2 | TRAIN confluence | `backtest_scenarios.replay_scenarios` `plan is None` | `plan_rejected` / `no_qualifying_target` | TRAIN |
| T3 | TRAIN confluence | shadow in `backtest_scenarios._replay_ticker` after `simulate_exit` | `plan_rejected` / `risk_cap` | TRAIN shadow, over-cap |
| O1 | strategy | `_emit_signal` `plan is None` for non-compression strategies | none | out: the constructor found no geometry; not one of the three gates; nothing to simulate (partner decision 8) |
| O2 | strategy | `risk_sizing_ok(plan)` false (`sizing_blocked`) | none | out: v104 configuration fail-closed guard, not a quality gate |
| O3 | all | dedup (`already_emitted`), cooldown | none | out: "already have this trade" |
| O4 | strategy/confluence | pullback dry-up | none | out: inactive since v122 (its scope knob defaults off) |
| O5 | confluence/short | requirement rejects (`short_funnel._REQUIREMENT_STAGE`) | none | out (spec) |
| O6 | confluence | heat cap, correlated-cluster cap, kill switch, `short_run._stamp_risk_flags` | none | out: flagged, never dropped (size 0) |
| O7 | strategy | masked strategies (`_goes_live` false → `stored_only`) | none | out: stored, not rejected |
| O8 | TRAIN strategy | `StrategyEngine` plan None, `_skipped` not_triggered | none | out: O1's twin; fill-time cancels are taken-arm `no-fill` rows |

V147-1 adds any further site it finds (for example a regime or dead-cat-bounce veto) to the out-of-scope list with its reason, or stops and reports if one falls under the three gates and is missing above.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-09-v147-gate-counterfactual_1-simulator.md` | V147-1..V147-4 | block-point enumeration, `simulate_blocked` (walk, signal bar, price basis; truncated plan build), TRAIN row recorder module |
| 2 | `2026-10-09-v147-gate-counterfactual_2-train-and-stores.md` | V147-5..V147-7 | scenario replay + `run_backtest_range.py --record-blocked`, StrategyEngine + `measure_arms.py --record-blocked`, `gate_rejections` table/migration/repository |
| 2b | `2026-10-09-v147-gate-counterfactual_2b-report-store.md` | V147-8 | light report store (split from Part 2 for the 1500-line cap) |
| 3 | `2026-10-09-v147-gate-counterfactual_3-live.md` | V147-9..V147-11 | `record_rejection` helper, live block-point hooks, resolver core |
| 3b | `2026-10-09-v147-gate-counterfactual_3b-resolver-loop.md` | V147-12 | nightly resolver loop (split from Part 3 for the 1500-line cap) |
| 4 | `2026-10-09-v147-gate-counterfactual_4-report-ops.md` | V147-13..V147-14 | verdict statistics, report inputs (carries the part-4 controller decisions and the notes for v150) |
| 4b | `2026-10-09-v147-gate-counterfactual_4b-report-assembly-ops.md` | V147-15..V147-18 | `build_report` + script, progress cron, TRAIN runs + results doc, full suite (split from Part 4 for the 1500-line cap) |

## Task ledger

| Task | Title | Part | Model | Files created / modified | Creates for later tasks |
|---|---|---|---|---|---|
| V147-1 | Enumerate block points from code | 1 | sonnet | C `docs/superpowers/results/2026-10-09-v147-block-points.md` | the verified covered / out-of-scope table (hook list for V147-5, -6, -10) |
| V147-2 | `simulate_blocked` core: signal bar, price basis, walk, status | 1 | opus | C `swingbot/core/backtesting/gate_counterfactual.py`, C `tests/backtesting/test_gate_counterfactual.py` | `BlockedCandidate` (frozen dataclass: `ticker, gate, reason, source, strategy, horizon, direction, signal_date: str, plan: dict \| None = None, scenario: dict \| None = None, scan_params: dict \| None = None, signal_close: float \| None = None, margin: float \| None = None`); `CounterfactualResult` (frozen: `cf_status, cf_r: float \| None, win: bool \| None, exit_index: int \| None, last_bar_date: str \| None, bars_sha256: str \| None, reanchored: bool, plan: dict \| None`); `CF_STATUSES = ("pending","filled","no-fill","no-plan","no-data")`; `simulate_blocked(candidate, bars, *, last_session: str \| None = None) -> CounterfactualResult` (returns `cf_status="pending"` when too few bars follow the signal); `result_from_exit(exit_result) -> tuple[str, float \| None, bool \| None]`; `REANCHOR_TOLERANCE = 0.005`; `bars_sha256(frame) -> str` |
| V147-3 | Truncated plan build, pinned overrides, no-lookahead and replay-parity tests | 1 | opus | M `swingbot/core/backtesting/gate_counterfactual.py`, M `tests/backtesting/test_gate_counterfactual.py` | `build_candidate_plan(candidate, window) -> TradePlanV2 \| None` (strategy → `build_strategy_plan` with pinned `stop_mult/tp2_r/time_stop_days/scan_params`; confluence/short_lane → `build_confluence_plan` from `scenario_from_dict(candidate.scenario)` with `level_map` from the window); `scenario_from_dict(d: dict) -> levels.Scenario`; `scenario_to_dict(sc) -> dict` |
| V147-4 | TRAIN gate-row recorder module | 1 | sonnet | C `swingbot/core/backtesting/blocked_recorder.py`, C `tests/backtesting/test_blocked_recorder.py` | `TRAIN_WINDOW = ("2020-01-01","2023-12-31")`; `require_train_window(date_from, date_to, *, validation=False) -> None` (raises `SystemExit(2)` with a message); `over_cap(plan) -> bool`; `risk_cap_margin(plan) -> float`; `dollar_risk(cf_r, planned_loss) -> float \| None`; `gate_row(*, population, arm, source, ticker, strategy, horizon, direction, signal_date, gate, reason, margin, cf_status, cf_r, win, planned_loss_pct=None, expiry_bars=None, in_sample=False) -> dict` (the shared row shape below); `row_from_exit(exit_result, plan, **row_fields) -> dict`; `write_gate_rows(rows, path) -> int` |
| V147-5 | Confluence replay hooks + `run_backtest_range.py --record-blocked` | 2 | opus | M `swingbot/core/backtesting/backtest_scenarios.py`, M `scripts/backtest/run_backtest_range.py`, C `tests/backtesting/test_scenario_gate_rows.py`, C `tests/scripts/test_range_record_blocked.py` | `replay_scenarios(..., blocked: list \| None = None)`; `run_scenario_backtest(..., record_blocked: bool = False)` adds key `"gate_rows": list[dict]` only when True; `run_scenario_mode(..., record_blocked: str \| None = None)`; CLI `--record-blocked PATH` |
| V147-6 | StrategyEngine compression rows + `measure_arms.py --record-blocked` | 2 | opus | M `swingbot/core/backtesting/arms/strategy_engine.py`, M `swingbot/core/backtesting/arms/compression_research.py`, M `scripts/backtest/measure_arms.py`, C `tests/backtesting/arms/test_strategy_engine_gate_rows.py`, C `tests/scripts/test_measure_arms_record_blocked.py` | `StrategyEngine.__init__(self, strategies=None, compression_context=None, *, blocked_sink: list \| None = None, compression_allowlist: tuple \| None = None)`; `compression_research.record_blocked_compression(frames, window, *, context, horizons=("2w",)) -> list[dict]`; CLI `measure_arms.py --record-blocked PATH [--from --to]` (early dispatch, own parser) |
| V147-7 | `gate_rejections` table, Alembic `v147_001`, repository | 2 | opus | M `swingbot/core/db/schema.py`, C `swingbot/core/db/migrations/versions/v147_001_gate_rejections.py`, C `swingbot/core/db/repositories/gate_rejections.py`, M `tests/db/test_unknown_field_round_trip.py`, C `tests/db/test_gate_rejections_repository.py` | table `gate_rejections` (`id`, `ticker`, `gate`, `strategy`, `horizon`, `signal_date TEXT`, `cf_status TEXT`, `created_at TIMESTAMPTZ NOT NULL`, `resolved_at TIMESTAMPTZ NULL`, standard columns; `UNIQUE(ticker, gate, strategy, horizon, signal_date)` named `gate_rejections_key_uq`; index `gate_rejections_status_idx` on `cf_status`); `GateRejectionRepository(Repository)` key `"id"` with `insert_ignore(record, *, conn=None) -> bool`, `pending(*, limit: int, conn=None) -> list[dict]`, `resolve(row_id, *, cf_status, resolved_at, outcome: dict, conn=None) -> bool` (only `WHERE cf_status='pending'`), `list_since(since: str \| None = None, *, conn=None) -> list[dict]`; `gate_rejections_repo()` lazy singleton |
| V147-8 | Light report store (atomic write, verdict-of-record carry-forward) | 2b | sonnet | C `swingbot/core/infra/gate_counterfactual_store.py`, C `tests/infra/test_gate_counterfactual_store.py` | `report_path() -> Path` (`<config.DATA_DIR>/reports/gate-counterfactual.json`, resolved at call time); `load_report(path=None) -> dict \| None` (None when missing/empty/corrupt/non-object); `write_report(result: dict, path=None) -> dict` (atomic via `jsonio.atomic_write_json`; per cell keyed `(gate, population)`, a complete on-disk `verdict_of_record` `{verdict, date, n}` is carried forward over the new one; input not mutated) |
| V147-9 | Fail-open `record_rejection` helper + snapshot adapters | 3 | opus | C `swingbot/core/scanning/rejection_recorder.py`, M `swingbot/core/edge/rs_gate.py`, C `tests/scanning/test_rejection_recorder.py` | `rs_gate.rs_margin(rs_value: float) -> float`; `record_rejection(*, ticker, gate, reason, source, strategy, horizon, direction, signal_date, frame, margin=None, plan=None, scenario=None, scan_params=None, entry_context=None) -> bool`; `record_strategy_block(deps, frame, *, ticker, strategy, horizon, direction, gate, reason) -> bool`; `record_item_block(item, frames: dict, gate: str, reason: str, *, source: str) -> bool`; `record_short_verdict(verdict, frames: dict) -> bool`; module-level `_repo()` factory (tests monkeypatch) |
| V147-10 | Live hooks at L1–L6 | 3 | opus | M `swingbot/core/scanning/strategy_pass.py`, M `swingbot/core/scanning/scan_run.py`, M `swingbot/core/scanning/short_run.py`, M `swingbot/core/scanning/analyze.py`, C `tests/scanning/test_gate_rejection_hooks.py` | `analyze._reject_plan(item, reason, ticker, horizon_key, *, plan=None, margin=None)` stamps `item.plan_v2_rejected_plan: dict \| None` and `item.plan_v2_rejected_margin: float \| None` |
| V147-11 | Resolver core | 3 | opus | C `swingbot/core/backtesting/gate_resolver.py`, C `tests/backtesting/test_gate_resolver.py` | `RESOLVE_BATCH_CAP = 200`; `GRACE_SESSIONS = 5`; `due_bars(horizon: str, expiry_bars: int \| None) -> int`; `resolve_due(today: str, *, limit: int = RESOLVE_BATCH_CAP, repo=None, load_bars=None) -> dict[str, int]` (counts per resulting `cf_status`; default `load_bars = lambda t: data_store.load_normalized(t, "daily")`) |
| V147-12 | Nightly resolver loop | 3b | sonnet | M `swingbot/commands/scanning/loops.py`, C `tests/commands/test_gate_resolver_loop.py` | `gate_counterfactual_resolve` (`tasks.loop(minutes=1)`, weekdays at `SESSION_END_HOUR:45` Berlin, fire-once via `_scheduled_job_already_fired`/`_mark_scheduled_job_fired`, `asyncio.to_thread(gate_resolver.resolve_due, ...)`), listed in `_always_on_loops()` |
| V147-13 | Verdict statistics | 4 | opus | C `swingbot/core/analytics/gate_counterfactual_report.py`, C `tests/analytics/test_gate_counterfactual_stats.py` (and `swingbot/core/backtesting/instrument/stats.py` only if v146's p formula exists) | `VERDICT_FLOOR`, `Q_MAX`, `BOOTSTRAP_RESAMPLES`, `BOOTSTRAP_SEED`, `NEAR_MISS_BANDS = {"rs": 5.0, "risk_cap": 0.5}`; `CELLS = (("rs","live"),("risk_cap","live"),("compression","live"),("risk_cap","train"),("compression","train"))`; `two_sided_bootstrap_p(draws) -> float`; `distinct_setups(rows) -> list[dict]`; `arm_stats(rows) -> dict` (`n, filled_n, no_plan_n, fill_rate, exp_r, win_rate`); `difference_reading(blocked, taken, *, seed=BOOTSTRAP_SEED) -> dict \| None` (`difference, ci_low, ci_high, p`); `classify(reading, q, n) -> str` (EARNS/COSTS/INCONCLUSIVE/WAITING); `cell_key(row) -> str` (`"rs"`, `"risk_cap"`, `"compression"`, `"no_qualifying_target"`) |
| V147-14 | Report inputs: TRAIN JSONL, live table, live taken re-walk | 4 | opus | C `swingbot/core/analytics/gate_counterfactual_inputs.py`, C `tests/analytics/test_gate_counterfactual_inputs.py` | `load_train_rows(paths) -> list[dict]`; `live_blocked_rows(records) -> list[dict]`; `live_taken_rows(plans, load_bars) -> list[dict]` (stored plan → `simulate_exit(df, i, plan, scale_out=True)`; also carries `realised_r` for context); `load_live(*, since="2026-10-01") -> tuple[list[dict], list[dict]]` |
| V147-15 | `build_report`, cells/rows, persistence, script wrapper | 4b | sonnet | M `swingbot/core/analytics/gate_counterfactual_report.py`, C `scripts/reports/gate_counterfactual_report.py`, C `tests/analytics/test_gate_counterfactual_report.py`, C `tests/scripts/test_gate_counterfactual_report_script.py` | `build_report(*, train_rows=None, live_blocked=None, live_taken=None, today=None, write=True, path=None) -> dict` (v150 shape: `generated_at, live_window, cells[], rows[]`); `_cell(...)`, `_row(...)`; `load_report` re-exported from the infra store |
| V147-16 | Production progress script + weekly cron installer | 4b | sonnet | C `scripts/ops/gate_counterfactual_progress.py`, C `scripts/ops/install_gate_counterfactual_cron.sh`, C `tests/scripts/test_gate_counterfactual_progress.py` | `progress_lines(records) -> list[str]` |
| V147-17 | TRAIN runs and results doc | 4b | sonnet | C `docs/superpowers/results/2026-10-09-v147-gate-counterfactual.md` | none |
| V147-18 | Full suite | 4b | haiku | none | none |

### The shared gate-row shape (TRAIN JSONL and normalised live rows)

```python
{"population": "train" | "live", "arm": "blocked" | "taken", "source": "strategy" | "confluence" | "short_lane",
 "ticker": str, "strategy": str, "horizon": str, "direction": "bullish" | "bearish",
 "signal_date": "YYYY-MM-DD", "entry_date": "YYYY-MM-DD",   # entry_date == signal_date (week_cluster_bootstrap key)
 "gate": "rs" | "plan_rejected" | "compression", "reason": str | None,   # taken rows: reason None
 "margin": float | None, "cf_status": "filled" | "no-fill" | "no-plan" | "no-data",
 "cf_r": float | None, "win": bool | None,                  # None unless filled
 "planned_loss_pct": float | None, "dollar_risk": float | None,   # risk_cap rows only
 "expiry_bars": int | None, "in_sample": bool}
```

Taken rows: TRAIN confluence: every simulated scenario plan that passes the cap is one `taken` row for `gate="plan_rejected"`; TRAIN compression: every compression plan that passes the decision is one `taken` row for `gate="compression"` (its `not_triggered` walk is `no-fill`); live: issued plans re-walked by V147-14, scoped per cell by `(source, direction)` and, for compression, `strategy == COMPRESSION_SHORT`.

### The `gate_rejections` record (flat dict at the repository boundary)

Promoted: `ticker, gate, strategy, horizon, signal_date, cf_status, created_at, resolved_at`. In `doc`: `reason, margin, direction, source, plan (plan_to_dict or None), scenario (scenario_to_dict or None), scan_params, signal_close, entry_context, heat_before (None), heat_cap (None)`, and once resolved `cf_r, win, exit_index, last_bar_date, bars_sha256, reanchored, pending_checks` (the grace counter). `strategy` for a confluence/short-lane row is `primary_strategy_for(scenario)`.

## Parallelisation

- **Sequential first:** V147-1 (hook list for every later hook task). Then V147-2 → V147-3 (same two files).
- **Group A, after V147-3, parallel (disjoint files, no shared symbol):** V147-4, V147-7, V147-8, V147-13.
- **After V147-4, parallel:** V147-5 (`backtest_scenarios.py`, `run_backtest_range.py`) and V147-6 (`arms/strategy_engine.py`, `arms/compression_research.py`, `measure_arms.py`): disjoint files, both only consume V147-4's functions.
- **Sequential after V147-7:** V147-9 (consumes the repository) → V147-10 (consumes `record_*` and edits four scanning files that share the merge path; one task). V147-11 needs V147-3 + V147-7; it may run beside V147-9/-10 (disjoint files). V147-12 needs V147-11 (`resolve_due`).
- **Group B:** V147-14 needs V147-3 + V147-4 + V147-7 (it builds rows with `blocked_recorder.gate_row`; may run beside V147-13: disjoint files). V147-15 needs V147-8, V147-13, V147-14 (edits V147-13's file: a sequential edge). V147-16 needs V147-7, V147-13 and V147-14 (the progress script counts distinct filled setups with `cell_key`/`distinct_setups` over `live_blocked_rows`); disjoint files from V147-15, so it may run beside it.
- **V147-17** needs V147-5, V147-6 and V147-15 (the TRAIN runs need only the recorders and can start, via `backtest-runner`, while Part 3 is built; the results doc needs V147-15). **V147-18** is last.
- At most 2 implementers at once (controller rule).

## Handoff

(none yet)
