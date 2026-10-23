# v180 — Turtle Soup entry, structural arm: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V180-4:" -A 400 docs/superpowers/plans/2026-10-21-v180-turtle-soup-entry_1-signal-instrument-and-plan.md`.

**Bump:** bot patch
**Edge:** expectancy — adds a long entry on a trigger that passed the idea screen (paired ΔExpR +0.316R [+0.254, +0.381], N = 10,438, PIT S&P 500 2011–2019, yfinance, fixed 1.5/3 ATR race). The screen covers the trigger only, not the structural plan shape tested here. Base case: a fail on the win-rate clause; a pass is the upside.
**Screen:** screen-turtle_soup SCREEN-PASS
**Spec:** [2026-10-21-v180-turtle-soup-entry-design.md](../specs/2026-10-21-v180-turtle-soup-entry-design.md)
**Brief:** `.superpowers/briefs/2026-10-21-v180-turtle-soup-entry.md`
**Worktree:** implement V180-1..V180-9 in `.claude/worktrees/2026-10-21-v180-turtle-soup-entry` (branch of the same name, created in V180-1; `docs/claude/document-lifecycle.md`). The merge to `main` is V180-9's last step. V180-10..V180-14 (the frozen pre-registration block, the measurement runs, the one-shot VALIDATION, the record and close-out) run on `main` in the main tree.

## Goal

The idea screen found that a daily "Turtle Soup" sweep pays. The pattern: a bar
trades under the lowest low of the prior 20 bars, where that low was set at least
4 bars earlier, then closes back above it. Over 10,438 events, after costs, it
beat matched random entries by +0.316R. The screen used a fixed 1.5/3 ATR
bracket. Under that bracket only 29% of decided trades won, below break-even and
far below the badge's 50% floor. The partner therefore dropped that shape. They
kept one arm: the stop sits just under the sweep bar's own low, and the target is
the nearest real level from the level map.

This plan builds that arm as a masked strategy and runs it through the standard
funnel once. Nothing the user, the live scan, the alerts or any default backtest
sees changes. `Turtle Soup` is registered in `ENTRY_FUNCS`, but
`STRATEGY_GATES` masks it everywhere. It runs only inside a scoped
`("bullish", "2w")` research cell, and only while the new research knob
`TURTLE_SOUP_RESEARCH_MODE=structural` is set in the `measure_arms.py` replay.

The plan has four pieces:

- **The signal.** A live re-implementation of the frozen screen trigger. Tests
  prove it equals the screen bar for bar and reads no later bar.
- **The plan builder.**
  - Stop: `Low[t] − 0.25 × ATR14`.
  - Target: the nearest level-map level inside the 1.5–2.5 R:R band. With no
    level in the band, there is no plan.
  - One whole-position leg and a 10-session hold cap.
- **A replay path that fills like the live order would.**
  - The fill is at the next session's open.
  - An open at or below the stop cancels the plan.
  - A stop more than 3% from the fill drops the plan; it is never squeezed.
  - A gap through the stop or target fills at the open.
  - Costs are 5 bps a side plus commission, booked on Turtle Soup rows only.
- **The v119 A1–A3 acceptance amendment.** The standard win-rate statistic
  weights strata by the baseline's mix, so it cannot see a strategy the baseline
  lacks. The amendment adds a pooled ΔWR that does, selectable in
  `validate_component.py`, in the walk-forward fold rows, and in a new
  circular-shift replay inside `permutation_test.py`.

The amendment is committed before any MDE, fold or VALIDATION run starts.

Success is an honest, finished record, not a pass:

- one ledger row `v180-turtle-soup-structural`;
- a results doc with every stage's reading, plus the descriptive blocks the spec
  lists: drop and cancel shares by reason, each excluded population's
  screen-style outcome, sweep depth, early stops, exit mix, regime split, signal
  clustering and the share outside the S&P 500.

A fail closes the spec as `no-lift`, and Turtle Soup never re-enters under this
shape. A pass ships nothing. It licenses the follow-on change the spec
describes: unmask, shadow soak, time-exit alert, explain text.

## Architecture

- **Signal (V180-1).** `swingbot/core/market/turtle_soup.py` holds the frozen trigger (`CHANNEL = 20`, `MIN_AGE = 4`) as its own implementation. Live code never imports `swingbot.core.backtesting.screen`. `entry_filters.turtle_soup_entries` returns all-False unless `admits(TURTLE_SOUP, "bullish", horizon_key)`, following the `fibonacci_limit_entries` precedent. Parity tests import the screen module, which tests may do.
- **Acceptance instrument (V180-2, V180-3).**
  - `acceptance.delta_pooled_win_rate` is the A1 statistic. A name-keyed table `WR_STATISTICS` exposes it. `evaluate(..., wr_statistic=)` uses it for clause 1.
  - `backtest_wf.win_rate_fold_row(..., wr_statistic=)` builds the stage-2 fold rows. With `pooled`, each fold's `n` counts the decided **added** trades. `gate_win_rate` itself is unchanged.
  - `validate_component.py --wr-statistic pooled` covers A1 in the validation gate, A3 at stage 0 (`--train-effect-from-arms` computes the A1 point estimate on the same fold-train arms) and the fold rows.
  - A2: `arms/shift_permutation.py`, run by `permutation_test.py --shift-replay`. It replays only the added strategy with `bt.ENTRY_SHIFT` rolled, using the existing shift draw, and keeps the real baseline fixed. Null value per shift = A1(baseline, baseline + shifted added rows).
- **Plan (V180-4).** `swingbot/core/planning/turtle_soup_plan.py` computes the levels.
  - Stop through `_bounded_stop`. `TURTLE_SOUP` is in `STRUCTURAL_DROP_STRATEGIES`, so `stop_scope` drops it at the 2w 3% ceiling and never caps it at 2%. It is not added to `SHORT_STRATEGIES`.
  - Target: `select_structural_target` over the level-map resistances **pre-filtered to the band**, so the synthetic `entry + 2.5R` fallback can never fire.
  - The level map comes from `inputs.level_map`, or is built from bars ≤ t when that is None.
  - `PLAN_SHAPES[TURTLE_SOUP]` gives `entry_type "market"`, `tp1_fraction 1.0`, `breakeven_trigger_fraction 1.0`, `hold_cap_bars 10`.
  - The level lifecycle is skipped for Turtle Soup, as for the compression short.
- **Fill and walk (V180-5).** v1 `simulate_exit`'s market branch moves into `_market_exit`. For a plan in `NEXT_OPEN_STRATEGIES` it calls `next_open_entry.next_open_exit`; every other market plan still fills at the signal close.
  - The fill is at `Open[t+1]`. An open at or below the stop returns `not_triggered("open_through_stop")`. `planned_loss_pct(fill, stop) > plan_stop_ceiling(plan)` returns `not_triggered("risk_cap")`.
  - `gap_aware_single_leg_walk` then walks from the fill bar. An open beyond the stop or target fills at the open, by the live `plan_manager.gap_stop_fill` / `gap_target_fill` convention. Otherwise the stop is checked before the target, then the v129 acceptance exit.
  - The fill session counts as session 1: `SESSION_ONE_HOLD_CAP` generalises `_hold_cap_bars`, so the cap is unchanged for the compression short. The last session closes as `time_exit`.
  - The v2 simulator is untouched.
- **Research cell, costs, events (V180-6, V180-7).**
  - V180-6 registers the knob in `config.py` (Field, searchable set, enum map), `.env.example`, `ScanParams` and the reachability `REGISTRY`.
  - `arms/turtle_soup_research.py` holds the knob constants, the research cell and `net_r(plan, result)`. `net_r` is `expectancy_attribution.net_r`: `apply_frictions` on both fills plus `commission_r()`, the screen's model.
  - `StrategyEngine` adds `TURTLE_SOUP` when the knob is `structural` and reads its entries under `gate_override(TURTLE_SOUP, RESEARCH_CELL)`. It books Turtle Soup rows at net R and appends one event per counted Turtle Soup candidate to `turtle_soup_events`. `iter_trades` (cc 14) is not touched.
  - `backtest._refuse_compression` also refuses Turtle Soup on the signal-close path.
- **Diagnostics and badge (V180-8).** `arms/turtle_soup_report.py` turns the engine's events and the live signal series into the spec's descriptive blocks, and runs the screen's own `race()` on each excluded population. `measure_arms.py` writes it as a `<out>.turtle_soup.json` sidecar beside the stamped arms. `scripts/backtest/turtle_soup_report.py --arms` runs the stage-3 badge check on the stamped pair's added rows.
- **Runs (V180-10..V180-13).** Run by `backtest-runner`, one stage per invocation, `--data-source alpaca`, each followed by an explicit stop/continue gate. VALIDATION is a single shot, taken only after the partner's go.

## Global Constraints

- Signal parity is the contract: the live bullish series equals `screen/ideas/turtle_soup.events(df)` bar for bar (random walks, the screen fixture, the equal-lows tie fixture). `swingbot/core/backtesting/screen/ideas/turtle_soup.py` is never edited. No trend, volume or zone filter and no short mirror is added.
- Masked by default: `STRATEGY_GATES["Turtle Soup"] == {"directions": ()}`; `"Turtle Soup" not in backtest.ALL_STRATEGIES`; it runs only under `entry_filters.gate_override(TURTLE_SOUP, {"directions": (), "cells": {("bullish", "2w")}})` inside `StrategyEngine`, always as a context manager.
- Frozen plan values, never tuned: `channel = 20`, `min_age = 4`, `STRUCTURE_BUFFER_ATR = 0.25`, R:R band `MIN_RISK_REWARD_RATIO` 1.5 / `MAX_RISK_REWARD_RATIO` 2.5 (from `ScanParams`), hold cap 10 sessions with the fill session as session 1, the 2w `max_risk_pct` 3.0 measured from the fill. `HORIZONS["2w"]["max_holding_days"]` (14) ≥ 10 is asserted in a test.
- Drop, never squeeze: a Turtle Soup stop beyond the ceiling returns no plan (builder, from the signal close via `_bounded_stop`) or a `risk_cap` cancel (at the fill); it is never moved. `TURTLE_SOUP` is never added to `SHORT_STRATEGIES`.
- Baseline rows are byte-identical: with the knob `off` nothing changes for any strategy, and with `structural` every baseline row appears unchanged in the component (`population_split` → `removed == []`, `changed == []`). Costs touch Turtle Soup rows only.
- Behaviour-preserving generalisations: `_hold_cap_bars`, `_lifecycle_pair`, `stop_scope._ALWAYS_IN_SCOPE`, `StrategyEngine._entries` / `_run_strategies` and `backtest._refuse_compression` keep every existing strategy's result identical; every existing test passes unmodified.
- `exit_sim_v2.py`, `instrument/`, `plan_manager.py` (read-only import of `gap_stop_fill` / `gap_target_fill`), the frozen screen module and every acceptance threshold are not modified. `standardised` stays the default `wr_statistic` everywhere; `render_json` output is key-for-key identical unless `pooled` is selected.
- Every function written or changed stays below cyclomatic complexity 15 (`scripts/dev/complexity_gate.py`). `build_strategy_plan`, `StrategyEngine.iter_trades` and `_single_leg_exit_walk` already sit at 14, so add no branch to them: use the dispatch tables (`_STRUCTURAL_BRANCHES`, `PLAN_SHAPES`) and new helpers instead.
- No lookahead: the signal, the stop, the level map and the ATR read bars ≤ t only. Only the fill and the walk read t+1 onward.
- Order (spec § 4): V180-2 and V180-3 are committed (and merged in V180-9) before any MDE, selection, fold or VALIDATION run. Stage −1 (V180-10) measures reachability only.
- Runs: `--data-source alpaca` on every producer and replay command, named in the frozen block of the pre-registration doc before any TRAIN bar is read. `measure_arms.py`, engine `strategy`, instrument v1. Stages run serially through `backtest-runner`; never two heavy replays at once. VALIDATION is read once, only after the partner's explicit go (`AskUserQuestion`).
- Gates are verbatim from the spec. Stage 0: A1 TRAIN point < paired MDE (A3) → refused, budget intact. Stage 1 tests nothing (one cell). Stage 2: `gate_win_rate` on A1 fold rows, ≥ 2 of 3 folds improving, none worse than −1.0pp, per-fold N ≥ 30 decided added Turtle Soup trades. Stage 3: all six clauses with A1/A2 (clause 3 applied, clause 6 `SKIPPED`), plus the badge check on the added rows: `win_rate >= 50` over win+loss, `expectancy_r > 0`, N ≥ 15, scratches + timeouts ≤ 50% of closed, time-cap exits counted as timeouts.
- Per-task verification is the narrow run (`python scripts/dev/testrun.py file <test>`). The full suite runs once, in V180-9.
- Implementation tasks commit on the worktree branch, one scoped commit per task. Run and record tasks commit on `main`.

## Contracts

### Names (V180-1, V180-4 create; everyone consumes)

```python
# swingbot/core/market/strategy_types.py
TURTLE_SOUP = "Turtle Soup"                                    # V180-1
STRATEGY_GATES[TURTLE_SOUP] = {"directions": ()}               # V180-1
STRUCTURAL_DROP_STRATEGIES: tuple[str, ...] = (TURTLE_SOUP,)   # V180-4: long strategies always in the DROP scope

# swingbot/core/market/turtle_soup.py                          # V180-1
CHANNEL = 20
MIN_AGE = 4
def sweep_frame(df: pd.DataFrame) -> pd.DataFrame
    # index = df.index; columns: "prior_low" (min Low of t-20..t-1, NaN until 20 prior bars),
    # "age" (bars from the LATEST bar holding prior_low to t), "signal" (bool)
def turtle_soup_signal(df: pd.DataFrame) -> pd.Series         # sweep_frame(df)["signal"], bool, name "turtle_soup"

# swingbot/core/market/entry_filters.py                        # V180-1
def turtle_soup_entries(df, horizon_key, params=None) -> tuple[pd.Series, pd.Series]
ENTRY_FUNCS[TURTLE_SOUP] = turtle_soup_entries
```

### Acceptance instrument (V180-2, V180-3)

```python
# swingbot/core/backtesting/acceptance.py
def delta_pooled_win_rate(baseline, component) -> float | None   # win_rate(component) - win_rate(baseline), pp; None if either is None
WR_STATISTICS: dict[str, Callable] = {"standardised": delta_standardised_win_rate, "pooled": delta_pooled_win_rate}
def win_rate_statistic(name: str) -> Callable                     # KeyError -> ValueError naming WR_STATISTICS
def evaluate(baseline, component, *, stage, permutation_p=None, n_resamples=..., seed=42,
             cluster="ticker", wr_statistic: str = "standardised") -> AcceptanceResult
AcceptanceResult.wr_statistic: str = "standardised"              # render_json adds "wr_statistic" only when != "standardised"

# swingbot/core/backtesting/backtest_wf.py
def win_rate_fold_row(test_year: str, baseline, component, *, wr_statistic: str = "standardised") -> dict
    # standardised: {"test_years", "delta_win_rate_pp", "n": min(decided b, decided c)}   (today's row, byte-identical)
    # pooled:       {"test_years", "delta_win_rate_pp": delta_pooled_win_rate(b, c),
    #                "n": decided count of population_split(b, c)["added"], "wr_statistic": "pooled"}

# scripts/backtest/validate_component.py (new flags)
--wr-statistic {standardised,pooled}   default standardised; parser.error with --gate harvest
--train-effect-from-arms               stage mde: claimed effect = the selected statistic on the --arms pair (prints it)

# swingbot/core/backtesting/arms/shift_permutation.py           # V180-3
SHIFT_RANGE = (20, 200)
class NotAdditive(ValueError)
class ReplayMismatch(ValueError)
def additive_added(baseline, component) -> list[ArmTrade]       # raises NotAdditive when anything is removed or changed
def shift_permutation(baseline, component, replay_added: Callable[[int], list], statistic, *,
                      n_perm: int = 200, seed: int = 42, verify_zero: bool = True,
                      progress: Callable[[int, int], None] | None = None) -> dict
    # {"observed", "p_value", "n", "n_valid", "seed", "shift_range", "added", "statistic"}
    # null_s = statistic(baseline, baseline + replay_added(s)); p = mean(null >= observed) over valid
    # verify_zero: replay_added(0) keys must equal the added keys, else ReplayMismatch
def strategy_shift_replay(frames: dict, strategy: str, horizons, window: tuple[str, str],
                          delta: dict, *, instrument=None) -> Callable[[int], list]
    # shift s: bt.ENTRY_SHIFT = s (restored to 0 in finally), apply_knobs(delta),
    # StrategyEngine(strategies=(strategy,), instrument=instrument).run_ticker per ticker,
    # rows kept when window[0] <= entry_date <= window[1]

# scripts/backtest/permutation_test.py (new mode)
--arms FILE --shift-replay --wr-statistic pooled [--n 200 --seed 42 --out-json F --data-source alpaca]
```

### Plan and fill (V180-4, V180-5)

```python
# swingbot/core/planning/turtle_soup_plan.py                    # V180-4
RISK_CAP = "risk_cap"; NO_LEVEL_IN_BAND = "no_level_in_band"; PLAN_OTHER = "plan_other"
@dataclass(frozen=True)
class TurtleSoupLevels:
    stop: float | None; tp1: float | None; candidates: tuple[float, ...]; reason: str | None
def in_band(entry: float, stop: float, prices, min_rr: float, max_rr: float) -> list[float]
def turtle_soup_levels(df, index, horizon_key, *, entry, atr_val, level_map=None, scan_params=None) -> TurtleSoupLevels
def turtle_soup_branch(inputs) -> tuple | None       # (stop, tp1, list(candidates), None) or None
def turtle_soup_rejection_reason(df, index, horizon_key, scan_params=None, level_map=None) -> str
    # RISK_CAP | NO_LEVEL_IN_BAND | PLAN_OTHER (levels fine: a gate or the geometry check said no)
# builders.py: _STRUCTURAL_BRANCHES[TURTLE_SOUP] = _turtle_soup_branch (lazy wrapper);
#              _LIFECYCLE_EXEMPT = frozenset({COMPRESSION_SHORT, TURTLE_SOUP})
# params.py:   EXIT_V2_PARAMS[TURTLE_SOUP] = {"trail_atr_mult": 2.5, "tp2": False}
#              PLAN_SHAPES[TURTLE_SOUP] = {"entry_type": "market", "expiry_bars": 1, "tp1_fraction": 1.0,
#                                          "breakeven_trigger_fraction": 1.0, "hold_cap_bars": 10}

# swingbot/core/planning/next_open_entry.py                     # V180-5
NEXT_OPEN_STRATEGIES = frozenset({TURTLE_SOUP})
OPEN_THROUGH_STOP = "open_through_stop"; RISK_CAP = "risk_cap"
GAP_STOP_REASON = "gap_stop"; GAP_TARGET_REASON = "gap_target"
def uses_next_open_fill(plan) -> bool
def next_open_exit(df, signal_index: int, plan, max_holding_days: int) -> ExitResult
def gap_aware_single_leg_walk(df, entry_index: int, entry_price: float, plan, max_holding_days: int) -> ExitResult
    # walks entry_index .. min(entry_index + max_holding_days, n-1); per bar: open <= stop -> loss at open
    # ("gap_stop"); open >= tp1 -> exit at open ("gap_target"; "win" if r > 0 else "scratch"); low <= stop ->
    # loss at stop -1R ("stop"); high >= tp1 -> win at tp1 ("tp1"); v129 acceptance exit; end -> "timeout"
    # at the last close, leg reason TIME_EXIT_REASON + price_basis PROXY_BASIS when the cap was reached
# exit_sim.py: SESSION_ONE_HOLD_CAP = frozenset({COMPRESSION_SHORT, TURTLE_SOUP}); _counts_fill_session(plan);
#              _market_exit(df, signal_index, plan, scale_out, max_holding_days)
```

### Research cell, events, diagnostics (V180-6..V180-8)

```python
# swingbot/core/backtesting/arms/turtle_soup_research.py        # V180-7
RESEARCH_KNOB = "TURTLE_SOUP_RESEARCH_MODE"; RESEARCH_MODES = ("off", "structural"); HORIZON = "2w"
RESEARCH_CELL = {"directions": (), "cells": {("bullish", HORIZON)}}
CANCEL_STATUS = {"open_through_stop": "cancelled_open_through_stop", "risk_cap": "cancelled_risk_cap_fill"}
def research_mode() -> str
def net_r(plan, result) -> float                  # expectancy_attribution.net_r(result.entry_price, plan.stop_loss, plan.direction, result.legs)
def trade_event(ticker, df, signal_date, plan, result, r_net) -> dict
def cancel_event(ticker, signal_date, cancel_reason) -> dict
def plan_none_event(ticker, signal_date) -> dict
# event: {"ticker", "signal_date", "status"} with status "trade" | "plan_none" | CANCEL_STATUS values | "not_triggered";
#   a trade adds "entry_date", "exit_date", "entry_index", "exit_index", "hold_sessions", "outcome",
#   "exit_reason", "r_gross", "r_net", "entry_price", "stop_loss", "tp1"
# StrategyEngine.turtle_soup_events: list[dict]

# swingbot/core/backtesting/arms/turtle_soup_report.py          # V180-8
EARLY_STOP_SESSIONS = 2; SCREEN_CAP = 10; BADGE_MIN_N = 15
STATUSES = ("trade", "risk_cap", "no_level_in_band", "plan_other", "cancelled_open_through_stop",
            "cancelled_risk_cap_fill", "not_triggered", "position_open")
def signal_rows(ticker, df, events, window, *, params, horizon_key="2w") -> list[dict]
def screen_outcomes(df, positions) -> dict
def drop_shares(rows) -> dict
def sweep_depth_summary(rows) -> dict
def early_stop_share(rows) -> float | None
def exit_mix(rows) -> dict
def regime_split(rows, spy) -> dict
def clustering(rows) -> dict
def universe_share(rows, intervals) -> dict
def badge_check(trades, *, min_n: int = BADGE_MIN_N) -> dict
def measure(frames: dict, window, params, *, spy, intervals) -> dict
# scripts/backtest/measure_arms.py: TURTLE_SOUP_KNOB, turtle_soup_sidecar(blob, delta, universe, spec) -> dict | None,
#   written to <out stem>.turtle_soup.json
# scripts/backtest/turtle_soup_report.py --arms FILE [--out-json F] [--min-n 15]
```

## Open risks and decisions the controller should check

- **Costs on the added rows only.** Baseline rows stay gross (byte-identical, as the brief requires); Turtle Soup rows are net of 5 bps a side plus `commission_r()` (0.02R at the default basis). Clause 2 (ΔExpR non-inferiority) and the badge's `expectancy_r > 0` therefore compare a net cohort against a gross book. The bias runs **against** the arm (conservative, never favourable). Clause 1 and the badge win rate are unaffected, because costs never flip win/loss classification. The results doc states this.
- **"No level in the band" is read literally.** `select_structural_target` alone returns a synthetic `entry + 2.5R` target when the nearest level lies beyond the band. The spec says "No plan when no level falls in the band", so candidates are pre-filtered to the band and that fallback never fires.
- **Fill bar.** The walk includes the fill bar itself, matching the screen's bars t+1..t+cap and live intraday monitoring. On that bar the open is the fill, so only "open ≥ target" can gap (an exit at the fill, 0R gross, `scratch`). The hold cap is 10 sessions with the fill as session 1. This is identical to the screen's `CAP = 10` accounting (exit at the close of t+10) and to `_hold_cap_bars`' compression semantics.
- **Two risk-cap readings.** The builder drops at 3% from the signal close (the spec routes the stop "via `_bounded_stop`"), and the fill re-checks at 3% from the open. They are reported apart (`risk_cap`, `cancelled_risk_cap_fill`).
- **Per-fold N** counts the **decided** added Turtle Soup trades (the gate's existing `n` counts decided trades), which is stricter than all added trades.

## Parallelisation

| Task | May run alongside | Sequential edge and why |
|---|---|---|
| V180-1 | V180-2 | first task: creates the worktree the others work in |
| V180-2 | V180-1 | disjoint files (`acceptance.py`, `backtest_wf.py`, `validate_component.py`); no contract dependency |
| V180-3 | V180-4 | after V180-2: imports `win_rate_statistic` / `delta_pooled_win_rate` (contract dependency) |
| V180-4 | V180-3 | after V180-1: same file `strategy_types.py` and the `TURTLE_SOUP` constant |
| V180-5 | V180-6 | after V180-4: the fill risk cap reads `plan_stop_ceiling`, which returns the 3% DROP ceiling only once `STRUCTURAL_DROP_STRATEGIES` exists; tests build plans with `PLAN_SHAPES[TURTLE_SOUP]` |
| V180-6 | V180-3, V180-4, V180-5 | disjoint files (`config.py`, `.env.example`, `scan_params.py`, `reachability.py`); no contract dependency |
| V180-7 | — | after V180-1, V180-4, V180-5, V180-6: the engine runs the signal, the plan, the fill and the knob end to end |
| V180-8 | — | after V180-7: reads `turtle_soup_events` and `turtle_soup_research`; same file `measure_arms.py` is touched by no other task |
| V180-9 | — | after every code task: the plan's single full-suite run, then the merge and bump |
| V180-10 | — | after V180-9: runs the merged code on `main`; the frozen block must be committed before any TRAIN bar is read |
| V180-11 | — | after V180-10's gate (reachability refused stops the plan) and after V180-2/V180-3 are on `main` (spec § 4) |
| V180-12 | — | after V180-11's gate (stage 0 refused stops the plan) |
| V180-13 | — | after V180-12's gate; needs the partner's go |
| V180-14 | — | after whichever of V180-10..V180-13 ended the funnel: the record reads their outputs |

At most 2 implementers at once: V180-1 with V180-2, then V180-3 with V180-4, then V180-5 with V180-6. V180-10..V180-13 each launch a long `backtest-runner` job, one at a time (shared tree, CPU).

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-21-v180-turtle-soup-entry_1-signal-instrument-and-plan.md` | V180-1..V180-4 | live signal and mask, A1/A3 pooled statistic, A2 shift-replay permutation, structural plan builder |
| 2a | `2026-10-21-v180-turtle-soup-entry_2a-fill-engine-and-research-cell.md` | V180-5..V180-7 | next-open fill and gap-aware walk, research knob, StrategyEngine cell with costs and events |
| 2b | `2026-10-21-v180-turtle-soup-entry_2b-diagnostics-and-badge.md` | V180-8 | diagnostics sidecar and badge check |
| 3 | `2026-10-21-v180-turtle-soup-entry_3-merge-runs-and-close-out.md` | V180-9..V180-14 | full suite and merge, frozen pre-registration, stages −1 to 3, record, /panel, /close-out |

## Task ledger

| Task | Title | Part | Model | Files created / modified | Creates (consumed later) |
|---|---|---|---|---|---|
| V180-1 | Live Turtle Soup signal, mask and screen parity | 1 | opus | C `swingbot/core/market/turtle_soup.py`, `tests/market/test_turtle_soup_signal.py`; M `swingbot/core/market/strategy_types.py`, `swingbot/core/market/entry_filters.py` | `TURTLE_SOUP`, `STRATEGY_GATES[TURTLE_SOUP]`, `CHANNEL`, `MIN_AGE`, `sweep_frame(df)`, `turtle_soup_signal(df)`, `turtle_soup_entries(df, horizon_key, params=None)`, `ENTRY_FUNCS[TURTLE_SOUP]` |
| V180-2 | A1/A3: pooled ΔWR selectable in acceptance, fold rows and validate_component | 1 | opus | M `swingbot/core/backtesting/acceptance.py`, `swingbot/core/backtesting/backtest_wf.py`, `scripts/backtest/validate_component.py`; C `tests/backtesting/test_acceptance_pooled_wr.py`, `tests/backtesting/test_wf_pooled_fold_row.py`, `tests/backtesting/test_validate_component_pooled.py` | `delta_pooled_win_rate`, `WR_STATISTICS`, `win_rate_statistic(name)`, `evaluate(..., wr_statistic=)`, `AcceptanceResult.wr_statistic`, `win_rate_fold_row(test_year, b, c, *, wr_statistic=)`, CLI `--wr-statistic`, `--train-effect-from-arms` |
| V180-3 | A2: circular-shift replay permutation on the A1 statistic | 1 | opus | C `swingbot/core/backtesting/arms/shift_permutation.py`, `tests/backtesting/arms/test_shift_permutation.py`, `tests/backtesting/test_permutation_shift_replay.py`; M `scripts/backtest/permutation_test.py` | `SHIFT_RANGE`, `NotAdditive`, `ReplayMismatch`, `additive_added`, `shift_permutation(...)`, `strategy_shift_replay(...)`, CLI `--shift-replay` |
| V180-4 | Structural plan: drop scope, plan shape, Turtle Soup branch | 1 | opus | C `swingbot/core/planning/turtle_soup_plan.py`, `tests/planning/test_turtle_soup_plan.py`; M `swingbot/core/market/strategy_types.py`, `swingbot/core/planning/stop_scope.py`, `swingbot/core/planning/params.py`, `swingbot/core/planning/builders.py`, `tests/planning/test_strategy_branch_table.py` | `STRUCTURAL_DROP_STRATEGIES`, `PLAN_SHAPES[TURTLE_SOUP]`, `EXIT_V2_PARAMS[TURTLE_SOUP]`, `TurtleSoupLevels`, `in_band`, `turtle_soup_levels`, `turtle_soup_branch`, `turtle_soup_rejection_reason`, `RISK_CAP`, `NO_LEVEL_IN_BAND`, `PLAN_OTHER`, `_LIFECYCLE_EXEMPT` |
| V180-5 | Next-open fill, open-through-stop cancel, fill risk cap and gap-aware single leg | 2a | opus | C `swingbot/core/planning/next_open_entry.py`, `tests/planning/test_next_open_entry.py`; M `swingbot/core/planning/exit_sim.py` | `NEXT_OPEN_STRATEGIES`, `OPEN_THROUGH_STOP`, `GAP_STOP_REASON`, `GAP_TARGET_REASON`, `uses_next_open_fill`, `next_open_exit`, `gap_aware_single_leg_walk`, `SESSION_ONE_HOLD_CAP`, `_counts_fill_session`, `_market_exit` |
| V180-6 | Research knob TURTLE_SOUP_RESEARCH_MODE | 2a | haiku | M `swingbot/config.py`, `.env.example`, `swingbot/scan_params.py`, `swingbot/core/backtesting/arms/reachability.py`; C `tests/backtesting/test_turtle_soup_knob.py` | config `TURTLE_SOUP_RESEARCH_MODE` (`off`/`structural`, default `off`), `ScanParams.turtle_soup_research_mode`, `REGISTRY["TURTLE_SOUP_RESEARCH_MODE"]` |
| V180-7 | StrategyEngine research cell, net-of-cost rows, events, subset fixture | 2a | opus | C `swingbot/core/backtesting/arms/turtle_soup_research.py`, `tests/backtesting/test_turtle_soup_engine.py`; M `swingbot/core/backtesting/arms/strategy_engine.py`, `swingbot/core/backtesting/backtest.py` | `RESEARCH_KNOB`, `RESEARCH_MODES`, `RESEARCH_CELL`, `HORIZON`, `CANCEL_STATUS`, `research_mode()`, `net_r(plan, result)`, `trade_event`, `cancel_event`, `plan_none_event`, `StrategyEngine.turtle_soup_events` |
| V180-8 | Diagnostics sidecar and the stage-3 badge check | 2b | opus | C `swingbot/core/backtesting/arms/turtle_soup_report.py`, `scripts/backtest/turtle_soup_report.py`, `tests/backtesting/test_turtle_soup_report.py`, `tests/backtest_scripts/test_measure_arms_turtle_sidecar.py`; M `scripts/backtest/measure_arms.py` | the report contract above, `TURTLE_SOUP_KNOB`, `turtle_soup_sidecar`, the `<out stem>.turtle_soup.json` sidecar, CLI `turtle_soup_report.py --arms` |
| V180-9 | Full suite, merge, bot patch bump | 3 | sonnet | M `VERSION.json`, `version_history.json` (regenerated) | merged branch on `main` |
| V180-10 | Frozen pre-registration block and stage −1 pilot (gate) | 3 | sonnet | C `docs/superpowers/results/2026-10-21-v180-turtle-soup-preregistration.md`, `docs/superpowers/results/v180/pilot-reachability.txt`, `docs/superpowers/results/v180/pilot.turtle_soup.json` | the frozen block; reachability verdict |
| V180-11 | Stage 0: A3 paired MDE on fold-train (gate) | 3 | sonnet | C `docs/superpowers/results/v180/mde.txt`, `docs/superpowers/results/v180/selection.turtle_soup.json`; M the pre-registration doc (`## Readings`) | A1 TRAIN point, paired MDE, RESOLVABLE/REFUSED |
| V180-12 | Stage 1 statement and stage 2 walk-forward (gate) | 3 | sonnet | C `docs/superpowers/results/v180/walkforward.json`, `docs/superpowers/results/v180/walkforward.turtle_soup.json`; M the pre-registration doc | stage-2 verdict |
| V180-13 | Stage 3: the one VALIDATION shot (partner go) | 3 | sonnet | C `docs/superpowers/results/v180/permutation.json`, `docs/superpowers/results/v180/validation-gate.md`, `docs/superpowers/results/v180/validation-gate.json`, `docs/superpowers/results/v180/badge.json`, `docs/superpowers/results/v180/validation.turtle_soup.json`; M the pre-registration doc | stage-3 verdict |
| V180-14 | Results doc, ledger row, closed row, /panel, /close-out | 3 | sonnet | C `docs/superpowers/results/<date>-v180-turtle-soup-result.md`; M `docs/superpowers/results/preregistration-ledger.jsonl`, `docs/claude/backtest-methodology.md`, `.claude/hooks/guardrails.py`; plan and spec moved by `/close-out` | ledger row `v180-turtle-soup-structural` |

Arm files (large, never committed) live under `logs/v180/<stage>.json`, with the sidecar beside each one as `logs/v180/<stage>.turtle_soup.json`. The run tasks copy each sidecar into `docs/superpowers/results/v180/`.

## Panel review

Run at close-out over the v180 merge diff, the pre-registration and the result doc (funnel ended NO-LIFT at Stage 0). No finding changes a reading or the verdict.

- veteran-trader BLOCKING (next-open cancel is not reproducible by a pre-open market order) -- rejected for v180: verdict-neutral (the sign of A1 alone refused the shot) and the code is masked. Partner decision 2026-10-23: carried as a reuse caveat in the result doc; any live use must fill those cases or prove a conditional order exists.
- quant-researcher: ExpR comparator (+0.07R raw vs +0.316R paired), decided-N wording, ExpR prediction miss stated (about -0.23R), non-replication of the screen noted, re-run rule cited as a plan-level call, broken spec link (moved at close-out) -- applied in the result doc.
- quant-researcher: A2 p-value has no +1 correction (`shift_permutation.py:73`); A2 null is not count-matched to the added-row count (`shift_permutation.py:54-58`); A3 is a strict power gate for small additive arms (~45x dilution) -- ADVISORY, left open for any future additive-arm funnel.
- veteran-trader: gap bucket merges gap_stop and gap_target, trades-per-day, descriptive-n labelling -- applied as wording; slippage at stops, survivorship, MOO/day-10 exit statement -- ADVISORY, carried to any reuse.
- technical-analyst: trigger, stop and target correct and lookahead-free; check `_LIFECYCLE_EXEMPT` against the chart overlay before any promotion -- ADVISORY.
