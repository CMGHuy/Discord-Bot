# v113 Bearish-day coverage: a 1w horizon, a downtrend overbought fade, and inverse-ETF longs — Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-28-v113-bearish-day-coverage-design.md`
**Bump:** none until Phase C wiring; `bot minor` only if a cell ships (V113-18, V113-24 or V113-25)
**Edge:** volume

**Goal:** Add a masked-by-default `1w` horizon with its own reward floor, a `cells` mask key, the short-only Downtrend Overbought Fade (Part A), and measure A, every legacy strategy × direction on `1w` (Part B) and the live bullish masks on SH/PSQ/RWM/DOG (Part D) through TRAIN → folds → one 2026 holdout shot, shipping only what passes — and, if the fade passes, give it live parity (earnings context, limit entry, whole-position target, enforced time stop) before unmasking it.

**Architecture:**
- `strategy_types.py` gains `HORIZONS["1w"]` (first key), `MASKED_BY_DEFAULT_HORIZONS`, `LEGACY_HORIZONS` (the ten pre-v113 keys), `admits(strategy, direction, horizon)` (the single mask rule, honouring the new `cells` key) and `live_horizons()` (legacy plus any masked horizon a `cells` pair admits). `entry_filters.entries_for` delegates to `admits`. Every loop that used to iterate `HORIZONS` now iterates `LEGACY_HORIZONS` (confluence scan, replays, scripts) or `live_horizons()` (strategy vocabulary: commands, admin, strategy pass), enforced by an AST guard test.
- A new `planning/reward_floor.py` holds the per-horizon strategy-plan reward floor (only `1w` has one) and counts drops, shared by `build_strategy_plan` and `backtest._trade_plan_at`.
- A new `limit` entry type in `planning/exit_sim.py` (fill on bar t+1 only if it trades through the limit; fill-bar stop checked first) and a per-strategy plan shape (`params.PLAN_SHAPES`, `builders.plan_shape_for`) used by both the live builder and the backtest.
- Pattern A lives in `market/short_entries.py` (signal) and `planning/short_builders.py` (fixed 2% stop, `m`×R target), registered like the v104 shorts and masked.
- Measurement is one new script, `scripts/backtest/measure_v113.py`, built on `funnel.py` and `measure_v104.py`'s helpers.
- Conditional on a fade pass (V113-20 … V113-24): live strategy frames attach `evt_*` columns from the live earnings calendar; `PlanManager` gains a `limit` pending step (next session only, else expires), a whole-position ACTIVE step for `tp1_fraction 1.0`, and an enforced time stop for the new plan field `time_stop_bars` — each reached only by plans that declare it, pinned by a pre-change `PlanManager` golden.

**Tech Stack:** Python 3.11+, pandas, numpy, pytest; Angular only in V113-18/V113-24 if a `1w` cell ships.

## Parts

| Part | File | Tasks | Where |
|---|---|---|---|
| 1a — Horizon, mask, vocabulary | `2026-09-28-v113-bearish-day-coverage_1a-horizon.md` | V113-1 … V113-4 | worktree branch |
| 1b — Floor, limit entry, the fade | `2026-09-28-v113-bearish-day-coverage_1b-fade.md` | V113-5 … V113-9 | same branch |
| 1c — Measurement script | `2026-09-28-v113-bearish-day-coverage_1c-measure-script.md` | V113-10 … V113-11 | same branch, then merge |
| 2 — Data and measurement | `2026-09-28-v113-bearish-day-coverage_2-measurement.md` | V113-12 … V113-17 | `main` |
| 3 — Ship decisions, fade live parity, close-out | `2026-09-28-v113-bearish-day-coverage_3-ship.md` | V113-18 … V113-27 | wiring branch, then `main` |

`grep -n "^### Task" docs/superpowers/plans/2026-09-28-v113-*` lists every task.

## Global Constraints

- **`1w` values (spec §1), verbatim, never grid-searched:** `label "3-7 day swing"`, `ema_fast 5`, `ema_slow 8`, `vwap_window 5`, `fib_lookback 10`, `sr_lookback 5`, `atr_stop_multiple 1.5`, `max_risk_pct 2.0`, `sr_stop_pct 2.0`, `sr_target_min_pct 2.0`, `sr_target_max_pct 5.0`, `max_holding_days 7`, `rs_window 10`. Plus `min_reward_pct 2.0` (the reward floor, see amendment 1). `MIN_BARS["1w"] = 20` (amendment 4).
- **Masked by default.** `1w` is admitted for no strategy until a `STRATEGY_GATES[<name>]["cells"]` pair names it; the confluence scan never runs it. With no `cells` anywhere, every existing horizon's entries, plans and exits are byte-identical to pre-v113 — pinned by V113-1's golden, which is generated **before any other v113 change** and must stay green after every task.
- **`cells` (spec §2):** optional set of `(direction, horizon)` pairs; a pair is admitted if the legacy `directions`/`horizons`/`horizons_by_direction` axes admit it **or** it is in `cells`. `strategy_types.admits` is the rule; `entry_filters.entries_for` is its single signal-path reader.
- **Part A (spec §3):** short-only, `1w` only. Signal at the close of bar *t* from bars ≤ *t*: `close_t < SMA200_t`, `SMA200_t < SMA200_{t-20}`, `RSI(2)_t ≥ 90`, and no earnings reaction within the next 7 bars (`0 ≤ evt_bars_to_next ≤ 7` blocks). Plan: sell limit at `close_t`, good for one bar; stop `entry × 1.02`; target `entry − m × (stop − entry)`, grid `m ∈ {1.0, 1.25, 1.5}`; time stop at the close of the 7th bar after entry (`max_holding_days 7`); v104 fail-closed dollar-risk sizing (`SHORT_STRATEGIES` ⇒ always in scope).
- **Fill model (spec §3, amendment 3):** the limit fills only on bar *t+1*, only if its high ≥ the limit, at `max(open, limit)`. On that fill bar: if the fill is at or above the stop → scratch, 0R; else if the high reaches the stop → loss, −1R. One target for the whole position (`tp1_fraction 1.0`), no break-even move.
- **Part B (spec §4):** the 11 `backtest.ALL_STRATEGIES` × {bullish, bearish} = 22 cells on `1w`, each strategy's own builder, no grid. Bar: every Tier 1 clause **and** the bootstrap lower bound > 0 ("Tier 1 only"); Stage 2 fixed folds. Reported per cell: cap-bind rate and floor-drop rate.
- **Part D (spec §5):** SH, PSQ, RWM, DOG only; every `(strategy, horizon)` the live masks admit **bullish** today (`measure_v113.d_cells()`), unchanged; one pooled cell, standard tiers (Tier 1 or Tier 2). Per-strategy and per-ticker breakdowns are reported, never used to select.
- **Windows:** `TRAIN = 2010-01-01..2025-12-31`; folds anchored test years `2013..2025` (13); `HOLDOUT = 2026-01-01..2026-09-25` (`HOLDOUT_END` fixed by the spec, committed in V113-10). One holdout shot per cell, ever.
- **Thin-holdout rule:** at holdout N < 15 write N only (`status: "sealed-thin"`); the shot is unspent and may run once more only when `HOLDOUT_END ≥ 2026-12-31`.
- **Tiers:** Tier 1 = WR ≥ 50, ExpR > 0, decided N ≥ 30 on TRAIN (≥ 15 on the holdout), scratch+timeout share ≤ 50%. Tier 2 = ExpR > 0 and ticker-cluster bootstrap lower bound on ExpR > 0 (`BOOTSTRAP_RESAMPLES = 10_000`, seed 42, 2.5th percentile), same N and scratch floors, no WR floor.
- **Pre-registration** (`docs/superpowers/results/2026-09-28-v113-preregistration.md`) is its **own commit before any TRAIN number exists** (V113-13).
- **The shared cache `data/backtest_cache/` is never written.** Every v113 measurement runs with `BACKTEST_CACHE_DIR=data/backtest_cache_ext`.
- **NO-LOOKAHEAD:** load the `no-lookahead` skill before V113-6, V113-7, V113-21 and V113-22. Every new per-bar series gets a truncation test (`frame.iloc[:k+1]` equals the full result at k, with k < len − 1). The documented exception is `evt_bars_to_next` (scheduled report dates are known in advance; v104 spec §3.4).
- **Complexity:** every function written or changed ends with radon CC < 15 (`python -m radon cc -s -n C <file>`). Legacy functions ≥ 15 never get worse: `run_backtest` (59) gets no new branch (V113-6 removes one), `_scale_out_exit_walk` (30) and `_single_leg_exit_walk` (16) are not edited, `_sync_run_scan` (108) changes only expressions; `PlanManager.poll` (21), `_step_active` (21), `_step_partial` (19) and `_on_event` (15) are not edited — V113-22/23 route new behaviour through `_step` into new methods.
- **Tests:** iterate with `python scripts/dev/testrun.py file <path>`. Run `... fast` once at the end of Part 1c (V113-11). The full suite runs once, in V113-27. **Green means `0 failed` and `0 xfailed`.** Never add an `xfail`.
- **Worktree hygiene:** no `cd` in any command; stage files by explicit path, never `git add -A`; in the worktree never run a command containing the substring `eval` (the measurement `evaluate` subcommand runs only on `main`, Phase B).
- **Commit trailer:** end every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Spec amendments made with this plan (review before execution)

1. **§1 reward floor — premise corrected.** `config.MIN_REWARD_PCT` (default 3.0, not 5.0) gates only confluence scenarios (`scanning/analyze.py`, `backtest_scenarios.py`, `armed_replay.py`); strategy-source plans have no reward floor today. So "every other horizon keeps exactly today's value" means *no* strategy-plan floor on the ten legacy horizons, and the `1w` floor is a new `HORIZONS["1w"]["min_reward_pct"] = 2.0` read by `planning/reward_floor.py` from both `build_strategy_plan` and `backtest._trade_plan_at`. That floor is what Part B's floor-drop rate reports. The confluence path is untouched and never runs `1w`.
2. **§7 shipping Part A — partner decision 2026-09-28.** Live execution cannot match the measured backtest today: live strategy frames carry no `evt_*` columns, and `PlanManager` has no `limit` fill, no whole-position TP1 close and no enforced time-stop exit (only the advice-only recycle notice). So a fade pass ships **with** live parity, in Phase C: V113-19 gates on the holdout; V113-20 writes a pre-change `PlanManager` golden for existing plans; V113-21 attaches live earnings context; V113-22 adds the limit entry (next session only, first regular-hours print through the limit fills at that print, else at the limit; expires unfilled); V113-23 adds the whole-position target (`tp1_fraction 1.0`, no break-even, no PARTIAL) and an enforced time stop (new plan field `time_stop_bars`, closing from 15:45 ET on the 7th session after the fill); V113-24 adds the resting-order alert line and unmasks the fade on `(bearish, 1w)`. Each behaviour is reached only by plans that declare its field. If the fade does not pass, V113-20 … V113-24 are recorded as skipped.
3. **§3 fill-bar rule.** The spec fixes the fill (bar *t+1* high ≥ limit, at the limit or the open). It is silent on the stop being reached on that same bar. Plan: stop first (the repo's standing same-bar rule) — a stop touch after the fill is −1R; a fill at/above the stop (gap through) exits flat, 0R, as a scratch. No break-even move and a single whole-position target, since resting orders are never edited.
4. **§1 horizon tables the spec does not list.** `MIN_BARS["1w"] = 20` (the 2w floor already covers every 1w lookback ≤ 10 and the 20-bar volume mean). Per-strategy tables with no `1w` row keep their existing code fallbacks, unedited: MACD `(12, 26, 9)` (the `.get` default — the 4w periods, not 2w's `(8, 17, 9)`), MA Ribbon `(10, 20, 50)`, Break & Retest recent 10 / retest 1.0%, VWAP `hold_bars_other` 2, HTF EMA none. Recorded in the pre-registration.
5. **§5 universe manifest.** A new `data/universe/inverse_etfs.json` (tagged `"inverse": true`); `etfs.json` is read by live code and is not touched. Part D writes **no registry row** (it pools many strategies on four tickers; the registry is keyed by strategy). At D ship, the confluence scan and bearish strategy signals on the four tickers are unmeasured populations: V113-25 asks the partner, recommending "measured population only".
6. **Going live** stays behind soak: `STRATEGY_ALERTS_MODE` and `STRATEGY_ALERTS_LIVE_STRATEGIES` are never changed by this plan (v104 V104-19 precedent).

## Review Focus

1. **Byte identity of the ten legacy horizons** — V113-1's golden must be generated on the untouched branch head and pass after every later task.
2. **Nothing iterates `HORIZONS`** outside the three allow-listed lines (V113-3/V113-4 guard tests). A missed loop silently scans or measures `1w`.
3. **Fill model** — `exit_sim._limit_entry_exit` reads bar *t+1* only, fills at `max(open, limit)` for a sell, and never considers bar *t+2* (`expiry_bars 1`). Pinned in V113-6.
4. **`admits` equals the pre-v113 rule** on every legacy (strategy, direction, horizon), pinned in V113-2 against a copy of the deleted nested function.
5. **Holdout one-shot** — `measure_v113.check_shot_allowed` refuses a spent shot under any date and allows exactly one thin retry at `HOLDOUT_END ≥ 2026-12-31` (V113-11).
6. **Existing live plans unchanged** — V113-20's `PlanManager` golden (written before V113-22) stays green through V113-24; the recycle notice is untouched (V113-23 pins it).

## Parallelisation

- **Part 1a:**
  - V113-1 first, alone: its golden must be written before any code changes.
  - V113-2 next: it introduces `LEGACY_HORIZONS`, `admits`, `live_horizons` and `tests/horizon_iteration.py`, which V113-3/4/5/7/10 consume.
  - Then **Group 1 (parallel): V113-3, V113-4, V113-9** — V113-3 edits `swingbot/` vocabulary files only; V113-4 edits `scripts/backtest|dev|data|reports/*.py` (except `fetch_backtest_data.py`) and four test files; V113-9 edits `scripts/data/fetch_backtest_data.py` and creates one test. Disjoint files, each consumes only V113-2.
- **Part 1b:**
  - **Group 2 (parallel): V113-5 (after V113-3), V113-7 (after V113-4).** V113-5 touches `planning/reward_floor.py` (new), `planning/builders.py`, `backtesting/backtest.py`; V113-7 touches `market/short_entries.py`, `market/strategy_types.py`, `scripts/backtest/measure_v104.py`. Sequential edges: V113-5 after V113-3 (both edit `backtest.py`); V113-7 after V113-4 (both edit `measure_v104.py`).
  - V113-6 after V113-5 (both edit `builders.py` and `backtest.py`).
  - V113-8 after V113-6 and V113-7 (it adds the fade's `PLAN_SHAPES` row that V113-6 creates, and plans the fade V113-7 defines).
- **Part 1c:** V113-10 after V113-5, V113-8 and V113-9 (it reads `reward_floor` counters and the fade, and the D data path); V113-11 after V113-10 (same file). Then merge to `main`.
- **Part 2** is a strict chain on `main`: V113-12 → V113-13 (the pre-registration commit) → V113-14/15/16 → V113-17. V113-14, V113-15 and V113-16 are independent processes writing disjoint result files, so their `backtest-runner` dispatches may run concurrently (V113-15 is itself up to 4 concurrent strategy chunks); each commits only its own files.
- **Part 3** (one wiring branch; one `testrun.py fast` and one merge in V113-25 Step 7):
  - V113-18 (B wiring) and V113-19 (the fade gate) first; each is a no-op unless its holdout passed.
  - V113-20 before V113-22 and V113-23: its golden must be written before `plan_manager.py` changes.
  - **Group 3 (parallel, after V113-20): V113-21 and V113-22** — `strategy_pass.py`/`short_entries.py` vs `plan_manager.py`; no shared symbol.
  - V113-23 after V113-22 (both edit `plan_manager.py`; it reuses `sessions_since`). V113-24 after V113-21 and V113-23 (it unmasks what they make runnable) and after V113-18 (both edit `STRATEGY_GATES`, `validation_registry.json` and `test_v113_shipped.py`).
  - V113-25 (D wiring) after V113-24 (both edit `alert_embeds.py`) and V113-21 (both edit `strategy_pass.py`).
  - V113-26 after all of them (it records their outcomes); V113-27 last.
- **Cross-plan:** live plans v105–v111 touch `scan_run.py`, `strategy_pass.py`, `alert_embeds.py` and `builders.py`. Before merging the Phase 1 branch or the Phase C wiring branch, run `git log --oneline main -- <each file this branch edits>` and rebase over anything new (`worktree-lifecycle`). v67 (JSON→Postgres): the only store touched is the watchlist, and only through `watchlist.add_ticker` (V113-27) — no schema change. `TradePlanV2.time_stop_bars` (V113-23) lives in the plans table's JSONB `doc`, so it needs no migration; check v67's plans-store task for a field list and add it there if one exists.
