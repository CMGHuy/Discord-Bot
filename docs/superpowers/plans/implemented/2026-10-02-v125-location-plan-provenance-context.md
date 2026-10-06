# Location, leg phase and plan-provenance entry features — implementation plan

> **For agentic workers:** Use the repo's `task-brief` and one-task implement/review cycle (`superpowers:subagent-driven-development` or `superpowers:executing-plans`). Steps use `- [ ]` for tracking; read the spec with the task.

**Goal:** Stamp nine descriptive keys onto every entry snapshot (live and replay) — whether tp1 is the synthetic `MAX_RISK_REWARD_RATIO` cap, whether the stop is the v115 clamp, where price sits against the nearest zones and the latest confirmed swing range, the leg phase, and the traded zone's lifecycle state, touches and departure — and add them plus a `target_capped × stop_clamped` cross-table to v121's descriptive report.
**Architecture:** A new pure module `swingbot/core/market/location.py` owns `location_features(df, direction, horizon_key)`; it builds the level map on the frame it is given and takes pivots only from v121's `structure.confirmed_pivots`. A pure `plan_provenance(entry, stop, tp1, max_rr)` in `edge/context.py` derives the two flags by exact arithmetic from the **planned** entry, so no builder return type changes. `entry_context` gains one keyword, `entry=None`, and merges both dicts with two unconditional statements; `stamp_entry_context` passes `plan.trigger_price`, and the two direct replay calls in `backtesting/backtest.py` pass the pre-slippage `entry`.
**Tech Stack:** Python 3.11, pandas/numpy, existing `market.levels.build_level_map`, `market.levels_lifecycle.classify_levels`, v121 `market.structure`, pytest (real-Postgres `db_conn` fixture for the storage task).
**Spec:** `docs/superpowers/specs/2026-10-02-v125-location-plan-provenance-context-design.md`
**Bump:** bot patch
**Edge:** none (integrity)
**Progress:** CLOSED 2026-10-06 -- all seven tasks implemented and merged to `main` (merge `37a71380`, bot 2.0.2). Full suite 6397 passed, 3 skipped, 0 failed, 0 xfailed; only the pre-existing `entry_context` C (17) over the complexity limit. Predictions held (`Bump: bot patch`, `Edge: none (integrity)`). `volume_context_report.py` was deliberately never run; its first run waits on the "#3" structure-break entry spec freezing its grid.

## Global constraints

- **Hard dependency: v121 must be merged to `main` before any task here starts.** V125-1 Step 1 is the gate; every other task repeats its one-line check. v125 builds on v121's exact names: `swingbot/core/market/structure.py` (`confirmed_pivots`, `_num`, `STRUCTURE_KEYS`, `structure_features`), the 34-key `FEATURE_KEYS`, `tests/market/structure_fixtures.py`, `tests/db/test_entry_context_doc.py`, `scripts/reports/volume_context_report.py`.
- Measurement only: no gate, score weight, exit rule, alert text, chart, builder return type or backfill change. The structure-break entry trigger ("#3") is a separate expectancy spec.
- **Ordering constraint (load-bearing):** the "#3" structure-break entry spec must be written and its grid frozen **before** `volume_context_report.py` is ever run with these keys. This plan therefore contains **no run of the report at all** — not even v121's optional smoke run — only its unit tests.
- Frozen descriptive definitions (changing one is a new spec): 60-bar minimum (`location.MIN_BARS`), 10-bar departure window (`DEPARTURE_WINDOW`), the lifecycle module's touch tolerance `TOUCH_ATR_MULT × ATR14[t]` (0.25), `1e-6` relative tolerance for `target_capped`, `1e-6` percentage-point tolerance for `stop_clamped`.
- Pivots come **only** from v121's `confirmed_pivots` — never `indicators.zigzag_pivots` or `signals._swing_highs`. Levels come **only** from `levels.build_level_map(df, HORIZONS[horizon_key], Close[t])` built inside the feature function on the frame given.
- `target_capped`/`stop_clamped` use the **planned** entry (trigger), never a fill. Without `entry=` both are `None`, never guessed.
- `max_rr` is `config.MAX_RISK_REWARD_RATIO`, read at call time inside `entry_context` (see "Spec ambiguities resolved" 2).
- Every pre-existing `entry_context` key (all 34 after v121) keeps its value byte-identical. Old records carry no new keys and read `None` via `dict.get` — the existing default, no read-time upcasting, no backfill.
- `entry_context` is `C (17)` (v121 adds no branch): v125 adds **no branch** to it either — two unconditional `out.update(...)` statements. Every new function stays below CC 15 (`python -m radon cc -s -n C <files>`); prototype max is B (6).
- `location_features` and `plan_provenance` never raise: `backtest.py` calls `entry_context` bare (a raise crashes a backtest) and `stamp_entry_context`'s `except` would blank the whole live snapshot.
- Invoke `no-lookahead` on `market/location.py` and `edge/context.py` (V125-3) and `schema-change` for the storage confirmation (V125-5). Read `architecture.md`, `known-traps.md`, `code-complexity.md`, `schema-evolution.md` before editing.
- Each task uses its narrow test files and a focused commit. The full Python suite runs once, in V125-7.

## Spec ambiguities resolved

1. **`plan.entry` does not exist.** `TradePlanV2` (`planning/plan_types.py:31-32`) has `trigger_price` (the planned entry for every plan) and `entry_price` (`None` for `stop_entry`). `stamp_entry_context` passes `entry=getattr(plan, "trigger_price", None)`; `getattr` keeps v121's duck-typed `SimpleNamespace` stamp test (no `trigger_price`) producing a full snapshot with `None` flags instead of an `AttributeError` that would blank it.
2. **Where `max_rr` comes from.** The spec gives `entry_context` exactly one new keyword (`entry=`), so it cannot receive a caller's `ScanParams`. Site check: `ScanParams.from_config()` (`scan_params.py:116`) is the only production constructor and sets `max_risk_reward_ratio=config.MAX_RISK_REWARD_RATIO`; no non-test code overrides it (`git grep -n "max_risk_reward_ratio"`); and `MAX_RISK_REWARD_RATIO` is in config's `"frozen"` search class (`config.py:1138`), so no grid varies it. Reading `config.MAX_RISK_REWARD_RATIO` at call time therefore equals the plan's `ScanParams` value at all five call sites. Only tests that `dataclasses.replace` the field differ; they call `plan_provenance` directly with their own `max_rr`.
3. **"< 60 bars → every new key `None`".** Applies to the seven location keys (spec § Placement). The two flags read no bars, so they are merged **before** `entry_context`'s `len(df) < 20` early return; on a short frame with no `entry=` all nine are `None` (the spec's test, literally), and with an `entry=` the flags are still computed.
4. **"Four call sites."** Three callers (`scanning/analyze.py:396`, `scanning/strategy_pass.py:70`, `backtesting/backtest_scenarios.py:155`) reach `entry_context` through `planning/params.py:stamp_entry_context` and need no edit; the code changes are `params.py:193` and the two direct calls `backtesting/backtest.py:417`, `:495`.
5. **`zone_touches` buckets as continuous** (TRAIN quintiles), not categorical: it is a count up to dozens, unlike v121's 0..10 `absorption_count_10`.
6. **Departure "touch".** "Range touched the level" is `Low <= level + tol and High >= level - tol` with `tol = TOUCH_ATR_MULT × ATR14[t]` — the lifecycle module's tolerance, without `classify_levels`' close-hold condition (the spec says *range*).
7. **Unusable provenance inputs** (`None`/non-finite entry, stop or tp1, `entry <= 0`, `stop == entry`) give both flags `None`; a missing `max_rr` gives `target_capped = None` only. An unknown `horizon_key` gives `None` for the five level-derived keys and still computes `range_pos`/`leg_phase`.

## File map and interfaces

| File | Responsibility |
|---|---|
| `swingbot/core/market/location.py` (new) | `LOCATION_KEYS`, `MIN_BARS`, `DEPARTURE_WINDOW`, `side_levels`, `swing_location`, `zone_departure_atr`, `location_features`. Pure, causal, reads only the frame it is given. |
| `swingbot/core/edge/context.py` | `PROVENANCE_KEYS`, `plan_provenance` (V125-2); nine keys appended to `FEATURE_KEYS`, `entry=` keyword, two merges (V125-3). |
| `swingbot/core/planning/params.py` | `stamp_entry_context` passes `entry=getattr(plan, "trigger_price", None)` (V125-3). |
| `swingbot/core/backtesting/backtest.py` | `:417` and `:495` pass `entry=entry` (V125-4). |
| `scripts/reports/volume_context_report.py` (v121) | Nine keys bucketed; `provenance_table`, `_sum_r`, `_provenance_lines`, `V125_NOTE` (V125-6). |
| Tests (new) | `tests/market/test_location_features.py`, `tests/edge/test_plan_provenance.py`, `tests/edge/test_edge_context_location.py`, `tests/backtesting/test_backtest_provenance.py`, `tests/backtesting/test_replay_provenance.py`, `tests/db/test_entry_context_doc_v125.py`, `tests/scripts/test_volume_context_report_v125.py`. Modified: `tests/backtesting/test_backtest_context.py` (one kwarg). |

Verified anchors (HEAD `427784c7`): `edge/context.py:11` `FEATURE_KEYS`, `:29` `entry_context(df, *, direction, horizon_key, stop, target, asof=None)`, `:33` the `len(df) < 20` early return; `planning/params.py:190` `stamp_entry_context(plan, df, asof)`, `:193` its `entry_context(...)` call inside `try/except Exception`; `backtesting/backtest.py:70` module-level `from swingbot.core.edge.context import entry_context`, `:201` planned entry `= Close[i]`, `:417` v2-branch call (variable `entry`), `:420-427` v1 `entry_fill = apply_frictions(entry, ...)`, `:495` v1 call; `backtest_scenarios.py:155`; `scanning/analyze.py:396`; `scanning/strategy_pass.py:70`; `planning/targets.py:10` `select_structural_target(entry, stop_loss, is_bull, candidate_levels, min_rr, max_rr)`, `:55-56` synthetic `entry ± risk * max_rr`; `planning/builders.py:9` `from swingbot import config`, `:39` `_atr_plan(entry, atr_val, direction, horizon_key, strategy, stop_mult=None, candidate_levels=None, params=None)`, `:365` `CLAMP_HEADROOM_PCT = 0.25`, `:368` `_clamp_stop_to_hard_cap(entry, stop_loss, is_bull)`, `:386` `build_confluence_plan(scenario, df, *, ticker, horizon_key, primary_strategy, level_map=None, quality_inputs=None, params=None, regime2_state=None)` (clamp at `:407`, before target selection at `:414`); `planning/plan_engine.py:15` re-exports `build_confluence_plan`, `_atr_plan`; `planning/lifecycle.py:37` `apply_level_lifecycle` re-selects tp1 via `select_structural_target` after widening, so the identity survives; `risk_limits.py:9` `HARD_MAX_PLANNED_LOSS_PCT = 2.0`, `:17` `planned_loss_pct(entry_price, stop_loss)` (`inf` when invalid); `market/levels.py:108` `Level(price, sources)`, `:564` `build_level_map(df, h, current_price, candidates=None, params=None)` (supports strictly `<` price sorted nearest-first, resistances strictly `>`); `market/levels_lifecycle.py:53` `TOUCH_ATR_MULT = 0.25`, `:64` `_MIN_BARS = 30`, `:68` `LevelState(price, role, state, touches, bars_since_touch, strength, is_king, sources)`, `:114` `classify_levels(df, i, raw_levels, *, horizon_key) -> list[LevelState]` (slices `df.iloc[:i + 1]`); `market/strategy_types.py:44` `HORIZONS` (no horizon has `max_risk_pct` 1.75, so no strategy stop lands on the clamp by accident); `config.py:162` `CLAMP_STOP_TO_HARD_CAP`, `:176` `MAX_RISK_REWARD_RATIO`, `:1138` frozen class; `scan_params.py:62`, `:116`; `planning/plan_types.py:31` `trigger_price`; `tests/conftest.py:32` `make_ohlcv(closes, spread_pct=1.0, volumes=None, start=...)`; `tests/helpers.py:10` `make_ohlcv(closes, *, start, spread=0.01, volume=...)`; `backtesting/acceptance.py:98` `DECIDED`, `:100` `CLOSED`, `:103` `win_rate`, `:111` `expectancy_r`; `db/repositories/base.py:41` `get`, `:67` `insert`; `tracking/performance.py:468` `_db_record`, `:475` `_json_record`; `tests/db/conftest.py:127` `db_conn`. Import-cycle check done: importing `planning.builders` never imports `edge.context` or `backtesting.backtest`, so `context.py` may import `builders` at module level.

## Review focus

1. **A plan object without `trigger_price`** (v121's `SimpleNamespace` stamp test, any duck-typed caller) must still get a full snapshot with `None` flags, not `{}` from the swallowed `AttributeError` — V125-3 `test_live_stamp_on_a_plan_without_a_trigger_keeps_the_snapshot`.
2. **The slipped v1 fill passed instead of the trigger** silently hides every capped target (the synthetic price is relative to the trigger) — V125-4 `test_the_slipped_fill_would_have_hidden_the_cap`.
3. **NaN bars, an unknown horizon key, a flat (ATR 0) frame** must not raise — a raise crashes a backtest (`backtest.py` calls `entry_context` bare) or blanks the live snapshot — V125-1 `test_nan_bars_do_not_raise`, `test_unknown_horizon_...`, `test_flat_prices_...`.
4. **The clamp switched off or a hot-reloaded cap**: a 1.75% stop with `CLAMP_STOP_TO_HARD_CAP` off is not "clamped", and `MAX_RISK_REWARD_RATIO` is read at call time, not import time — V125-2 `test_clamp_flag_off_means_never_clamped`, V125-3 `test_snapshot_provenance_reads_the_planned_entry_and_config_cap` (monkeypatches `config` after import).
5. **Old live records with no v125 keys** must land in a `"None"/"None"` cross-table cell, not raise `KeyError` — V125-6 `test_provenance_cross_table_splits_source_direction_and_cell` (the "old record" row).

## Parallelisation

- **Group A (parallel, after V125-1 Step 1's v121 gate passes):** V125-1, V125-2, V125-5 — disjoint files (`market/location.py` + `tests/market/test_location_features.py`; `edge/context.py` + `tests/edge/test_plan_provenance.py`; `tests/db/test_entry_context_doc_v125.py`). No contract dependency: V125-5 uses literal key names and the existing `FEATURE_KEYS`, never `plan_provenance` or `location_features`; V125-1 and V125-2 consume nothing from each other.
- **Sequential:** V125-3 after V125-1 and V125-2 (consumes `location_features`, `LOCATION_KEYS`, `plan_provenance`, `PROVENANCE_KEYS`, and edits `edge/context.py`, the file V125-2 edits).
- **Group B (parallel, after V125-3):** V125-4 and V125-6 — disjoint files (`backtesting/backtest.py` + `tests/backtesting/*` vs `scripts/reports/volume_context_report.py` + `tests/scripts/*`). V125-4 consumes the `entry=` keyword V125-3 adds; V125-6 buckets the keys V125-3 makes `entry_context` emit (its tests use literal rows, but its strategy rows are stamped through V125-3's `stamp_entry_context`). Neither consumes the other.
- **Sequential:** V125-7 last (the single full-suite run and the release).

# Phase 1 — Pure features

### Task V125-1: `market/location.py` — location, leg-phase and zone features

**Files:** Create `swingbot/core/market/location.py`, `tests/market/test_location_features.py`.

**Interfaces:**
- Consumes (v121, must exist on `main`): `swingbot.core.market.structure.confirmed_pivots(df, k=PIVOT_K) -> pd.DataFrame` (columns include `last_sh`, `last_sl`; NaN when missing), `structure._num(value) -> float | None` (finite, rounded to 6), `structure.STRUCTURE_KEYS`; fixtures `tests.market.structure_fixtures.UP`, `BROKEN`, `frame(points, *, mirror=False)`, `wavy_frame(n=300)`. Existing: `levels.build_level_map`, `levels.Level`, `levels_lifecycle.classify_levels`, `levels_lifecycle.TOUCH_ATR_MULT`, `indicators.atr`, `strategy_types.HORIZONS`.
- Produces: `MIN_BARS = 60`; `DEPARTURE_WINDOW = 10`; `LOCATION_KEYS = ("zone_dist_atr", "room_atr", "range_pos", "leg_phase", "zone_state", "zone_touches", "zone_departure_atr")`; `side_levels(df, horizon_key, direction) -> tuple[Level | None, Level | None]` (entry-side, opposing); `swing_location(df, direction) -> dict` (`range_pos`, `leg_phase`); `zone_departure_atr(df, t, level, direction, atr_value) -> float | None`; `location_features(df, direction, horizon_key) -> dict` with exactly `LOCATION_KEYS`. `leg_phase` is `"impulse" | "pullback" | "broken" | None`; `zone_state` is one of `levels_lifecycle.STATES` or `None`; `zone_touches` is `int | None`; floats rounded to 6. The module imports `build_level_map` by name, so tests pin it with `monkeypatch.setattr(location, "build_level_map", ...)`.

- [ ] **Step 1: v121 gate — implementation starts only after v121 is merged.** On an up-to-date `main`, run:

```bash
git log --oneline main | grep -c "v121"
git grep -n "^def confirmed_pivots\|^def _num\|^STRUCTURE_KEYS\|^def structure_features" -- swingbot/core/market/structure.py
git grep -n "impulse_range_decay\")" -- swingbot/core/edge/context.py
git grep -n "^def frame\|^def wavy_frame\|^UP = \|^BROKEN = " -- tests/market/structure_fixtures.py
git grep -n "^CATEGORICAL\|^CONTINUOUS\|^def render\|^def bucket_of" -- scripts/reports/volume_context_report.py
git grep -n "def test_" -- tests/db/test_entry_context_doc.py
```

Expect: every grep returns a line (`confirmed_pivots`, `_num`, `STRUCTURE_KEYS`, `structure_features`; the v121 `FEATURE_KEYS` tail ending `"impulse_range_decay")`; the four fixtures; the four report symbols; three storage tests). **If any is missing, stop and report `BLOCKED: v121 not merged` to the controller** — do not create `structure.py` or any v121 file here. Also confirm `python -m pytest tests/market/test_structure_features.py -q` passes on `main`.

- [ ] **Step 2: Write the failing tests.**

```python
# tests/market/test_location_features.py
"""v125: location, leg-phase and zone-quality features (market/location.py)."""
import numpy as np
import pytest

from swingbot.core.market import levels
from swingbot.core.market import location as lo
from swingbot.core.market import structure as st
from swingbot.core.market.indicators import atr
from swingbot.core.market.levels_lifecycle import classify_levels
from tests.conftest import make_ohlcv
from tests.market.structure_fixtures import BROKEN, UP, frame, wavy_frame

IMPULSE = UP + [135]            # closes through the last confirmed SH (130) without forming a new pivot


def _atr14(df):
    return float(atr(df, 14).iloc[-1])


def _mock_levels(monkeypatch, below=(), above=()):
    """Pin build_level_map so zone answers are exact. Nearest-first, like the real one."""
    supports = [levels.Level(p, ["test"]) for p in sorted(below, reverse=True)]
    resistances = [levels.Level(p, ["test"]) for p in sorted(above)]
    monkeypatch.setattr(lo, "build_level_map", lambda df, h, price: (supports, resistances))


def _departure_frame(after, before=60, level=100.0):
    """`before` flat bars ON the level (High == Low == Close), then the `after` closes."""
    return make_ohlcv(np.r_[np.full(before, level), np.asarray(after, dtype=float)], spread_pct=0.0)


# --- range_pos / leg_phase (latest confirmed swing range) --------------------

def test_mid_range_close_is_about_half():
    # last SH 130 (High 130.65), last SL 124 (Low 123.38), close 127
    out = lo.location_features(frame(UP), "bullish", "2w")
    assert out["range_pos"] == round(3.62 / 7.27, 6)
    assert out["leg_phase"] == "pullback"


def test_bearish_mid_range_mirror():
    # mirrored: last SH 126 (High 126.63), last SL 120 (Low 119.4), close 123
    out = lo.location_features(frame(UP, mirror=True), "bearish", "2w")
    assert out["range_pos"] == round(3.63 / 7.23, 6)
    assert out["leg_phase"] == "pullback"


@pytest.mark.parametrize("mirror,direction", [(False, "bullish"), (True, "bearish")])
def test_close_beyond_the_last_swing_high_is_impulse(mirror, direction):
    out = lo.location_features(frame(IMPULSE, mirror=mirror), direction, "2w")
    assert out["leg_phase"] == "impulse"
    assert out["range_pos"] > 1.0                  # not clipped


@pytest.mark.parametrize("mirror,direction", [(False, "bullish"), (True, "bearish")])
def test_close_through_the_last_swing_low_is_broken(mirror, direction):
    out = lo.location_features(frame(BROKEN, mirror=mirror), direction, "2w")
    assert out["leg_phase"] == "broken"
    assert out["range_pos"] < 0.0                  # not clipped


def test_counter_direction_reads_the_same_range_from_the_other_side():
    df = frame(UP)
    bull, bear = lo.swing_location(df, "bullish"), lo.swing_location(df, "bearish")
    assert bull["range_pos"] + bear["range_pos"] == pytest.approx(1.0, abs=1e-6)
    assert bear["leg_phase"] == "pullback"


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_swing_location_matches_the_full_frame_pivots_on_every_cut(direction):
    df = wavy_frame()
    full = st.confirmed_pivots(df)
    for t in range(lo.MIN_BARS, len(df)):
        got = lo.swing_location(df.iloc[:t + 1], direction)
        sh, sl = full["last_sh"].iloc[t], full["last_sl"].iloc[t]
        close = float(df["Close"].iloc[t])
        if np.isnan(sh) or np.isnan(sl):
            assert got == {"range_pos": None, "leg_phase": None}, t
            continue
        raw = (close - sl) / (sh - sl) if direction == "bullish" else (sh - close) / (sh - sl)
        assert got["range_pos"] == (round(raw, 6) if sh > sl else None), t


def test_no_confirmed_swing_gives_none():
    df = make_ohlcv(np.linspace(100, 160, 80), spread_pct=1.0)       # straight line: no pivot at all
    assert lo.swing_location(df, "bullish") == {"range_pos": None, "leg_phase": None}


# --- zone_dist_atr / room_atr / zone_state / zone_touches --------------------

def test_price_sitting_on_a_support(monkeypatch):
    df = frame(UP)
    close, a = float(df["Close"].iloc[-1]), _atr14(df)
    _mock_levels(monkeypatch, below=[close - 0.1 * a, close - 4 * a], above=[close + 2 * a])
    out = lo.location_features(df, "bullish", "2w")
    assert out["zone_dist_atr"] == pytest.approx(0.1, abs=1e-6)
    assert out["room_atr"] == pytest.approx(2.0, abs=1e-6)


def test_bearish_zone_is_the_nearest_resistance(monkeypatch):
    df = frame(UP, mirror=True)
    close, a = float(df["Close"].iloc[-1]), _atr14(df)
    _mock_levels(monkeypatch, below=[close - 2 * a], above=[close + 0.1 * a, close + 5 * a])
    out = lo.location_features(df, "bearish", "2w")
    assert out["zone_dist_atr"] == pytest.approx(0.1, abs=1e-6)
    assert out["room_atr"] == pytest.approx(2.0, abs=1e-6)


def test_no_level_on_a_side_gives_none_for_that_side_only(monkeypatch):
    df = frame(UP)
    _mock_levels(monkeypatch, below=[], above=[float(df["Close"].iloc[-1]) + 1.0])
    out = lo.location_features(df, "bullish", "2w")
    assert out["zone_dist_atr"] is None and out["zone_state"] is None
    assert out["zone_touches"] is None and out["zone_departure_atr"] is None
    assert out["room_atr"] is not None and out["range_pos"] is not None


def test_an_untouched_support_is_fresh(monkeypatch):
    _mock_levels(monkeypatch, below=[60.0])
    out = lo.location_features(frame(UP), "bullish", "2w")
    assert (out["zone_state"], out["zone_touches"], out["zone_departure_atr"]) == ("fresh", 0, None)


def test_a_retested_swing_low_is_tested_and_counted(monkeypatch):
    df = frame(UP)
    level = float(df["Low"].iloc[80])          # the 124 trough's Low, 123.38; last touched at bar 80
    _mock_levels(monkeypatch, below=[level])
    out = lo.location_features(df, "bullish", "2w")
    state = classify_levels(df, len(df) - 1, [level], horizon_key="2w")[0]
    assert (out["zone_state"], out["zone_touches"]) == ("tested", state.touches)
    assert out["zone_touches"] == 5
    # best close in bars 81..88 is the entry close 127: (127 - 123.38) / ATR14
    assert out["zone_departure_atr"] == pytest.approx(3.62 / _atr14(df), abs=1e-6)


def test_real_level_map_is_built_on_the_frame_given():
    df = wavy_frame()
    close, a = float(df["Close"].iloc[-1]), _atr14(df)
    supports, resistances = levels.build_level_map(df, lo.HORIZONS["2w"], close)
    bull = lo.location_features(df, "bullish", "2w")
    bear = lo.location_features(df, "bearish", "2w")
    assert bull["zone_dist_atr"] == pytest.approx((close - supports[0].price) / a, abs=1e-6)
    assert bull["room_atr"] == pytest.approx((resistances[0].price - close) / a, abs=1e-6)
    assert (bear["zone_dist_atr"], bear["room_atr"]) == (bull["room_atr"], bull["zone_dist_atr"])


# --- zone_departure_atr ------------------------------------------------------

def test_touch_then_a_three_atr_close_away():
    df = _departure_frame([100.5, 101.5, 103.0, 102.0, 101.0])
    assert lo.zone_departure_atr(df, len(df) - 1, 100.0, "bullish", 1.0) == 3.0


def test_bearish_departure_mirror():
    df = _departure_frame([99.5, 98.5, 97.0, 98.0, 99.0])
    assert lo.zone_departure_atr(df, len(df) - 1, 100.0, "bearish", 1.0) == 3.0


def test_departure_window_is_capped_at_t_and_reads_nothing_after_it():
    df = _departure_frame([100.5, 101.5, 103.0, 102.0, 101.0])
    poisoned = df.copy()
    poisoned.iloc[62:, :4] = 1_000.0
    assert lo.zone_departure_atr(df, 61, 100.0, "bullish", 1.0) == 1.5
    assert lo.zone_departure_atr(poisoned, 61, 100.0, "bullish", 1.0) == 1.5
    assert lo.zone_departure_atr(df.iloc[:62], 61, 100.0, "bullish", 1.0) == 1.5


def test_departure_counts_only_ten_bars_after_the_touch():
    df = _departure_frame(100.0 + np.arange(1, 13))        # closes 101 .. 112; last touch is bar 59
    assert lo.zone_departure_atr(df, len(df) - 1, 100.0, "bullish", 1.0) == 10.0


def test_a_touch_on_the_entry_bar_itself_is_not_the_last_touch():
    df = _departure_frame([103.0, 104.0, 100.0])           # bar t = 62 sits on the level
    assert lo.zone_departure_atr(df, 62, 100.0, "bullish", 1.0) == 4.0


def test_departure_is_signed_when_price_fell_through():
    df = _departure_frame([99.8, 99.0, 98.0])              # bar 60 still touches (tol 0.25)
    assert lo.zone_departure_atr(df, 62, 100.0, "bullish", 1.0) == -1.0


def test_no_touch_no_level_or_no_atr_gives_none():
    df = _departure_frame([100.5, 101.5, 103.0])
    assert lo.zone_departure_atr(df, 62, 50.0, "bullish", 1.0) is None
    assert lo.zone_departure_atr(df, 62, None, "bullish", 1.0) is None
    assert lo.zone_departure_atr(df, 62, 100.0, "bullish", 0.0) is None


def test_departure_is_truncation_stable_on_every_cut():
    df = wavy_frame()
    for t in range(1, len(df)):
        poisoned = df.copy()
        poisoned.iloc[t + 1:, :4] = 1_000.0
        expected = lo.zone_departure_atr(df.iloc[:t + 1], t, 104.0, "bullish", 1.0)
        assert lo.zone_departure_atr(df, t, 104.0, "bullish", 1.0) == expected, t
        assert lo.zone_departure_atr(poisoned, t, 104.0, "bullish", 1.0) == expected, t


# --- degenerate frames -------------------------------------------------------

def test_short_frame_returns_all_none():
    out = lo.location_features(frame(UP).iloc[:59], "bullish", "2w")
    assert set(out) == set(lo.LOCATION_KEYS)
    assert all(value is None for value in out.values())
    assert lo.location_features(frame(UP).iloc[:60], "bullish", "2w")["zone_dist_atr"] is not None


def test_flat_prices_have_no_atr_and_return_all_none():
    out = lo.location_features(make_ohlcv(np.full(80, 100.0), spread_pct=0.0), "bullish", "2w")
    assert all(value is None for value in out.values())


def test_nan_bars_do_not_raise():
    df = frame(UP).copy()
    df.iloc[40:42, df.columns.get_loc("High")] = np.nan
    df.iloc[50, df.columns.get_loc("Close")] = np.nan
    out = lo.location_features(df, "bullish", "2w")
    assert set(out) == set(lo.LOCATION_KEYS)


def test_unknown_horizon_leaves_level_keys_none_and_does_not_raise():
    out = lo.location_features(frame(UP), "bullish", "no-such-horizon")
    assert out["zone_dist_atr"] is None and out["room_atr"] is None and out["zone_state"] is None
    assert out["leg_phase"] == "pullback"


def test_keys_are_disjoint_from_v121_structure_keys():
    assert not set(lo.LOCATION_KEYS) & set(st.STRUCTURE_KEYS)
```

- [ ] **Step 3:** Run `python scripts/dev/testrun.py file tests/market/test_location_features.py`; expect FAIL (`ImportError: cannot import name 'location'`).

- [ ] **Step 4: Implement the module.**

```python
# swingbot/core/market/location.py
"""Location, leg-phase and zone-quality features at the entry bar (v125).

Every value is computed at ``df``'s final bar from ``df`` alone, so the
caller's slicing (``df.iloc[:i + 1]`` in replay, the completed frame live)
is the only time boundary. Swing pivots come only from v121's
``structure.confirmed_pivots`` (the single home of the confirmation lag);
levels come from ``levels.build_level_map`` built here on the same frame;
zone lifecycle comes from ``levels_lifecycle.classify_levels``, which slices
to ``:i + 1`` itself. Frozen descriptive constants: 60-bar minimum, 10-bar
departure window, the lifecycle module's TOUCH_ATR_MULT touch tolerance.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.market.indicators import atr
from swingbot.core.market.levels import build_level_map
from swingbot.core.market.levels_lifecycle import TOUCH_ATR_MULT, classify_levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.market.structure import _num, confirmed_pivots

MIN_BARS = 60             # below this every key is None
DEPARTURE_WINDOW = 10     # frozen: bars after the last touch that count as the departure
LOCATION_KEYS = ("zone_dist_atr", "room_atr", "range_pos", "leg_phase",
                 "zone_state", "zone_touches", "zone_departure_atr")


def side_levels(df: pd.DataFrame, horizon_key: str, direction: str):
    """(entry-side level, opposing level) as ``levels.Level`` or None.

    Bullish: nearest support below the close, nearest resistance above.
    Bearish mirrors. Unknown horizon -> (None, None)."""
    h = HORIZONS.get(horizon_key)
    if h is None:
        return None, None
    supports, resistances = build_level_map(df, h, float(df["Close"].iloc[-1]))
    support = supports[0] if supports else None
    resistance = resistances[0] if resistances else None
    return (support, resistance) if direction == "bullish" else (resistance, support)


def _range_pos(close: float, sh: float, sl: float, bullish: bool) -> float | None:
    if not sh > sl:
        return None
    return _num((close - sl) / (sh - sl) if bullish else (sh - close) / (sh - sl))


def _leg_phase(close: float, sh: float, sl: float, bullish: bool) -> str:
    beyond, broken = (close > sh, close < sl) if bullish else (close < sl, close > sh)
    if beyond:
        return "impulse"
    return "broken" if broken else "pullback"


def swing_location(df: pd.DataFrame, direction: str) -> dict:
    """``range_pos`` and ``leg_phase`` from the last confirmed swing high/low."""
    piv = confirmed_pivots(df).iloc[-1]
    sh, sl = piv["last_sh"], piv["last_sl"]
    if pd.isna(sh) or pd.isna(sl):
        return {"range_pos": None, "leg_phase": None}
    close, bullish = float(df["Close"].iloc[-1]), direction == "bullish"
    return {"range_pos": _range_pos(close, float(sh), float(sl), bullish),
            "leg_phase": _leg_phase(close, float(sh), float(sl), bullish)}


def zone_departure_atr(df: pd.DataFrame, t: int, level: float | None, direction: str,
                       atr_value: float | None) -> float | None:
    """Best direction-signed close beyond ``level`` in the DEPARTURE_WINDOW bars
    after the last bar ``j < t`` whose range touched it, in ATR. Reads bars
    ``0..t`` only, even when the window would run past ``t``."""
    if level is None or not atr_value:
        return None
    tol = atr_value * TOUCH_ATR_MULT
    high = df["High"].to_numpy(float)[:t]
    low = df["Low"].to_numpy(float)[:t]
    touched = np.flatnonzero((low <= level + tol) & (high >= level - tol))
    if not touched.size:
        return None
    j = int(touched[-1])
    window = df["Close"].to_numpy(float)[j + 1:min(j + DEPARTURE_WINDOW, t) + 1]
    if not window.size:
        return None
    sign = 1.0 if direction == "bullish" else -1.0
    return _num(float(np.max(sign * (window - level))) / atr_value)


def _zone_lifecycle(df: pd.DataFrame, level, horizon_key: str) -> dict:
    states = classify_levels(df, len(df) - 1, [level], horizon_key=horizon_key) if level is not None else []
    if not states:
        return {"zone_state": None, "zone_touches": None}
    return {"zone_state": states[0].state, "zone_touches": int(states[0].touches)}


def _distance_atr(close: float, level, atr_value: float) -> float | None:
    return None if level is None else _num(abs(close - float(level.price)) / atr_value)


def location_features(df: pd.DataFrame, direction: str, horizon_key: str) -> dict:
    """Every LOCATION_KEYS value at ``df``'s final bar, for the trade's
    direction. < 60 bars or no ATR returns all None; never raises on NaN bars."""
    out = dict.fromkeys(LOCATION_KEYS)
    if df is None or len(df) < MIN_BARS:
        return out
    atr_value = _num(atr(df, 14).iloc[-1])
    if not atr_value:
        return out
    close, t = float(df["Close"].iloc[-1]), len(df) - 1
    entry_side, opposing = side_levels(df, horizon_key, direction)
    out.update(zone_dist_atr=_distance_atr(close, entry_side, atr_value),
               room_atr=_distance_atr(close, opposing, atr_value),
               zone_departure_atr=zone_departure_atr(
                   df, t, None if entry_side is None else float(entry_side.price), direction, atr_value))
    out.update(swing_location(df, direction))
    out.update(_zone_lifecycle(df, entry_side, horizon_key))
    return out
```

**Implementation detail.** `_num(atr)` rounds ATR to 6 dp before it divides, exactly as v121's `structure_features` does, which is why the ATR-scaled assertions use `pytest.approx(..., abs=1e-6)`. `build_level_map` excludes a level exactly at the close (strict `<`/`>`), which matches `classify_levels`' role split (`price < spot` is a floor). `zone_departure_atr` slices `High`/`Low` to `[:t]` (touches strictly before `t`) and the window to `≤ t`, so even a full frame passed with an earlier `t` cannot leak — the poisoned-future tests pin it. On the wavy fixture `zone_departure_atr` equals `zone_dist_atr` because the entry close is the best close since a touch within 10 bars; that is the definition, not a duplicate (the departure-frame tests show them apart).

- [ ] **Step 5:** Run `python scripts/dev/testrun.py file tests/market/test_location_features.py`; expect PASS (29 tests). Run `python -m radon cc -s -n C swingbot/core/market/location.py` (expect no output; prototype max `zone_departure_atr` B (6)).
- [ ] **Step 6:** Commit.

```bash
git add swingbot/core/market/location.py tests/market/test_location_features.py
git commit -m "feat(v125): location, leg-phase and zone-quality entry features in market/location.py"
```

### Task V125-2: `plan_provenance` — synthetic-target and clamped-stop flags

**Files:** Modify `swingbot/core/edge/context.py` (imports, constants, four helpers; **`entry_context` and `FEATURE_KEYS` untouched in this task**); create `tests/edge/test_plan_provenance.py`.

**Interfaces:**
- Consumes (existing): `config.CLAMP_STOP_TO_HARD_CAP`; `planning.builders.CLAMP_HEADROOM_PCT`; `risk_limits.HARD_MAX_PLANNED_LOSS_PCT`, `risk_limits.planned_loss_pct`; for tests `plan_engine.build_confluence_plan`, `builders._atr_plan`, `targets.select_structural_target`, `ScanParams.from_config`, `levels.Level`, `tests.helpers.make_ohlcv`.
- Produces: `PROVENANCE_KEYS = ("target_capped", "stop_clamped")`; `CAP_TOLERANCE = 1e-6`; `CLAMP_TOLERANCE = 1e-6`; `plan_provenance(entry, stop, tp1, max_rr) -> dict` with exactly `PROVENANCE_KEYS`, values `bool | None`. Pure, reads no bars, never raises.

- [ ] **Step 1:** Repeat the v121 gate: `git grep -n "impulse_range_decay\")" -- swingbot/core/edge/context.py` returns a line (else `BLOCKED: v121 not merged`).

- [ ] **Step 2: Write the failing tests.**

```python
# tests/edge/test_plan_provenance.py
"""v125: target_capped / stop_clamped derived from real builder output."""
import dataclasses
import types

import pytest

from swingbot import config
from swingbot.core.edge.context import PROVENANCE_KEYS, plan_provenance
from swingbot.core.market import levels
from swingbot.core.planning.builders import _atr_plan
from swingbot.core.planning.plan_engine import build_confluence_plan
from swingbot.core.planning.targets import select_structural_target
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv

MAX_RR = 2.5


def _params():
    return dataclasses.replace(ScanParams.from_config(),
                               min_risk_reward_ratio=1.5, max_risk_reward_ratio=MAX_RR)


def _scenario(direction, entry, stop_loss, take_profit):
    return types.SimpleNamespace(direction=direction, entry=entry, stop_loss=stop_loss,
                                 take_profit=take_profit, target_sources=["Rolling S/R"],
                                 stop_sources=["Rolling S/R"])


def _plan(direction, entry, stop_loss, take_profit, level_map=None):
    plan = build_confluence_plan(
        _scenario(direction, entry, stop_loss, take_profit), make_ohlcv([entry] * 60),
        ticker="XYZ", horizon_key="4w", primary_strategy="S/R Confluence",
        level_map=level_map, params=_params())
    assert plan is not None
    return plan


def _flags(plan):
    return plan_provenance(plan.trigger_price, plan.stop_loss, plan.tp1, MAX_RR)


@pytest.fixture(autouse=True)
def clamp_on(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)


@pytest.mark.parametrize("direction,stop,target,capped_tp1", [
    ("bullish", 98.5, 110.0, 103.75), ("bearish", 101.5, 90.0, 96.25)])
def test_nearest_level_beyond_the_cap_is_flagged_capped(direction, stop, target, capped_tp1):
    plan = _plan(direction, 100.0, stop, target)
    assert plan.tp1 == pytest.approx(capped_tp1)               # the synthetic price, not the level
    assert _flags(plan) == {"target_capped": True, "stop_clamped": False}


@pytest.mark.parametrize("direction,stop,target,clamped_stop", [
    ("bullish", 96.0, 104.0, 98.25), ("bearish", 104.0, 96.0, 101.75)])
def test_a_stop_beyond_two_percent_is_flagged_clamped(direction, stop, target, clamped_stop):
    plan = _plan(direction, 100.0, stop, target)
    assert plan.stop_loss == pytest.approx(clamped_stop)
    assert _flags(plan) == {"target_capped": False, "stop_clamped": True}


def test_clamped_and_capped_together():
    plan = _plan("bullish", 100.0, 96.0, 112.0)                # risk 1.75 -> cap 104.375
    assert (plan.stop_loss, plan.tp1) == (pytest.approx(98.25), pytest.approx(104.375))
    assert _flags(plan) == {"target_capped": True, "stop_clamped": True}


def test_an_ordinary_plan_is_neither():
    plan = _plan("bullish", 100.0, 98.5, 103.0)                # 2.0R real level, 1.5% stop
    assert _flags(plan) == {"target_capped": False, "stop_clamped": False}


def test_a_real_level_inside_the_band_is_not_capped():
    resistances = [levels.Level(p, ["Fibonacci"]) for p in (103.0, 104.5, 112.0)]
    supports = [levels.Level(90.0, ["Rolling S/R"])]
    plan = _plan("bullish", 100.0, 95.0, 112.0, level_map=(supports, resistances))
    assert plan.tp1 == pytest.approx(103.0)
    assert _flags(plan) == {"target_capped": False, "stop_clamped": True}


def test_capped_flag_holds_on_an_awkward_price():
    entry, stop = 613.37, 604.21
    tp1 = select_structural_target(entry, stop, True, [700.0], 1.5, MAX_RR)
    assert plan_provenance(entry, stop, tp1, MAX_RR)["target_capped"] is True


def test_strategy_atr_plan_on_the_cap_is_flagged():
    # 2w: risk = 2 ATR, cap = 5 ATR. Only a 9-ATR candidate -> synthetic cap price.
    stop, tp1 = _atr_plan(100.0, 1.0, "bullish", "2w", "RSI", candidate_levels=[109.0], params=_params())
    assert tp1 == pytest.approx(105.0)
    assert plan_provenance(100.0, stop, tp1, MAX_RR) == {"target_capped": True, "stop_clamped": False}


def test_no_entry_gives_none_never_a_guess():
    assert plan_provenance(None, 98.0, 104.0, MAX_RR) == {"target_capped": None, "stop_clamped": None}
    assert set(PROVENANCE_KEYS) == {"target_capped", "stop_clamped"}


@pytest.mark.parametrize("entry,stop,tp1", [(100.0, None, 104.0), (100.0, 98.0, None),
                                            (float("nan"), 98.0, 104.0), (0.0, -1.0, 2.0),
                                            (100.0, 100.0, 104.0), ("x", 98.0, 104.0)])
def test_unusable_inputs_give_none(entry, stop, tp1):
    assert plan_provenance(entry, stop, tp1, MAX_RR) == {"target_capped": None, "stop_clamped": None}


def test_missing_max_rr_leaves_only_target_capped_unknown():
    assert plan_provenance(100.0, 98.25, 104.375, None) == {"target_capped": None, "stop_clamped": True}


def test_clamp_flag_off_means_never_clamped(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
    assert plan_provenance(100.0, 98.25, 104.0, MAX_RR)["stop_clamped"] is False


def test_a_stop_just_inside_the_landing_is_not_clamped():
    assert plan_provenance(100.0, 98.26, 104.0, MAX_RR)["stop_clamped"] is False
```

- [ ] **Step 3:** Run `python scripts/dev/testrun.py file tests/edge/test_plan_provenance.py`; expect FAIL (`ImportError: cannot import name 'PROVENANCE_KEYS'`).

- [ ] **Step 4: Implement.** In `swingbot/core/edge/context.py`, add to the imports (keep alphabetical with the existing ones; `structure_features` is v121's):

```python
from swingbot import config
from swingbot.core.planning.builders import CLAMP_HEADROOM_PCT
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
```

Directly below the `FEATURE_KEYS` tuple add the constants, and below `_pctile` add the helpers:

```python
PROVENANCE_KEYS = ("target_capped", "stop_clamped")
CAP_TOLERANCE = 1e-6       # frozen: relative price tolerance for the synthetic-target identity
CLAMP_TOLERANCE = 1e-6     # frozen: absolute tolerance, in percentage points, for the clamp identity
```

```python
def _finite(*values) -> bool:
    try:
        return all(value is not None and math.isfinite(float(value)) for value in values)
    except (TypeError, ValueError):
        return False


def _target_capped(entry: float, stop: float, tp1: float, max_rr) -> bool | None:
    """tp1 sits exactly where select_structural_target puts its SYNTHETIC cap price."""
    if not _finite(max_rr):
        return None
    synthetic = entry + (entry - stop) * float(max_rr)
    return abs(tp1 - synthetic) <= CAP_TOLERANCE * max(1.0, abs(entry))


def _stop_clamped(entry: float, stop: float) -> bool:
    """stop sits exactly where _clamp_stop_to_hard_cap moves a wide confluence stop."""
    landing = HARD_MAX_PLANNED_LOSS_PCT - CLAMP_HEADROOM_PCT
    return bool(config.CLAMP_STOP_TO_HARD_CAP) and abs(planned_loss_pct(entry, stop) - landing) <= CLAMP_TOLERANCE


def plan_provenance(entry, stop, tp1, max_rr) -> dict:
    """Whether a plan's tp1 is the synthetic max_rr cap and its stop the v115
    clamp, derived from the PLANNED entry. Both None without a usable entry,
    stop and tp1 -- never guessed. Pure; reads no bars."""
    if not _finite(entry, stop, tp1) or float(entry) <= 0 or float(entry) == float(stop):
        return dict.fromkeys(PROVENANCE_KEYS)
    entry, stop, tp1 = float(entry), float(stop), float(tp1)
    return {"target_capped": _target_capped(entry, stop, tp1, max_rr),
            "stop_clamped": _stop_clamped(entry, stop)}
```

**Implementation detail.** `entry + (entry - stop) * max_rr` is `select_structural_target`'s `entry ± abs(entry - stop) * max_rr` with the sign taken from the stop's side — identical magnitude bit for bit, so no direction argument is needed. Both flags are spec-literal: `stop_clamped` does not look at `source`, because no strategy stop ceiling is 1.75% (`HORIZONS[*]["max_risk_pct"]` ≥ 2.0, capped at 2.0). `config` is read at call time (hot reload). The `builders` import is cycle-free (verified: importing `planning.builders` never imports `edge.context`).

- [ ] **Step 5:** Run `python scripts/dev/testrun.py file tests/edge/test_plan_provenance.py`; expect PASS (19 tests). Then `python -c "import swingbot.core.edge.context; import swingbot.core.backtesting.backtest"` and `python -c "import swingbot.core.backtesting.backtest"` in fresh interpreters (expect no `ImportError`). Run `python -m radon cc -s swingbot/core/edge/context.py`: new helpers A, `entry_context` still `C (17)`.
- [ ] **Step 6:** Commit.

```bash
git add swingbot/core/edge/context.py tests/edge/test_plan_provenance.py
git commit -m "feat(v125): plan_provenance -- synthetic-target and clamped-stop flags from the planned entry"
```

# Phase 2 — Snapshot integration and storage

### Task V125-3: Merge provenance and location into the entry snapshot

**Files:** Modify `swingbot/core/edge/context.py` (`FEATURE_KEYS`, `entry_context`), `swingbot/core/planning/params.py:190-196` (`stamp_entry_context`); create `tests/edge/test_edge_context_location.py`.

**Interfaces:**
- Consumes (V125-1): `location_features(df, direction, horizon_key) -> dict`, `LOCATION_KEYS`. (V125-2): `plan_provenance(entry, stop, tp1, max_rr) -> dict`, `PROVENANCE_KEYS`. (v121): `structure.STRUCTURE_KEYS`, `structure_features`, fixtures `UP`, `MIXED`, `BROKEN`, `frame`, `pullback_frame`, `slowing_pullback_frame`, `wavy_frame`.
- Produces: `FEATURE_KEYS` = v121's 34 keys in their order, then `"target_capped", "stop_clamped", "zone_dist_atr", "room_atr", "range_pos", "leg_phase", "zone_state", "zone_touches", "zone_departure_atr"` (43 total). `entry_context(df, *, direction, horizon_key, stop, target, asof=None, entry=None) -> dict`. `stamp_entry_context(plan, df, asof)` signature unchanged; it now passes `entry=getattr(plan, "trigger_price", None)`.

- [ ] **Step 1: Write the witness test FIRST and run it on the unchanged code.** The literal values below are what `entry_context` returned on this fixture with the v121 plan's code (prototyped 2026-10-02). If any differs on merged `main`, recapture from the **unchanged** code (after V125-2, before Step 4 — V125-2 does not touch `entry_context`) and record why in the commit body — never edit the witness after touching `entry_context`.

```python
# tests/edge/test_edge_context_location.py
"""v125: entry_context carries plan provenance and location features."""
import numpy as np
import pytest

from swingbot.core.edge.context import entry_context
from tests.conftest import make_ohlcv

ASOF = {"regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": None, "rs_combined": 61.0}
_COMMON = {
    "stop_atr": 3.389932, "stop_pct": 5.588532, "planned_rr": 2.0, "swing_high_atr": 3.127987,
    "swing_low_atr": -2.005931, "horizon_key": "2w", "atr_pctile_250": 36.0, "vol_ratio_20": 1.115516,
    "rsi_14": 19.789007, "adx_14": 42.545477, "bb_width_pctile_250": None, "gap_p90_pct": 0.0,
    "gap_fragile": False, "dow": 0, "regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": None,
    "rs_combined": 61.0, "structure_state": "down", "vol_trend_10_50": 1.086677, "range_trend_10_50": 0.914935,
    "absorption_bar": False, "absorption_count_10": 0, "impulse_range_decay": None,
}
WITNESS = {
    "bullish": {**_COMMON, "direction": "bullish", "htf_aligned": False, "structure_aligned": False,
                "last_pivot_held": False, "hh_failed": True, "progress_atr_10": -2.531944,
                "pullback_vol_ratio": 1.197042, "pullback_depth_frac": 3.19318,
                "pullback_bars_ratio": 2.666667, "impulse_atr_per_bar": 0.374019},
    "bearish": {**_COMMON, "direction": "bearish", "htf_aligned": True, "structure_aligned": True,
                "last_pivot_held": True, "hh_failed": False, "progress_atr_10": 2.531944,
                "pullback_vol_ratio": None, "pullback_depth_frac": None,
                "pullback_bars_ratio": None, "impulse_atr_per_bar": None},
}


def _wavy(n=300):
    i = np.arange(n)
    closes = 100 + 0.05 * i + 6 * np.sin(i / 7.0) + 2 * np.sin(i / 2.3)
    return make_ohlcv(closes, spread_pct=1.5, volumes=1_000_000 + 300_000 * np.sin(i / 3.1) + 5_000 * i)


def _context(df, direction, **kwargs):
    close = float(df["Close"].iloc[-1])
    sign = 1 if direction == "bullish" else -1
    return entry_context(df, direction=direction, horizon_key="2w",
                         stop=close - sign * 6.0, target=close + sign * 12.0, asof=ASOF, **kwargs)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_pre_existing_keys_are_unchanged(direction):
    out = _context(_wavy(), direction)
    assert {key: out[key] for key in WITNESS[direction]} == WITNESS[direction]
    assert len(WITNESS[direction]) == 34
```

Run `python scripts/dev/testrun.py file tests/edge/test_edge_context_location.py`; expect **PASS** on the unchanged code (a characterisation, not a red test). Commit it alone so the before-state is in history:

```bash
git add tests/edge/test_edge_context_location.py
git commit -m "test(v125): witness all 34 entry_context values before the location merge"
```

- [ ] **Step 2: Add the failing merge tests** to the same file. Replace the import block at the top with:

```python
from swingbot import config
from swingbot.core.edge.context import FEATURE_KEYS, PROVENANCE_KEYS, entry_context, plan_provenance
from swingbot.core.market import structure as st
from swingbot.core.market.location import LOCATION_KEYS, location_features
from tests.conftest import make_ohlcv
from tests.market.structure_fixtures import BROKEN, MIXED, UP, frame, pullback_frame, slowing_pullback_frame, wavy_frame

V125_NEW = ("target_capped", "stop_clamped", "zone_dist_atr", "room_atr", "range_pos", "leg_phase",
            "zone_state", "zone_touches", "zone_departure_atr")
```

(keep `import numpy as np` / `import pytest` above it), and append:

```python
def test_feature_keys_append_the_nine_v125_keys_in_order():
    assert len(FEATURE_KEYS) == 43
    assert FEATURE_KEYS[34:] == V125_NEW
    assert FEATURE_KEYS[:34] == tuple(dict.fromkeys(FEATURE_KEYS[:34]))     # no key moved or duplicated
    assert set(LOCATION_KEYS) | set(PROVENANCE_KEYS) == set(V125_NEW)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_snapshot_carries_location_features(direction):
    df = _wavy()
    out = _context(df, direction, entry=float(df["Close"].iloc[-1]))
    assert set(out) == set(FEATURE_KEYS)
    assert {key: out[key] for key in LOCATION_KEYS} == location_features(df, direction, "2w")
    assert out["zone_state"] == "tested" and out["leg_phase"] in ("broken", "impulse")


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_snapshot_provenance_reads_the_planned_entry_and_config_cap(direction, monkeypatch):
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    df = _wavy()
    sign = 1 if direction == "bullish" else -1
    entry = 100.0
    out = entry_context(df, direction=direction, horizon_key="2w", stop=entry - sign * 1.75,
                        target=entry + sign * 1.75 * 2.5, asof=ASOF, entry=entry)
    assert (out["target_capped"], out["stop_clamped"]) == (True, True)
    assert {key: out[key] for key in PROVENANCE_KEYS} == plan_provenance(entry, entry - sign * 1.75,
                                                                           entry + sign * 4.375, 2.5)


def test_without_entry_both_flags_are_none():
    out = _context(_wavy(), "bullish")
    assert out["target_capped"] is None and out["stop_clamped"] is None
    assert out["zone_dist_atr"] is not None                  # location does not need the entry


@pytest.mark.parametrize("bars", [10, 40, 59])
def test_short_frames_leave_every_new_key_none(bars):
    out = _context(_wavy().iloc[:bars], "bullish")
    assert set(out) == set(FEATURE_KEYS)
    assert all(out[key] is None for key in V125_NEW)


def test_short_frame_with_an_entry_still_flags_the_plan(monkeypatch):
    """The flags are arithmetic on entry/stop/tp1 and read no bars."""
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)
    out = entry_context(_wavy().iloc[:10], direction="bullish", horizon_key="2w",
                        stop=98.25, target=104.375, asof=None, entry=100.0)
    assert all(out[key] is None for key in LOCATION_KEYS)
    assert (out["target_capped"], out["stop_clamped"]) == (True, True)


def test_no_v125_key_duplicates_a_v121_key_on_the_fixtures():
    fixtures = [frame(UP), frame(MIXED), frame(BROKEN), pullback_frame(), slowing_pullback_frame(),
                wavy_frame(), _wavy()]
    for direction in ("bullish", "bearish"):
        rows = [(location_features(f, direction, "2w"), st.structure_features(f, direction)) for f in fixtures]
        for new in LOCATION_KEYS:
            for old in st.STRUCTURE_KEYS:
                assert not all(loc[new] == struct[old] for loc, struct in rows), (direction, new, old)


def test_live_stamp_passes_the_trigger_as_entry(monkeypatch):
    from swingbot.core.planning.params import stamp_entry_context
    from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)
    df = _wavy()
    plan = TradePlanV2(plan_id="p", ticker="AAPL", created_at="2026-10-02", source="confluence",
                       strategy="S/R Confluence", horizon_key="2w", direction="bullish",
                       entry_type="stop_entry", trigger_price=100.0, entry_price=None, expiry_bars=5,
                       stop_loss=98.0, tp1=105.0, tp1_fraction=0.5, tp2=None,
                       breakeven_trigger_fraction=0.5, trail_atr_mult=2.0, quality_score=0,
                       quality_breakdown=[], badge="WEAK", badge_stats={}, status=PlanStatus.PENDING)
    stamp_entry_context(plan, df, ASOF)
    assert set(plan.entry_context) == set(FEATURE_KEYS)
    assert plan.entry_context["target_capped"] is True        # 100 + 2.0 * 2.5 = 105, from the TRIGGER
    assert plan.entry_context["stop_clamped"] is False


def test_live_stamp_on_a_plan_without_a_trigger_keeps_the_snapshot():
    """Duck-typed plans (v121's stamp test uses a SimpleNamespace) must not blank the snapshot."""
    from types import SimpleNamespace

    from swingbot.core.planning.params import stamp_entry_context
    df = _wavy()
    close = float(df["Close"].iloc[-1])
    plan = SimpleNamespace(direction="bearish", horizon_key="2w", stop_loss=close + 6.0,
                           tp1=close - 12.0, entry_context=None)
    stamp_entry_context(plan, df, ASOF)
    assert set(plan.entry_context) == set(FEATURE_KEYS)
    assert plan.entry_context["target_capped"] is None
```

- [ ] **Step 3:** Run `python scripts/dev/testrun.py file tests/edge/test_edge_context_location.py`; expect the two witness tests PASS and the new tests FAIL (`len(FEATURE_KEYS) == 34`, `TypeError: entry_context() got an unexpected keyword argument 'entry'`).

- [ ] **Step 4: Implement.** In `swingbot/core/edge/context.py`:

```python
# imports -- add beside the v121 structure import
from swingbot.core.market.location import location_features
```

Extend the `FEATURE_KEYS` tuple: after v121's last key `"impulse_range_decay"` (keep everything before it unchanged), close the tuple as

```python
                "impulse_range_decay",
                # v125: plan provenance (plan_provenance) and location / leg / zone (market/location.py)
                "target_capped", "stop_clamped", "zone_dist_atr", "room_atr", "range_pos", "leg_phase",
                "zone_state", "zone_touches", "zone_departure_atr")
```

Change the signature and docstring of `entry_context`, and add exactly two unconditional statements:

```python
def entry_context(df, *, direction: str, horizon_key: str, stop: float, target: float, asof=None,
                  entry=None) -> dict:
    """Return only values knowable from ``df``'s final entry bar or before.

    ``entry`` is the PLANNED entry (trigger), never a slipped fill; without it
    the two plan-provenance flags are None."""
    out = {key: None for key in FEATURE_KEYS}
    out.update(direction=direction, horizon_key=horizon_key)
    out.update(plan_provenance(entry, stop, target, config.MAX_RISK_REWARD_RATIO))   # v125; reads no bars
    if df is None or len(df) < 20:
        return out
```

and directly after v121's `out.update(structure_features(df, direction))   # v121; all None below 60 bars`:

```python
    out.update(location_features(df, direction, horizon_key))   # v125; all None below 60 bars
```

Nothing else in `entry_context` changes. In `swingbot/core/planning/params.py`, `stamp_entry_context` becomes:

```python
def stamp_entry_context(plan: TradePlanV2, df, asof: dict | None) -> None:
    from swingbot.core.edge.context import entry_context
    try:
        plan.entry_context = entry_context(df, direction=plan.direction, horizon_key=plan.horizon_key,
                                            stop=plan.stop_loss, target=plan.tp1, asof=asof,
                                            entry=getattr(plan, "trigger_price", None))
    except Exception:
        plan.entry_context = {}
```

`trigger_price` is the planned entry for every `TradePlanV2` (`builders.py:296` strategy `= close`, `:437` confluence `= scenario.entry`); `entry_price` is `None` for `stop_entry` plans, so it must not be used. The three callers — `scanning/analyze.py:396` (live confluence), `scanning/strategy_pass.py:70` (live strategy), `backtesting/backtest_scenarios.py:155` (confluence replay) — gain the keys with no edit; confirm with `git grep -n "stamp_entry_context(" -- swingbot` that no other caller exists.

- [ ] **Step 5:** Run `python scripts/dev/testrun.py file tests/edge/test_edge_context_location.py` (expect 15 PASS), then the existing context suites: `... file tests/edge/test_edge_context_structure.py` (v121: its `FEATURE_KEYS[20:] == STRUCTURE_NEW` assertion now sees 23 keys — **update that one assertion to `FEATURE_KEYS[20:34] == STRUCTURE_NEW`** and say so in the commit body; every other v121 assertion must pass unchanged), `... file tests/scanning/test_live_context_stamp.py`, `... file tests/scanning/test_strategy_pass_emit.py`, `... file tests/backtesting/test_replay_context.py`. `... file tests/backtesting/test_backtest_context.py` still passes here (neither its replay trade nor its direct call passes `entry=` yet); it goes red only after V125-4's `backtest.py` edit, which updates it in the same step — do not touch it in this task. Run `python -m radon cc -s swingbot/core/edge/context.py` and confirm `entry_context` is still `C (17)`.
- [ ] **Step 6: No-lookahead review.** Invoke the `no-lookahead` skill on `swingbot/core/market/location.py` and `swingbot/core/edge/context.py`. Confirm in the review note: every location input is the frame passed in (`df.iloc[:i + 1]` in replay); pivots come only from `confirmed_pivots` (row `t` reads bars `<= t`); `build_level_map` and `classify_levels(df, len(df) - 1, ...)` see only that frame; `zone_departure_atr` reads `[:t]` for touches and `[:t + 1]` for its window; `plan_provenance` reads no bars; no `shift(-n)`, `iloc[t + …]` or centred window anywhere. Record the forming-bar caveat (the live snapshot may end on a forming bar, as v121's does; no consumer may act on these keys). Fix any finding before committing.
- [ ] **Step 7:** Commit.

```bash
git add swingbot/core/edge/context.py swingbot/core/planning/params.py tests/edge/test_edge_context_location.py tests/edge/test_edge_context_structure.py
git commit -m "feat(v125): entry_context carries plan provenance and location features; stamp passes the trigger"
```

### Task V125-4: Replay call sites pass the planned entry

**Files:** Modify `swingbot/core/backtesting/backtest.py:417-419` and `:495-497`, `tests/backtesting/test_backtest_context.py:33-37` (one kwarg); create `tests/backtesting/test_backtest_provenance.py`, `tests/backtesting/test_replay_provenance.py`.

**Interfaces:**
- Consumes (V125-3): `entry_context(..., entry=None)`; (V125-2): `plan_provenance`, `PROVENANCE_KEYS`. Existing: `bt.run_backtest`, `bt._vectorized_entries`, `bs.replay_scenarios(ticker, df, horizon_key, *, params=None, gates=..., asof=...)`.
- Produces: nothing later tasks import.

- [ ] **Step 1: Write the failing tests.**

```python
# tests/backtesting/test_backtest_provenance.py
"""v125: replay snapshots carry plan provenance from the PLANNED entry, never the fill."""
import numpy as np
import pandas as pd
import pytest

import swingbot.core.backtesting.backtest as bt
from swingbot import config
from swingbot.core.edge.context import entry_context, plan_provenance
from tests.conftest import make_ohlcv

ALL_SITES = [{"exit_model": "v1", "frictions": False}, {"exit_model": "v1", "frictions": True},
             {"exit_model": "v2", "scale_out": True}]


def _df(spread_pct):
    closes = np.full(120, 100.0)
    closes[81:] = 104.0
    return make_ohlcv(closes, spread_pct=spread_pct)


def _forced(monkeypatch, df, bar, **kwargs):
    bull = pd.Series(False, index=df.index)
    bear = pd.Series(False, index=df.index)
    bull.iloc[bar] = True
    monkeypatch.setattr(bt, "_vectorized_entries", lambda *args, **kw: (bull, bear))
    return bt.run_backtest("TEST", df, "EMA Crossover", "2w", **kwargs)


def _spy(monkeypatch):
    seen = []

    def spy(*args, **kwargs):
        seen.append(kwargs.get("entry"))
        return entry_context(*args, **kwargs)

    monkeypatch.setattr(bt, "entry_context", spy)
    return seen


@pytest.fixture(autouse=True)
def cap(monkeypatch):
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)


@pytest.mark.parametrize("kwargs", ALL_SITES)
def test_every_replay_site_passes_the_planned_entry(monkeypatch, kwargs):
    df = _df(1.0)
    seen = _spy(monkeypatch)
    trade = _forced(monkeypatch, df, 80, **kwargs).trades[0]
    assert seen == [100.0]                                       # Close[80], the planned entry
    # 1% spread: ATR ~1, stop 2 ATR (98), nearest ladder rung paying 1.5R is 103 -- a real rung
    assert (trade.take_profit, trade.context["target_capped"], trade.context["stop_clamped"]) == \
        (103.0, False, False)


@pytest.mark.parametrize("kwargs", ALL_SITES)
def test_a_target_on_the_cap_is_flagged_at_every_site(monkeypatch, kwargs):
    # 6% spread: ATR ~6, stop bounded to 2% (98), first ladder rung 106 > cap 105 -> synthetic 105
    trade = _forced(monkeypatch, _df(6.0), 80, **kwargs).trades[0]
    assert (trade.stop_loss, trade.take_profit) == (98.0, 105.0)
    assert trade.context["target_capped"] is True


def test_the_slipped_fill_would_have_hidden_the_cap(monkeypatch):
    trade = _forced(monkeypatch, _df(6.0), 80, exit_model="v1", frictions=True).trades[0]
    assert trade.entry != 100.0                                  # the fill slipped
    assert trade.context["target_capped"] is True                # from the trigger
    assert plan_provenance(trade.entry, trade.stop_loss, trade.take_profit, 2.5)["target_capped"] is False
```

```python
# tests/backtesting/test_replay_provenance.py
"""v125: confluence replay (backtest_scenarios -> stamp_entry_context) flags from plan.trigger_price."""
import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.edge.context import PROVENANCE_KEYS, plan_provenance
from tests.helpers import make_ohlcv

pytestmark = pytest.mark.slow

GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def _structured_df():
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(index / 4)) for index in range(60)]
    return make_ohlcv(trend + box)


def test_replayed_confluence_plans_carry_provenance_from_the_trigger(monkeypatch):
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    output = bs.replay_scenarios("AAPL", _structured_df(), "4w", gates=GATES)
    assert output, "fixture must yield at least one plan"
    for _, plan in output:
        expected = plan_provenance(plan.trigger_price, plan.stop_loss, plan.tp1, 2.5)
        assert {key: plan.entry_context[key] for key in PROVENANCE_KEYS} == expected
        assert plan.entry_context["stop_clamped"] in (True, False)
    # prototype: 16 plans, 13 capped, 1 clamped -- both populations exist on this fixture
    assert any(plan.entry_context["target_capped"] for _, plan in output)
    assert any(plan.entry_context["stop_clamped"] for _, plan in output)
```

- [ ] **Step 2:** Run `python scripts/dev/testrun.py file tests/backtesting/test_backtest_provenance.py`; expect FAIL (`seen == [None]`, `target_capped` is `None`). `tests/backtesting/test_backtest_context.py` still passes at this point. Run `... file tests/backtesting/test_replay_provenance.py`; expect **PASS** already (the confluence replay path goes through V125-3's `stamp_entry_context`; this test pins it).

- [ ] **Step 3: Implement.** In `swingbot/core/backtesting/backtest.py`, the v2 branch call (`:417`) becomes:

```python
                context=entry_context(df.iloc[:i + 1], direction=direction, horizon_key=horizon_key,
                                      stop=stop_loss, target=take_profit,
                                      asof=asof_row(asof, df.index[i]), entry=entry),
```

and the v1 call (`:495`) becomes:

```python
            context=entry_context(df.iloc[:i + 1], direction=direction, horizon_key=horizon_key,
                                  stop=stop_loss, target=take_profit,
                                  asof=asof_row(asof, df.index[i]), entry=entry),
```

Pass `entry` — the planned price from `_trade_plan_at` (`= Close[i]`, `:201`), which the v1 loop deliberately never reassigns (`:419-427` comment) — **never `entry_fill`**. In `tests/backtesting/test_backtest_context.py::test_context_uses_only_bars_to_entry_and_joins_asof`, add the planned entry to the direct call so it compares like with like:

```python
    direct = entry_context(df.iloc[:81], direction="bullish", horizon_key="2w",
                           stop=trade.stop_loss, target=trade.take_profit,
                           asof={"regime2_state": "bear_quiet", "rs_pctile": 12.5,
                                 "sector_pctile": None, "rs_combined": 12.5},
                           entry=float(df["Close"].iloc[80]))
```

- [ ] **Step 4:** Run `python scripts/dev/testrun.py file tests/backtesting/test_backtest_provenance.py` (expect 7 PASS), `... file tests/backtesting/test_backtest_context.py` (expect PASS), `... file tests/backtesting/test_replay_provenance.py` (expect PASS). Run `python -m radon cc -s swingbot/core/backtesting/backtest.py | grep run_backtest` and confirm its score is unchanged from before the edit (keyword additions add no branch).
- [ ] **Step 5:** Commit.

```bash
git add swingbot/core/backtesting/backtest.py tests/backtesting/test_backtest_context.py tests/backtesting/test_backtest_provenance.py tests/backtesting/test_replay_provenance.py
git commit -m "feat(v125): replay snapshots flag synthetic targets / clamped stops from the planned entry"
```

### Task V125-5: Confirm the snapshot's storage shape for the v125 keys (JSONB doc, no revision)

**Files:** Create `tests/db/test_entry_context_doc_v125.py`. No schema, migration or repository change.

**Finding (to confirm):** v121 Task 4 settled that `entry_context` lives in `trades.doc` JSONB (`db/schema.py:70`; promoted columns are `trade_id, ticker, strategy, horizon, direction, status, opened_at, closed_at, entry, stop_loss`), so per `schema-evolution.md` an added field "lands in `doc`. Migration: None." v125 adds two `bool | None`, two `str | None`, one `int | None` and four `float | None` values inside that same document. Invoke the `schema-change` skill to re-confirm before writing the test, and record "add → doc, no revision" in the commit body.

**Interfaces:** Consumes existing `TradeRepository` (`db/repositories/trades.py`, `insert`/`get` from `repositories/base.py:67`/`:41`), `tracking.performance._db_record` / `_json_record`, `edge.context.FEATURE_KEYS` (only to build a `None` default — the v125 keys are written as literals so this task does not depend on V125-3), the `db_conn` fixture. Produces nothing later tasks import.

- [ ] **Step 1:** Repeat the v121 gate: `git grep -n "def test_" -- tests/db/test_entry_context_doc.py` returns v121's three tests (else `BLOCKED: v121 not merged`).
- [ ] **Step 2: Write the tests.**

```python
# tests/db/test_entry_context_doc_v125.py
"""v125: the nine new snapshot keys ride in trades.doc JSONB -- add, no revision."""
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.db.schema import trades
from swingbot.core.edge.context import FEATURE_KEYS
from swingbot.core.tracking.performance import _db_record, _json_record

V125 = {"target_capped": True, "stop_clamped": False, "zone_dist_atr": 0.473761, "room_atr": 1.257851,
        "range_pos": -1.787727, "leg_phase": "broken", "zone_state": "tested", "zone_touches": 5,
        "zone_departure_atr": 0.473761}


def _trade(trade_id, context):
    return {"id": trade_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
            "direction": "bullish", "status": "open", "opened_at": "2026-10-02T15:00:00+00:00",
            "entry_context": context}


def test_no_v125_key_is_a_promoted_column():
    assert not set(V125) & set(trades.c.keys())
    assert "entry_context" not in trades.c


def test_v125_keys_round_trip_with_their_types(db_conn):
    context = {key: None for key in FEATURE_KEYS} | V125
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V125-T1", context)), conn=db_conn)
    back = _json_record(repository.get("V125-T1", conn=db_conn))["entry_context"]
    assert back == context
    assert type(back["zone_touches"]) is int and back["leg_phase"] == "broken"
    assert back["target_capped"] is True and back["stop_clamped"] is False


def test_unknown_provenance_round_trips_as_none(db_conn):
    context = {key: None for key in FEATURE_KEYS} | V125 | {"target_capped": None, "stop_clamped": None}
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V125-T2", context)), conn=db_conn)
    back = _json_record(repository.get("V125-T2", conn=db_conn))["entry_context"]
    assert back["target_capped"] is None and back["stop_clamped"] is None


def test_a_pre_v125_record_reads_every_new_key_as_none(db_conn):
    old = {"vol_ratio_20": 1.2, "structure_state": "up"}
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V125-T0", old)), conn=db_conn)
    back = _json_record(repository.get("V125-T0", conn=db_conn))["entry_context"]
    assert all(back.get(key) is None for key in V125)
    assert back == old                              # nothing upcast on read
```

- [ ] **Step 3:** Run `python scripts/dev/testrun.py file tests/db/test_entry_context_doc_v125.py`; expect PASS immediately (it characterises existing storage). It needs the Compose test Postgres (`TEST_DATABASE_URL`, default `127.0.0.1:55432`); if the container is down, start it per `tests/db/conftest.py` rather than skipping. **If a test FAILS, stop:** the storage assumption is wrong and the plan needs an additive revision per `schema-evolution.md` — report `BLOCKED` to the controller.
- [ ] **Step 4:** Commit.

```bash
git add tests/db/test_entry_context_doc_v125.py
git commit -m "test(v125): new entry_context keys live in trades.doc -- add, no revision"
```

# Phase 3 — Descriptive report

### Task V125-6: Extend `volume_context_report.py` with the nine keys and the provenance cross-table

**Files:** Modify `scripts/reports/volume_context_report.py` (v121); create `tests/scripts/test_volume_context_report_v125.py`.

**Interfaces:**
- Consumes (v121): `ReportRow(source, direction, outcome, r_multiple, context)`, `bucket_of(value, edges)`, `render(rows, edges, *, source)`, `_fmt`, `main(argv)`, `replay_all`, `CATEGORICAL`, `CONTINUOUS`, `HEADER`; `acceptance.win_rate`, `acceptance.expectancy_r`, `acceptance.CLOSED`.
- Produces: `V125_NOTE: str`; `PROVENANCE_CELL = ("target_capped", "stop_clamped")`; `_sum_r(members) -> float | None`; `provenance_table(rows) -> list[dict]` (keys `source, direction, target_capped, stop_clamped, n, win_rate, expectancy_r, sum_r`; cell values are `bucket_of` strings `"True"`, `"False"`, `"None"`); `_provenance_lines(rows) -> list[str]`. `CATEGORICAL` gains `"target_capped", "stop_clamped", "leg_phase", "zone_state"`; `CONTINUOUS` gains `"zone_dist_atr", "room_atr", "range_pos", "zone_touches", "zone_departure_atr"` (TRAIN quintiles via v121's existing edges file).

**Do not run the report** (not even v121's two-ticker smoke): the "#3" structure-break entry spec must freeze its grid first (Global constraints). Only the unit tests run.

- [ ] **Step 1:** Repeat the v121 gate: `git grep -n "^CATEGORICAL\|^def render" -- scripts/reports/volume_context_report.py` returns both (else `BLOCKED: v121 not merged`).
- [ ] **Step 2: Write the failing tests.**

```python
# tests/scripts/test_volume_context_report_v125.py
"""v125: the volume-context report buckets the nine new keys and renders the provenance cross-table."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import volume_context_report as vcr  # noqa: E402

V125_CATEGORICAL = ("target_capped", "stop_clamped", "leg_phase", "zone_state")
V125_CONTINUOUS = ("zone_dist_atr", "room_atr", "range_pos", "zone_touches", "zone_departure_atr")


def _row(source, direction, outcome, r, **context):
    return vcr.ReportRow(source=source, direction=direction, outcome=outcome, r_multiple=r, context=context)


def test_the_nine_keys_are_bucketed_and_v121_keys_are_kept():
    assert vcr.CATEGORICAL[-4:] == V125_CATEGORICAL
    assert vcr.CONTINUOUS[-5:] == V125_CONTINUOUS
    assert vcr.CATEGORICAL[:6] == ("structure_state", "structure_aligned", "last_pivot_held", "hh_failed",
                                   "absorption_bar", "absorption_count_10")
    assert not set(vcr.CATEGORICAL) & set(vcr.CONTINUOUS)


def test_provenance_cross_table_splits_source_direction_and_cell():
    rows = [_row("confluence", "bullish", "win", 1.5, target_capped=True, stop_clamped=False),
            _row("confluence", "bullish", "loss", -1.0, target_capped=True, stop_clamped=False),
            _row("confluence", "bullish", "timeout", 0.25, target_capped=True, stop_clamped=False),
            _row("confluence", "bearish", "loss", -1.0, target_capped=True, stop_clamped=True),
            _row("strategy", "bullish", "win", 2.0, target_capped=False, stop_clamped=False),
            _row("strategy", "bullish", "loss", -1.0)]                       # an old record
    table = {(line["source"], line["direction"], line["target_capped"], line["stop_clamped"]): line
             for line in vcr.provenance_table(rows)}
    capped = table[("confluence", "bullish", "True", "False")]
    assert (capped["n"], capped["win_rate"], capped["sum_r"]) == (3, 50.0, 0.75)
    assert capped["expectancy_r"] == pytest.approx(0.25)
    assert table[("confluence", "bearish", "True", "True")]["sum_r"] == -1.0
    assert table[("strategy", "bullish", "False", "False")]["win_rate"] == 100.0
    assert table[("strategy", "bullish", "None", "None")]["n"] == 1
    assert len(table) == 4


def test_sum_r_skips_rows_without_an_r():
    rows = [_row("strategy", "bullish", "win", None, target_capped=True, stop_clamped=False)]
    assert vcr.provenance_table(rows)[0]["sum_r"] is None


def test_render_carries_the_cross_table_and_the_grid_warning():
    rows = [_row("confluence", "bullish", "win", 1.0, target_capped=True, stop_clamped=False,
                 leg_phase="pullback", range_pos=0.4)]
    out = vcr.render(rows, {"range_pos": [0.1, 0.2, 0.3, 0.5]}, source="replay")
    assert "== target_capped x stop_clamped ==" in out
    assert "structure-break entry spec" in out and "p=" not in out
    assert "== leg_phase ==" in out and "== range_pos ==" in out
    assert "capped=True  clamped=False" in out


def test_replay_writes_train_edges_for_the_v125_continuous_keys(tmp_path, monkeypatch):
    rows = [_row("confluence", "bullish", "win", 1.0, range_pos=v, zone_touches=n)
            for v, n in ((0.2, 1), (0.4, 2), (0.6, 3), (0.8, 4), (1.0, 5))]
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: rows)
    out_path = tmp_path / "edges.json"
    assert vcr.main(["--source", "replay", "--tickers", "AAA", "--edges", str(out_path)]) == 0
    edges = json.loads(out_path.read_text(encoding="utf-8"))["edges"]
    assert edges["range_pos"] == [0.36, 0.52, 0.68, 0.84]
    assert edges["zone_touches"] == [1.8, 2.6, 3.4, 4.2]
    assert edges["zone_dist_atr"] is None                          # no values -> no edges


@pytest.mark.parametrize("start,end", [("2020-01-01", "2024-01-01"), ("2020-01-01", "2026-10-02")])
def test_replay_refusal_is_inherited(start, end, monkeypatch, capsys):
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: pytest.fail("computed"))
    assert vcr.main(["--source", "replay", "--start", start, "--end", end]) == 1
    assert "refused" in capsys.readouterr().out
```

- [ ] **Step 3:** Run `python scripts/dev/testrun.py file tests/scripts/test_volume_context_report_v125.py`; expect FAIL (5 tests: `CATEGORICAL[-4:]` mismatch, `AttributeError: ... 'provenance_table'`); the inherited-refusal tests already pass.

- [ ] **Step 4: Implement.** In `scripts/reports/volume_context_report.py`, extend the two key tuples (v121 entries unchanged and first):

```python
CATEGORICAL = ("structure_state", "structure_aligned", "last_pivot_held", "hh_failed",
               "absorption_bar", "absorption_count_10",
               # v125: plan provenance and leg / zone labels
               "target_capped", "stop_clamped", "leg_phase", "zone_state")
CONTINUOUS = ("swing_high_atr", "swing_low_atr", "vol_trend_10_50", "range_trend_10_50",
              "progress_atr_10", "pullback_vol_ratio", "pullback_depth_frac", "pullback_bars_ratio",
              "impulse_atr_per_bar", "impulse_range_decay",
              # v125: location and zone quality
              "zone_dist_atr", "room_atr", "range_pos", "zone_touches", "zone_departure_atr")
```

Directly above `LIVE_WARNING = (` add:

```python
V125_NOTE = ("v125 keys (plan provenance, location, leg phase, zone): not to be used to choose "
             "the structure-break entry spec's grid values (frozen in that spec before this report exists).")
PROVENANCE_CELL = ("target_capped", "stop_clamped")
```

Directly below `_fmt` add:

```python
def _sum_r(members) -> float | None:
    """Total R over closed rows -- the same population acceptance.expectancy_r averages."""
    rs = [row.r_multiple for row in members
          if row.outcome in acceptance.CLOSED and row.r_multiple is not None]
    return round(float(sum(rs)), 4) if rs else None


def provenance_table(rows) -> list[dict]:
    """v125 cross-table: one line per (source, direction, target_capped, stop_clamped)."""
    groups: dict[tuple, list] = {}
    for row in rows:
        cell = tuple(bucket_of(row.context.get(key), None) for key in PROVENANCE_CELL)
        groups.setdefault((row.source, row.direction, *cell), []).append(row)
    return [{"source": source, "direction": direction, "target_capped": capped, "stop_clamped": clamped,
             "n": len(members), "win_rate": acceptance.win_rate(members),
             "expectancy_r": acceptance.expectancy_r(members), "sum_r": _sum_r(members)}
            for (source, direction, capped, clamped), members in sorted(groups.items())]


def _provenance_lines(rows) -> list[str]:
    lines = ["\n== target_capped x stop_clamped =="]
    for line in provenance_table(rows):
        lines.append(f"{line['source']:<10} {line['direction']:<8} capped={line['target_capped']:<5} "
                     f"clamped={line['stop_clamped']:<5} N={line['n']:>5}  "
                     f"WR {_fmt(line['win_rate'], '6.2f')}%  ExpR {_fmt(line['expectancy_r'], '+.4f')}  "
                     f"sumR {_fmt(line['sum_r'], '+.2f')}")
    return lines
```

In `render`, change the first line and add one line before the `return`:

```python
    lines = [HEADER, V125_NOTE] + ([LIVE_WARNING] if source == "live" else []) + [f"closed trades: {len(rows)}"]
```

```python
    lines.extend(_provenance_lines(rows))
    return "\n".join(lines)
```

Also append to the module docstring's first paragraph: `v125 adds plan-provenance, location, leg-phase and zone keys; they must not be used to choose the structure-break entry spec's grid values (frozen in that spec before this report exists).` The TRAIN-only replay refusal (`window_refusal`), the live "monitoring only" warning and the "no inferential statistic" rule are inherited unchanged. `data/v121_*.json` (the edges file) is already git-ignored by v121.

- [ ] **Step 5:** Run `python scripts/dev/testrun.py file tests/scripts/test_volume_context_report_v125.py` (expect 7 PASS) and `... file tests/scripts/test_volume_context_report.py` (v121's 12 tests, expect PASS unchanged). Run `python -m radon cc -s -n C scripts/reports/volume_context_report.py` (expect no output; prototype max B (6)).
- [ ] **Step 6:** Commit.

```bash
git add scripts/reports/volume_context_report.py tests/scripts/test_volume_context_report_v125.py
git commit -m "feat(v125): volume-context report buckets location/provenance keys and the capped x clamped cross-table"
```

# Phase 4 — Verification

### Task V125-7: Full-suite verification and release

**Files:** No new feature files; fix only failures attributable to this plan, with their narrow tests. Release commit touches `VERSION.json` and `swingbot/admin/version_history.json` only.

- [ ] Run `python scripts/dev/testrun.py full` once (or dispatch the `test-runner` subagent) over everything this plan implemented. Green requires `0 failed`, `0 xfailed`. **If it is not green, fix forward from the failures it names** — they are this plan's regressions. A changed pass count alone is not a failure. Before blaming this plan for an unrelated red test, check the diff scope and run that file alone (shared-DB flakiness is known on this machine; `testing-cost.md`). Likely suspects if red: another test that compares a full `entry_context(...)` dict against a stamped one without `entry=` (fix it the way V125-4 fixed `test_backtest_context.py`), or a test asserting `len(FEATURE_KEYS)`.
- [ ] Watch replay-heavy test timings: `entry_context` now builds a level map and classifies one level per stamped trade (prototype ≈ 9–12 ms per call on 300–1500 bars, warm). If a test's runtime regresses noticeably, measure before optimising; do not change feature semantics to save time.
- [ ] Run `python -m radon cc -s -n C swingbot/core/market/location.py swingbot/core/edge/context.py scripts/reports/volume_context_report.py`; only the pre-existing `entry_context C (17)` may appear.
- [ ] After green, release per `working-conventions.md` § Versioning: bump the **bot** line at **patch** level from the then-current `VERSION.json` (read it; never a number from this plan), set `bot_updated` (UTC `YYYY-MM-DD HH-MM-SS`), commit `release(bot): <new> -- v125 location and plan-provenance entry snapshot`, then run `python scripts/dev/build_version_matrix.py`, commit `swingbot/admin/version_history.json`, and run `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`.
- [ ] Do **not** run `volume_context_report.py` as part of close-out: its first run waits on the "#3" structure-break entry spec freezing its grid.
