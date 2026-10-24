# v192 — Wait for a reclaim when a market plan's next open gaps toward its stop: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V192-8:" -A 300 docs/superpowers/plans/2026-10-24-v192-gap-toward-stop-reclaim_2-live-path.md`.

**Bump:** bot patch
**Edge:** expectancy — removes market-entry trades whose next open has already moved toward the stop and never trades back to the planned entry; prediction on the selected cell: decided win rate +1.5pp or more, ΔExpR > 0, removed population WR lower and ExpR ≤ 0 (v72 clause 6). The +1.5pp is a judgement, not derived from the autopsy cell.
**Screen:** exempt (post-signal)
**Spec:** [2026-10-24-v192-gap-toward-stop-reclaim-design.md](../specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md)
**Brief:** `.superpowers/briefs/2026-10-24-v192-gap-toward-stop-reclaim.md`
**Worktree:** every code task runs in `.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim` (branch of the same name, created in V192-1's first step; `docs/claude/document-lifecycle.md`). The measurement tasks (V192-22..V192-25) run from the same worktree and read the main checkout's git-ignored training data by absolute path. The merge to `main` is V192-26's last step.

## Goal

In both 2026 autopsy windows the live book's worst bucket was the trades
whose fill-day open sat beyond the planned entry **toward the stop** (the
autopsy's `open_gap_bucket=favourable`: a cheaper fill, a worse position):
N = 226, WR 35.4%, net ExpR −0.467 over 2026-07-20..2026-10-21, and N = 88,
WR 21.6% in the current exit-model era. Those windows overlap the 2026
holdout, so they motivate and never select. Today a market plan fills at the
alert price whatever the next session does, so a plan whose next open has
already broken toward the stop is entered anyway.

Once this ships, two settings exist, both inert at their defaults.
`MARKET_ENTRY_NEXT_OPEN` (default off) makes every market plan wait for the
next session's open: it is built PENDING, the alert reads "Enter at the open
(market-on-open)", and at the open the plan fills at the open, or is
cancelled when the open is at or through the stop (`open_through_stop`) or
past the 2% stop ceiling (`risk_cap`). A stop crossed in extended hours
before that open cancels the plan after two consecutive confirming polls.
`GAP_RECLAIM_ATR` (`g`, default 0, honoured only with the first knob on)
adds the veto: when the open sits at or beyond `X = E ∓ g × ATR14` (stored
on the plan at creation, rounded to the tick away from `E`), the bot posts a
DAY buy-stop (sell-stop for a short) at the planned entry `E` and fills only
if the session trades one tick through `E`; otherwise it cancels at the
close with `gap_no_reclaim`. Every cancel and the stop-order instruction
reach the execution feed and Following followers.

How it works, in idea: one pure rule module
(`swingbot/core/planning/gap_reclaim.py`) decides at the open from the
plan's own stored values (`trigger_price`, `stop_loss`, `reclaim_level`),
and both the live `PlanManager` step and the replay call it, so live and
replay cannot drift. The replay gains a next-open market fill that hands off
to each plan's normal exit walk (scale-out where the plan uses it), after a
fill-bar check of the stop and TP1 (stop-first); both arms of the
measurement run on it, so the comparison isolates the veto.

What it leaves alone: stop-entry and limit plans, v180's Turtle Soup
next-open path, every stop, target, gate and size, today's v1 close fill
when the knobs are off, and the dead extended-hours config fields (the
premarket cancel is new code with its own constant).

Success is measured twice. Code: a flag-off golden captured before any
change shows replay output, arm rows and plan JSON byte-identical with both
knobs off; the rule's bullish and bearish edges, no-lookahead ATR, the live
open decision, the reclaim wait and the premarket cancel are pinned by
tests. Edge: the v72 win-rate funnel through `measure_arms.py` with a new
baseline knob delta, scored on frozen strata (removed / re-priced / added /
unchanged), Stage −1 reachability through one VALIDATION shot on instrument
v1 with `data_source = alpaca`. A pass is recorded and both knobs stay off
until the partner decides; `MARKET_ENTRY_NEXT_OPEN` itself needs its own
non-inferiority pre-registration before it can go live.

## Architecture

- **Flag-off golden first (V192-1).** Replay `ExitResult` fields for market (confluence and strategy), stop-entry, limit and v180 Turtle Soup plans, `run_arm` rows for both engines on one fixture ticker, and `plan_to_dict` snapshots of market plans, captured on unmodified code into `tests/fixtures/v192/`.
- **Config (V192-2).** Two `Field`s, two `ScanParams` slots, two reachability rows; `config.enforce_gap_reclaim_coupling()` at the end of every `_apply_env` (import and SIGHUP reload) zeroes `GAP_RECLAIM_ATR` when `MARKET_ENTRY_NEXT_OPEN` is off, with `log.error`; `arms.knobs.apply_knobs` raises on the same combination in the merged arm config.
- **Plan fields (V192-3).** `TradePlanV2.reclaim_atr`, `reclaim_level`, `reclaim_session`, all omit-when-None in `plans.doc` JSONB; no migration.
- **Rule (V192-4).** `gap_reclaim.py`: tick, Wilder ATR14 through the creating bar, `X`, the open decision, the reclaim touch, the replay reclaim fill price, the builder stamp.
- **Builders (V192-5).** With the knob on, market plans (v180 Turtle Soup excepted) are built PENDING with `entry_price=None` and stamped through `gap_reclaim.stamp_next_open`.
- **Replay (V192-6, V192-7).** `swingbot/core/planning/market_next_open.py`: the next-open fill, the fill-bar check (stop and TP1, stop-first, the scale-out runner continuing from the fill bar), the veto branch, and an observer hook (`observing`) the census reads. `exit_sim._market_exit` dispatches to it for a waiting market plan; `_counts_fill_session` counts the fill session for such plans.
- **Live (V192-8, V192-9).** `swingbot/core/planning/market_open.py` (session timing: which session's open decides, extended-hours phase, session close) and a `PlanManager._step_market_open` ahead of `_step_pending`: premarket debounce cancel, the open decision, the reclaim wait and fill, the end-of-session cancel, a missed-open expiry.
- **Feed and followers (V192-10, V192-11).** Three new events (`cancelled_open_through_stop`, `cancelled_gap_no_reclaim`, `gap_reclaim_order`) wired through `NOTICE_EVENTS`, `_TRANSITION_LOG`, the `_on_event` placeholder discard (split first: cc 15), `instructions`, `kinds`, `lifecycle_embeds`, `execution_embeds`, `follow_notify`, and `render_feed_samples`.
- **Alert (V192-12)** and **live integration (V192-13)**: market-on-open wording and the `X` reference line; analyze/scan_run accept a waiting market plan, the trade is logged at the fill; a live/replay parity test pins `E`, `a_t`, `X`.
- **Measurement code (V192-14..V192-19).** `measure_arms.py --baseline-knob` with a stamped `baseline_knob_delta`; the census sidecar `<out stem>.gap_reclaim.json`; `gap_reclaim_clauses.py` (strata split, mechanism and volume clauses, SKIPPED-fails verdict, re-priced-fixed permutation null, Stage 1 eligibility, reports); CLI flags in `validate_component.py` and `permutation_test.py`; the report script; the autopsy `--entry-type` filter.
- **Docs (V192-20)**, **runs (V192-21..V192-25)** through `backtest-runner`, **release (V192-26)**: bump, the single full-suite run, merge.

## Global Constraints

- Every knob ships inert: `MARKET_ENTRY_NEXT_OPEN` default `"false"`, `GAP_RECLAIM_ATR` default `"0"`. With both at default, replay `ExitResult`s, arm rows and plan dicts equal the V192-1 golden byte for byte; no plan gains `reclaim_atr`, `reclaim_level` or `reclaim_session`; every market plan is built ACTIVE with `entry_price = close` exactly as today.
- Coupling: `GAP_RECLAIM_ATR > 0` is honoured only with `MARKET_ENTRY_NEXT_OPEN` on. Live: config load and reload set it to `0.0` and log at ERROR (`enforce_gap_reclaim_coupling`). Measurement: `apply_knobs` raises `ValueError(GAP_RECLAIM_NEEDS_NEXT_OPEN)` on the merged arm config; the component `--knob` list therefore carries both knobs and the baseline carries `MARKET_ENTRY_NEXT_OPEN=true` alone.
- Scope: market-entry plans only, confluence and strategy sources, bullish and bearish. v180 Turtle Soup (`next_open_entry.uses_next_open_fill(plan)`) keeps its own path and is never built PENDING by this plan. Stop-entry and limit plans are untouched.
- Frozen definitions: `E = plan.trigger_price`; `a_t` = Wilder ATR14 (`swingbot/core/market/indicators.atr(df, 14)`) of `df.iloc[:t + 1]`, `None` when NaN, ≤ 0 or fewer than 15 bars (then no veto stamp: the plan fills at the open as the baseline does); `g ∈ {0.10, 0.25, 0.50}`; `X = E − g·a_t` (bull, floored to the tick) / `E + g·a_t` (bear, ceiled to the tick); tick `0.01` when `E ≥ 1`, else `0.0001`. `X` and `a_t` are computed once at creation and never rewritten (reload, knob flip, restart).
- The open decision (`gap_reclaim.decide_at_open`, one function for live and replay), in this order: open at or beyond the stop → `open_through_stop`; `reclaim_level` set and open at or beyond `X` toward the stop (bull `open ≤ X`, bear `open ≥ X`) → `reclaim_wait`; `planned_loss_pct(open, stop) > plan_stop_ceiling(plan)` → `risk_cap`; else `open` (fill at the open).
- Reclaim: bull `High ≥ E + tick`, bear `Low ≤ E − tick`, same session only. Replay fills at `E + tick` (bull) / `E − tick` (bear), the one adverse tick that models the stop order's slippage (the v1 arm replay applies no frictions in either arm). Live fills at `E` (the DAY stop order's price), on the first RTH poll with `price ≥ E + tick` (bull) / `≤ E − tick` (bear).
- Fill bar (both arms, `market_next_open.next_open_fill_bar`): stop touched on the fill bar → full loss at the stop (−1R), even when TP1 is also touched (stop-first); else TP1 touched → the single-leg TP1 win, or for a scale-out plan the TP1 leg banked and `exit_sim._runner_phase` continuing from the fill bar; else the normal `_walk_for` walk from the fill bar. An ambiguous reclaim bar (reclaim and stop both touched) is therefore −1R. `_fill_bar_exit`'s 0R `gap_through_stop` scratch is not reused: an open at or through the stop is a `not_triggered` cancel in both arms.
- Hold cap: `_counts_fill_session(plan)` is also true for a waiting market plan (`gap_reclaim.waits_for_open(plan)`), so a plan with `hold_cap_bars` counts the fill session as session 1. Confluence plans carry no `hold_cap_bars` and keep `max_holding_days` bars after the fill (the spec's "nothing changes for them").
- Live timing: the deciding session is the first NYSE session whose 09:30 ET open is at or after the plan's `issued_at` (fallback: the session after `created_at`). The first poll with `is_regular_session(now)` on that session decides at its price. Extended-hours polls (`is_tape_open` and not `is_regular_session`) before that open run the stop-cross debounce: `PREMARKET_STOP_CONFIRM_POLLS = 2` consecutive polls at or through the stop cancel `open_through_stop` with detail `phase="premarket"`; a poll back inside the stop resets the count. A first RTH poll that lands on a later session than the deciding one cancels `cancelled_expired` with reason `missed_open`. A plan resting for its reclaim (`reclaim_session` set) cancels `gap_no_reclaim` on the first poll after `session_close(reclaim_session)`.
- Event and reason names, exact strings: transitions `cancelled_open_through_stop`, `cancelled_gap_no_reclaim`, `gap_reclaim_order` (plus existing `filled`, `cancelled_risk_cap`, `cancelled_expired`); `record_transition` reasons `next_open_fill`, `gap_reclaim_fill`, `open_through_stop`, `gap_no_reclaim`, `risk_cap`, `missed_open`. Replay `cancel_reason`s `open_through_stop`, `gap_no_reclaim`, `risk_cap`.
- Sizing unchanged (`gap_sizing.size_for_plan` on `E` and the stop); the 2% dollar cap holds; no order is placed anywhere (paper only).
- Complexity: every function written or changed ends `< 15`. `PlanManager._on_event` (15), `poll` (20), `_step_active` (21) and `measure_arms.main` (14) gain no branch — new logic lives in helpers or tables; `_on_event`'s discard tuple becomes the module set `PLACEHOLDER_DISCARD_EVENTS`. `python scripts/dev/complexity_gate.py` passes after each code task.
- NO-LOOKAHEAD: `a_t` reads bars through `t` only; a test mutates bar `t + 1` and sees `a_t` and `X` unchanged (V192-4, V192-5, V192-13).
- Frozen measurement block: instrument **v1**, `--data-source alpaca`, universe `measure_arms.cached_universe()` (the watchlist-era universe v139/v180 used), producer stages `pilot` (Stage −1), `selection` (fold-train 2018-06-01..2022-12-31, Stages 0 and 1), `walkforward` (folds 2021/2022/2023, Stage 2), `validation` (2024-01-01..2025-12-31, Stage 3, once). Intervals `week_cluster_bootstrap` (`cluster="week"`). Stage 1 winner: highest whole-window fold-train ΔWR (standardised, `blob["baseline"]`/`blob["component"]`, never the expanding folds pooled) among cells with point ΔExpR ≥ −0.01R, ties to the smaller `g`, plateau via `selection.select_cell(..., "GAP_RECLAIM_ATR", tie="smaller")`; a spike does not proceed. Stage 3: all six v72 clauses, mechanism and volume from the strata, a SKIPPED clause fails.
- Strata (frozen before TRAIN): **removed** = baseline keys absent from the component (the `gap_no_reclaim` cancels); **re-priced** = keys in the census's reclaimed set present in both arms; **added** = component keys absent from the baseline; **unchanged** = every other paired key. `open_through_stop` and `risk_cap` cancels are `not_triggered` in both arms and excluded from both. Clause 6: removed WR < unchanged WR and removed ExpR ≤ 0; volume cut = removed ÷ baseline N ≤ `VOLUME_MAX_CUT_PCT`; geometry on every kept component trade, re-priced included.
- Permutation (clause 5): the v72 removal-label null of `permutation_test.arm_pair_permutation` (ticker-circular shift of the removed labels over the baseline), with re-priced trades held at their component version in every null draw, so the null rotates only which trades the veto removes (`gap_reclaim_clauses.repriced_permutation`).
- Measurement in the worktree: `MEASURE_ARMS_UNIVERSE=cache`, `HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data` and `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache` set in the same command; results under `docs/superpowers/results/v192/`. Long runs go to `backtest-runner`, one runner at a time, chunked per `g`; 15 min+ prints a percent.
- Stage 3 runs once, refused when its output exists and without `--preregistration docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md`. No closed pre-registration is re-run; no threshold, window, grid or MDE ceiling changes after fold-train is read. Next-open vs close-fill is read on fold-train only, never on VALIDATION.
- Stored records change additively only (`docs/claude/schema-evolution.md`): plan doc keys `reclaim_atr`, `reclaim_level`, `reclaim_session`; stamp key `baseline_knob_delta` (present only when non-empty). `ArmTrade` gains no field. The DB round trip runs against the shared `swing-db` (`/replicate-prod-db` first, CLAUDE.md) and is never left skipped at close-out.
- Per-task verification is `python scripts/dev/testrun.py file <test>`; the full suite runs once, in V192-26. New tests join existing directories (`tests/planning/`, `tests/backtesting/arms/`, `tests/presentation/`, `tests/scanning/`, `tests/backtest_scripts/`, `tests/scripts/`); no new `tests/` directory.
- Commits: one scoped commit per task, in the worktree; never `--no-verify`; the controller merges.

## Contracts

```python
# swingbot/config.py                                                    (V192-2)
Field("MARKET_ENTRY_NEXT_OPEN", "MARKET_ENTRY_NEXT_OPEN", "Trade Filters & Risk",
      "Market plans wait for the next open (v192)", type="checkbox", default="false")
Field("GAP_RECLAIM_ATR", "GAP_RECLAIM_ATR", "Trade Filters & Risk",
      "Gap-toward-stop reclaim threshold g x ATR14 (v192)", default="0", min=0, max=1.0, step=0.05)  # float caster
# both in _SEARCH_CLASSES["searchable"]
def enforce_gap_reclaim_coupling() -> bool      # True when it zeroed GAP_RECLAIM_ATR; called last in _apply_env

# swingbot/scan_params.py                                               (V192-2)
ScanParams.market_entry_next_open: bool = False
ScanParams.gap_reclaim_atr: float = 0.0

# swingbot/core/backtesting/arms/knobs.py                               (V192-2)
GAP_RECLAIM_NEEDS_NEXT_OPEN = "GAP_RECLAIM_ATR > 0 needs MARKET_ENTRY_NEXT_OPEN on"
# apply_knobs(delta): after setting the delta, raises ValueError(GAP_RECLAIM_NEEDS_NEXT_OPEN)
# when config.GAP_RECLAIM_ATR > 0 and not config.MARKET_ENTRY_NEXT_OPEN; config is restored first

# swingbot/core/planning/plan_types.py                                  (V192-3)
TradePlanV2.reclaim_atr: float | None = None       # a_t, price units
TradePlanV2.reclaim_level: float | None = None     # X
TradePlanV2.reclaim_session: str | None = None     # ISO date of the session the plan rests at E (live only)
# all three in _OMIT_WHEN_NONE

# swingbot/core/planning/gap_reclaim.py                                 (V192-4, new)
OPEN_THROUGH_STOP = "open_through_stop"; GAP_NO_RECLAIM = "gap_no_reclaim"; RISK_CAP = "risk_cap"
FILL_OPEN = "open"; RECLAIM_WAIT = "reclaim_wait"; ATR_PERIOD = 14; MIN_ATR_BARS = 15
def tick_for(price: float) -> float
def atr_at(df, index: int) -> float | None
def reclaim_level_for(entry: float, atr: float, g: float, direction: str) -> float
def effective_g() -> float                         # config.GAP_RECLAIM_ATR if config.MARKET_ENTRY_NEXT_OPEN else 0.0
def next_open_applies(plan) -> bool                # market plan, MARKET_ENTRY_NEXT_OPEN on, not a v180 next-open strategy
def waits_for_open(plan) -> bool                   # entry_type == "market" and status == PlanStatus.PENDING
def stamp_next_open(plan, df, index: int) -> None  # entry_price=None; reclaim_atr/reclaim_level when effective_g() > 0 and atr_at is not None
def gap_toward_stop(plan, open_price: float) -> float   # bull E - open, bear open - E
def decide_at_open(plan, open_price: float) -> str      # OPEN_THROUGH_STOP | RECLAIM_WAIT | RISK_CAP | FILL_OPEN
def reclaim_touched(plan, high: float, low: float) -> bool
def reclaim_fill_price(plan) -> float              # replay: E + tick (bull) / E - tick (bear)

# swingbot/core/planning/market_next_open.py                            (V192-6, V192-7, new)
@dataclass(frozen=True)
class NextOpenDecision:
    ticker: str; strategy: str; horizon_key: str; source: str; direction: str
    signal_date: str; entry: float; stop: float; open_price: float | None
    atr: float | None; reclaim_level: float | None; gap_atr: float | None
    decision: str            # gap_reclaim.FILL_OPEN | RECLAIM_WAIT | OPEN_THROUGH_STOP | RISK_CAP | "no_bar"
    reclaimed: bool; ambiguous: bool; fill_price: float | None
def observing(callback) -> ContextManager[None]    # callback(NextOpenDecision) for every next-open market plan simulated inside
def next_open_fill_bar(df, j: int, fill: float, plan, scale_out: bool,
                       max_holding_days: int) -> ExitResult | None
def next_open_market_exit(df, signal_index: int, plan, scale_out: bool,
                          max_holding_days: int) -> ExitResult
# exit_sim._market_exit: v180 first, then waits_for_open(plan) -> next_open_market_exit, else today's close fill
# exit_sim._counts_fill_session(plan): ... or gap_reclaim.waits_for_open(plan)

# swingbot/core/planning/market_open.py                                 (V192-8, new)
PREMARKET_STOP_CONFIRM_POLLS = 2
def deciding_session(plan) -> dt.date | None       # first NYSE session whose 09:30 ET open is >= issued_at
def market_phase(plan, now) -> str                 # "before" | "extended" | "open" | "missed" | "waiting" | "after_close"

# swingbot/core/planning/plan_manager.py                                (V192-8, V192-9, V192-11)
PlanManager._step_market_open(self, plan, price: float, now=None) -> list[PlanEvent]   # _step routes waits_for_open(plan) here
PlanManager._premarket_hits: dict[str, int]        # plan_id -> consecutive extended-hours polls through the stop
NOTICE_EVENTS |= {"cancelled_open_through_stop", "cancelled_gap_no_reclaim", "gap_reclaim_order"}   # V192-11
PLACEHOLDER_DISCARD_EVENTS = frozenset({"cancelled_expired", "cancelled_invalidated", "cancelled_risk_cap",
                                        "cancelled_open_through_stop", "cancelled_gap_no_reclaim"})  # V192-11
# PlanEvent details: filled {"entry_price", "live_price", "fill": "open"|"reclaim"};
#   gap_reclaim_order {"entry_price": E, "open_price", "reclaim_level": X, "order": "buy_stop"|"sell_stop", "tif": "DAY"};
#   cancelled_open_through_stop {"live_price", "phase": "open"|"premarket"};
#   cancelled_gap_no_reclaim {"entry_price": E, "session": ISO date}

# swingbot/core/presentation/kinds.py                                   (V192-10)
Kind.RECLAIM_ORDER = KindSpec(Family.ENTRY, "STOP ORDER AT ENTRY")
# instructions._CANCEL_LEADS / _BUILDERS / _cancel_why, lifecycle_embeds.PLAN_EVENT_KINDS,
# execution_embeds kind map: the three new transitions
# follow_notify (V192-11): _BY_TRANSITION {"cancelled_open_through_stop": "closed_other",
#   "cancelled_gap_no_reclaim": "closed_other", "gap_reclaim_order": "reclaim_order"};
#   _KIND_BY_EVENT["reclaim_order"] = Kind.RECLAIM_ORDER;
#   _CLOSED_OTHER_KIND {"cancelled_open_through_stop": Kind.INVALIDATED, "cancelled_gap_no_reclaim": Kind.EXPIRED}

# swingbot/core/presentation/instructions.py                            (V192-12)
def market_on_open_lines(plan) -> list[str]        # ["Enter at the open (market-on-open)", the X reference line when reclaim_level is set]

# scripts/backtest/measure_arms.py, arms/provenance.py                  (V192-14)
# --baseline-knob ATTR=value (repeatable, optional); produce(stage, delta, *, baseline_delta=None, ...)
# _run_arm_all / _produce_population take the baseline delta in place of {}
# build_stamp(..., baseline_knob_delta=None): key "baseline_knob_delta" only when non-empty
# static_refusal / population_refusal run on the baseline delta too

# swingbot/core/backtesting/arms/gap_reclaim_census.py                  (V192-15, new)
SIDECAR_SUFFIX = "gap_reclaim"
def row_key(row: dict) -> tuple                    # (ticker, strategy, horizon_key, signal_date, source, direction) == ArmTrade.key
def census_ticker(ticker, df, engines, horizons, signal_window, delta) -> list[dict]   # dataclasses.asdict(NextOpenDecision) rows
def census(universe, engines, horizons, signal_window, delta, *, workers=None) -> list[dict]
def reachability_summary(rows: list[dict]) -> dict # per (horizon, direction): market_plans, armed, reclaimed, ambiguous,
                                                   # open_through_stop, risk_cap; gap_atr quantiles; verdict REACHABLE | refused:zero-diff
def repriced_keys(rows) -> set[tuple]
def ambiguous_keys(rows) -> set[tuple]
# measure_arms.gap_reclaim_sidecar(blob, delta, universe, spec) -> dict | None, registered in _SIDECARS

# swingbot/core/backtesting/acceptance.py                               (V192-16)
def verdict_of(clauses, *, skipped_fails: bool = False) -> str
# evaluate(..., skipped_fails: bool = False)   -- the default keeps every existing verdict

# swingbot/core/backtesting/arms/gap_reclaim_clauses.py                 (V192-16, V192-17, new)
def strata_split(baseline, component, repriced: set) -> dict   # removed, repriced[(bt, ct)], added, unchanged[(bt, ct)], is_subset False
def mechanism_clause(split: dict) -> ClauseResult
def volume_clause(baseline, split: dict) -> ClauseResult
def evaluate_gap_reclaim(baseline, component, repriced: set, *, stage, permutation_p=None,
                         n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> AcceptanceResult   # cluster="week", skipped_fails=True
def strata_rows(split: dict) -> list[dict]
def repriced_permutation(baseline, component, repriced: set, *, n_perm=200, seed=42,
                         statistic=delta_standardised_win_rate) -> dict
def selection_cell(value, baseline, component, *, resolvable, n_resamples, seed) -> CellEval
def ambiguous_sensitivity(baseline, component, ambiguous: set) -> dict
def report(baseline, component, census_rows, *, n_resamples, seed, reference_account=100_000.0,
           risk_pct=1.0) -> dict

# CLI                                                                    (V192-18, V192-19)
# validate_component.py --gap-reclaim   (reachability: census summary beside the zero-diff check;
#                                        selection: axis GAP_RECLAIM_ATR / g / smaller with selection_cell;
#                                        validation: evaluate_gap_reclaim with the sidecar's repriced keys)
# permutation_test.py --arms <file> --gap-reclaim
# scripts/reports/gap_reclaim_report.py --arms <file> [--basis <file>] --out-json <path> --out-md <path>
# scripts/reports/book_autopsy.py --entry-type market|stop_entry|limit
```

## Review Focus

- **A market plan with no usable ATR14** (fewer than 15 completed bars, NaN or zero) with `g > 0` — no `reclaim_level` stamp, the plan fills at the open like the baseline, never a crash: V192-4 (helper) and V192-5 (builder).
- **A sub-$1 instrument** — tick `0.0001` for `X`, the reclaim touch and the replay reclaim fill: V192-4 tests `E = 0.85`.
- **A restart or SIGHUP reload while a plan rests for its reclaim** — `reclaim_session`, `reclaim_level` and `reclaim_atr` unchanged, the open decision is not taken twice, and the plan still cancels at that session's close: V192-9.
- **The bot is down or silent through the deciding open** (first RTH poll lands on a later session, or a holiday follows the alert) — `cancelled_expired` / `missed_open`, never a fill at a stale price: V192-8.
- **A bearish plan** — the mirror of every rule (ceil `X`, `open ≥ X`, `Low ≤ E − tick`, sell-stop copy): a bearish twin of each bullish rule test in V192-4, V192-6, V192-7, V192-8 and V192-10.

## Parallelisation

| Task | May run alongside | Sequential edge and why |
|---|---|---|
| V192-1 | — | first: creates the worktree and captures the golden on unmodified code; every later code task changes code the golden pins |
| V192-2 | V192-3, V192-16 | after V192-1; files `config.py`, `scan_params.py`, `reachability.py`, `knobs.py` are disjoint from V192-3 |
| V192-3 | V192-2, V192-16 | after V192-1; disjoint file `plan_types.py` |
| V192-4 | V192-16 | after V192-2 (`effective_g` reads both knobs) and V192-3 (`reclaim_level`, `reclaim_atr`) |
| V192-5 | V192-6, V192-10, V192-16 | after V192-4 (`stamp_next_open`, `next_open_applies`); file `builders.py` |
| V192-6 | V192-5, V192-10, V192-16 | after V192-4 (`decide_at_open`, `waits_for_open`); files `market_next_open.py`, `exit_sim.py`; tests build PENDING plans directly |
| V192-7 | V192-8, V192-10, V192-16 | after V192-6: same file `market_next_open.py` |
| V192-8 | V192-7, V192-10, V192-14 | after V192-4 and V192-5 (a waiting market plan exists live); file `plan_manager.py` |
| V192-9 | V192-10, V192-14 | after V192-8: same file `plan_manager.py`, extends `_step_market_open` |
| V192-10 | V192-5..V192-9 | after V192-4 (event names only); files under `core/presentation/` and `core/scanning/*_embeds.py`, disjoint from the manager |
| V192-11 | V192-12, V192-14 | after V192-9 (same file `plan_manager.py`) and V192-10 (`Kind.RECLAIM_ORDER`) |
| V192-12 | V192-8, V192-9, V192-14 | after V192-5 (`waits_for_open`, stamped `reclaim_level`) and V192-10 (same file `instructions.py`) |
| V192-13 | V192-14..V192-17 | after V192-5, V192-9, V192-11 and V192-12: drives a waiting plan from scan to fill and a cancel to the placeholder discard; files `analyze.py`, `scan_run.py` |
| V192-14 | V192-8..V192-13, V192-16 | after V192-2 (the knobs `--baseline-knob` names); files `measure_arms.py`, `provenance.py` |
| V192-15 | V192-16, V192-17 | after V192-7 (`observing`, `NextOpenDecision` with the veto fields) and V192-14 (same file `measure_arms.py`) |
| V192-16 | V192-2..V192-15 | after V192-1; files `acceptance.py` and the new `gap_reclaim_clauses.py` |
| V192-17 | V192-15 | after V192-16: same file `gap_reclaim_clauses.py` |
| V192-18 | V192-19 | after V192-14, V192-15 and V192-17 (every function the CLIs call) |
| V192-19 | V192-2..V192-18 | after V192-1; disjoint autopsy script |
| V192-20 | V192-21 | after V192-13 and V192-18: documents what they built |
| V192-21 | V192-20 | after V192-19; reads the replicated live book only, before any TRAIN run |
| V192-22 | — | after V192-1..V192-19 are committed in the worktree and V192-21 is recorded (the market-only disclosure precedes TRAIN); one `backtest-runner` |
| V192-23 | — | after V192-22 (at least one cell REACHABLE); one runner at a time |
| V192-24 | — | after V192-23 (a SELECTED `g`) |
| V192-25 | — | after V192-24 (Stage 2 PASS; a Stage 2 FAIL skips straight to the record step of this task) |
| V192-26 | — | after every other task: bump, the plan's single full-suite run, merge |

At most 2 implementers at once (shared tree, CPU). Suggested pairs: V192-2 + V192-3, V192-5 + V192-6, V192-7 + V192-10, V192-8 + V192-16, V192-9 + V192-14, V192-11 + V192-17 (after V192-16), V192-12 + V192-15, V192-18 + V192-19, V192-20 + V192-21. Measurement runs (V192-22..V192-25) never overlap each other.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-24-v192-gap-toward-stop-reclaim_1-foundations-and-replay.md` | V192-1..V192-7 | worktree and flag-off golden, the two knobs with ScanParams, reachability, the load coupling and the `apply_knobs` guard, the three plan fields, the `gap_reclaim` rule module, builders building waiting market plans, the replay next-open fill with its fill-bar check and hold cap, the veto branch |
| 2 | `2026-10-24-v192-gap-toward-stop-reclaim_2-live-path.md` | V192-8..V192-13 | live session timing and the open decision with the premarket cancel, the reclaim wait and close cancel, feed instruction copy and the new Kind, manager notices and follower wiring, the alert line, scan-to-fill integration and live/replay parity |
| 3 | `2026-10-24-v192-gap-toward-stop-reclaim_3-measurement-code.md` | V192-14..V192-19 | the baseline knob delta, the census sidecar, strata and the SKIPPED-fails verdict, permutation/selection/sensitivity/report functions, CLI wiring and the report script, the autopsy entry-type filter |
| 4 | `2026-10-24-v192-gap-toward-stop-reclaim_4-runs-docs-and-release.md` | V192-20..V192-26 | docs, the pre-TRAIN market-only autopsy disclosure, Stage −1, Stages 0–1 with the next-open basis, Stage 2, Stage 3 with reports, results record and ledger row, release and full suite |

## Task ledger

| Task | Title | Part | Model | Files created / modified | Creates (consumed later) |
|---|---|---|---|---|---|
| V192-1 | Worktree; flag-off golden (replay results, arm rows, plan dicts) | 1 | sonnet | C `tests/backtesting/arms/test_v192_flag_off_golden.py`, `tests/fixtures/v192/replay_golden.json`, `tests/planning/test_v192_plan_golden.py`, `tests/fixtures/v192/plan_golden.json` | worktree branch `2026-10-24-v192-gap-toward-stop-reclaim`; golden fixtures every later task keeps green |
| V192-2 | Config knobs, ScanParams slots, reachability rows, load coupling, `apply_knobs` guard | 1 | sonnet | M `swingbot/config.py`, `swingbot/scan_params.py`, `swingbot/core/backtesting/arms/reachability.py`, `swingbot/core/backtesting/arms/knobs.py`, `tests/infra/test_config_flags.py`, `tests/backtesting/arms/test_knobs.py`; C `tests/planning/test_v192_config.py` | `config.MARKET_ENTRY_NEXT_OPEN`, `config.GAP_RECLAIM_ATR`, `config.enforce_gap_reclaim_coupling()`, `ScanParams.market_entry_next_open`, `ScanParams.gap_reclaim_atr`, two `REGISTRY` rows, `knobs.GAP_RECLAIM_NEEDS_NEXT_OPEN` |
| V192-3 | `TradePlanV2.reclaim_atr`, `reclaim_level`, `reclaim_session` with serialization and DB round trip | 1 | sonnet | M `swingbot/core/planning/plan_types.py`, `tests/planning/test_plan_serialization.py`, `tests/db/test_plans_repository.py` | the three plan fields (in `_OMIT_WHEN_NONE`) |
| V192-4 | `gap_reclaim.py`: tick, ATR at t, X, open decision, reclaim touch, builder stamp | 1 | opus | C `swingbot/core/planning/gap_reclaim.py`, `tests/planning/test_gap_reclaim.py` | everything under `gap_reclaim.py` in § Contracts |
| V192-5 | Builders: waiting market plans under `MARKET_ENTRY_NEXT_OPEN` | 1 | opus | M `swingbot/core/planning/builders.py`; C `tests/planning/test_v192_builders_next_open.py` | PENDING market plans with `entry_price=None` and the reclaim stamp |
| V192-6 | Replay next-open market fill: fill-bar check, hold cap, observer | 1 | opus | C `swingbot/core/planning/market_next_open.py`, `tests/planning/test_market_next_open.py`; M `swingbot/core/planning/exit_sim.py` | `NextOpenDecision`, `observing`, `next_open_fill_bar`, `next_open_market_exit` (baseline branch), the `_market_exit` dispatch, widened `_counts_fill_session` |
| V192-7 | Replay veto branch: reclaim fill, ambiguous bar, `gap_no_reclaim` | 1 | opus | M `swingbot/core/planning/market_next_open.py`; C `tests/planning/test_market_next_open_veto.py` | the veto branch of `next_open_market_exit`; `NextOpenDecision.reclaimed` / `ambiguous` populated |
| V192-8 | Live open decision and premarket stop-cross cancel | 2 | opus | C `swingbot/core/planning/market_open.py`, `tests/planning/test_market_open.py`, `tests/planning/test_plan_manager_market_open.py`; M `swingbot/core/planning/plan_manager.py` | `PREMARKET_STOP_CONFIRM_POLLS`, `deciding_session`, `market_phase`, `PlanManager._step_market_open` (open, premarket, missed), `_premarket_hits` |
| V192-9 | Live reclaim wait: fill at E, end-of-session cancel, reload safety | 2 | opus | M `swingbot/core/planning/plan_manager.py`; C `tests/planning/test_plan_manager_gap_reclaim.py` | `_step_market_open` waiting and after-close branches |
| V192-10 | Feed instruction copy and `Kind.RECLAIM_ORDER` | 2 | opus | M `swingbot/core/presentation/kinds.py`, `swingbot/core/presentation/instructions.py`, `swingbot/core/scanning/lifecycle_embeds.py`, `swingbot/core/scanning/execution_embeds.py`, `scripts/dev/render_feed_samples.py`; C `tests/presentation/test_gap_reclaim_instructions.py` | `Kind.RECLAIM_ORDER`; instruction builders for the three transitions |
| V192-11 | Manager notices, transition log, placeholder discard; follower mapping | 2 | opus | M `swingbot/core/planning/plan_manager.py`, `swingbot/commands/scanning/follow_notify.py`; C `tests/planning/test_plan_manager_gap_reclaim_feed.py`, `tests/scanning/test_follow_notify_gap_reclaim.py` | `NOTICE_EVENTS` additions, `_TRANSITION_LOG` rows, `PLACEHOLDER_DISCARD_EVENTS`, follow_notify table rows |
| V192-12 | Alert: market-on-open wording and the X reference line | 2 | sonnet | M `swingbot/core/presentation/instructions.py`, `swingbot/core/scanning/alert_embeds.py`; C `tests/presentation/test_market_on_open_alert.py` | `instructions.market_on_open_lines(plan)` |
| V192-13 | Live integration: scan to fill with the knob on; live/replay parity of E, a_t, X | 2 | opus | M `swingbot/core/scanning/analyze.py`, `swingbot/core/scanning/scan_run.py`; C `tests/scanning/test_v192_scan_to_fill.py`, `tests/scanning/test_v192_live_replay_parity.py` | — |
| V192-14 | `measure_arms.py --baseline-knob`; `baseline_knob_delta` stamp; refusals on it | 3 | sonnet | M `scripts/backtest/measure_arms.py`, `swingbot/core/backtesting/arms/provenance.py`, `scripts/backtest/validate_component.py` (reachability prints and classifies the baseline delta); C `tests/backtest_scripts/test_measure_arms_baseline_delta.py` | `produce(..., baseline_delta=)`, `build_stamp(..., baseline_knob_delta=)` |
| V192-15 | Census module and the `gap_reclaim` sidecar | 3 | opus | C `swingbot/core/backtesting/arms/gap_reclaim_census.py`, `tests/backtesting/arms/test_gap_reclaim_census.py`; M `scripts/backtest/measure_arms.py` | everything under `gap_reclaim_census.py` in § Contracts; `measure_arms.gap_reclaim_sidecar` |
| V192-16 | Strata split, mechanism and volume clauses, SKIPPED-fails verdict | 3 | opus | M `swingbot/core/backtesting/acceptance.py`, `tests/backtesting/test_acceptance_gate.py`; C `swingbot/core/backtesting/arms/gap_reclaim_clauses.py`, `tests/backtesting/arms/test_gap_reclaim_clauses.py` | `acceptance.verdict_of`, `evaluate(..., skipped_fails=)`, `strata_split`, `mechanism_clause`, `volume_clause`, `evaluate_gap_reclaim`, `strata_rows` |
| V192-17 | Permutation null, Stage 1 cell, ambiguous sensitivity, report | 3 | opus | M `swingbot/core/backtesting/arms/gap_reclaim_clauses.py`; C `tests/backtesting/arms/test_gap_reclaim_report.py` | `repriced_permutation`, `selection_cell`, `ambiguous_sensitivity`, `report` |
| V192-18 | CLI: `validate_component --gap-reclaim`, `permutation_test --gap-reclaim`, `gap_reclaim_report.py` | 3 | sonnet | M `scripts/backtest/validate_component.py`, `scripts/backtest/permutation_test.py`; C `scripts/reports/gap_reclaim_report.py`, `tests/backtest_scripts/test_gap_reclaim_cli.py` | CLI in § Contracts |
| V192-19 | Autopsy `--entry-type` filter | 3 | sonnet | M `scripts/reports/book_autopsy.py`; C `tests/scripts/test_book_autopsy_entry_type.py` | `--entry-type` |
| V192-20 | Docs: architecture, known-traps, AGENTS.md | 4 | haiku | M `docs/claude/architecture.md`, `docs/claude/known-traps.md`, `AGENTS.md` | — |
| V192-21 | Pre-TRAIN disclosure: autopsy cells re-cut to market plans | 4 | sonnet | C `docs/superpowers/results/2026-10-24-v192-gap-reclaim.md` (disclosure section), data under `docs/superpowers/results/v192/autopsy-market/` | the disclosure section |
| V192-22 | Stage −1 reachability for g in 0.10, 0.25, 0.50 | 4 | sonnet | data: `docs/superpowers/results/v192/2026-10-24-v192-g{010,025,050}-pilot.json` (+ `.gap_reclaim.json`); M results doc | per-cell reachability verdicts |
| V192-23 | Stages 0 and 1, plus the next-open vs close-fill basis on fold-train | 4 | sonnet | data: `docs/superpowers/results/v192/2026-10-24-v192-g{010,025,050}-selection.json`, `2026-10-24-v192-basis-selection.json`, `2026-10-24-v192-stage0.json`, `2026-10-24-v192-stage1.json`; M results doc | the selected `g` |
| V192-24 | Stage 2 walk-forward for the selected g | 4 | sonnet | data: `docs/superpowers/results/v192/2026-10-24-v192-walkforward.json`, `2026-10-24-v192-stage2.json`; M results doc | Stage 2 verdict |
| V192-25 | Stage 3 VALIDATION, reports, results record, ledger row | 4 | sonnet | data: `docs/superpowers/results/v192/2026-10-24-v192-validation.json` (+ sidecar), `2026-10-24-v192-stage3.json`, `2026-10-24-v192-permutation.json`, `2026-10-24-v192-report.json`; M results doc, `docs/superpowers/results/preregistration-ledger.jsonl`, `docs/claude/backtest-methodology.md` (on fail), `AGENTS.md` (on fail), `swingbot/config.py` (knob help names the verdict) | recorded verdict |
| V192-26 | Version bump, full suite, merge | 4 | sonnet | M `VERSION.json`, `swingbot/admin/version_history.json` (regenerated by `scripts/dev/build_version_matrix.py`) | merged branch on `main`; `/close-out` follows |
