# v104 Structural stops with dollar-risk sizing, and three short strategies — Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-25-v104-structural-stops-and-shorts-design.md`
**Bump:** none until Task V104-19; `bot minor` there only if a strategy × direction ships
**Edge:** expectancy

**Goal:** Let chosen strategy × direction pairs keep their structural stop (up to the horizon's `max_risk_pct`) under fixed-dollar-risk sizing, add three short-only strategies (Bull Trap, Vol Expansion Breakdown, Earnings Gap Drift), and measure every candidate on TRAIN 2010–2025 with one shot each on a fresh 2026 holdout.

**Architecture:**
- One new module decides the stop regime: `swingbot/core/planning/stop_scope.py`. Its `stop_ceiling(strategy, direction, horizon)` returns `(pct, "cap"|"drop")`. The builders, the level lifecycle and the live fill check all read it, so backtest and live cannot diverge.
- A config list, `STRUCTURAL_STOP_SCOPE`, defaults to empty (today's behaviour). The three shorts are always in scope.
- The shorts live in their own modules. Signals are in `swingbot/core/market/short_entries.py`, registered into `ENTRY_FUNCS`. Sizing is in `swingbot/core/planning/short_builders.py`. They ship masked.
- Measurement is one new script, `scripts/backtest/measure_v104.py`, on `scripts/backtest/funnel.py`, which is `fib_funnel.py` renamed and generalised.

**Tech Stack:** Python 3.11+, pandas, numpy, pytest.

## Parts

| Part | File | Tasks | Where |
|---|---|---|---|
| 1a — Risk model | `2026-09-25-v104-structural-stops-and-shorts_1a-risk-model.md` | V104-1 … V104-6 | worktree branch |
| 1b — Shorts | `2026-09-25-v104-structural-stops-and-shorts_1b-shorts.md` | V104-7 … V104-11 | same branch |
| 1c — Measurement script | `2026-09-25-v104-structural-stops-and-shorts_1c-measure-script.md` | V104-12 | same branch |
| 2 — Measurement | `2026-09-25-v104-structural-stops-and-shorts_2-measurement.md` | V104-13 … V104-18 | `main`, after merge |
| 3 — Wiring and close-out | `2026-09-25-v104-structural-stops-and-shorts_3-wiring.md` | V104-19 … V104-21 | wiring branch, then `main` |

`grep -n "^### Task" docs/superpowers/plans/2026-09-25-v104-*` lists every task.

## Global Constraints

- **The 2% price cap stays the default.** With `STRUCTURAL_STOP_SCOPE=""`, every strategy path builds the same stop as today. Only Part 0's lifecycle fix changes today's numbers, on purpose. Out-of-scope arithmetic must reuse the existing expressions (`capped_planned_loss_pct`, `entry ∓ entry × pct / 100`) so float results stay identical.
- **In scope = drop, never cap.** A stop beyond the horizon's `max_risk_pct` builds no plan.
- **Real-money invariant (spec §2.4):** an in-scope plan is not stored or posted unless `compute_position_size(entry, stop)` returns a dict with `mode == "risk_pct"` and `0 < risk_amount ≤ balance × risk_pct / 100`.
- **Windows (spec §5.1):** `TRAIN = 2010-01-01..2025-12-31`; folds are anchored test years `2013..2025`; `HOLDOUT = 2026-01-01..HOLDOUT_END`, frozen in V104-15. There is one holdout shot per candidate, ever.
- **Thin-holdout rule (spec §5.4):** at holdout N < 15, write N only (`status: "sealed-thin"`). The shot is unspent. It may run once more only when `HOLDOUT_END ≥ 2026-12-31`.
- **Tiers:** Tier 1 = WR ≥ 50, ExpR > 0, decided N ≥ 30 on TRAIN (≥ 15 on the holdout), scratch+timeout share ≤ 50%. Tier 2 = ExpR > 0, and the ticker-cluster bootstrap lower bound on ExpR > 0 (`BOOTSTRAP_RESAMPLES = 10_000`, seed 42, 2.5th percentile), with the same N and scratch floors and no WR floor.
- **Grids (spec §3):** B1 `k ∈ {1, 2, 3}` (loosest 3); B2 `m ∈ {1.0, 1.2, 1.4}` (loosest 1.0); B3 `g ∈ {0.05, 0.08, 0.12}` (loosest 0.05). B1 and B2 also have an earnings axis `e ∈ {hold, exit_before}`. The plateau is checked along the grid within one `e`.
- **Shorts ship inert:** `STRATEGY_GATES[name] = {"directions": ()}`, not in `backtest.ALL_STRATEGIES`, `STRATEGY_ALERTS_MODE` never changed.
- **NO-LOOKAHEAD:** load the `no-lookahead` skill before V104-7 … V104-11. Every new per-bar series gets a truncation test (`frame.iloc[:k+1]` equals the full result at k). The one documented exception is `evt_bars_to_next`: companies schedule earnings dates in advance, so the next scheduled date is treated as known (spec §3.4, v82 precedent).
- **The shared cache `data/backtest_cache/` is never written.** Every v104 measurement runs with `BACKTEST_CACHE_DIR=data/backtest_cache_ext`.
- **Complexity:** every function written or changed ends with radon CC < 15 (`python -m radon cc -s -n C <file>`). Legacy functions ≥ 15 never get worse: `run_backtest` (59) gets no new branch, and `run_strategy_pass` (20) must end **below 15** after V104-5's extraction.
- **Tests:** iterate with `python scripts/dev/testrun.py file <path>`. Run `... fast` once at the end of Parts 1a and 1b. The full suite runs once, in V104-21.
- **Green means `0 failed` and `0 xfailed`.** Never add an `xfail`.
- **No `cd` in commands.** Stage files by explicit path, never `git add -A`.
- **Commit trailer:** end every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Spec amendments made with this plan (committed together)

1. **§3.4 `exit_before` entry block.** "An entry whose next reaction falls within `max_holding_days`" would block almost every entry on long horizons: reports come about every 63 sessions, and horizons hold up to 270. Amended: block only when the next reaction is ≤ 1 bar away. Otherwise enter, with the hold capped at the bar before the reaction.
2. **§6 registry rows.** The registry is keyed `(source, strategy, horizon)` with no direction. A Part A pass writes that strategy's row only when **every** direction the strategy's live gate admits passed. Otherwise no row is written, and the methodology row records why (the v103 rule). Each short is one direction, so it gets one row.
3. **§3.3 B3 data.** `market_data/earnings/*.csv` (untracked, 73 tickers) already covers 2002–2026. The pre-registration records a sha256 of that directory instead of a coverage caveat.

## Review Focus

1. **Out-of-scope float identity.** `_sr_plan` must still compute `entry * (1 - stop_pct / 100)` with `stop_pct = min(sr_stop_pct, 2.0)`. `test_sizing_parity.py` pins exact values.
2. **A missing context column** (a frame built without `market_context.attach` or `earnings_context.attach`): B2 and B3 return no signals, not an error, while masked. `exit_before` in the backtest **raises** when `evt_bars_to_next` is missing, because silently holding through would measure the wrong arm. Pinned in V104-9, V104-10 and V104-11.
3. **The sizing guard with sizing unavailable** (account file unreadable, balance 0): fail closed. Pinned in V104-5 (`test_risk_sizing_fails_closed_*`).
4. **A second holdout shot:** refused unless the first was `sealed-thin` and `HOLDOUT_END ≥ 2026-12-31`. Pinned in V104-12 (`test_holdout_refuses_*`).
5. **Consecutive breakouts in B1:** the first trap bar wins, and a bar never fires twice. Pinned in V104-9.

## Parallelisation

- **Part 1a:**
  - V104-1 first; every other task consumes `stop_scope`.
  - Then V104-2 (lifecycle), V104-3 (builders), V104-4 (plan_manager) and V104-6 (funnel rename) in parallel. Their files are disjoint.
  - V104-5 after V104-1 (it touches `strategy_pass.py` and `stop_scope.py`, appending one function).
- **Part 1b:**
  - V104-7 (`market_context.py`) and V104-8 (`earnings_context.py`, `plan_types.py`, `exit_sim.py`) in parallel.
  - V104-9 after both, since it creates `short_entries.py`.
  - V104-10 after V104-9 (both edit `short_entries.py`); V104-11 after V104-10 (it sizes all three shorts).
- **V104-12** after V104-6 and V104-11.
- **Part 2** is a strict chain on `main`. Inside V104-16, the 15 Part A cells are independent processes, so dispatch up to 4 `backtest-runner` agents at once. Inside V104-17, B1/B2/B3 run concurrently.
- **Cross-plan:**
  - v67 (JSON→Postgres) is live. V104-8 adds a `TradePlanV2` field (`hold_cap_bars`, default `None`). Check v67's plans-store task (`_2b-trading-state-plans.md`) for a column list and add the field there if one exists (memory: v67 parallel-plan rule).
  - No other live plan touches these files.
