# v191 — Confluence ATR-band stops, sized to a gap-aware dollar loss: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V191-8:" -A 300 docs/superpowers/plans/2026-10-24-v191-confluence-atr-band-stops_2-band-stop-path.md`.

**Bump:** bot patch
**Edge:** expectancy — moves stop and target geometry on confluence plans and changes which scenarios are admitted; prediction per cell on the floor-moved stratum: ΔWR ≥ +4pp, arm K ΔExpR > 0, arm R ΔExpR < 0.
**Screen:** harvest-headroom docs/superpowers/results/2026-10-21-book-autopsy-sep-era.md
**Spec:** [2026-10-24-v191-confluence-atr-band-stops-design.md](../specs/2026-10-24-v191-confluence-atr-band-stops-design.md)
**Brief:** `.superpowers/briefs/2026-10-24-v191-confluence-atr-band-stops.md`
**Worktree:** every code task runs in `.claude/worktrees/2026-10-24-v191-confluence-atr-band-stops` (branch of the same name, created in V191-1's first step; `docs/claude/document-lifecycle.md`). The measurement tasks (V191-20..V191-22) run from the same worktree and read the main checkout's git-ignored training data by absolute path. The merge to `main` is V191-25's last step.

## Goal

Live confluence stops sit inside one ordinary day's range. In the current
exit-model era of the live book (N = 221, exploratory) the median stop is
about 0.37 × ATR14 away, 101 of 221 trades closed at the stop, the decided
win rate is 31.2%, and 47 of 288 plans were cancelled because the fill could
not keep the stop inside 2%. The cause is structural: confluence stops are
admitted only between `MIN_STOP_DISTANCE_PCT` and the 2% hard cap (clamped to
1.75% beyond it), a band measured in price percent, on a watchlist whose
ATR14 runs 4.5–5.5% of price. Every idea that screened positive raced a
1.5 × ATR stop. The partner has settled that the 2% rule bounds **dollars**,
not distance, and that the preset maximum loss must never be exceeded.

Once this ships, three new settings exist, all inert at their defaults:
`CONFLUENCE_ATR_STOP_FLOOR` (`k`, default 0), `CONFLUENCE_ATR_TARGET_MODE`
(`rechoose` | `keep`) and `LONG_GAP_SIZING` (default off). With the floor on,
a confluence plan's stop sits in an ATR band — no closer than `k × ATR14`,
no further than `2 × ATR14` — rounded to the tick away from entry, and the
plan stores `stop_ceiling_pct = band distance + 0.25` plus a new
`stop_moved_by` (`floor` / `ceiling` / `untouched`). The percent admission
gates and the 2% clamp step aside for that plan, and one dollar rule takes
their place: shares are sized on the worst fill the plan accepts (plus the
p99 gap allowance), floored to the cent so the planned loss can never exceed
`RISK_PER_TRADE_PCT`; a plan that cannot fit is refused and logged. Arm R
re-chooses TP1 against the wider stop; arm K keeps today's TP1 and drops the
plan when its reward:risk falls under the minimum. Part B extends v183's
short-side gap sizing to longs with the p99 **down**-gap, behind its own
flag. A live floor is honoured only with both gap-sizing flags on, guarded in
the admin validator and at every config load.

How it works, in idea: the band is pure arithmetic on raw Wilder ATR14 of
completed bars through the creating bar (`swingbot/core/market/atr_band.py`),
computed once at admission and carried on the `Scenario` to the builder, so
admission and plan agree and live, replay and the measurement read one rule.
Sizing for a band plan rides in the existing `gap_sizing` stamp
(`band_sizing_distance`), which every alert, engine and paper-trade sizing
site already threads, so the alert's shares equal the engine's.

What it leaves alone: strategy-path stops and `STRUCTURAL_STOP_SCOPE`, the 2%
constant, `CLAMP_HEADROOM_PCT`, the v139 knobs, the heat basis (candidate
heat stays the configured risk %), entries, charts, badges and alert layout
beyond one added band line. v114's "stops at real levels" rule is overridden
for this measurement only; no knob goes live without the partner.

Success is measured twice. Code: a flag-off golden captured before any
change shows replay and plan output byte-identical with every knob off; the
dollar invariant, the coupling, tick rounding, the no-lookahead ATR and the
reload rule are pinned by tests. Edge: a v92 harvest-gate pre-registration
(arm K primary, arm R second, Holm across the two) scored on the
**floor-moved stratum alone**, Stage −1 through one VALIDATION shot per arm,
on instrument v1 with `data_source = alpaca`; a pass is recorded and the
knob stays 0 until the partner decides. Part B ships regardless, with a
descriptive dollar-exceedance report on the live book.

## Architecture

- **Flag-off golden first (V191-1).** Replay rows (v139 shape plus `stop_ceiling_pct`) on AAPL `_structured_df()` and DELL ≤ 2019, and `plan_to_dict` snapshots of confluence plans built from fixed scenarios, captured on unmodified code into `tests/fixtures/v191/`.
- **Config (V191-2, V191-3).** Three `Field`s, two `ScanParams` slots, two reachability rows; `config.enforce_atr_band_coupling()` runs at the end of every `_apply_env` (import and SIGHUP reload) and zeroes a floor whose gap-sizing flags are off, with `log.error`; the admin `_validate` refuses the same combination on the effective form.
- **Plan field (V191-4).** `TradePlanV2.stop_moved_by: str | None = None`, in `_OMIT_WHEN_NONE`, riding in `plans.doc` JSONB; no migration.
- **Part B (V191-5, V191-6).** `gap_stats` gains `p99_down_gap_pct` / `n_down`; `gap_sizing` stamps and sizes longs behind `LONG_GAP_SIZING` with v183's exact rule (`max(stop distance, entry × p99%)`, ≥ 60 gaps, else sized on the stop); readers that assumed "short" (`gap_risk_amount_for`, admin `trades.py`, `risk.py`, `dashboard.py`) become direction-aware.
- **Band arithmetic (V191-7).** New `swingbot/core/market/atr_band.py`: raw ATR14%, tick rounding away from entry, `band_stop`, `band_for`, reason constants. Pure; imported by `levels`, `builders`, `analyze`, the replay.
- **Builder (V191-8).** `build_confluence_plan` asks `_plan_geometry` for `(stop, ceiling, moved_by, tp1, reason)`: the band path when the floor is on and the scenario carries `atr14_pct`, else today's `confluence_stop_geometry` unchanged. Arm R re-selects TP1 against the band stop; arm K keeps the TP1 picked against today's 1.75–2% stop and drops below `MIN_RISK_REWARD_RATIO`.
- **Admission (V191-9 replay side, V191-10 live side).** `levels.build_scenarios(..., band=AtrBand | None)` skips the min/max stop-distance checks and evaluates own-target R:R against the band stop when the band is active, and stamps `Scenario.atr14_pct`. Replay builds the band from `window`; live from `strategy_pass.completed_frame(df, now)` inside `_horizon_scenarios`, logging `band_no_atr`. `requirements.py` shows the band.
- **Dollar invariant (V191-11, V191-12).** `gap_sizing.worst_fill_distance` / `band_sizing_distance`, the `band_sizing_distance` stamp key and a band branch in `size_for` that floors shares to 0.01; `stop_scope.band_sizing_verdict` → `None` / `band_size_zero` / `risk_sizing`. `attach_plan_v2` stamps a band plan's gap sizing **before** its dollar check and rejects through `_reject_plan`, so the existing `plan rejected (` line logs every band reason.
- **Alert (V191-13).** `presentation/band_stop.py: band_stop_line(plan, *, currency)` at every site that renders `gap_risk_line`.
- **Measurement (V191-14..V191-17).** `atr_band_replay.py` (census and outcome rows per arm, baseline = floor 0, unions keyed by `(ticker, horizon, signal index, direction)` so newly admitted rows survive), `atr_band_funnel.py` (frozen windows, Stage −1..3, Holm family, reports), and the driver `scripts/backtest/measure_atr_band_stop.py` (v139's stage chain and refusals, `--arm`, `--family`, alpaca only).
- **Part B report (V191-18).** `scripts/reports/short_gap_sizing_impact.py --side short|long|both` (default `short`, byte-identical output).
- **Docs (V191-19)**, **runs (V191-20..V191-22)** through `backtest-runner`, **record (V191-23)**, **Part B impact on the live book (V191-24)**, **release (V191-25)**: bump, the single full-suite run, merge.

## Global Constraints

- Every knob ships inert: `CONFLUENCE_ATR_STOP_FLOOR` default `"0"`, `CONFLUENCE_ATR_TARGET_MODE` default `"rechoose"`, `LONG_GAP_SIZING` default `"false"`. With all three at default, replay rows and plan dicts equal the V191-1 golden byte for byte; no long plan gains a `gap_sizing` key and no plan gains `stop_moved_by`.
- Frozen band values: floor grid `k ∈ (0.75, 1.0, 1.5)`; ceiling `2.0 × a`; `a = raw Wilder ATR14 / entry × 100` of completed bars through the creating bar — **never** `levels.atr_floor_pct` / `Scenario.atr_floor_pct` (those carry `atr_stop_multiple`). `k` must be `< 2.0` (`ValueError` otherwise); the config field's max is 1.5.
- Band stop: `d < lo` → `entry ∓ lo%` (`floor`); `lo ≤ d ≤ hi` → the level (`untouched`, not rounded); `d > hi` → `entry ∓ hi%` (`ceiling`). Floor and ceiling stops round **away from entry** to the tick: `0.01` when entry ≥ 1, `0.0001` below. Bull floors, bear ceils.
- Stored ceiling: `stop_ceiling_pct = planned_loss_pct(entry, band stop) + CLAMP_HEADROOM_PCT` (0.25, unchanged). Computed once at creation; a SIGHUP or knob flip never rewrites an open or pending plan.
- Dollar invariant: a band plan's shares satisfy `shares × band_sizing_distance ≤ balance × risk_pct / 100` exactly, shares a multiple of 0.01 (floored, never rounded up); `shares == 0.00` → `band_size_zero`; non-`risk_pct` sizing mode, a sizing exception or an overshoot → `risk_sizing`. Worst-fill distance: long `stop × c / (100 − c)`, short `stop × c / (100 + c)`, `c = stop_ceiling_pct`. The gap allowance follows v183's convention, `max(worst-fill distance, trigger × p99% / 100)`: the spec's "plus" wording is read as v183's rule, which the spec says Part B mirrors exactly.
- Heat call sites are not edited: `scan_run.py:1167/1181` and `short_run.py:240-243` keep `account_cfg.get('risk_pct', 1.0)` (AST pin `test_candidate_heat_and_cluster_inputs_are_the_configured_risk_pct`).
- Coupling: a live `CONFLUENCE_ATR_STOP_FLOOR > 0` needs `LONG_GAP_SIZING` and `SHORT_GAP_SIZING` both true; otherwise config load/reload sets it to `0.0` and logs at ERROR, and the admin save/preview returns 400 `invalid`. Replay and measurement set knobs through `arms.knobs.apply_knobs`, which bypasses the load hook, so measurement is uncoupled by construction.
- Rejection reasons, exact strings: `band_no_target`, `band_rr_drop`, `band_no_atr`, `band_size_zero` (constants in `atr_band.py`). Each band reason that reaches an item goes through `analyze._reject_plan`, so `scan_run._skip_rejected_plan` prints the existing `plan rejected (` line; `band_no_atr` (no item exists) logs its own INFO line containing `plan rejected (band_no_atr`.
- v139 knobs are never set with a v191 knob: the band replay raises if `CONFLUENCE_STRUCTURAL_STOP_PCT` or `CONFLUENCE_STOP_DROP_PCT` is non-zero; with the band active, the builder takes the band path and never calls v139's arms.
- Complexity: every function written or changed ends `< 15`; `levels.build_scenarios` (C 15, legacy) and `build_confluence_plan` (C 13) gain no branch — new logic lives in helpers. `python scripts/dev/complexity_gate.py` passes after each code task.
- NO-LOOKAHEAD: the band reads ATR14 through the creating bar only; live reads `completed_frame(df, now)`; a test mutates the bar after the creating bar and sees no change (V191-7, V191-9, V191-10).
- Frozen measurement block: instrument **v1**, `data_source` **`alpaca`**, universe `measure_arms.cached_universe()` (the watchlist-era universe v139/v180 used), replay `gates=None` (live `ScanParams` through config, the v139 precedent), fold-train `2018-06-01..2022-12-31`, folds 2021/2022/2023 (per-fold N ≥ 30, ≥ 2 of 3 positive ΔExpR), VALIDATION `2024-01-01..2025-12-31`, MDE ceiling `+0.10R` at power 0.80, plateau tolerance `backtest_wf.PLATEAU_TOLERANCE_R` (0.03, unchanged, via `plateau_report`), week-clustered bootstrap, permutation n = 200, v92 harvest gate (`acceptance_harvest.evaluate_harvest`), every clause scored on the floor-moved stratum alone; Holm across the two arms on each arm's Stage 3 `permutation_p`, an arm that never reached Stage 3 entering as p = 1.0. Date literals live in `swingbot/core/backtesting/atr_band_funnel.py`, never in `scripts/backtest/*.py`.
- Measurement in the worktree: `MEASURE_ARMS_UNIVERSE=cache`, `HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data` and `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache` set in the same command; results under `docs/superpowers/results/v191/`. Long runs go to `backtest-runner`, chunked per arm, one runner at a time; 15 min+ prints a percent.
- Stage 3 runs once per arm, refused when its output exists and without `--preregistration docs/superpowers/specs/2026-10-24-v191-confluence-atr-band-stops-design.md`. No closed pre-registration is re-run; no threshold, window, grid or MDE ceiling changes after fold-train is read.
- Stored records change additively only (`docs/claude/schema-evolution.md`): plan doc key `stop_moved_by`; stamp keys `down_gap_p99_pct`, `n_down_gaps`, `band_sizing_distance`; `gap_stats` keys `p99_down_gap_pct`, `n_down`. The DB round trip runs against `docker compose --profile test up -d db-test` and is never left skipped at close-out.
- A task that runs DB tests runs `/replicate-prod-db` first into the shared `swing-db` container (CLAUDE.md).
- Per-task verification is `python scripts/dev/testrun.py file <test>`; the full suite runs once, in V191-25. No new `tests/` directory: every new test file joins an existing one.
- Each `docs/claude/*.md` edit ships its `AGENTS.md` condensed mirror in the same commit.
- Paper trades only; nothing in this plan touches eToro or the VM.

## Contracts

```python
# swingbot/core/market/atr_band.py                                   (V191-7, new)
ATR_PERIOD = 14
BAND_CEILING_ATR = 2.0
FLOOR_GRID = (0.75, 1.0, 1.5)
MOVED_FLOOR, MOVED_CEILING, MOVED_UNTOUCHED = "floor", "ceiling", "untouched"
REASON_NO_TARGET, REASON_RR_DROP = "band_no_target", "band_rr_drop"
REASON_NO_ATR, REASON_SIZE_ZERO = "band_no_atr", "band_size_zero"
class AtrBand(NamedTuple):
    k: float
    atr_pct: float | None                 # None = ATR unavailable -> today's admission/geometry
class BandStop(NamedTuple):
    stop: float                           # rounded away from entry when moved
    moved_by: str                         # MOVED_*
    lo_pct: float                         # k * a
    hi_pct: float                         # 2.0 * a
    distance_pct: float                   # planned_loss_pct(entry, stop)
def raw_atr14_pct(df, entry: float) -> float | None    # indicators.atr(df, 14) at df's LAST row / entry * 100; None if df None/empty, NaN, <= 0, entry <= 0
def tick_size(price: float) -> float                    # 0.01 if price >= 1 else 0.0001
def round_away_from_entry(stop: float, entry: float, is_bull: bool) -> float
def band_stop(entry: float, level: float | None, is_bull: bool, atr_pct: float | None, k: float) -> BandStop | None
    # None when k <= 0, atr_pct None/<= 0, entry <= 0, level None or not on the stop side; ValueError when k >= BAND_CEILING_ATR
def band_for(df, entry: float, k: float) -> AtrBand | None   # None when k <= 0, else AtrBand(k, raw_atr14_pct(df, entry))

# swingbot/config.py, swingbot/scan_params.py                          (V191-2, V191-3)
CONFLUENCE_ATR_STOP_FLOOR: float          # Field type "float", default "0", min 0, max 1.5, step 0.25, section "Trade Filters & Risk", searchable
CONFLUENCE_ATR_TARGET_MODE: str           # Field type "select", options rechoose|keep, default "rechoose", same section, searchable
LONG_GAP_SIZING: bool                     # Field type "checkbox", default "false", section "Account Defaults", directly after SHORT_GAP_SIZING, live_only
ScanParams.confluence_atr_stop_floor: float = 0.0
ScanParams.confluence_atr_target_mode: str = "rechoose"
def enforce_atr_band_coupling() -> bool   # config.py; True when it zeroed the floor; called at the end of _apply_env

# swingbot/admin/api_v1/system.py                                       (V191-3)
def _coupling_problem(values: Mapping) -> tuple[str, str] | None   # on _effective_form(values); called from _validate

# swingbot/core/planning/plan_types.py                                  (V191-4)
TradePlanV2.stop_moved_by: str | None = None      # "floor" | "ceiling" | "untouched"; in _OMIT_WHEN_NONE

# swingbot/core/edge/gates.py                                           (V191-5)
gap_stats(df, lookback=250) -> dict   # + "p99_down_gap_pct": float | None (p99 of |negative gaps|, a positive percent), "n_down": int; the empty-frame return carries both
# swingbot/core/planning/gap_sizing.py                                  (V191-5, V191-11)
MIN_DOWN_GAPS = 60
# long stamp: {"rule": RULE_GAP | RULE_STOP, "down_gap_p99_pct": float | None, "n_down_gaps": int}
#   present only when LONG_GAP_SIZING is on, or (V191-11) the plan is a band plan
def gap_floor_for(direction, gap_sizing) -> float | None      # bullish reads down_gap_p99_pct, bearish up_gap_p99_pct
def gap_risk_amount_for(shares, entry, stop_loss, gap_sizing, direction: str = "bearish") -> float | None
BAND_KEY = "band_sizing_distance"                                                           # (V191-11)
def worst_fill_distance(stop_loss: float, stop_ceiling_pct: float, direction: str) -> float # (V191-11)
def band_sizing_distance(trigger: float, stop_loss: float, stop_ceiling_pct: float,
                         direction: str, gap_sizing: dict | None) -> float                  # (V191-11)
# size_for(...) (V191-11): a stamp carrying BAND_KEY takes the band branch; its result gains "band_sizing_distance"

# swingbot/core/planning/stop_scope.py                                  (V191-11)
def band_sizing_verdict(plan, sizing_fn=None) -> str | None   # None | "band_size_zero" | "risk_sizing"

# swingbot/core/planning/builders.py                                    (V191-8)
TODAY_BAND_FLOOR_PCT = HARD_MAX_PLANNED_LOSS_PCT - CLAMP_HEADROOM_PCT   # 1.75
class PlanGeometry(NamedTuple):
    stop_loss: float | None
    stop_ceiling_pct: float | None
    moved_by: str | None
    tp1: float | None
    reason: str | None                    # REASON_NO_TARGET | REASON_RR_DROP | None
def confluence_atr_band_stop(entry, level, is_bull, atr_pct, params) -> tuple[float, float, str] | None   # (stop_loss, stop_ceiling_pct, moved_by)
def arm_k_today_stop(entry: float, level: float, is_bull: bool) -> float
def band_no_plan_reason(scenario, level_map=None, params=None) -> str | None
def _plan_geometry(scenario, candidates, params) -> PlanGeometry | None   # None = v139 arm D drop (today's)

# swingbot/core/market/levels.py                                        (V191-9)
Scenario.atr14_pct: float | None = None   # set only when build_scenarios received an active band (atr_pct not None)
def build_scenarios(..., block_bullish=False, band: AtrBand | None = None) -> list
# swingbot/core/scanning/gating.py                                      (V191-9)
# scenario_gate_inputs(params, horizon) -> dict gains "atr_stop_floor": params.confluence_atr_stop_floor
# swingbot/core/scanning/analyze.py                                     (V191-10, V191-12)
def _horizon_scenarios(df, h, current_price, trendline_candidates, hard_filters, *, ticker: str = "", now=None) -> HorizonBuild
def _band_live(df, current_price: float, k: float, now, ticker: str, horizon_label: str) -> AtrBand | None
def _sizing_reject_reason(plan, df, now) -> str | None      # V191-12
# hard_filters gains "confluence_atr_stop_floor" (scan_run._hard_filters_snapshot, analyze._default_hard_filters; read with .get(..., 0.0))

# swingbot/core/presentation/band_stop.py                               (V191-13, new)
def band_stop_line(plan, *, currency: str = "$") -> str | None

# swingbot/core/backtesting/atr_band_replay.py                          (V191-14, new)
FLOOR_KNOB = "CONFLUENCE_ATR_STOP_FLOOR"; MODE_KNOB = "CONFLUENCE_ATR_TARGET_MODE"
ARMS = {"R": "rechoose", "K": "keep"}
K_STEPS = FLOOR_GRID
REFERENCE_ACCOUNT = {"balance": 10000.0, "risk_pct": 1.0, "sizing_mode": "risk_pct", "position_pct": 10.0,
                     "max_position_pct": 100.0, "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}
def cell_key(k) -> str                    # "k0.75", "k1", "k1.5"
def census(ticker, df, horizons, *, arm, start=None, end=None, cells=K_STEPS, gates=None) -> list[dict]
def replay_entries(ticker, df, horizons, *, arm, start=None, end=None, cells=K_STEPS, gates=None) -> list[dict]
# outcome row: {"arm", "ticker", "horizon_key", "entry_date", "signal_index", "direction", "d", "atr_pct",
#               "baseline": record | None, "cells": {key: record | None}, "moved_by": {key: str | None},
#               "newly_admitted": {key: bool}}
# record: ArmTrade fields + "exit_mix", "gap_through", "fill_beyond_ceiling", "stop_moved_by",
#         "stop_distance_pct", "stop_distance_atr", "early_stop", "dollar_pnl", "dollar_exceeds_budget"

# swingbot/core/backtesting/atr_band_funnel.py                          (V191-15, V191-16, new)
FOLD_TRAIN = ("2018-06-01", "2022-12-31"); VALIDATION = ("2024-01-01", "2025-12-31")
FOLD_YEARS = (2021, 2022, 2023); FOLD_2023 = ("2023-01-01", "2023-12-31")
MIN_FOLD_N = 30; MIN_POSITIVE_FOLDS = 2; MDE_CEILING_R = 0.10; MDE_POWER = 0.80
CLUSTER = "week"; INSTRUMENT = "v1"; DATA_SOURCE = "alpaca"; HOLM_ALPHA = 0.05
def floor_moved(rows, key) -> list
def stage_minus1(census_rows, arm, cells=K_STEPS) -> dict      # verdict REACHABLE | refused:zero-diff
def stage0(rows, arm, cells=K_STEPS) -> dict                   # POWERED | UNDERPOWERED
def stage1(rows, arm, cells=K_STEPS, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> dict   # SELECTED | NO_ELIGIBLE_CELL; "selected": {"cell", "k"}
def stage2(rows_by_year: dict[int, list], arm, key) -> dict    # PASS | FAIL
def stage3(rows, arm, key, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> dict   # PASS | FAIL, "permutation_p"
def holm_family(stage3_by_arm: dict[str, dict | None]) -> dict # missing arm enters as p = 1.0
def report(rows, arm, key, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> dict

# scripts/backtest/measure_atr_band_stop.py                             (V191-17, new)
# --arm K|R  --stage -1|0|1|2|3  --family  --out-dir  --preregistration  --tickers  --workers  --resamples  --data-source alpaca
# RESULTS = docs/superpowers/results/v191 ; PREFIX = "2026-10-24-v191-arm{arm}" ; family file "2026-10-24-v191-family.json"
```

## Review Focus

- **A short band plan** — the mirror of every long rule (ceil to tick, `stop × c / (100 + c)`, up- vs down-gap): pinned with a bearish twin of each long test in V191-7, V191-8 and V191-11.
- **A sub-$1 instrument** — tick `0.0001`, a floor stop that rounds on the entry's own tick: V191-7 tests `entry = 0.85`.
- **An ATR that is NaN, zero, or a frame under 15 bars** with the floor on — today's admission and geometry, `band_no_atr` logged: V191-7 (helper), V191-10 (live log line).
- **A pending band plan when the knob flips or the account changes** — stop, ceiling and shares unchanged; a fill inside the stored headroom is not cancelled, one past it is: V191-12.
- **A band long in tests/replay with `LONG_GAP_SIZING` off, and a pre-v191 trade dict** — the band stamp still exists (rule `stop`), sizing uses the worst-fill distance only; a stamp without `band_sizing_distance` sizes exactly as today: V191-11.

## Parallelisation

| Task | May run alongside | Sequential edge and why |
|---|---|---|
| V191-1 | — | first: creates the worktree and captures the golden on unmodified code; every later task changes code the golden pins |
| V191-2 | V191-4, V191-7 | after V191-1; file `config.py` is V191-3's too, and V191-5 reads `config.LONG_GAP_SIZING` |
| V191-3 | V191-4, V191-5, V191-7 | after V191-2: same file `config.py`, reads `CONFLUENCE_ATR_STOP_FLOOR` / `LONG_GAP_SIZING` |
| V191-4 | V191-2, V191-3, V191-5, V191-7 | after V191-1; disjoint file `plan_types.py` |
| V191-5 | V191-3, V191-4, V191-7 | after V191-2 (`config.LONG_GAP_SIZING` exists) |
| V191-6 | V191-3, V191-7, V191-8 | after V191-5: consumes the long stamp keys and `gap_risk_amount_for(direction=)` |
| V191-7 | V191-2..V191-6 | after V191-1; new file only |
| V191-8 | V191-6, V191-9 | after V191-2 (ScanParams slots), V191-4 (`stop_moved_by`), V191-7 (`band_stop`, reasons) |
| V191-9 | V191-8 | after V191-2 (`params.confluence_atr_stop_floor`) and V191-7 (`AtrBand`, `band_for`, `band_stop`); files `levels.py`, `gating.py`, `backtest_scenarios.py` are disjoint from V191-8's |
| V191-10 | V191-11 | after V191-8 and V191-9: its live/replay parity test builds band plans through both; file `analyze.py` is V191-12's too |
| V191-11 | V191-10 | after V191-5 (same file `gap_sizing.py`) and V191-4 (`stop_moved_by`) |
| V191-12 | — | after V191-8, V191-10 (same file `analyze.py`) and V191-11 (`band_sizing_verdict`, the band stamp) |
| V191-13 | V191-14 | after V191-6 (same render sites as `gap_risk_line`) and V191-12 (band plans reach the alert) |
| V191-14 | V191-13, V191-18 | after V191-8 and V191-9 (replay builds band plans) and V191-11 (dollar view sizes through `size_for`) |
| V191-15 | V191-18 | after V191-14 (row schema) |
| V191-16 | V191-18 | after V191-15: same file `atr_band_funnel.py` |
| V191-17 | V191-18, V191-19 | after V191-16 (every stage function) |
| V191-18 | V191-7..V191-17 | after V191-5 (long stamp keys); disjoint script |
| V191-19 | V191-17, V191-18 | after V191-12 and V191-13: documents what they built |
| V191-20 | — | after V191-1..V191-17 are committed in the worktree; one `backtest-runner` |
| V191-21 | — | after V191-20 (arm K Stage −1 REACHABLE); one runner at a time |
| V191-22 | — | after V191-21 (one runner at a time; arm K is primary and runs first) |
| V191-23 | — | after V191-22 (both arms' final stage files feed `--family`) |
| V191-24 | V191-20..V191-23 | after V191-18; reads the replicated live book only |
| V191-25 | — | after every other task: bump, the plan's single full-suite run, merge |

At most 2 implementers at once (shared tree, CPU). Suggested pairs: V191-2 + V191-7, V191-4 + V191-5, V191-3 + V191-6, V191-8 + V191-9, V191-10 + V191-11, V191-13 + V191-14, V191-15 + V191-18. Measurement runs (V191-20..V191-22) never overlap each other.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-24-v191-confluence-atr-band-stops_1-foundations-and-gap-sizing.md` | V191-1..V191-6 | worktree and flag-off golden, the three config fields with ScanParams and reachability, the coupling guard (config load and admin validator), `stop_moved_by`, Part B long gap sizing core and its direction-aware readers |
| 2 | `2026-10-24-v191-confluence-atr-band-stops_2-band-stop-path.md` | V191-7..V191-13 | `atr_band.py` arithmetic, the builder's arm R / arm K geometry, admission bypass on the replay and live sides, band sizing and the dollar invariant, `attach_plan_v2` wiring, the alert band line |
| 3 | `2026-10-24-v191-confluence-atr-band-stops_3-measurement-code.md` | V191-14..V191-18 | band replay rows, funnel Stages −1..1, Stages 2..3 with Holm and reports, the stage driver, the Part B impact report `--side` |
| 4 | `2026-10-24-v191-confluence-atr-band-stops_4-runs-docs-and-release.md` | V191-19..V191-25 | docs and Codex mirror, Stage −1 run, arm K chain, arm R chain, results doc and ledger rows, Part B live-book impact, release and full suite |

## Task ledger

| Task | Title | Part | Model | Files created / modified | Creates (consumed later) |
|---|---|---|---|---|---|
| V191-1 | Worktree; flag-off golden (replay rows and plan dicts) | 1 | sonnet | C `tests/backtesting/test_v191_flag_off_golden.py`, `tests/fixtures/v191/flag_off_golden.json`, `tests/planning/test_v191_plan_golden.py`, `tests/fixtures/v191/plan_golden.json` | worktree branch `2026-10-24-v191-confluence-atr-band-stops`; golden fixtures every later task keeps green |
| V191-2 | Config fields, ScanParams slots, reachability rows | 1 | sonnet | M `swingbot/config.py`, `swingbot/scan_params.py`, `swingbot/core/backtesting/arms/reachability.py`, `tests/market/test_v115_strategy_work_off.py`, `tests/planning/test_v183_config_switches.py`; C `tests/test_config_v191_atr_band.py` | `config.CONFLUENCE_ATR_STOP_FLOOR`, `config.CONFLUENCE_ATR_TARGET_MODE`, `config.LONG_GAP_SIZING`, `ScanParams.confluence_atr_stop_floor`, `ScanParams.confluence_atr_target_mode`, two `REGISTRY` rows |
| V191-3 | Coupling guard: config load/reload and admin validator | 1 | sonnet | M `swingbot/config.py`, `swingbot/admin/api_v1/system.py`, `tests/admin/test_api_v1_system_settings.py`; C `tests/test_config_v191_coupling.py` | `config.enforce_atr_band_coupling() -> bool`, `system._coupling_problem(values)` |
| V191-4 | `TradePlanV2.stop_moved_by` with serialization and DB round trip | 1 | sonnet | M `swingbot/core/planning/plan_types.py`, `tests/planning/test_plan_serialization.py`, `tests/db/test_plans_repository.py` | `TradePlanV2.stop_moved_by` (in `_OMIT_WHEN_NONE`) |
| V191-5 | Part B core: down-gap p99, long stamp and sizing behind `LONG_GAP_SIZING` | 1 | opus | M `swingbot/core/edge/gates.py`, `swingbot/core/planning/gap_sizing.py`, `tests/edge/test_edge_gates.py`, `tests/planning/test_gap_sizing.py`; C `tests/planning/test_gap_sizing_long.py` | `gap_stats` keys `p99_down_gap_pct`, `n_down`; `MIN_DOWN_GAPS`; long stamp keys; `gap_floor_for` long branch; `gap_risk_amount_for(..., direction=)` |
| V191-6 | Part B readers: admin trades/risk/dashboard and the alert gap line for longs; long sizing parity | 1 | sonnet | M `swingbot/admin/api_v1/trades.py`, `swingbot/admin/api_v1/risk.py`, `swingbot/admin/dashboard.py`, `swingbot/core/tracking/performance.py`, `tests/scanning/test_gap_sizing_resize_sites.py`, `tests/presentation/test_gap_risk_line.py`; C `tests/scanning/test_long_gap_sizing_parity.py` | — |
| V191-7 | `atr_band.py`: raw ATR14%, tick rounding, band stop | 2 | opus | C `swingbot/core/market/atr_band.py`, `tests/market/test_atr_band.py` | everything under `atr_band.py` in § Contracts |
| V191-8 | Builder: band geometry, arm R and arm K, `stop_moved_by` | 2 | opus | M `swingbot/core/planning/builders.py`; C `tests/planning/test_confluence_atr_band_build.py` | `TODAY_BAND_FLOOR_PCT`, `PlanGeometry`, `confluence_atr_band_stop`, `arm_k_today_stop`, `band_no_plan_reason`, `_plan_geometry` |
| V191-9 | Admission (replay side): `build_scenarios(band=)`, `Scenario.atr14_pct`, gating input, `scenarios_at` | 2 | opus | M `swingbot/core/market/levels.py`, `swingbot/core/scanning/gating.py`, `swingbot/core/backtesting/backtest_scenarios.py`; C `tests/market/test_build_scenarios_atr_band.py`, `tests/backtesting/test_backtest_scenarios_atr_band.py` | `Scenario.atr14_pct`, `build_scenarios(..., band=)`, `scenario_gate_inputs()["atr_stop_floor"]` |
| V191-10 | Admission (live side): completed-frame band, `band_no_atr` log, requirements display, live/replay parity | 2 | opus | M `swingbot/core/scanning/analyze.py`, `swingbot/core/scanning/scan_run.py` (`_hard_filters_snapshot` only), `swingbot/core/scanning/requirements.py`; C `tests/scanning/test_horizon_scenarios_atr_band.py`, `tests/scanning/test_atr_band_live_replay_parity.py` | `_horizon_scenarios(..., *, ticker, now)`, `_band_live(...)`, hard-filter key `confluence_atr_stop_floor` |
| V191-11 | Band sizing: worst-fill distance, band stamp key, `size_for` band branch, `band_sizing_verdict` | 2 | sonnet | M `swingbot/core/planning/gap_sizing.py`, `swingbot/core/planning/stop_scope.py`; C `tests/planning/test_band_sizing.py` | `BAND_KEY`, `worst_fill_distance`, `band_sizing_distance`, band branch of `size_for` / `stamp_gap_sizing`, `band_sizing_verdict` |
| V191-12 | `attach_plan_v2` wiring: dollar check, band reasons, heat/fill/reload pins | 2 | opus | M `swingbot/core/scanning/analyze.py`; C `tests/scanning/test_attach_atr_band.py`, `tests/planning/test_plan_manager_atr_band.py` | `_sizing_reject_reason(plan, df, now)`; band reasons through `_no_plan_reason` |
| V191-13 | Alert band line | 2 | sonnet | C `swingbot/core/presentation/band_stop.py`, `tests/presentation/test_band_stop_line.py`; M every `gap_risk_line` render site (`swingbot/core/scanning/execution_embeds.py`, `swingbot/core/infra/notifier.py`, `swingbot/admin/api_v1/trades.py`) | `band_stop_line(plan, *, currency)` |
| V191-14 | Band replay rows: census and outcome rows per arm | 3 | opus | C `swingbot/core/backtesting/atr_band_replay.py`, `tests/backtesting/test_atr_band_replay.py` | everything under `atr_band_replay.py` in § Contracts |
| V191-15 | Funnel Stages −1..1: census verdict, paired MDE, plateau selection | 3 | opus | C `swingbot/core/backtesting/atr_band_funnel.py`, `tests/backtesting/test_atr_band_funnel.py` | constants, `floor_moved`, `stage_minus1`, `stage0`, `stage1` |
| V191-16 | Funnel Stages 2..3, Holm family, reports | 3 | opus | M `swingbot/core/backtesting/atr_band_funnel.py`, `tests/backtesting/test_atr_band_funnel.py` | `stage2`, `stage3`, `holm_family`, `report` |
| V191-17 | Driver `measure_atr_band_stop.py`; reachability text | 3 | sonnet | C `scripts/backtest/measure_atr_band_stop.py`, `tests/backtest_scripts/test_measure_atr_band_stop.py`; M `swingbot/core/backtesting/arms/reachability.py` (row reasons name the driver) | CLI in § Contracts |
| V191-18 | Part B impact report `--side long, short or both` | 3 | sonnet | M `scripts/reports/short_gap_sizing_impact.py`, `tests/scripts/test_short_gap_sizing_impact.py` | `--side` |
| V191-19 | Docs: known-traps, architecture, AGENTS.md | 4 | haiku | M `docs/claude/known-traps.md`, `docs/claude/architecture.md`, `AGENTS.md` | — |
| V191-20 | Stage −1 for both arms via `backtest-runner` | 4 | sonnet | data: `docs/superpowers/results/v191/2026-10-24-v191-arm{K,R}-stageM1.json` (+ census rows); C `docs/superpowers/results/2026-10-24-v191-atr-band-stops.md` (Stage −1 section) | census verdicts |
| V191-21 | Arm K chain, Stages 0→3 | 4 | sonnet | data: `docs/superpowers/results/v191/2026-10-24-v191-armK-stage{0,1,2,3}.json`; M results doc | arm K verdict |
| V191-22 | Arm R chain, Stages 0→3 | 4 | sonnet | data: `docs/superpowers/results/v191/2026-10-24-v191-armR-stage{0,1,2,3}.json`; M results doc | arm R verdict |
| V191-23 | Holm family, results record, ledger rows, closed row or pass record | 4 | sonnet | data: `docs/superpowers/results/v191/2026-10-24-v191-family.json`; M results doc, `docs/superpowers/results/preregistration-ledger.jsonl`, `docs/claude/backtest-methodology.md` (on fail), `AGENTS.md` (on fail), `swingbot/config.py` (knob help names the verdict) | recorded verdicts |
| V191-24 | Part B impact on the replicated live book | 4 | sonnet | C `docs/superpowers/results/2026-10-24-v191-long-gap-sizing-impact.md` | descriptive report |
| V191-25 | Version bump, full suite, merge | 4 | sonnet | M `VERSION.json`, `swingbot/admin/version_history.json` (regenerated by `scripts/dev/build_version_matrix.py`) | merged branch on `main`; `/close-out` follows |
