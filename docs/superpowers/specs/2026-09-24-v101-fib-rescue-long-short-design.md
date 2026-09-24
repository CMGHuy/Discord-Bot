# v101 — Fibonacci rescue: a new mechanism, long and short scored separately

**Version:** ui 1.21.0 · bot 1.10.3 (at writing)
**Bump:** bot minor if a mechanism passes VALIDATION in either direction; none on no-lift
**Edge:** expectancy

Fibonacci is `WEAK` with a positive expectancy: TRAIN 2020-01-01..2023-12-31,
N=246, WR 35.4%, ExpR +0.232 (`validation_registry.json`, `run_date:
2026-09-10`). It fails on the `win_rate >= 50` badge clause alone. A
`VALIDATED` badge moves it into the booked, top-plans population, so the lift
is expectancy delivered to the operator, not a new metric. The short side is
the widening that pairs with this tightening, but its baseline was already
measured and failed (v93, below), so it only re-enters if a mechanism in
Phase A turns it around.

> ### CORRECTION 2026-09-24, while planning: two premises were wrong
>
> 1. **The short side was already re-measured under current arithmetic.**
>    v93 (`results/2026-09-17-v93-bearish-arms-train.md`, closed row in
>    `backtest-methodology.md`): Fibonacci bearish, TRAIN, 226 trades before
>    the live `rs_combined` laggard rule and 107 after, decided N=89,
>    **WR 21.3%, ExpR −0.255**, decision `fail`. Negative ExpR also rules out
>    v93's Stage 2 horizon-subset search. The bullish-only gate is therefore
>    *supported* by current data, not stale; only its comment's figures are.
>    Enabling shorts with no mechanism would re-run v93 and is off the table.
> 2. **The horizon split (#3) is closed for the long side too.** v31's TRAIN
>    grid (`results/2026-08-17-structural-target-train.md`) found Fibonacci
>    "never clear[s] 50% win rate at any horizon with N>=30". #3 is dropped as
>    a mechanism. Phase A still reports per-horizon rows, as description only.
>
> What survives: mechanisms #1, #2 and #4 are new for **both** directions, so
> Phase A measures both. The short side starts from a far worse baseline, and
> the Phase A exit rule applies to it unchanged.

## What is already true (so nobody rebuilds it)

- **The short side exists and is gated off, not missing.**
  `fibonacci_entries` (`swingbot/core/market/entry_filters.py:190`) returns a
  `bearish` series (down-impulse retracement, bear regime, trend50 bear, RSI
  band). `_fibonacci_plan` (`swingbot/core/planning/builders.py:342`) prices
  both directions. The only block is
  `STRATEGY_GATES["Fibonacci"] = {"directions": ("bullish",)}`
  (`swingbot/core/market/strategy_types.py`). Its comment cites pre-v31
  WR 81.8%, arithmetic v31 deleted, but v93 re-measured the bearish arm and
  it failed (see the correction above), so the gate itself stands.
- **Closed and not re-runnable:** the 2026-09-10 legacy badge refresh and the
  v84 Fibonacci 1.0-extension target candidate (flag-on changed one trade).
  `docs/claude/backtest-methodology.md` requires a genuinely new mechanism to
  reopen Fibonacci. Lowering the 50% floor, or adding more far target
  candidates, is neither.
- **Live shorts lose.** Production journal, closed 2026-07-20..2026-09-22:
  bearish N=250, WR 53.2%, ExpR −0.168 (v98 spec correction). The Fibonacci
  short side therefore gets its own verdict; a passing long side never
  carries it.

## Success bar

Unchanged, stated before any measurement. Each direction is its own badge row
and must independently clear `win_rate >= 50`, `expectancy_r > 0`,
`N >= 30` (TRAIN) / `N >= 15` (VALIDATION), scratches+timeouts ≤ 50% of
closed trades. Then the v72 funnel: Stage 0 MDE → Stage 1 plateau (mandatory,
disqualifying) → Stage 2 walk-forward (≥ 2 of 3 folds improving, none worse
than −1.0pp, per-fold N ≥ 30) → Stage 3 VALIDATION 2024-01-01..2025-12-31,
**one shot per direction, ever**.

# Phase A — free TRAIN diagnostic

A read-only script, `scripts/backtest/measure_fib_diagnostic.py` (no
production code, no VALIDATION data). It sits beside
`measure_bearish_arms.py` and reuses that script's universe filter, laggard
rule and `gate_override` pattern, so its bearish baseline must reproduce
v93's figures exactly, which serves as the built-in sanity check. Trades come
from `run_backtest` with the v2 + scale-out exit engine, so its arithmetic is
the backtest's, not a copy. The bullish-only mask is lifted **inside the
script only**, through `entry_filters.gate_override`, never by editing
`STRATEGY_GATES`.

Over TRAIN 2020-01-01..2023-12-31, full cached universe × all 10 horizons, it
reports per direction and per direction × horizon:

1. **Stop-cap binding rate.** Share of plans where `max_risk_pct` pulled the
   stop in from `swing_extreme ± STRUCTURE_BUFFER_ATR·ATR`, with N / WR /
   ExpR for capped vs structural stops. Hypothesis #1: a capped stop sits in
   noise between the fib level and the swing extreme, which would explain a
   low WR alongside a positive ExpR.
2. **Deeper-ratio stop distance.** Distance from entry to the next deeper fib
   ratio (e.g. 0.786) in ATR, with the WR that stop would have produced
   (hypothesis #2).
3. **Horizon rows, description only.** N / WR / ExpR per horizon. #3 is
   closed as a mechanism (v31, see the correction above); these rows only
   show where #1, #2 and #4 act.
4. **Reclaim-close rate.** Share of signals where a later bar within the
   horizon's entry window closes back through the level, and the outcome of
   entering there instead (hypothesis #4).

Dispatched to `backtest-runner`, with flushed per-ticker progress and a
percent figure if it passes 15 minutes. Output:
`docs/superpowers/results/YYYY-MM-DD-v101-fib-diagnostic.md` plus raw JSON.
TRAIN is exploration data; reading it does not spend the budget.

**Exit from Phase A.** If no hypothesis shows a cell with WR ≥ 50 and N ≥ 30
in either direction, v101 closes **no-lift** here. The finding goes into the
closed pre-registrations table and the spec and plan move to `no-lift/`.

# Phase B — pre-registration (after A, before any scoring)

`docs/superpowers/results/YYYY-MM-DD-v101-fib-preregistration.md`, committed
before Stage 0 runs. It names:

- **exactly one mechanism** from #1, #2 or #4, with the Phase A figure that
  justifies it;
- its parameter grid and the plateau neighbours, fixed in advance;
- the direction(s) entering the funnel. A direction that failed Phase A does
  not enter;
- the per-direction verdict rule (the success bar above, per direction).

Adding a second mechanism after seeing Stage 1–2 results is a new
pre-registration, not a revision of this one.

**The mechanism's flag is built before the funnel runs, not after.** Stage 0–3
measure a config-flag arm (`measure_strategy_arm.py --component-json`, or
v100's `measure_arms.py` if v100 has merged by then, in which case its
stamp is required). So the flag, default off, lands in Phase B. Phase C
only flips it and rewrites the gate. The code for the flag depends on which
mechanism is chosen, so it goes in a second plan part written after the
pre-registration, not guessed now.

# Phase C — wiring (only for direction(s) that pass VALIDATION)

- **Flip the Phase B flag on.** It lives in `_fibonacci_plan` (#1, #2) or
  `fibonacci_entries` (#4); both are shared by the backtest and live scans,
  so parity holds by construction.
- **`STRATEGY_GATES["Fibonacci"]` rewritten** to list only the passing
  directions. The stale pre-v31 comment is replaced with the
  current-arithmetic TRAIN and VALIDATION figures, citing v93 for the
  bearish side if it stays gated.
- **Registry rows re-emitted** with `run_backtest_range.py --emit-registry`,
  one row per direction if the registry key supports it (otherwise the plan's
  first task extends the key). Never hand-edited.
- **No-lookahead review** of the bearish path: `down_impulse` relies on
  `_rolling_argmax_pos` / `_rolling_argmin_pos`, and any reclaim-close logic
  (#4) must only read bars at or before the decision bar.
- `docs/claude/backtest-methodology.md` gets a closed pre-registration row for
  v101 whatever the outcome.

## Testing

- Unit tests for the chosen mechanism in both directions, including the
  capped-stop edge case and a `None` return when no target clears
  `MIN_RISK_REWARD_RATIO`.
- A parity test: `_trade_plan_at` and the live `build_strategy_plan` path
  produce identical stop and target for the same bar, bullish and bearish.
- A gate test asserting `entries_for("Fibonacci", ...)` emits bearish signals
  only if the short side passed.
- The full suite runs once, as the plan's final task.

## Non-goals

- No change to the badge threshold, the funnel, or the reward:risk band.
- No change to other strategies' gates, even though several carry the same
  stale pre-v31 comment. Each needs its own pre-registration.
- No inverse-ETF routing (v98, closed no-lift).

## Parallelisation

- **Sequential:** Phase A → Phase B → Phase C. B's content is chosen from A's
  numbers, and C wires only what passed B's funnel.
- **Group 1 (parallel, inside Phase A):** the diagnostic script and its unit
  test fixture touch different files and can be written together. The run
  itself is a single `backtest-runner` dispatch.
- **Group 2 (parallel, inside Phase C):** the flag flip and the
  `STRATEGY_GATES` / registry update touch disjoint files. The parity test
  waits for both.
- **Cross-plan:** v100 (arm producer) is live and unimplemented. If it merges
  before Phase B, Phase B's funnel runs go through `measure_arms.py` stamps.
  Nothing in Phase A touches v100's files.
