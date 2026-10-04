# v131 Fibonacci resting limit entry inside the retracement zone — Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-10-04-v131-fib-zone-limit-entry-design.md`
**Bump:** none (measurement plus a plan-shape field and a masked strategy entry that no live path reaches; live wiring is a follow-on spec)
**Edge:** expectancy — a better entry price on the same stop raises R per win; the measurement decides whether adverse selection eats it

**Goal:** Add a masked `Fibonacci Limit` strategy — a resting buy limit armed ahead of today's Fibonacci retracement zone, priced, stopped and targeted from the limit price, filled only on a strict trade-through and cancelled if the leg extends first — and measure it against today's `Fibonacci` through Stage 0 (volume), Stage 1 (selection with profit clauses), Stage 2 (13 anchored folds) and one 2026 holdout shot.

**Architecture:**
- `market/entry_filters.py` gains `fibonacci_limit_setups` (the arming mask plus the frozen `swing_high`, `swing_low`, `swing_high_idx`, `limit_price`, with a causal per-ticker order book so a leg arms once and never while an order is live), `fib_limit_price_at` / `fib_limit_cancel_at` (the frozen prices at one bar) and the masked entry function.
- `planning/plan_types.TradePlanV2` gains two defaulted fields, `limit_cancel_level` and `limit_strict_fill`; `planning/lifecycle.py` reads them (`limit_hit` strict mode, new `limit_cancelled`) and `planning/exit_sim._limit_entry_exit` cancels an unfilled order on a trade beyond the cancel level, fill first. Plans without the fields — every plan today, including the v113 fade's limit — are untouched.
- `PLAN_SHAPES` gains an optional `"limit_price"` key naming a `builders.LIMIT_PRICERS` entry (`LimitPricer(price, cancel_level, strict_fill)`). `builders.build_strategy_plan` and `backtest._trade_plan_at` / `backtest._bt_plan` honour it through shared helpers (`plan_entry_reference`, `size_strategy_plan`, `limit_order_fields`); `run_backtest` records every placed cancellable order on `BacktestSummary.limit_orders` without a new branch in its body.
- `Fibonacci Limit` registers into `STRATEGY_GATES` masked (`{"directions": ()}`), `ENTRY_FUNCS`, `PLAN_SHAPES`, `EXIT_V2_PARAMS`, `LIMIT_PRICERS` and `builders._STRUCTURAL_BRANCHES`; it is not in `backtest.ALL_STRATEGIES`.
- One new script, `scripts/backtest/measure_fib_limit.py`, on `funnel.py`'s scoring, with a 2-D (L × N) plateau, the profit clauses, a reproduction gate against v103's reference, a gzip features record for the queued meta-label spec (B) and the v113 one-shot holdout ledger.

**Tech Stack:** Python 3.11+, pandas, numpy, pytest, radon.

## Parts

| Part | File | Tasks | Where |
|---|---|---|---|
| 1 — Witness, setup function, simulator | `2026-10-04-v131-fib-zone-limit-entry_1-setup-and-simulator.md` | V131-01 … V131-03 | worktree branch |
| 2 — Plan-shape field and registration | `2026-10-04-v131-fib-zone-limit-entry_2-shape-and-registration.md` | V131-04 … V131-05 | same branch |
| 3 — Measurement script | `2026-10-04-v131-fib-zone-limit-entry_3-measurement-script.md` | V131-06 … V131-08 | same branch, then merge to `main` |
| 4 — Pre-registration, runs, close-out | `2026-10-04-v131-fib-zone-limit-entry_4-runs-and-close-out.md` | V131-09 … V131-13 | `main` |

`grep -n "^### Task" docs/superpowers/plans/2026-10-04-v131-*` lists every task; `grep -n "^# Phase" docs/superpowers/plans/2026-10-04-v131-*` lists the phases.

**Worktree.** Phases 0–3 run on branch `2026-10-04-v131-fib-zone-limit-entry` in `.claude/worktrees/2026-10-04-v131-fib-zone-limit-entry` (load `worktree-lifecycle` before creating it). Name the worktree path in every subagent dispatch, and check `git -C E:/Documents/Private/Projects/Discord-Bot status --short` after each task: a subagent editing the main tree by mistake is a known failure here. V131-08 merges to `main`; Phases 4–6 run on `main`, because `require_committed` reads `main`'s index.

## Global Constraints

Values copied from the spec; every task's requirements include this section.

- **Bullish only.** Everything is computed at the close of the arming bar `t` from `df.iloc[:t+1]`.
- **Arming (all at `t`):** (1) a valid up-leg on today's rolling anchors — `swing_high`/`swing_low` are the rolling `fib_lookback` max High / min Low that `fibonacci_entries` uses, the low precedes the high (`argmax_pos > argmin_pos`); (2) the swing-high bar is at least 3 bars old (`t − 3` or earlier); (3) the close's retracement `(swing_high − close) / (swing_high − swing_low)` is ≥ 0.236 and < `L`; (4) MA200 above and rising over 20 bars, close > MA50, ATR ≥ 0.7% of the close, ATR ≤ 1.4× its 60-bar mean; (5) no live order on this ticker and horizon, and this leg (identified by its swing-high bar) has not already armed — an expired or cancelled order never re-arms the same leg.
- **Dropped from `fibonacci_entries`:** the RSI band, the volume ≥ 0.9× gate, the 5-bar pullback test and the bounce-bar shape.
- **The plan, priced entirely at `t` from the limit:** entry `limit_price = swing_high − L × (swing_high − swing_low)`; stop `swing_low − 0.25 × ATR14[t]` through `_bounded_stop` and `stop_ceiling` measured from the limit (capped at 2% below it; dropped only if `Fibonacci Limit` is ever placed in `STRUCTURAL_STOP_SCOPE`, which it is not); TP1 `select_structural_target` over `fib_target_candidates`, R from the limit, inside the frozen 1.5–2.5R band, no candidate ≥ 1.5R → no order; exits today's Fibonacci shape: v2, scale-out, `trail_atr_mult` 3.0, no TP2; order life `N` bars, `t+1 .. t+N`.
- **Fill and cancel:** fill on the first bar in `t+1 .. t+N` with `Low < limit_price`, strictly (an exact touch does not fill); fill price `min(Open, limit_price)`; pre-fill cancel on the first bar whose `High > swing_high` (frozen), before any fill; a bar that both makes a new high and trades through the limit is a fill and the fill-bar stop rule applies (count disclosed); fill bar: a fill at or beyond the stop scores a scratch, otherwise the stop is checked on the fill bar, the target not until the next bar; R from the fill price; expired and cancelled orders are counted per cell and produce no trade.
- **Plan-shape field:** `PLAN_SHAPES` gains an optional `limit_price` entry naming a registered limit-price function `(df, idx, horizon, direction) -> float | None`; `backtest._bt_plan` and `builders.build_strategy_plan` both honour it; absent, every existing strategy builds byte-identical plans (V131-01's witness).
- **Registration:** `Fibonacci Limit` is `{"directions": ()}` in `STRATEGY_GATES`, out of the backtest strategy list; the script unmasks it through `entry_filters.gate_override`.
- **Measurement data:** TRAIN 2010-01-01..2025-12-31, extended cache `data/backtest_cache_ext`, universe 74, bullish, all ten horizons (`LEGACY_HORIZONS`, 2w..9m — `HORIZONS` also holds the masked `1w`, which is not one of the ten). Holdout 2026-01-01 to the cache end at the time of the shot, read only by Stage 3, v113 one-shot ledger.
- **Grid:** six cells, `L ∈ {0.5, 0.618}` × `N ∈ {3, 5, 10}`; neighbours are adjacent values on one axis.
- **Reference arm:** today's `Fibonacci` (market entry on the bounce bar), same window and universe, v2 + scale-out; reported, never selected. Its TRAIN 2010-01-01..2023-12-31 slice must reproduce v103's reference (N=815, WR 36.81%, ExpR +0.2219, universe 73) before any cell is read, or a committed note explains the difference first.
- **Stages:** Stage 0 — `L=0.5, N=10` needs ≥ 30 fills, else volume-dead, budget intact. Stage 1 — `funnel.py` Tier 1 (WR ≥ 50, ExpR > 0, N ≥ 30, scratch+timeout share ≤ 0.5) and Tier 2 (ExpR > 0, ticker-cluster bootstrap lower bound > 0); plateau rule (a cell and every grid neighbour clear the same tier, Tier 1 tried first, winner the highest ExpR inside the plateau); profit clauses all required of the winner: (a) ExpR > the reference's ExpR, (b) fills ≥ 50% of the reference's trade count, (c) WR ≥ the reference's WR − 2.0pp; no winner closes, budget intact. Stage 2 — `fold_pick` re-selects on `2010..year−1` with N ≥ 30, a fold qualifies at N ≥ 15, clears with ≥ 3 qualifying folds and ≥ ⅔ positive, 13 fold years 2013–2025; fail closes, budget intact. Stage 3 — only the winner, at the tier it held on TRAIN, plus profit clause (a) against the reference on the same holdout; sealed-thin if fills < 15 (shot unspent, one retry once the cache reaches 2026-12-31).
- **Total R** (`N × ExpR`) is reported for every cell and the reference and never gates. **Badge** computed alongside, never gating: `VALIDATED` only if the winner holds Tier 1 on the holdout; a Tier 2 pass ships the mechanism and leaves the badge `WEAK`; today's `Fibonacci` row is not touched.
- **Disclosures never select:** fill rate per cell and the expired/cancelled split; the share of fills stopped out within 3 bars of the fill (cells and reference); how often the 2% cap binds, from the limit versus from the reference's close; same-bar new-high-and-fill count; top-2 horizon share against the 80% line; total R per cell.
- **Features for B:** each fill's `entry_context` (computed at the arming bar) with the fill bar index, fill price and outcome; `stop_pct`, `stop_atr`, `planned_rr` recomputed from the limit price. **The results documents report no split on any recorded feature.**
- **Out of scope:** any live resting order, `PlanManager` change or Discord alert line; bearish Fibonacci; v124's impulse leg; any change to today's `Fibonacci` entry, plan, exits, badge row or alerts; any friction model; any re-run of a closed Fibonacci row.
- **NO-LOOKAHEAD:** load the `no-lookahead` skill before V131-02 and for the review in V131-08. Every new per-bar series has a truncation test (`frame.iloc[:t+1]`'s last row equals row `t` of the full result).
- **Complexity:** every function written or changed ends with radon CC < 15 (`python -m radon cc -s -n C <file>` prints nothing new). Legacy functions ≥ 15 never get worse: `run_backtest` (58) gets **no** new branch — V131-04 adds one unconditional helper call and two keyword arguments only. `_trade_plan_at` (13 → 14) and `build_strategy_plan` (13 → 14) each gain exactly one branch.
- **Tests:** iterate with `python scripts/dev/testrun.py file <path>`; `... fast` once, in V131-08; the full suite once, in V131-13. **Green means `0 failed` and `0 xfailed`.** Never add an `xfail`.
- **Worktree hygiene:** no `cd` in any command; stage files by explicit path, never `git add -A`; never run a command containing the substring `eval` inside the worktree (the `evaluate` subcommand runs only on `main`, in V131-10).
- **Commit trailer:** end every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Decisions this plan makes where the spec is silent (frozen in the pre-registration, V131-09)

1. **The cancel level and strict fill travel on the plan.** The spec's limit-price function returns a price only, but the simulator needs the frozen swing high and the strict-fill rule. `LIMIT_PRICERS` entries are `LimitPricer(price, cancel_level, strict_fill)`; `PLAN_SHAPES["Fibonacci Limit"]["limit_price"]` names `"fib_zone"`, whose `price` is `fib_limit_price_at` (the spec's `(df, idx, horizon, direction) -> float | None`). Two `TradePlanV2` fields carry the result (`limit_cancel_level`, `limit_strict_fill`); added fields land in `plans.doc` with no Alembic revision (`schema-evolution.md` "add").
2. **The setup's order book.** "No live order" is tracked inside `fibonacci_limit_setups` from bars ≤ `t`: an order armed at `a` is live through bar `a+N` unless a bar trades below its limit (filled — from then on `run_backtest`'s `one_at_a_time` blocks new entries while the trade is open) or above its cancel level. The market layer cannot see the planner, so an arm whose plan is rejected (stop dropped, no ≥ 1.5R target) still consumes its leg and its N-bar slot. Conservative; disclosed.
3. **The level lifecycle applies as it ships** (`LEVEL_LIFECYCLE_STOPS_ENABLED` is on by default) to both the cells and the reference, through the same `apply_level_lifecycle` call every strategy plan takes.
4. **Windows are by signal (arming) date**, as `funnel.year_rows` and `run_backtest_range.window_trades` read `entry_date`. A TRAIN order may fill and exit on a 2026 bar.
5. **"Fills"** (Stage 0, clause (b), the sealed-thin rule) = filled orders that produced a closed trade; the reference's "trade count" = its closed trades. Tier N is decided trades (`arm_rule.pooled_stats`).
6. **Stopped out within 3 bars** = outcome `loss` with exit bar − fill bar ≤ 3 (the reference's fill bar is its signal bar). **Cap binds** = planned risk ≥ the ceiling − 0.001pp (the v113 tolerance).
7. **Cache end** for the holdout = the latest bar date across the loaded frames at the shot.
8. **The features record** is a gzip JSON (`<date>-v131-train-fills.json.gz`): every TRAIN fill of every cell. Only `stop_pct`, `stop_atr` and `planned_rr` are re-priced from the limit, as the spec names; `gap_fragile` (derived from the close-based `stop_pct`) is left as `entry_context` recorded it.
9. **The masked entry function short-circuits.** The live strategy pass calls every `ENTRY_FUNCS` entry; while `admits("Fibonacci Limit", "bullish", hk)` is False the function returns all-False without walking the order book, so the live scan pays nothing.
10. **Registry row on a pass.** On a passing holdout, `emit-registry` writes one `Fibonacci Limit` row (VALIDATED for a Tier 1 winner, WEAK for Tier 2); `STRATEGY_GATES` stays masked — unmasking is the live-wiring follow-on spec's job.

## Review Focus

1. **A bar that both makes a new high and trades through the limit** must be a fill, not a cancel, and still take the fill-bar stop check — V131-03 `test_the_same_bar_new_high_and_trade_through_is_a_fill` and `..._still_takes_the_fill_bar_stop`.
2. **The v113 fade's limit** (no cancel level, touch fills, reason-less no-fill) must be byte-identical — V131-03 `test_a_plan_without_a_cancel_level_keeps_the_v113_rules`, V131-04 `test_the_v113_fade_limit_keeps_its_touch_fill_and_records_no_orders`, and V131-01's witness.
3. **A TRAIN collect must never carry a 2026 row** — V131-06 `test_holdout_dated_rows_never_reach_a_train_collect`, `test_the_collect_command_has_no_window_argument`, plus `funnel.assert_rows_before` inside `_cmd_collect`.
4. **Price-scale invariance** of the arming rule (a live gold-scale frame must arm on the same bars) — V131-05 `test_arming_is_price_scale_invariant`.
5. **Truncation of the built plan**, not only of the setup frame: the plan at `t` built from `df.iloc[:t+1]` equals the plan from the full frame — V131-05 `test_truncation_invariance_of_the_built_plan`.

## Parallelisation

- **Phase 0 — sequential, alone:** V131-01 first. Its golden must be written on the untouched branch head, before any other v131 change; every later code task keeps it green.
- **Phase 1 — Group 1 (parallel): V131-02, V131-03.** Disjoint files — V131-02 edits `swingbot/core/market/entry_filters.py` and creates `tests/market/test_fib_limit_setups.py`; V131-03 edits `swingbot/core/planning/plan_types.py`, `lifecycle.py`, `exit_sim.py` and creates `tests/planning/test_limit_cancel.py`. No contract dependency: neither consumes a symbol the other introduces.
- **Phase 2 — sequential:**
  - V131-04 after Group 1: it consumes V131-03's `TradePlanV2.limit_cancel_level` / `limit_strict_fill` (written by `limit_order_fields`, read by `_record_limit_order`), and is the plumbing V131-05 registers V131-02's prices into.
  - V131-05 after V131-04: it registers into `LIMIT_PRICERS` and `PLAN_SHAPES["limit_price"]`, which V131-04 introduces, and it edits `entry_filters.py` (V131-02's file), `builders.py` and `params.py` (V131-04's files).
- **Phase 3 — sequential:** V131-06 after V131-05 (the script imports `FIB_LIMIT`, `PLAN_SHAPES["Fibonacci Limit"]` and reads `BacktestSummary.limit_orders`). V131-07 after V131-06 (same file, and it consumes `load_collects`, `cell_rows`, `disclosures`). V131-08 after V131-07 (it reviews the finished script and merges the branch).
- **Phase 4 — sequential:** V131-09 after V131-08 (`require_committed` checks `main`, and the pre-registration names the merged script's commit). It is committed alone, before any run.
- **Phase 5 — a chain, each gated on the previous verdict:** V131-10 (Stages 0–2) after V131-09; V131-11 (Stage 3) only if V131-10's evaluate JSON says `proceed_to_holdout: true`; V131-12 (close-out) after V131-10, and after V131-11 when it ran.
- **Phase 6:** V131-13 (full suite) last.
