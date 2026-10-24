# v191 — Confluence ATR-band stops, part 2: the band-stop path (V191-7..V191-13)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Never read this part whole**: `grep -n "^### Task V191-9:" -A 300 <this file>`.

**Spec:** [2026-10-24-v191-confluence-atr-band-stops-design.md](../specs/2026-10-24-v191-confluence-atr-band-stops-design.md)
**Index:** [2026-10-24-v191-confluence-atr-band-stops_0-index.md](2026-10-24-v191-confluence-atr-band-stops_0-index.md) — § Global Constraints, § Contracts, § Review Focus, § Parallelisation and the task ledger are binding here; this part never changes a shared name, signature or path.

Every path below is relative to the worktree root `.claude/worktrees/2026-10-24-v191-confluence-atr-band-stops` (created by V191-1); run every command from there, never from the main checkout. Every code task ends with `python scripts/dev/complexity_gate.py` passing and the V191-1 golden still green:

```bash
python scripts/dev/testrun.py file tests/backtesting/test_v191_flag_off_golden.py
python scripts/dev/testrun.py file tests/planning/test_v191_plan_golden.py
```

Scope of this part: `swingbot/core/market/atr_band.py` (pure band arithmetic), the builder's band geometry with arm R and arm K, admission bypass on the replay side and the live side, band sizing and the dollar invariant, the `attach_plan_v2` wiring, and the alert band line. Names consumed from part 1: `ScanParams.confluence_atr_stop_floor`, `ScanParams.confluence_atr_target_mode`, `config.CONFLUENCE_ATR_STOP_FLOOR`, `config.CONFLUENCE_ATR_TARGET_MODE`, `config.LONG_GAP_SIZING` (V191-2), `TradePlanV2.stop_moved_by` (V191-4), the long stamp keys `down_gap_p99_pct` / `n_down_gaps`, `gap_stats` keys `p99_down_gap_pct` / `n_down`, `MIN_DOWN_GAPS` and the long branch of `gap_floor_for` (V191-5).

---

# Phase 3 — Band arithmetic

### Task V191-7: `atr_band.py`: raw ATR14%, tick rounding, band stop

**Model:** opus — new pure module whose rounding and NO-LOOKAHEAD rules every later task, live and replay, reads; a wrong tick direction or a scaled ATR silently skews the whole measurement.

**Files:**
- Create: `swingbot/core/market/atr_band.py`
- Test: `tests/market/test_atr_band.py` (create; `tests/market/` already belongs to a suite)

**Interfaces:**
- Consumes: `swingbot.core.market.indicators.atr(df, period=14)` (Wilder, `min_periods=14`, NaN before 14 bars; `indicators.py:62`); `swingbot.core.risk_limits.planned_loss_pct(entry, stop)` (`risk_limits.py:17`, `|entry − stop| / entry × 100`, `inf` when invalid).
- Produces (index § Contracts, verbatim):
  - constants `ATR_PERIOD = 14`, `BAND_CEILING_ATR = 2.0`, `FLOOR_GRID = (0.75, 1.0, 1.5)`, `MOVED_FLOOR = "floor"`, `MOVED_CEILING = "ceiling"`, `MOVED_UNTOUCHED = "untouched"`, `REASON_NO_TARGET = "band_no_target"`, `REASON_RR_DROP = "band_rr_drop"`, `REASON_NO_ATR = "band_no_atr"`, `REASON_SIZE_ZERO = "band_size_zero"`
  - `class AtrBand(NamedTuple): k: float; atr_pct: float | None`
  - `class BandStop(NamedTuple): stop: float; moved_by: str; lo_pct: float; hi_pct: float; distance_pct: float`
  - `raw_atr14_pct(df, entry: float) -> float | None`
  - `tick_size(price: float) -> float`
  - `round_away_from_entry(stop: float, entry: float, is_bull: bool) -> float`
  - `band_stop(entry, level, is_bull, atr_pct, k) -> BandStop | None` (raises `ValueError` when `k >= BAND_CEILING_ATR`)
  - `band_for(df, entry: float, k: float) -> AtrBand | None`

- [ ] **Step 1: Write the failing tests** in `tests/market/test_atr_band.py`

```python
"""V191-7: the ATR band -- raw Wilder ATR14 of completed bars as a percent of
entry, tick rounding away from entry, and the floor / untouched / ceiling stop."""
import pandas as pd
import pytest

from swingbot.core.market import atr_band as ab
from swingbot.core.market import levels
from swingbot.core.risk_limits import planned_loss_pct


def _frame(n=60, close=100.0, half_range=2.0, end="2024-03-28"):
    """Flat closes with a constant high-low range: every true range is
    2 * half_range, so Wilder ATR14 is exactly that from bar 14 on."""
    idx = pd.bdate_range(end=end, periods=n)
    rows = [(close, close + half_range, close - half_range, close, 1_000_000.0)] * n
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=idx)


def test_the_frozen_constants():
    assert ab.ATR_PERIOD == 14
    assert ab.BAND_CEILING_ATR == 2.0
    assert ab.FLOOR_GRID == (0.75, 1.0, 1.5)
    assert (ab.MOVED_FLOOR, ab.MOVED_CEILING, ab.MOVED_UNTOUCHED) == ("floor", "ceiling", "untouched")
    assert (ab.REASON_NO_TARGET, ab.REASON_RR_DROP) == ("band_no_target", "band_rr_drop")
    assert (ab.REASON_NO_ATR, ab.REASON_SIZE_ZERO) == ("band_no_atr", "band_size_zero")


def test_raw_atr14_pct_of_a_constant_range_frame():
    assert ab.raw_atr14_pct(_frame(), 100.0) == pytest.approx(4.0)
    assert ab.raw_atr14_pct(_frame(), 50.0) == pytest.approx(8.0)   # a percent of ENTRY


def test_raw_atr_is_not_the_horizon_scaled_floor():
    df = _frame()
    assert levels.atr_floor_pct(df, 100.0, {"atr_stop_multiple": 1.5}) == pytest.approx(6.0)
    assert ab.raw_atr14_pct(df, 100.0) == pytest.approx(4.0)


@pytest.mark.parametrize("df,entry", [
    (None, 100.0),
    (_frame(n=0), 100.0),
    (_frame(n=13), 100.0),                    # Wilder warm-up: NaN before 14 bars
    (_frame(half_range=0.0), 100.0),          # zero range -> ATR 0
    (_frame(), 0.0),
    (_frame(), -1.0),
])
def test_raw_atr14_pct_is_none_when_unusable(df, entry):
    assert ab.raw_atr14_pct(df, entry) is None


def test_raw_atr14_pct_reads_the_last_row_of_the_frame_it_is_given():
    df = _frame(n=61)
    before = ab.raw_atr14_pct(df.iloc[:60], 100.0)
    df.iloc[60, df.columns.get_loc("High")] = 500.0        # the bar after the creating bar
    assert ab.raw_atr14_pct(df.iloc[:60], 100.0) == before
    assert ab.band_for(df.iloc[:60], 100.0, 1.0) == ab.AtrBand(1.0, before)


@pytest.mark.parametrize("price,tick", [(250.0, 0.01), (1.0, 0.01), (0.9999, 0.0001), (0.05, 0.0001)])
def test_tick_size(price, tick):
    assert ab.tick_size(price) == tick


@pytest.mark.parametrize("stop,entry,is_bull,expected", [
    (96.537, 100.0, True, 96.53),            # a long's stop floors
    (103.531, 100.0, False, 103.54),         # a short's stop ceils
    (96.53, 100.0, True, 96.53),             # already on the tick
    (100.0 * (1 - 0.06), 100.0, True, 94.0), # float noise (93.99999999999999) is not a tick
    (0.80756, 0.85, True, 0.8075),           # sub-$1: tick 0.0001
    (0.80751, 0.85, False, 0.8076),
    (0.9690, 1.02, True, 0.96),              # the ENTRY's tick (0.01), not the stop's
])
def test_round_away_from_entry(stop, entry, is_bull, expected):
    assert ab.round_away_from_entry(stop, entry, is_bull) == pytest.approx(expected, abs=1e-12)


# entry 100, a = 4.0, k = 1.0 -> lo 4.0%, hi 8.0%
@pytest.mark.parametrize("level,stop,moved", [
    (99.0, 96.0, "floor"),         # d 1.0 < lo
    (96.0, 96.0, "untouched"),     # d exactly lo
    (94.537, 94.537, "untouched"), # inside: the level itself, never rounded
    (92.0, 92.0, "untouched"),     # d exactly hi
    (90.0, 92.0, "ceiling"),       # d 10.0 > hi
])
def test_band_stop_bullish(level, stop, moved):
    got = ab.band_stop(100.0, level, True, 4.0, 1.0)
    assert got.stop == pytest.approx(stop) and got.moved_by == moved
    assert (got.lo_pct, got.hi_pct) == pytest.approx((4.0, 8.0))
    assert got.distance_pct == pytest.approx(planned_loss_pct(100.0, got.stop))


@pytest.mark.parametrize("level,stop,moved", [
    (101.0, 104.0, "floor"),
    (104.0, 104.0, "untouched"),
    (105.463, 105.463, "untouched"),
    (108.0, 108.0, "untouched"),
    (110.0, 108.0, "ceiling"),
])
def test_band_stop_bearish_mirror(level, stop, moved):
    got = ab.band_stop(100.0, level, False, 4.0, 1.0)
    assert got.stop == pytest.approx(stop) and got.moved_by == moved


def test_a_moved_stop_rounds_away_from_entry_so_the_band_is_never_tighter():
    bull = ab.band_stop(100.0, 99.0, True, 4.123, 0.75)       # lo 3.09225% -> 96.90775
    bear = ab.band_stop(100.0, 101.0, False, 4.123, 0.75)
    assert bull.stop == pytest.approx(96.90) and bull.distance_pct >= bull.lo_pct
    assert bear.stop == pytest.approx(103.10) and bear.distance_pct >= bear.lo_pct
    ceiling = ab.band_stop(100.0, 80.0, True, 4.123, 0.75)     # hi 8.246% -> 91.754
    assert ceiling.stop == pytest.approx(91.75)                # past hi by under one tick
    assert ceiling.hi_pct < ceiling.distance_pct < ceiling.hi_pct + 0.01


def test_a_sub_dollar_floor_stop_uses_the_small_tick():
    got = ab.band_stop(0.85, 0.84, True, 5.0, 1.0)            # lo 5% -> 0.8075
    assert got.stop == pytest.approx(0.8075) and got.moved_by == "floor"


@pytest.mark.parametrize("k", ab.FLOOR_GRID)
def test_lo_is_below_hi_for_every_grid_cell(k):
    got = ab.band_stop(100.0, 99.0, True, 4.0, k)
    assert got.lo_pct < got.hi_pct


def test_a_floor_at_or_past_the_ceiling_multiple_is_refused():
    with pytest.raises(ValueError):
        ab.band_stop(100.0, 99.0, True, 4.0, 2.0)


@pytest.mark.parametrize("entry,level,is_bull,atr_pct,k", [
    (100.0, 99.0, True, 4.0, 0.0),       # floor off
    (100.0, 99.0, True, None, 1.0),      # no ATR
    (100.0, 99.0, True, 0.0, 1.0),
    (0.0, 99.0, True, 4.0, 1.0),
    (100.0, None, True, 4.0, 1.0),
    (100.0, 101.0, True, 4.0, 1.0),      # a long's level above entry
    (100.0, 99.0, False, 4.0, 1.0),      # a short's level below entry
])
def test_band_stop_is_none_when_it_cannot_apply(entry, level, is_bull, atr_pct, k):
    assert ab.band_stop(entry, level, is_bull, atr_pct, k) is None


def test_band_for():
    assert ab.band_for(_frame(), 100.0, 0.0) is None
    assert ab.band_for(_frame(), 100.0, 1.0) == ab.AtrBand(1.0, pytest.approx(4.0))
    assert ab.band_for(_frame(n=10), 100.0, 1.0) == ab.AtrBand(1.0, None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_atr_band.py`
Expected: collection error, `ModuleNotFoundError: No module named 'swingbot.core.market.atr_band'`.

- [ ] **Step 3: Create `swingbot/core/market/atr_band.py`**

Module docstring: the v191 ATR band; pure arithmetic, no config read, no frame written; `a` is raw Wilder ATR14 of the frame's last row (the caller passes the creating bar's completed frame), never `levels.atr_floor_pct`. Imports: `math`; `Decimal`, `ROUND_FLOOR`, `ROUND_CEILING` from `decimal`; `NamedTuple`; `atr` from `swingbot.core.market.indicators`; `planned_loss_pct` from `swingbot.core.risk_limits`. The constants and the two `NamedTuple`s are exactly as in Interfaces. The rounding and the band rule are not fixed by the signatures, so their bodies are given here:

```python
_TOL = 1e-9          # boundary tolerance: d exactly at lo or hi is untouched


def tick_size(price: float) -> float:
    return 0.01 if price >= 1.0 else 0.0001


def round_away_from_entry(stop: float, entry: float, is_bull: bool) -> float:
    """The stop on the entry's tick, moved away from entry (a long floors, a
    short ceils), so a rounded stop is never tighter than the band. Rounded to
    9 decimals first so float noise (93.99999999999999) is not taken for a tick."""
    tick = Decimal(str(tick_size(entry)))
    exact = Decimal(repr(round(float(stop), 9)))
    steps = (exact / tick).to_integral_value(rounding=ROUND_FLOOR if is_bull else ROUND_CEILING)
    return float(steps * tick)


def _on_stop_side(entry, level, is_bull) -> bool:
    return level < entry if is_bull else level > entry


def _usable(entry, level, is_bull, atr_pct, k) -> bool:
    if k is None or k <= 0 or atr_pct is None or not atr_pct > 0:
        return False
    if entry is None or entry <= 0 or level is None:
        return False
    return _on_stop_side(entry, level, is_bull)


def _offset_stop(entry: float, pct: float, is_bull: bool) -> float:
    raw = entry * (1 - pct / 100.0) if is_bull else entry * (1 + pct / 100.0)
    return round_away_from_entry(raw, entry, is_bull)


def band_stop(entry, level, is_bull, atr_pct, k) -> BandStop | None:
    if k is not None and k >= BAND_CEILING_ATR:
        raise ValueError(f"ATR floor k={k} must be below the {BAND_CEILING_ATR} x ATR ceiling")
    if not _usable(entry, level, is_bull, atr_pct, k):
        return None
    lo, hi = k * atr_pct, BAND_CEILING_ATR * atr_pct
    d = planned_loss_pct(entry, level)
    if d < lo - _TOL:
        stop, moved = _offset_stop(entry, lo, is_bull), MOVED_FLOOR
    elif d > hi + _TOL:
        stop, moved = _offset_stop(entry, hi, is_bull), MOVED_CEILING
    else:
        stop, moved = float(level), MOVED_UNTOUCHED
    return BandStop(stop, moved, lo, hi, planned_loss_pct(entry, stop))
```

`raw_atr14_pct(df, entry)`: `None` when `df is None`, `len(df) == 0`, `entry is None` or `entry <= 0`; else `float(atr(df, ATR_PERIOD).iloc[-1])` inside `try/except Exception` (giving `None`); `None` when not `math.isfinite` or `<= 0`; else `value / entry * 100.0`.
`band_for(df, entry, k)`: `None` when `not k or k <= 0`; else `AtrBand(float(k), raw_atr14_pct(df, entry))`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_atr_band.py`
Expected: all pass, `0 failed`.

- [ ] **Step 5: Complexity and import check**

Run: `python scripts/dev/complexity_gate.py` then `python -c "import swingbot.core.market.atr_band, swingbot.core.market.levels"`
Expected: gate passes (every function in `atr_band.py` < 15); the import prints nothing (no cycle).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/atr_band.py tests/market/test_atr_band.py
git commit -m "feat(market): v191 ATR band arithmetic -- raw ATR14%, tick rounding away from entry, band stop

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 4 — Builder geometry

### Task V191-8: Builder: band geometry, arm R and arm K, `stop_moved_by`

**Model:** opus — rewires the one confluence plan constructor shared by live and replay; arm K's "today's TP1" and the boundary rules are subtle, and `build_confluence_plan` (C 13) must not cross 15.

**Files:**
- Modify: `swingbot/core/planning/builders.py` (`confluence_stop_geometry` region, lines ~545-640; `build_confluence_plan`, lines ~645-725)
- Test: `tests/planning/test_confluence_atr_band_build.py` (create)

**Interfaces:**
- Consumes: `atr_band.band_stop`, `atr_band.REASON_NO_TARGET`, `atr_band.REASON_RR_DROP` (V191-7); `ScanParams.confluence_atr_stop_floor: float`, `ScanParams.confluence_atr_target_mode: str` (V191-2); `TradePlanV2.stop_moved_by` (V191-4); the scenario attribute `atr14_pct` (set by V191-9's `build_scenarios`; read here with `getattr(scenario, "atr14_pct", None)` so `SimpleNamespace` scenarios and pre-v191 callers keep working); existing `select_structural_target(entry, stop_loss, is_bull, candidate_levels, min_rr, max_rr)` (`targets.py:10`), `confluence_stop_geometry`, `_confluence_candidates`, `CLAMP_HEADROOM_PCT`, `STOP_GEOMETRY_TOL`, `HARD_MAX_PLANNED_LOSS_PCT`, `planned_loss_pct`.
- Produces (index § Contracts):
  - `TODAY_BAND_FLOOR_PCT = HARD_MAX_PLANNED_LOSS_PCT - CLAMP_HEADROOM_PCT` (1.75)
  - `class PlanGeometry(NamedTuple): stop_loss: float | None; stop_ceiling_pct: float | None; moved_by: str | None; tp1: float | None; reason: str | None`
  - `confluence_atr_band_stop(entry, level, is_bull, atr_pct, params) -> tuple[float, float, str] | None` — `(stop_loss, stop_ceiling_pct, moved_by)`, `stop_ceiling_pct = BandStop.distance_pct + CLAMP_HEADROOM_PCT`
  - `arm_k_today_stop(entry: float, level: float, is_bull: bool) -> float`
  - `band_no_plan_reason(scenario, level_map=None, params=None) -> str | None` — consumed by V191-12 (`analyze._no_plan_reason`) and V191-14 (census)
  - `_plan_geometry(scenario, candidates, params) -> PlanGeometry | None` — `None` only for v139 arm D's drop

- [ ] **Step 1: Write the failing tests** in `tests/planning/test_confluence_atr_band_build.py`

```python
"""V191-8: build_confluence_plan's band path. Floor on and an ATR on the
scenario -> the stop sits in the ATR band, the ceiling stored is the band
distance + 0.25, stop_moved_by says why; arm R re-chooses TP1 against the band
stop, arm K keeps today's TP1 and drops below MIN_RISK_REWARD_RATIO."""
import dataclasses
import types

import pytest

from swingbot import config
from swingbot.core.planning import builders
from swingbot.core.planning.plan_engine import build_confluence_plan
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv


@pytest.fixture(autouse=True)
def clamp_on(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)


def _params(k=1.0, mode="rechoose", **kw):
    return dataclasses.replace(ScanParams.from_config(), min_risk_reward_ratio=1.5,
                               max_risk_reward_ratio=2.5, confluence_structural_stop_pct=0.0,
                               confluence_stop_drop_pct=0.0, confluence_atr_stop_floor=k,
                               confluence_atr_target_mode=mode, **kw)


def _scenario(direction, stop_loss, take_profit, atr14_pct, entry=100.0):
    return types.SimpleNamespace(
        direction=direction, entry=entry, stop_loss=stop_loss, take_profit=take_profit,
        target_sources=["Rolling S/R"], stop_sources=["Rolling S/R"], atr14_pct=atr14_pct)


def _build(scenario, params):
    return build_confluence_plan(
        scenario, make_ohlcv([scenario.entry] * 60), ticker="XYZ", horizon_key="4w",
        primary_strategy="S/R Confluence", level_map=None, params=params)


def test_today_band_floor_is_the_v115_clamp_target():
    assert builders.TODAY_BAND_FLOOR_PCT == pytest.approx(1.75)


# --- floor off / no ATR: today's plan, nothing new on it ---------------------------

def test_floor_off_builds_todays_clamped_plan_even_with_an_atr():
    plan = _build(_scenario("bullish", 96.5, 108.0, 4.0), _params(k=0.0))
    assert plan.stop_loss == pytest.approx(98.25)
    assert plan.stop_ceiling_pct is None and plan.stop_moved_by is None
    assert "stop_moved_by" not in plan_to_dict(plan)


def test_floor_on_without_an_atr_builds_todays_plan():
    plan = _build(_scenario("bullish", 96.5, 108.0, None), _params(k=1.0))
    assert plan.stop_loss == pytest.approx(98.25)
    assert plan.stop_ceiling_pct is None and plan.stop_moved_by is None


# --- the band stop (a = 4.0, k = 1.0 -> lo 4%, hi 8%) ------------------------------

def test_confluence_atr_band_stop_returns_stop_ceiling_and_reason():
    got = builders.confluence_atr_band_stop(100.0, 99.0, True, 4.0, _params(k=1.0))
    assert got == (pytest.approx(96.0), pytest.approx(4.25), "floor")
    assert builders.confluence_atr_band_stop(100.0, 99.0, True, 4.0, _params(k=0.0)) is None
    assert builders.confluence_atr_band_stop(100.0, 99.0, True, None, _params(k=1.0)) is None


def test_arm_r_floor_moved_plan():
    plan = _build(_scenario("bullish", 99.0, 108.0, 4.0), _params(k=1.0))
    assert plan.stop_loss == pytest.approx(96.0)
    assert plan.stop_ceiling_pct == pytest.approx(4.25)
    assert plan.stop_moved_by == "floor"
    assert plan.tp1 == pytest.approx(108.0)              # 2.0R against the 4.0 band risk
    assert plan.acceptance_level == 99.0                 # v129 still leans on the level
    assert plan_to_dict(plan)["stop_moved_by"] == "floor"


def test_arm_r_floor_moved_plan_bearish_mirror():
    plan = _build(_scenario("bearish", 101.0, 92.0, 4.0), _params(k=1.0))
    assert plan.stop_loss == pytest.approx(104.0)
    assert plan.stop_ceiling_pct == pytest.approx(4.25)
    assert plan.stop_moved_by == "floor"
    assert plan.tp1 == pytest.approx(92.0)


def test_arm_r_untouched_stop_between_two_percent_and_hi_is_not_clamped():
    plan = _build(_scenario("bullish", 95.0, 109.0, 4.0), _params(k=1.0))
    assert plan.stop_loss == 95.0                        # today would clamp to 98.25
    assert plan.stop_ceiling_pct == pytest.approx(5.25)
    assert plan.stop_moved_by == "untouched"
    assert plan.tp1 == pytest.approx(109.0)              # 1.8R


def test_arm_r_ceiling_moved_plan():
    plan = _build(_scenario("bullish", 90.0, 115.0, 4.0), _params(k=1.0))
    assert plan.stop_loss == pytest.approx(92.0)
    assert plan.stop_ceiling_pct == pytest.approx(8.25)
    assert plan.stop_moved_by == "ceiling"
    assert plan.tp1 == pytest.approx(115.0)              # 1.875R


def test_arm_r_no_candidate_clears_the_band_is_no_plan():
    scenario = _scenario("bullish", 99.0, 104.0, 4.0)    # 1.0R against the band stop
    assert _build(scenario, _params(k=1.0)) is None
    assert builders.band_no_plan_reason(scenario, None, _params(k=1.0)) == "band_no_target"


def test_arm_r_reselects_where_arm_k_drops():
    scenario = _scenario("bullish", 96.5, 106.0, 2.5)    # untouched at 3.5%, hi 5%
    plan = _build(scenario, _params(k=1.0, mode="rechoose"))
    assert plan.tp1 == pytest.approx(106.0)              # 1.71R against 3.5
    assert _build(scenario, _params(k=1.0, mode="keep")) is None
    # today's TP1 against the 1.75 risk is the synthetic 2.5R target 104.375 -> 1.25R
    assert builders.band_no_plan_reason(scenario, None, _params(k=1.0, mode="keep")) == "band_rr_drop"


# --- arm K: today's TP1 kept, dropped under the minimum ----------------------------

@pytest.mark.parametrize("entry,level,is_bull,expected", [
    (100.0, 99.0, True, 98.25),       # newly admitted, d 1.0 < 1.75: the 1.75% stop today requires
    (100.0, 98.1, True, 98.1),        # inside today's 1.75-2% band: the level
    (100.0, 96.5, True, 98.25),       # past 2%: the v115 clamp
    (100.0, 101.0, False, 101.75),
    (100.0, 103.5, False, 101.75),
])
def test_arm_k_today_stop(entry, level, is_bull, expected):
    assert builders.arm_k_today_stop(entry, level, is_bull) == pytest.approx(expected)


def test_arm_k_keeps_todays_tp1_against_the_band_stop():
    # a 2.4, k 0.75 -> lo 1.8: stop 98.2. Today's TP1 against 1.75: 104 (2.29R); 2.22R vs 1.8.
    plan = _build(_scenario("bullish", 99.0, 104.0, 2.4), _params(k=0.75, mode="keep"))
    assert plan.stop_loss == pytest.approx(98.2)
    assert plan.tp1 == pytest.approx(104.0)
    assert plan.stop_moved_by == "floor"
    assert plan.stop_ceiling_pct == pytest.approx(2.05)


def test_arm_k_keeps_todays_tp1_bearish_mirror():
    plan = _build(_scenario("bearish", 101.0, 96.0, 2.4), _params(k=0.75, mode="keep"))
    assert plan.stop_loss == pytest.approx(101.8)
    assert plan.tp1 == pytest.approx(96.0)


def test_arm_k_reward_risk_exactly_at_the_minimum_is_kept():
    # a 2.5, k 1.0 -> stop 97.5 (risk 2.5); today's TP1 103.75 is 2.14R vs 1.75, exactly 1.5R vs 2.5
    plan = _build(_scenario("bullish", 99.0, 103.75, 2.5), _params(k=1.0, mode="keep"))
    assert plan is not None and plan.tp1 == pytest.approx(103.75)


def test_arm_k_reward_risk_just_below_the_minimum_is_dropped():
    scenario = _scenario("bullish", 99.0, 103.74, 2.5)   # 1.496R vs 2.5
    params = _params(k=1.0, mode="keep")
    assert _build(scenario, params) is None
    assert builders.band_no_plan_reason(scenario, None, params) == "band_rr_drop"


def test_arm_k_without_a_today_tp1_is_band_no_target():
    scenario = _scenario("bullish", 99.0, 100.5, 2.5)    # 0.29R even against today's 1.75
    params = _params(k=1.0, mode="keep")
    assert _build(scenario, params) is None
    assert builders.band_no_plan_reason(scenario, None, params) == "band_no_target"


# --- the v139 arms and the reason helper ----------------------------------------------

def test_band_path_never_consults_the_v139_arms(monkeypatch):
    monkeypatch.setattr(builders, "_arm_s_stop", lambda *a, **k: pytest.fail("arm S consulted"))
    params = dataclasses.replace(_params(k=1.0), confluence_structural_stop_pct=4.0)
    plan = _build(_scenario("bullish", 95.0, 109.0, 4.0), params)
    assert plan.stop_moved_by == "untouched"


def test_band_no_plan_reason_is_none_when_a_plan_builds_or_the_band_is_off():
    built = _scenario("bullish", 99.0, 108.0, 4.0)
    assert builders.band_no_plan_reason(built, None, _params(k=1.0)) is None
    off = _scenario("bullish", 99.0, 104.0, 4.0)
    assert builders.band_no_plan_reason(off, None, _params(k=0.0)) is None


def test_plan_geometry_today_path_matches_confluence_stop_geometry():
    scenario = _scenario("bullish", 96.5, 108.0, None)
    geo = builders._plan_geometry(scenario, [108.0], _params(k=1.0))
    assert geo == builders.PlanGeometry(pytest.approx(98.25), None, None, pytest.approx(104.375), None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_confluence_atr_band_build.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.planning.builders' has no attribute 'TODAY_BAND_FLOOR_PCT'` (and the band plans come back with today's 98.25 stop).

- [ ] **Step 3: Add the band geometry to `swingbot/core/planning/builders.py`**

Import `from swingbot.core.market import atr_band` at the top with the other `swingbot.core.market` imports. Below `confluence_stop_geometry` add `TODAY_BAND_FLOOR_PCT`, `PlanGeometry` and the helpers. `confluence_stop_geometry` itself is **unchanged** (v139's callers keep their 2-tuple). The arm logic is not fixed by the signatures, so the bodies are:

```python
def arm_k_today_stop(entry, level, is_bull) -> float:
    """v191 arm K: the stop today's rules would use -- the level clamped into
    [TODAY_BAND_FLOOR_PCT, HARD_MAX_PLANNED_LOSS_PCT]; under 1.75% (a newly
    admitted scenario) and past 2% both land on the 1.75% stop."""
    d = planned_loss_pct(entry, level)
    if TODAY_BAND_FLOOR_PCT - STOP_GEOMETRY_TOL <= d <= HARD_MAX_PLANNED_LOSS_PCT + STOP_GEOMETRY_TOL:
        return float(level)
    offset = entry * TODAY_BAND_FLOOR_PCT / 100.0
    return entry - offset if is_bull else entry + offset


def _arm_k_tp1(entry, level, is_bull, stop, candidates, params):
    lo_rr, hi_rr = params.min_risk_reward_ratio, params.max_risk_reward_ratio
    today = select_structural_target(entry, arm_k_today_stop(entry, level, is_bull), is_bull,
                                     candidates, lo_rr, hi_rr)
    if today is None:
        return None, atr_band.REASON_NO_TARGET
    rr = abs(today - entry) / abs(entry - stop)
    if rr + STOP_GEOMETRY_TOL < lo_rr:
        return None, atr_band.REASON_RR_DROP
    return today, None


def _band_tp1(entry, level, is_bull, stop, candidates, params):
    """(tp1, reason): arm K ("keep") or arm R (any other mode, the default)."""
    if params.confluence_atr_target_mode == "keep":
        return _arm_k_tp1(entry, level, is_bull, stop, candidates, params)
    tp1 = select_structural_target(entry, stop, is_bull, candidates,
                                   params.min_risk_reward_ratio, params.max_risk_reward_ratio)
    return tp1, (None if tp1 is not None else atr_band.REASON_NO_TARGET)


def _plan_geometry(scenario, candidates, params):
    """v191: the confluence plan's stop, stored ceiling, band reason and TP1.
    The band path when the floor is on and the scenario carries a raw ATR14%;
    otherwise today's confluence_stop_geometry (v139 arms included) and today's
    TP1. None only for v139 arm D's drop."""
    entry, level = scenario.entry, scenario.stop_loss
    is_bull = scenario.direction == "bullish"
    band = confluence_atr_band_stop(entry, level, is_bull,
                                    getattr(scenario, "atr14_pct", None), params)
    if band is not None:
        stop, ceiling, moved_by = band
        tp1, reason = _band_tp1(entry, level, is_bull, stop, candidates, params)
        return PlanGeometry(stop, ceiling, moved_by, tp1, reason)
    geometry = confluence_stop_geometry(entry, level, is_bull, candidates, params)
    if geometry is None:
        return None
    stop, ceiling = geometry
    tp1 = select_structural_target(entry, stop, is_bull, candidates,
                                   params.min_risk_reward_ratio, params.max_risk_reward_ratio)
    return PlanGeometry(stop, ceiling, None, tp1, None)
```

Also, with bodies fixed by the contract: `TODAY_BAND_FLOOR_PCT` and `PlanGeometry` exactly as in Interfaces (comment: today's percent band as arm K reads it, the v115 clamp target); `confluence_atr_band_stop` calls `atr_band.band_stop(entry, level, is_bull, atr_pct, params.confluence_atr_stop_floor)` and returns `(band.stop, band.distance_pct + CLAMP_HEADROOM_PCT, band.moved_by)`, or `None` when that is `None`; `band_no_plan_reason` defaults `params` to `ScanParams.from_config()` (local import, as `confluence_stop_dropped` does) and returns `_plan_geometry(scenario, _confluence_candidates(scenario, level_map), params).reason`, `None` when the geometry is `None` — one geometry call shared with the builder, so `attach_plan_v2` and the replay census name the reason without a second rule.

`NamedTuple` comes from `typing` (add to the existing import if absent). `_confluence_candidates` is defined below `confluence_stop_geometry` today; place `band_no_plan_reason` after it.

- [ ] **Step 4: Rewire `build_confluence_plan` onto `_plan_geometry`**

Replace the block from `geometry = confluence_stop_geometry(...)` through `if tp1 is None: return None` with:

```python
    geometry = _plan_geometry(scenario, candidates, params)
    if geometry is None or geometry.tp1 is None:
        return None              # v139 arm D, no qualifying target, or a v191 band reason
    stop_loss, stop_ceiling_pct, tp1 = geometry.stop_loss, geometry.stop_ceiling_pct, geometry.tp1
```

and pass `stop_moved_by=geometry.moved_by` to `TradePlanV2(...)` next to `stop_ceiling_pct=stop_ceiling_pct`. Nothing after it changes: TP2 is selected beyond the (re-chosen or kept) TP1 as today, `stamp_confluence_acceptance(plan, df, level)` still reads the pre-band level. Extend the docstring with one v191 sentence: the stop comes from `_plan_geometry` — the ATR band when `CONFLUENCE_ATR_STOP_FLOOR > 0` and the scenario carries `atr14_pct`, else v139's geometry. The `if` count is unchanged (two `if`s became one `if ... or ...`), so the function stays at C 13.

- [ ] **Step 5: Run the new tests, the v139 builder tests and the goldens**

Run:
```bash
python scripts/dev/testrun.py file tests/planning/test_confluence_atr_band_build.py
python scripts/dev/testrun.py file tests/planning/test_confluence_stop_build.py
python scripts/dev/testrun.py file tests/scanning/test_attach_confluence_stop_geometry.py
python scripts/dev/testrun.py file tests/planning/test_v191_plan_golden.py
python scripts/dev/testrun.py file tests/backtesting/test_v191_flag_off_golden.py
python scripts/dev/complexity_gate.py
```
Expected: every file `0 failed`; the goldens byte-identical (knobs off never enter the band path); complexity gate passes with `build_confluence_plan` ≤ 13.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/builders.py tests/planning/test_confluence_atr_band_build.py
git commit -m "feat(planning): v191 band geometry in build_confluence_plan -- arm R re-chooses TP1, arm K keeps today's and drops under min RR

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 5 — Admission

### Task V191-9: Admission (replay side): `build_scenarios(band=)`, `Scenario.atr14_pct`, gating input, `scenarios_at`

**Model:** opus — edits `levels.build_scenarios` (C 15, legacy, may not grow) and the replay admission every measurement row comes from; NO-LOOKAHEAD applies.

**Files:**
- Modify: `swingbot/core/market/levels.py` (`Scenario` ~612-640; `build_scenarios` ~662-770)
- Modify: `swingbot/core/scanning/gating.py` (`scenario_gate_inputs`)
- Modify: `swingbot/core/backtesting/backtest_scenarios.py` (`scenarios_at` ~114-146)
- Test: `tests/market/test_build_scenarios_atr_band.py` (create), `tests/backtesting/test_backtest_scenarios_atr_band.py` (create)

**Interfaces:**
- Consumes: `atr_band.AtrBand`, `atr_band.band_for(df, entry, k)`, `atr_band.band_stop(...)` (V191-7); `ScanParams.confluence_atr_stop_floor` (V191-2).
- Produces: `Scenario.atr14_pct: float | None = None` (last dataclass field; set only when `band` is active, i.e. `band is not None and band.atr_pct is not None`); `build_scenarios(..., block_bullish=False, band: AtrBand | None = None)`; `scenario_gate_inputs(params, horizon)["atr_stop_floor"] == params.confluence_atr_stop_floor`. With the band active, the `min_stop_distance` and `max_stop_distance` constraints read `True` and `min_risk_reward` is computed against `band_stop(...).stop`; the scenario's `stop_loss`, `stop_distance_pct` and `tight_stop` stay the raw level's.

- [ ] **Step 1: Write the failing tests**

`tests/market/test_build_scenarios_atr_band.py`:

```python
"""V191-9: with an active ATR band, build_scenarios drops the min/max stop
distance gates and checks its own-target R:R against the band stop."""
import pytest

from swingbot.core.market import levels
from swingbot.core.market.atr_band import AtrBand

LIVE = dict(min_reward_pct=3.0, min_stop_distance_pct=1.75, max_stop_distance_pct=3.0,
            min_risk_reward=1.5)


def _bull(support, target, band=None, **gates):
    sup = [levels.Level(support, ["Rolling S/R"])]
    res = [levels.Level(target, ["Rolling S/R"])]
    got = levels.build_scenarios(100.0, sup, res, atr_floor=6.0, band=band, **{**LIVE, **gates})
    return [s for s in got if s.direction == "bullish"]


def test_a_one_percent_stop_is_refused_without_the_band_and_admitted_with_it():
    assert _bull(99.0, 108.0) == []
    (sc,) = _bull(99.0, 108.0, band=AtrBand(1.0, 4.0))
    assert sc.stop_loss == 99.0 and sc.stop_distance_pct == pytest.approx(1.0)  # the raw level
    assert sc.atr14_pct == pytest.approx(4.0)
    assert sc.constraints["min_stop_distance"] and sc.constraints["max_stop_distance"]
    assert sc.meets_all_own_constraints


def test_the_horizon_max_stop_is_bypassed_by_the_band():
    assert _bull(95.0, 110.0) == []                                  # 5% > max 3%
    assert len(_bull(95.0, 110.0, band=AtrBand(1.0, 4.0))) == 1      # untouched in [4, 8]


def test_own_target_reward_risk_is_measured_against_the_band_stop():
    # 5R against the raw 99 level, 1.25R against the 96 band stop -> refused
    assert _bull(99.0, 105.0, band=AtrBand(1.0, 4.0)) == []


def test_a_band_without_atr_is_todays_admission():
    assert _bull(99.0, 108.0, band=AtrBand(1.0, None)) == []
    (sc,) = _bull(98.0, 108.0, band=AtrBand(1.0, None))             # d 2.0 passes today
    assert sc.atr14_pct is None


def test_bearish_mirror():
    sup = [levels.Level(92.0, ["Rolling S/R"])]
    res = [levels.Level(101.0, ["Rolling S/R"])]
    off = levels.build_scenarios(100.0, sup, res, atr_floor=6.0, **LIVE)
    on = levels.build_scenarios(100.0, sup, res, atr_floor=6.0, band=AtrBand(1.0, 4.0), **LIVE)
    assert [s.direction for s in off] == []
    bear = [s for s in on if s.direction == "bearish"]
    assert bear[0].stop_loss == 101.0 and bear[0].atr14_pct == pytest.approx(4.0)


def test_no_band_keeps_the_constraint_keys_and_order():
    (sc,) = _bull(98.0, 108.0)
    assert list(sc.constraints) == ["min_reward", "min_stop_distance", "max_stop_distance",
                                    "min_risk_reward", "not_dead_cat_bounce"]
    assert sc.atr14_pct is None
```

`tests/backtesting/test_backtest_scenarios_atr_band.py`:

```python
"""V191-9: replay admission builds the band from the as-of window only."""
import dataclasses

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.market import atr_band, levels
from swingbot.core.scanning.gating import scenario_gate_inputs
from swingbot.scan_params import ScanParams
from tests.market.test_atr_band import _frame

HORIZON = {"bars": 60, "label": "4w", "sr_target_min_pct": 8.0, "max_risk_pct": 3.0}


@pytest.fixture
def spy(monkeypatch):
    seen = []
    real = levels.build_scenarios

    def _spy(*args, **kwargs):
        seen.append(kwargs.get("band"))
        return real(*args, **kwargs)

    monkeypatch.setattr(bs.levels, "build_scenarios", _spy)
    monkeypatch.setattr(bs, "levels_asof", lambda *a, **k: (
        [levels.Level(99.0, ["Rolling S/R"])], [levels.Level(108.0, ["Rolling S/R"])]))
    return seen


def _params(k):
    # admission pinned (legacy-gate values) so a config default never decides the test
    return dataclasses.replace(ScanParams.from_config(), confluence_atr_stop_floor=k,
                               min_reward_pct=3.0, min_stop_distance_pct=2.0,
                               max_stop_loss_pct=7.0, min_risk_reward_ratio=1.5)


def test_gate_inputs_carry_the_floor():
    assert scenario_gate_inputs(_params(1.0), HORIZON)["atr_stop_floor"] == 1.0
    assert scenario_gate_inputs(_params(0.0), HORIZON)["atr_stop_floor"] == 0.0


def test_floor_off_passes_no_band(spy):
    bs.scenarios_at("XYZ", _frame(n=80), 59, "4w", _params(0.0), {})
    assert spy == [None]


def test_floor_on_reads_the_window_through_bar_i_only(spy):
    df = _frame(n=80)
    bs.scenarios_at("XYZ", df, 59, "4w", _params(1.0), {})
    df.iloc[60, df.columns.get_loc("High")] = 500.0         # the bar after the creating bar
    bs.scenarios_at("XYZ", df, 59, "4w", _params(1.0), {})
    assert spy[0] == spy[1] == atr_band.band_for(df.iloc[:60], 100.0, 1.0)
    assert spy[0].atr_pct == pytest.approx(4.0)


def test_floor_on_admits_the_one_percent_stop_the_legacy_gates_refuse(spy):
    off = bs.scenarios_at("XYZ", _frame(n=80), 59, "4w", _params(0.0), {})[-1]
    on = bs.scenarios_at("XYZ", _frame(n=80), 59, "4w", _params(1.0), {})[-1]
    assert [s.direction for s in off] == []
    assert [s.direction for s in on] == ["bullish"]


def test_legacy_gates_take_the_floor_from_config(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_ATR_STOP_FLOOR", 1.0)
    params, legacy = bs._replay_params(None, bs.CONFLUENCE_GATES)
    assert legacy and params.confluence_atr_stop_floor == 1.0
    assert params.min_stop_distance_pct == 2.0                # the legacy floor, bypassed by the band
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_build_scenarios_atr_band.py` and `python scripts/dev/testrun.py file tests/backtesting/test_backtest_scenarios_atr_band.py`
Expected: FAIL — `TypeError: build_scenarios() got an unexpected keyword argument 'band'` and `KeyError: 'atr_stop_floor'`.

- [ ] **Step 3: Implement in `levels.py` without adding a branch to `build_scenarios`**

- `Scenario`: append `atr14_pct: float | None = None` after `constraints` (comment: v191 raw ATR14% of the creating bar; set only by an active band; the builder's band carrier).
- Import `from swingbot.core.market.atr_band import AtrBand, band_stop` (no cycle: `atr_band` imports only `indicators` and `risk_limits`).
- New module-level helpers (all branching lives here):
  - `_active_band(band: AtrBand | None) -> AtrBand | None` — `band` when `band is not None and band.atr_pct is not None`, else `None`.
  - `_stop_constraints(stop_dist, entry, stop_price, target_price, direction, band, min_stop_distance_pct, max_stop_distance_pct, min_risk_reward) -> dict` — returns the three keys `min_stop_distance`, `max_stop_distance`, `min_risk_reward` in that order. Without an active band: today's three expressions verbatim (R:R against `stop_price`). With one: `bs = band_stop(entry, stop_price, direction == "bullish", band.atr_pct, band.k)`; when `bs is None` fall back to today's three; else `min_stop_distance=True`, `max_stop_distance=True`, `min_risk_reward = min_risk_reward <= 0 or reward / abs(entry - bs.stop) >= min_risk_reward`.
- `build_scenarios` signature gains `band: AtrBand | None = None` last; its first line becomes `band = _active_band(band)`. The nested `_check_constraints` returns `{"min_reward": ..., **_stop_constraints(stop_dist, entry, stop_price, target_price, direction, band, min_stop_distance_pct, max_stop_distance_pct, min_risk_reward), "not_dead_cat_bounce": ...}` (key order unchanged). Both `Scenario(...)` calls add `atr14_pct=None if band is None else band.atr_pct` — write it as `atr14_pct=_band_atr(band)` with a one-line helper `_band_atr(band) -> float | None` so `build_scenarios` gains no conditional. Docstring: one v191 paragraph — with an active band the ATR band replaces both stop-distance gates and the own-target R:R uses the band stop.

- [ ] **Step 4: Thread the floor through `gating.py` and `scenarios_at`**

- `scenario_gate_inputs` adds `"atr_stop_floor": params.confluence_atr_stop_floor` as the last key.
- `scenarios_at` (backtest_scenarios.py): after `gate_inputs = ...` add `band = atr_band.band_for(window, price, gate_inputs["atr_stop_floor"])` and pass `band=band` to `levels.build_scenarios(...)`. Import `from swingbot.core.market import atr_band`. `window` is `df.iloc[:i + 1]`, so the band reads the creating bar and nothing after it. `armed_replay.py` keeps its own `build_scenarios` call without `band` (strategy arms are out of scope).

- [ ] **Step 5: Run the tests, the existing scenario and gating tests, and the goldens**

```bash
python scripts/dev/testrun.py file tests/market/test_build_scenarios_atr_band.py
python scripts/dev/testrun.py file tests/backtesting/test_backtest_scenarios_atr_band.py
python scripts/dev/testrun.py file tests/market/test_levels_scenarios.py
python scripts/dev/testrun.py file tests/market/test_build_scenarios_veto.py
python scripts/dev/testrun.py file tests/scanning/test_gating.py
python scripts/dev/testrun.py file tests/backtesting/test_v191_flag_off_golden.py
python scripts/dev/complexity_gate.py
```
Expected: `0 failed` everywhere; golden byte-identical; complexity gate passes with `build_scenarios` still at its baseline 15 (no new branch).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/levels.py swingbot/core/scanning/gating.py swingbot/core/backtesting/backtest_scenarios.py tests/market/test_build_scenarios_atr_band.py tests/backtesting/test_backtest_scenarios_atr_band.py
git commit -m "feat(levels): v191 band admission -- build_scenarios(band=) skips stop-distance gates, R:R vs the band stop; replay band from the as-of window

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V191-10: Admission (live side): completed-frame band, `band_no_atr` log, requirements display, live/replay parity

**Model:** opus — live scan path with a forming-bar NO-LOOKAHEAD trap and a parity contract against replay; touches the scan's hard-filter snapshot.

**Files:**
- Modify: `swingbot/core/scanning/analyze.py` (`_default_hard_filters` ~802, `_horizon_scenarios` ~815-860, its two callers `_scan_one` ~1050 and `rescenario` ~1246)
- Modify: `swingbot/core/scanning/scan_run.py` (`_hard_filters_snapshot` only, ~313-325)
- Modify: `swingbot/core/scanning/requirements.py` (`_build_requirement_checks`, the two stop-distance rows)
- Test: `tests/scanning/test_horizon_scenarios_atr_band.py` (create), `tests/scanning/test_atr_band_live_replay_parity.py` (create)

**Interfaces:**
- Consumes: `atr_band.band_for`, `atr_band.REASON_NO_ATR`, `AtrBand` (V191-7); `build_scenarios(..., band=)`, `Scenario.atr14_pct`, `bs.scenarios_at` (V191-9); `build_confluence_plan` band path (V191-8); `strategy_pass.completed_frame(df, now)`; `config.CONFLUENCE_ATR_STOP_FLOOR` (V191-2).
- Produces: `_horizon_scenarios(df, h, current_price, trendline_candidates, hard_filters, *, ticker: str = "", now=None) -> HorizonBuild`; `_band_live(df, current_price: float, k: float, now, ticker: str, horizon_label: str) -> AtrBand | None`; hard-filter key `"confluence_atr_stop_floor"` (in `scan_run._hard_filters_snapshot(params)` from `params.confluence_atr_stop_floor`, in `analyze._default_hard_filters()` from `config.CONFLUENCE_ATR_STOP_FLOOR`; always read with `.get("confluence_atr_stop_floor", 0.0)` because an item's stored `hard_filters` may predate the key).

- [ ] **Step 1: Write the failing tests**

`tests/scanning/test_horizon_scenarios_atr_band.py`:

```python
"""V191-10: the live scan builds the band from COMPLETED bars, logs
band_no_atr when ATR14 is missing, and the requirement table shows the band."""
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.market import atr_band, levels
from swingbot.core.market.strategy import HORIZONS
from swingbot.core.scanning import analyze, requirements, scan_run
from tests.market.test_atr_band import _frame

IN_SESSION = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)   # Wed 11:00 ET
FILTERS = {"min_reward_pct": 3.0, "max_stop_loss_pct": 7.0, "min_stop_distance_pct": 1.75,
           "min_risk_reward_ratio": 1.5}


@pytest.fixture
def seen(monkeypatch):
    calls = []
    real = levels.build_scenarios
    monkeypatch.setattr(levels, "collect_candidate_levels", lambda *a, **k: [])
    monkeypatch.setattr(levels, "build_level_map", lambda *a, **k: (
        [levels.Level(99.0, ["Rolling S/R"])], [levels.Level(108.0, ["Rolling S/R"])]))
    monkeypatch.setattr(analyze, "veto_bullish_for", lambda df: False)
    monkeypatch.setattr(levels, "build_scenarios",
                        lambda *a, **k: calls.append(k.get("band")) or real(*a, **k))
    return calls


def _run(df, k, now=IN_SESSION, filters=FILTERS):
    hf = {**filters, "confluence_atr_stop_floor": k} if k is not None else dict(filters)
    return analyze._horizon_scenarios(df, HORIZONS["4w"], 100.0, [], hf, ticker="XYZ", now=now)


def test_floor_off_or_a_pre_v191_snapshot_passes_no_band(seen):
    _run(_frame(), 0.0)
    _run(_frame(), None)                       # hard_filters without the key
    assert seen == [None, None]


def test_the_forming_bar_is_dropped_before_the_atr_is_read(seen):
    df = _frame(n=61, end="2026-10-21")
    df.iloc[-1, df.columns.get_loc("High")] = 500.0      # today's forming bar
    build = _run(df, 1.0)
    assert seen[0] == atr_band.band_for(df.iloc[:-1], 100.0, 1.0)
    assert seen[0].atr_pct == pytest.approx(4.0)
    assert [s.direction for s in build.scenarios] == ["bullish"]   # d 1.0 admitted by the band


def test_missing_atr_logs_band_no_atr_and_keeps_todays_admission(seen, caplog):
    with caplog.at_level(logging.INFO, logger=analyze.log.name):
        build = _run(_frame(n=10), 1.0)
    assert seen == [atr_band.AtrBand(1.0, None)]
    assert build.scenarios == []                                  # d 1.0 < 1.75, as today
    assert "XYZ (4-week swing): plan rejected (band_no_atr" in caplog.text


def test_the_hard_filter_snapshots_carry_the_floor(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_ATR_STOP_FLOOR", 1.0)
    assert analyze._default_hard_filters()["confluence_atr_stop_floor"] == 1.0
    assert scan_run._hard_filters_snapshot()["confluence_atr_stop_floor"] == 1.0


def _checks(scenario):
    conf = SimpleNamespace(level=3, label="Medium", score=60)
    return {c.key: c for c in requirements._build_requirement_checks(scenario, (2, ["A", "B"]), conf, 2, 1)}


def test_requirement_rows_show_the_band(monkeypatch):
    monkeypatch.setattr(requirements.opex, "suppress_new_entries", lambda **k: False)
    monkeypatch.setattr(config, "CONFLUENCE_ATR_STOP_FLOOR", 1.0)
    sc = levels.build_scenarios(100.0, [levels.Level(99.0, ["S"])], [levels.Level(108.0, ["R"])],
                                3.0, min_stop_distance_pct=1.75, max_stop_distance_pct=7.0,
                                min_risk_reward=1.5, band=atr_band.AtrBand(1.0, 4.0))[0]
    checks = _checks(sc)
    assert checks["min_stop_distance"].detail == "1.0% away (ATR band 4.0–8.0%: 1× to 2× ATR14)"
    assert checks["max_stop_distance"].detail == checks["min_stop_distance"].detail


def test_requirement_rows_without_a_band_are_todays_text(monkeypatch):
    monkeypatch.setattr(requirements.opex, "suppress_new_entries", lambda **k: False)
    sc = levels.build_scenarios(100.0, [levels.Level(98.0, ["S"])], [levels.Level(108.0, ["R"])],
                                3.0, min_stop_distance_pct=1.75, max_stop_distance_pct=7.0)[0]
    detail = _checks(sc)["min_stop_distance"].detail
    assert detail == f"2.0% away (needs {config.MIN_STOP_DISTANCE_PCT:.1f}%+)"
```

`tests/scanning/test_atr_band_live_replay_parity.py`:

```python
"""V191-10: live and replay admit the same band scenario and build the same
band plan from it -- replay's legacy 2.0% floor and live's 1.75% are both
bypassed by the band, and both refuse d = 1.0% with the floor off."""
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.market import levels
from swingbot.core.market.strategy import HORIZONS
from swingbot.core.planning.plan_engine import build_confluence_plan
from swingbot.core.scanning import analyze, scan_run
from tests.market.test_atr_band import _frame

SAT = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)   # no forming bar
MAP = ([levels.Level(99.0, ["Rolling S/R"])], [levels.Level(108.0, ["Rolling S/R"])])


@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    monkeypatch.setattr(levels, "collect_candidate_levels", lambda *a, **k: [])
    monkeypatch.setattr(levels, "build_level_map", lambda *a, **k: MAP)
    monkeypatch.setattr(bs, "levels_asof", lambda *a, **k: MAP)
    monkeypatch.setattr(analyze, "veto_bullish_for", lambda df: False)
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 1.75)
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 3.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 7.0)


def _both(monkeypatch, k):
    monkeypatch.setattr(config, "CONFLUENCE_ATR_STOP_FLOOR", k)
    df = _frame(n=80)
    live = analyze._horizon_scenarios(df, HORIZONS["4w"], 100.0, [], scan_run._hard_filters_snapshot(),
                                      ticker="XYZ", now=SAT).scenarios
    params, _ = bs._replay_params(None, bs.CONFLUENCE_GATES)
    replay = bs.scenarios_at("XYZ", df, len(df) - 1, "4w", params, {})[-1]
    return df, [s for s in live if s.direction == "bullish"], [s for s in replay if s.direction == "bullish"]


def test_floor_off_both_refuse_a_one_percent_stop(monkeypatch):
    _, live, replay = _both(monkeypatch, 0.0)
    assert live == [] and replay == []


def test_floor_on_both_admit_and_build_the_same_band_plan(monkeypatch):
    df, (live,), (replay,) = _both(monkeypatch, 1.0)
    assert live.atr14_pct == replay.atr14_pct == pytest.approx(4.0)
    plans = [build_confluence_plan(sc, df, ticker="XYZ", horizon_key="4w",
                                   primary_strategy="S/R Confluence") for sc in (live, replay)]
    key = [(p.stop_loss, p.stop_ceiling_pct, p.stop_moved_by, p.tp1) for p in plans]
    assert key[0] == key[1] == (pytest.approx(96.0), pytest.approx(4.25), "floor", pytest.approx(108.0))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_horizon_scenarios_atr_band.py` and `... file tests/scanning/test_atr_band_live_replay_parity.py`
Expected: FAIL — `TypeError: _horizon_scenarios() got an unexpected keyword argument 'ticker'`.

- [ ] **Step 3: Implement the live band in `analyze.py` and `scan_run.py`**

- `_default_hard_filters`: add `'confluence_atr_stop_floor': config.CONFLUENCE_ATR_STOP_FLOOR` last. `scan_run._hard_filters_snapshot`: add `"confluence_atr_stop_floor": params.confluence_atr_stop_floor` last.
- `_band_live(df, current_price, k, now, ticker, horizon_label)`: `None` when `not k or k <= 0`. Else `frame = completed_frame(df, now or datetime.now(timezone.utc))` inside `try/except Exception` (`swallowed(log, "scan.analyze.band_frame", exc, level=logging.DEBUG)`, `frame = None`); `band = atr_band.band_for(frame, current_price, k)`; when `band.atr_pct is None` log at INFO exactly `"%s (%s): plan rejected (%s) -- ATR14 unavailable, today's stop band applies"` with `ticker, horizon_label, atr_band.REASON_NO_ATR`; return `band` (with `atr_pct=None` it is inert in `build_scenarios`).
- `_horizon_scenarios` gains `*, ticker: str = "", now=None`; before the `build_scenarios` call: `band = _band_live(df, current_price, hard_filters.get("confluence_atr_stop_floor", 0.0), now, ticker, h.get("label", ""))`; pass `band=band`. `levels.atr_floor_pct` and every other input stay as they are.
- Callers: `_scan_one` passes `ticker=ticker` (no `now`: the wall clock, as `_stamp_gap_sizing_live` does); `rescenario` passes `ticker=item.result.ticker`.

- [ ] **Step 4: Show the band in `requirements.py`**

Add `_stop_distance_detail(scenario, default: str) -> str`: when `getattr(scenario, "atr14_pct", None)` is `None` return `default`; else with `a = scenario.atr14_pct`, `k = config.CONFLUENCE_ATR_STOP_FLOOR` return `f"{scenario.stop_distance_pct:.1f}% away (ATR band {k * a:.1f}–{2 * a:.1f}%: {k:g}× to 2× ATR14)"`. The `min_stop_distance` and `max_stop_distance` rows pass today's f-string as `default`.

- [ ] **Step 5: Run the tests, the neighbouring scan tests and the gates**

```bash
python scripts/dev/testrun.py file tests/scanning/test_horizon_scenarios_atr_band.py
python scripts/dev/testrun.py file tests/scanning/test_atr_band_live_replay_parity.py
python scripts/dev/testrun.py file tests/infra/test_config_reload.py
python scripts/dev/testrun.py changed
python scripts/dev/complexity_gate.py
```
Expected: `0 failed`; `changed` widens over the scan suites touching `analyze.py` and stays green; complexity gate passes.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/analyze.py swingbot/core/scanning/scan_run.py swingbot/core/scanning/requirements.py tests/scanning/test_horizon_scenarios_atr_band.py tests/scanning/test_atr_band_live_replay_parity.py
git commit -m "feat(scan): v191 live band admission from completed bars, band_no_atr log, requirement rows; live/replay parity pinned

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 6 — The dollar invariant

### Task V191-11: Band sizing: worst-fill distance, band stamp key, `size_for` band branch, `band_sizing_verdict`

**Model:** sonnet — arithmetic and branching fully specified below on a module with an established test harness.

**Files:**
- Modify: `swingbot/core/planning/gap_sizing.py` (as left by V191-5)
- Modify: `swingbot/core/planning/stop_scope.py` (append `band_sizing_verdict`)
- Test: `tests/planning/test_band_sizing.py` (create)

**Interfaces:**
- Consumes: V191-5's long stamp (`{"rule", "down_gap_p99_pct", "n_down_gaps"}`, present only with `LONG_GAP_SIZING` on) and its helpers `_long_stamp(df, rule) -> dict` and `_fallback_stamp(direction) -> dict | None`, `MIN_DOWN_GAPS`, the long branch of `gap_floor_for`; `TradePlanV2.stop_moved_by` (V191-4); `account.compute_position_size(..., gap_floor_pct=)`.
- Produces: `BAND_KEY = "band_sizing_distance"`; `worst_fill_distance(stop_loss, stop_ceiling_pct, direction) -> float` (long `stop × c / (100 − c)`, short `stop × c / (100 + c)`); `band_sizing_distance(trigger, stop_loss, stop_ceiling_pct, direction, gap_sizing) -> float` = `max(worst_fill_distance(...), trigger × p99 / 100)` when `gap_floor_for(direction, gap_sizing)` gives a p99, else the worst-fill distance; `stamp_gap_sizing(plan, df)` stamps every band plan (`stop_moved_by is not None`), long or short, flag on or off, and adds `BAND_KEY`; `size_for(...)` takes the band branch for a stamp carrying `BAND_KEY` and adds `"band_sizing_distance"` to its result; `stop_scope.band_sizing_verdict(plan, sizing_fn=None) -> str | None` (`None` | `"band_size_zero"` | `"risk_sizing"`).

- [ ] **Step 1: Write the failing tests** in `tests/planning/test_band_sizing.py`

```python
"""V191-11: a band plan is sized on the worst fill its stored ceiling accepts
(plus the p99 gap allowance when the stamp has one), shares floored to 0.01,
so shares x distance never exceeds balance x risk_pct / 100."""
import math

import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning import gap_sizing as gs
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from swingbot.core.planning.stop_scope import band_sizing_verdict
from swingbot.core.risk_limits import planned_loss_pct
from tests.market.test_atr_band import _frame

CFG = {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": "risk_pct", "position_pct": 10.0,
       "max_position_pct": 100.0, "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}
BUDGET = 100.0


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(account, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(config, "LONG_GAP_SIZING", False)
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", True)


def _plan(direction, d, *, moved="floor", trigger=100.0):
    bull = direction == "bullish"
    stop = trigger * (1 - d / 100) if bull else trigger * (1 + d / 100)
    return TradePlanV2(
        plan_id="p1", ticker="ZZZ", created_at="2026-10-20", source="confluence", strategy="S/R Confluence",
        horizon_key="4w", direction=direction, entry_type="stop_entry", trigger_price=trigger, entry_price=None,
        expiry_bars=5, stop_loss=stop, tp1=trigger * (1.1 if bull else 0.9), tp1_fraction=0.5, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.0, quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,
        stop_ceiling_pct=d + 0.25, stop_moved_by=moved)


def test_worst_fill_distance_long_and_short():
    assert gs.worst_fill_distance(95.0, 5.25, "bullish") == pytest.approx(95.0 * 5.25 / 94.75)
    assert gs.worst_fill_distance(105.0, 5.25, "bearish") == pytest.approx(105.0 * 5.25 / 105.25)
    fill = 95.0 + gs.worst_fill_distance(95.0, 5.25, "bullish")
    assert planned_loss_pct(fill, 95.0) == pytest.approx(5.25)     # the edge of the headroom


def test_band_sizing_distance_takes_the_gap_allowance_only_from_a_usable_p99():
    worst = gs.worst_fill_distance(95.0, 5.25, "bullish")
    assert gs.band_sizing_distance(100.0, 95.0, 5.25, "bullish", None) == pytest.approx(worst)
    stop_rule = {"rule": gs.RULE_STOP, "down_gap_p99_pct": 9.0, "n_down_gaps": 120}
    assert gs.band_sizing_distance(100.0, 95.0, 5.25, "bullish", stop_rule) == pytest.approx(worst)
    gap_rule = {"rule": gs.RULE_GAP, "down_gap_p99_pct": 9.0, "n_down_gaps": 120}
    assert gs.band_sizing_distance(100.0, 95.0, 5.25, "bullish", gap_rule) == pytest.approx(9.0)


def test_a_band_long_is_stamped_with_the_long_flag_off():
    plan = _plan("bullish", 5.0)
    gs.stamp_gap_sizing(plan, _frame())
    assert plan.gap_sizing == {"rule": gs.RULE_STOP, "down_gap_p99_pct": None, "n_down_gaps": 0,
                               gs.BAND_KEY: pytest.approx(gs.worst_fill_distance(95.0, 5.25, "bullish"))}


def test_a_non_band_long_with_the_flag_off_is_still_unstamped():
    plan = _plan("bullish", 1.5, moved=None)
    gs.stamp_gap_sizing(plan, _frame())
    assert plan.gap_sizing is None


def test_a_stamp_failure_still_stamps_the_band_distance(monkeypatch):
    monkeypatch.setattr(gs, "gap_sizing_stamp", lambda *a, **k: 1 / 0)
    plan = _plan("bearish", 5.0)
    gs.stamp_gap_sizing(plan, None)
    assert plan.gap_sizing[gs.BAND_KEY] == pytest.approx(gs.worst_fill_distance(105.0, 5.25, "bearish"))


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("d", [1.5, 4.0, 9.0])
def test_the_dollar_invariant(direction, d):
    plan = _plan(direction, d)
    gs.stamp_gap_sizing(plan, _frame())
    sizing = gs.size_for_plan(plan)
    distance = plan.gap_sizing[gs.BAND_KEY]
    assert sizing[gs.BAND_KEY] == distance
    assert sizing["shares"] * distance <= BUDGET + 1e-9
    assert sizing["shares"] * 100 == pytest.approx(round(sizing["shares"] * 100))   # 0.01 steps
    assert (sizing["shares"] + 0.01) * distance > BUDGET                            # floored, not over-cut
    assert band_sizing_verdict(plan) is None


def test_shares_floor_where_rounding_would_overshoot():
    stamp = {"rule": gs.RULE_STOP, "down_gap_p99_pct": None, "n_down_gaps": 0, gs.BAND_KEY: 6.0}
    got = gs.size_for(100.0, 95.0, direction="bullish", gap_sizing=stamp)
    assert got["shares"] == 16.66                     # 16.666..., round() would give 16.67 -> $100.02


def test_a_long_with_the_gap_flag_on_sizes_on_the_down_gap():
    stamp = {"rule": gs.RULE_GAP, "down_gap_p99_pct": 9.0, "n_down_gaps": 120}
    plan = _plan("bullish", 4.0)
    plan.gap_sizing = {**stamp, gs.BAND_KEY: gs.band_sizing_distance(100.0, 96.0, 4.25, "bullish", stamp)}
    sizing = gs.size_for_plan(plan)
    assert sizing["shares"] * 9.0 <= BUDGET + 1e-9 and sizing["gap_floor_pct"] == 9.0


def test_a_pre_v191_stamp_sizes_exactly_as_today():
    stamp = {"rule": gs.RULE_GAP, "up_gap_p99_pct": 3.0, "n_up_gaps": 125}
    got = gs.size_for(100.0, 102.0, direction="bearish", gap_sizing=stamp)
    assert got == account.compute_position_size(100.0, 102.0, None, gap_floor_pct=3.0)
    assert gs.BAND_KEY not in got


def test_verdicts(monkeypatch):
    plan = _plan("bullish", 20.0)
    gs.stamp_gap_sizing(plan, _frame())
    monkeypatch.setattr(account, "load_account_config", lambda: {**CFG, "balance": 10.0})
    assert band_sizing_verdict(plan) == "band_size_zero"            # $0.10 / ~$20 -> 0.00 shares
    monkeypatch.setattr(account, "load_account_config", lambda: {**CFG, "sizing_mode": "account_pct"})
    assert band_sizing_verdict(plan) == "risk_sizing"
    assert band_sizing_verdict(plan, sizing_fn=lambda p: 1 / 0) == "risk_sizing"
    over = lambda p: {"mode": "risk_pct", "balance": 10_000.0, "risk_pct": 1.0, "shares": 50.0,
                      gs.BAND_KEY: p.gap_sizing[gs.BAND_KEY]}
    assert band_sizing_verdict(plan, sizing_fn=over) == "risk_sizing"
    assert band_sizing_verdict(_plan("bullish", 1.5, moved=None)) is None   # not a band plan
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_band_sizing.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.planning.gap_sizing' has no attribute 'worst_fill_distance'` / `ImportError: cannot import name 'band_sizing_verdict'`.

- [ ] **Step 3: Implement in `gap_sizing.py`**

Add `import math`. Constants and the two distance functions per Interfaces (`direction == "bullish"` picks the long formula). Then:

- `_band_base_stamp(df, direction) -> dict`: `gap_sizing_stamp(df, direction) or _long_stamp(df, RULE_STOP)` — V191-5's `_long_stamp(df, rule)` covers the long with `LONG_GAP_SIZING` off, for which `gap_sizing_stamp` returns `None`.
- `_empty_band_stamp(direction) -> dict`: `_fallback_stamp(direction) or {"rule": RULE_STOP, "down_gap_p99_pct": None, "n_down_gaps": 0}` (V191-5's `_fallback_stamp` returns `None` only for a long with the switch off).
- `_stamp_band_plan(plan, df) -> None`: `stamp = _band_base_stamp(...)` in `try/except Exception` (fallback `_empty_band_stamp`, `swallowed(log, "scan.gap_sizing.band_stamp", exc, "%s: band sizing stamp failed (%s) -- sized on the worst fill", plan.ticker, exc, level=logging.INFO)`); then `stamp[BAND_KEY] = band_sizing_distance(plan.trigger_price, plan.stop_loss, plan.stop_ceiling_pct, plan.direction, stamp)`; `plan.gap_sizing = stamp`.
- `stamp_gap_sizing(plan, df)`: first statement `if getattr(plan, "stop_moved_by", None) is not None: return _stamp_band_plan(plan, df)`; the rest is unchanged.
- `size_for(...)`: first statement `if (gap_sizing or {}).get(BAND_KEY) is not None: return _band_size(entry, stop_loss, direction, gap_sizing, account_cfg, label)`.
- `_band_size(...)`: `distance = float(gap_sizing[BAND_KEY])`; `result = account.compute_position_size(entry, stop_loss, account_cfg, gap_floor_pct=distance / float(entry) * 100.0)` in `try/except Exception` (`swallowed(..., "scan.gap_sizing.band_size", ...)`, return `None`); `None` passes through. Drop the three `_NO_GAP` keys from `result`. In `risk_pct` mode: `budget = balance × risk_pct / 100`, `shares = math.floor(min(result["shares"], budget / distance) * 100 + 1e-9) / 100`, and re-derive `risk_amount = round(shares × |entry − stop|, 2)` and `position_value = round(shares × entry, 2)`. Set `result[BAND_KEY] = distance` and merge `_band_gap_fields(entry, stop_loss, direction, gap_sizing, result["shares"], distance)`.
- `_band_gap_fields(...) -> dict`: `{}` for a `RULE_STOP` stamp; `dict(_NO_GAP)` for a gap rule without a usable p99; otherwise `{"gap_risk_amount": round(shares × account._sizing_distance(entry, |entry − stop|, floor), 2), "gap_sized": entry × floor / 100 >= distance − 1e-9, "gap_floor_pct": floor}` with `floor = gap_floor_for(direction, gap_sizing)`.

Update the module docstring: a band plan (v191) is stamped long or short and sized on its stamped worst-fill distance; a stamp without `band_sizing_distance` sizes exactly as v183.

- [ ] **Step 4: Implement `band_sizing_verdict` in `stop_scope.py`**

`None` when `getattr(plan, "stop_moved_by", None) is None`. `sizing_fn` defaults to `gap_sizing.size_for_plan` (imported inside the function: no import cycle). `sizing = sizing_fn(plan)` inside `try/except Exception` → `"risk_sizing"`. `"risk_sizing"` when `sizing` is falsy, `sizing.get("mode") != "risk_pct"` or `BAND_KEY not in sizing`. `budget = balance × risk_pct / 100`, `shares = float(sizing["shares"] or 0)`; `shares <= 0` → `atr_band.REASON_SIZE_ZERO`; `shares × sizing[BAND_KEY] > budget + 1e-9` → `"risk_sizing"`; else `None`.

- [ ] **Step 5: Run the tests and v183's sizing tests**

```bash
python scripts/dev/testrun.py file tests/planning/test_band_sizing.py
python scripts/dev/testrun.py file tests/planning/test_gap_sizing.py
python scripts/dev/testrun.py file tests/planning/test_gap_sizing_long.py
python scripts/dev/testrun.py file tests/scanning/test_gap_sizing_resize_sites.py
python scripts/dev/complexity_gate.py
```
Expected: `0 failed`; v183's pinned long-plan key list still holds (a non-band long gains no key); complexity gate passes (`size_for` gains one `if`).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/gap_sizing.py swingbot/core/planning/stop_scope.py tests/planning/test_band_sizing.py
git commit -m "feat(planning): v191 band sizing -- worst-fill distance plus p99 allowance, shares floored to 0.01, band_sizing_verdict

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V191-12: `attach_plan_v2` wiring: dollar check, band reasons, heat/fill/reload pins

**Model:** opus — the live gate between a built plan and a posted alert; a mis-ordered stamp or a skipped check issues a plan that can lose more than the preset maximum.

**Files:**
- Modify: `swingbot/core/scanning/analyze.py` (`_no_plan_reason` ~415, `attach_plan_v2` ~487-560; new `_sizing_reject_reason`)
- Test: `tests/scanning/test_attach_atr_band.py` (create), `tests/planning/test_plan_manager_atr_band.py` (create)

**Interfaces:**
- Consumes: `band_no_plan_reason` (V191-8); `stamp_gap_sizing` band path, `BAND_KEY`, `worst_fill_distance`, `size_for_plan`, `stop_scope.band_sizing_verdict` (V191-11); `_horizon_scenarios` band admission (V191-10); `_reject_plan`, `_stamp_gap_sizing_live`, `scan_run._skip_rejected_plan` (unchanged); `edge.heat.trade_risk_pct`.
- Produces: `_sizing_reject_reason(plan, df, now) -> str | None` — for a band plan (`stop_moved_by is not None`): `_stamp_gap_sizing_live(plan, df, now)` first, then `band_sizing_verdict(plan)`; otherwise today's rule, `"risk_sizing"` when `plan.stop_ceiling_pct is not None and not risk_sizing_ok(plan)`, else `None`. `_no_plan_reason` returns `band_no_plan_reason(scenario, level_map)` when that is not `None`, then today's two reasons.

- [ ] **Step 1: Write the failing tests**

`tests/scanning/test_attach_atr_band.py`:

```python
"""V191-12: a band plan is stamped and dollar-checked before it is issued;
every band reason reaches the existing 'plan rejected (' line."""
import logging
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.edge.heat import trade_risk_pct
from swingbot.core.planning import account
from swingbot.core.planning import gap_sizing as gs
from swingbot.core.scanning import analyze, engine, scan_run
from tests.helpers import make_ohlcv

CFG = {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": "risk_pct", "position_pct": 10.0,
       "max_position_pct": 100.0, "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for name, value in [("PLAN_ENGINE_V2", "on"), ("CLAMP_STOP_TO_HARD_CAP", True),
                        ("MIN_RISK_REWARD_RATIO", 1.5), ("MAX_RISK_REWARD_RATIO", 2.5),
                        ("CONFLUENCE_ATR_STOP_FLOOR", 1.0), ("CONFLUENCE_ATR_TARGET_MODE", "rechoose"),
                        ("LONG_GAP_SIZING", False), ("SHORT_GAP_SIZING", True)]:
        monkeypatch.setattr(config, name, value)
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    for mod in (account, analyze):
        monkeypatch.setattr(mod, "load_account_config", lambda: dict(CFG))


def _attach(stop, target, atr=4.0, direction="bullish"):
    scenario = SimpleNamespace(direction=direction, entry=100.0, stop_loss=stop, take_profit=target,
                               target_sources=["EMA21"], stop_sources=["Rolling support"],
                               atr14_pct=atr, stop_distance_pct=abs(100.0 - stop))
    item = SimpleNamespace(plan_v2=None, plan=scenario, previous_confirmed=None,
                           result=SimpleNamespace(ticker="AAPL", horizon_key="4w", trend=direction,
                                                  state_key="k", state_value="v"))
    engine.attach_plan_v2(item, scenario, make_ohlcv([100.0] * 60), "AAPL", "4w", level_map=None)
    return item


def test_a_band_plan_is_issued_with_its_stamp_and_a_dollar_safe_size():
    plan = _attach(99.0, 108.0).plan_v2
    assert (plan.stop_loss, plan.stop_moved_by) == (pytest.approx(96.0), "floor")
    assert plan.gap_sizing[gs.BAND_KEY] == pytest.approx(gs.worst_fill_distance(96.0, 4.25, "bullish"))
    shares = gs.size_for_plan(plan)["shares"]
    assert shares * plan.gap_sizing[gs.BAND_KEY] <= 100.0 + 1e-9
    # heat counts |entry - stop| x shares: a wider stop with fewer shares buys no extra heat
    assert trade_risk_pct({"entry": 100.0, "stop_loss": plan.stop_loss, "shares": shares}, 10_000.0) <= 1.0


def test_the_band_plan_is_stamped_exactly_once(monkeypatch):
    calls = []
    real = analyze.stamp_gap_sizing
    monkeypatch.setattr(analyze, "stamp_gap_sizing", lambda p, df: calls.append(1) or real(p, df))
    assert _attach(99.0, 108.0).plan_v2 is not None
    assert _attach(96.5, 108.0, atr=None).plan_v2 is not None      # today's plan, stamped as today
    assert calls == [1, 1]


@pytest.mark.parametrize("cfg,reason", [({"balance": 10.0}, "band_size_zero"),
                                        ({"sizing_mode": "account_pct"}, "risk_sizing")])
def test_a_band_plan_that_cannot_fit_the_budget_is_refused_and_logged(monkeypatch, caplog, cfg, reason):
    for mod in (account, analyze):
        monkeypatch.setattr(mod, "load_account_config", lambda: {**CFG, **cfg})
    item = _attach(80.0, 160.0, atr=10.0)                            # d 20% untouched in [10, 20]
    assert item.plan_v2 is None and item.plan_v2_rejected == reason
    with caplog.at_level(logging.INFO, logger=scan_run.log.name):
        scan_run._skip_rejected_plan(item, require_confirmation=False)
    assert f"plan rejected ({reason}" in caplog.text


@pytest.mark.parametrize("mode,target,reason", [("rechoose", 104.0, "band_no_target"),
                                                ("keep", 106.0, "band_rr_drop")])
def test_band_no_plan_reasons(monkeypatch, mode, target, reason):
    monkeypatch.setattr(config, "CONFLUENCE_ATR_TARGET_MODE", mode)
    stop, atr = (99.0, 4.0) if mode == "rechoose" else (96.5, 2.5)
    item = _attach(stop, target, atr=atr)
    assert item.plan_v2 is None and item.plan_v2_rejected == reason


def test_a_pre_band_plan_still_uses_risk_sizing_ok(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_ATR_STOP_FLOOR", 0.0)
    monkeypatch.setattr(analyze, "risk_sizing_ok", lambda plan: pytest.fail("consulted"))
    assert _attach(96.5, 108.0).plan_v2.stop_loss == pytest.approx(98.25)
```

`tests/planning/test_plan_manager_atr_band.py`:

```python
"""V191-12: a pending band plan's stop, ceiling and sizing input are fixed at
creation -- a knob flip changes none of them; a fill inside the stored
headroom fills, one past it cancels; the edge-of-headroom loss fits the budget."""
import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning import gap_sizing as gs
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_pending import _mgr, _pending

STOP, CEILING = 100.8, 4.25                       # 4.0% under the 105.0 trigger
STAMP = {"rule": gs.RULE_STOP, "down_gap_p99_pct": None, "n_down_gaps": 0,
         gs.BAND_KEY: gs.worst_fill_distance(STOP, CEILING, "bullish")}
CFG = {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": "risk_pct", "position_pct": 10.0,
       "max_position_pct": 100.0, "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(account, "load_account_config", lambda: dict(CFG))


def _band_plan():
    return _pending(source="confluence", strategy="S/R Confluence", stop_loss=STOP,
                    stop_ceiling_pct=CEILING, stop_moved_by="floor", gap_sizing=dict(STAMP))


def _poll(tmp_path, price):
    store, mgr = _mgr(tmp_path, FakePriceFeed([("AAPL", price)]))
    store.add(_band_plan())
    return store, mgr.poll()


def test_a_fill_inside_the_stored_headroom_fills(tmp_path):
    store, events = _poll(tmp_path, 105.2)                  # 4.18% at the fill
    assert [e.transition for e in events] == ["filled"]


def test_a_fill_past_the_stored_headroom_cancels(tmp_path):
    _, events = _poll(tmp_path, 105.4)                      # 4.36% at the fill
    assert [e.transition for e in events] == ["cancelled_risk_cap"]
    assert events[0].detail["max_planned_loss_pct"] == pytest.approx(CEILING)


def test_a_knob_flip_changes_nothing_on_a_pending_band_plan(tmp_path, monkeypatch):
    before = gs.size_for_plan(_band_plan())
    monkeypatch.setattr(config, "CONFLUENCE_ATR_STOP_FLOOR", 0.0)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", True)
    store, events = _poll(tmp_path, 105.2)
    plan = store.get("p1")
    assert (plan.stop_loss, plan.stop_ceiling_pct, plan.gap_sizing) == (STOP, CEILING, STAMP)
    assert gs.size_for_plan(plan, entry=105.0)["shares"] == before["shares"]


def test_an_account_change_resizes_on_the_same_stamped_distance(monkeypatch):
    monkeypatch.setattr(account, "load_account_config", lambda: {**CFG, "balance": 20_000.0})
    sizing = gs.size_for_plan(_band_plan())
    assert sizing[gs.BAND_KEY] == STAMP[gs.BAND_KEY]
    assert sizing["shares"] * STAMP[gs.BAND_KEY] <= 200.0 + 1e-9


def test_the_loss_at_the_edge_of_the_headroom_fits_the_budget():
    shares = gs.size_for_plan(_band_plan())["shares"]
    worst_fill = STOP + STAMP[gs.BAND_KEY]
    assert shares * (worst_fill - STOP) <= 100.0 + 1e-9
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_attach_atr_band.py` and `... file tests/planning/test_plan_manager_atr_band.py`
Expected: the attach file fails (`band_size_zero` plans are issued; band reasons read `no_qualifying_target`; the stamp is computed after the check); the plan-manager file passes already where it only reads V191-11 behaviour — that is expected, it pins the fill and reload contract.

- [ ] **Step 3: Wire `analyze.py`**

- Import `band_no_plan_reason` from `swingbot.core.planning.builders` (next to `confluence_stop_dropped`) and `band_sizing_verdict` from `swingbot.core.planning.stop_scope` (next to `plan_stop_ceiling, risk_sizing_ok`).
- `_no_plan_reason`: first `band = band_no_plan_reason(scenario, level_map)`; `if band is not None: return band`; then today's body. Docstring names the two band reasons.
- `_sizing_reject_reason(plan, df, now)`: per Interfaces. Docstring: a band plan's stamp is set before its dollar check (the check sizes on the stamped distance); every other plan keeps v139's rule.
- `attach_plan_v2`: replace the `if plan.stop_ceiling_pct is not None and not risk_sizing_ok(plan):` block with `reason = _sizing_reject_reason(plan, df, now)` / `if reason is not None: _reject_plan(item, reason, ticker, horizon_key, plan=plan); return` (keep v139's comment, add one v191 line). Replace the later `_stamp_gap_sizing_live(plan, df, now)` with `if plan.stop_moved_by is None: _stamp_gap_sizing_live(plan, df, now)` — a band plan was stamped in the check. The `risk_cap` block is untouched: a band plan passes it at its own stored ceiling. The heat and cluster call sites in `scan_run.py`/`short_run.py` are **not** edited.

- [ ] **Step 4: Run the tests, the v139 attach tests, the heat AST pin and the goldens**

```bash
python scripts/dev/testrun.py file tests/scanning/test_attach_atr_band.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_atr_band.py
python scripts/dev/testrun.py file tests/scanning/test_attach_confluence_stop_geometry.py
python scripts/dev/testrun.py file tests/scanning/test_gap_sizing_cap_invariants.py
python scripts/dev/testrun.py file tests/planning/test_v191_plan_golden.py
python scripts/dev/complexity_gate.py
```
Expected: `0 failed`; `test_candidate_heat_and_cluster_inputs_are_the_configured_risk_pct` passes unchanged; `attach_plan_v2` stays at C 12 (one `if ... and ...` became two plain `if`s).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/analyze.py tests/scanning/test_attach_atr_band.py tests/planning/test_plan_manager_atr_band.py
git commit -m "feat(scan): v191 attach_plan_v2 stamps a band plan before its dollar check; band reasons reach 'plan rejected ('

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 7 — Alert

### Task V191-13: Alert band line

**Model:** sonnet — one pure text function wired at the existing `gap_risk_line` render sites, following v183's pattern.

**Files:**
- Create: `swingbot/core/presentation/band_stop.py`
- Modify: `swingbot/core/scanning/execution_embeds.py` (`ticket_gap_line` / `_with_gap_line` ~91-103), `swingbot/core/scanning/alert_embeds.py` (`_gap_risk_fields` ~143), `swingbot/core/infra/notifier.py` (`_gap_risk_lines` ~129), `swingbot/admin/api_v1/trades.py` (`_plan_detail`, `_legacy_detail`)
- Test: `tests/presentation/test_band_stop_line.py` (create)

**Interfaces:**
- Consumes: `TradePlanV2.stop_moved_by` (V191-4); band plans from V191-12; `HORIZONS[...]["label"]`; `planned_loss_pct`.
- Produces: `band_stop_line(plan, *, currency: str = "$") -> str | None` — `plan` is a `TradePlanV2` or a plan-doc `dict` (read through one `_field(plan, name)` helper); `None` when `plan` is `None` or `stop_moved_by` is `None`. `execution_embeds.ticket_band_line(plan) -> str | None` (the configured currency). Plan-detail API key `"band_stop_line"` (`None` on legacy rows).

Copy (fixed here): `ATR-band stop {cur}{stop} ({dist:.2f}% from entry, {why}) · TP1 {rr:.2f}R · {horizon label} · expires after {n} bars`; `{stop}` with 2 decimals (`,` separators), 4 below a $1 trigger; `why` is `moved out to the ATR floor` / `pulled in to the 2× ATR ceiling` / `at the level`; `rr = |tp1 − trigger| / |trigger − stop|`, the real R:R against the band stop.

- [ ] **Step 1: Write the failing tests** in `tests/presentation/test_band_stop_line.py`

```python
"""V191-13: a band plan's alert restates the rounded stop, its distance, TP1's
real R:R against it, the horizon and the expiry -- on every channel."""
import pytest

from swingbot import config
from swingbot.admin.api_v1 import trades
from swingbot.core.infra import notifier
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.core.presentation.band_stop import band_stop_line
from swingbot.core.presentation.instructions import Instruction
from swingbot.core.scanning import alert_embeds, execution_embeds
from tests.planning.test_plan_engine_model import _plan

FLOOR_LINE = ("ATR-band stop $96.00 (4.00% from entry, moved out to the ATR floor) · "
              "TP1 2.00R · 4-week swing · expires after 5 bars")


def _band(**kw):
    return _plan(source="confluence", stop_loss=96.0, tp1=108.0, stop_ceiling_pct=4.25,
                 stop_moved_by="floor", **kw)


def test_the_floor_line():
    assert band_stop_line(_band()) == FLOOR_LINE


@pytest.mark.parametrize("moved,why", [("ceiling", "pulled in to the 2× ATR ceiling"),
                                       ("untouched", "at the level")])
def test_the_other_reasons(moved, why):
    assert f"(4.00% from entry, {why})" in band_stop_line(_band(stop_moved_by=moved))


def test_a_short_and_a_sub_dollar_plan():
    short = _plan(direction="bearish", stop_loss=104.0, tp1=92.0, stop_moved_by="floor")
    assert band_stop_line(short).startswith("ATR-band stop $104.00 (4.00% from entry")
    penny = _plan(trigger_price=0.85, stop_loss=0.8075, tp1=0.94, stop_moved_by="floor")
    assert band_stop_line(penny, currency="€").startswith("ATR-band stop €0.8075 (5.00% from entry")


def test_no_line_without_a_band():
    assert band_stop_line(None) is None
    assert band_stop_line(_plan()) is None                      # stop_moved_by None


def test_a_plan_doc_dict_reads_the_same():
    assert band_stop_line(plan_to_dict(_band())) == FLOOR_LINE


def test_every_channel_carries_it(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(execution_embeds, "ticket_gap_line", lambda plan: None)
    monkeypatch.setattr(alert_embeds, "ticket_gap_line", lambda plan: None)
    item = type("Item", (), {"plan_v2": _band()})()
    assert execution_embeds.ticket_band_line(_band()) == FLOOR_LINE
    assert FLOOR_LINE in notifier._gap_risk_lines(item)
    assert (alert_embeds.BAND_STOP_FIELD, FLOOR_LINE, False) in alert_embeds._gap_risk_fields(item)
    ticket = execution_embeds._with_gap_line(Instruction("PLACE", "AAPL", "bullish", "Buy stop"), _band())
    assert ticket.lines == (FLOOR_LINE,)
    assert trades._band_stop_detail(plan_to_dict(_band())) == FLOOR_LINE
    assert trades._band_stop_detail({}) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/presentation/test_band_stop_line.py`
Expected: collection error, `ModuleNotFoundError: No module named 'swingbot.core.presentation.band_stop'`.

- [ ] **Step 3: Implement**

- `swingbot/core/presentation/band_stop.py`: module docstring (the one wording of the v191 band line; pure text, imports nothing from `scanning`); `_WHY = {"floor": ..., "ceiling": ..., "untouched": ...}` per the copy above; `_field(plan, name)` = `plan.get(name)` for a `Mapping`, else `getattr(plan, name, None)`; `band_stop_line` builds the copy from `trigger_price` (falling back to `entry_price`), `stop_loss`, `tp1`, `horizon_key` (label from `HORIZONS`, the key itself when unknown), `expiry_bars`, `stop_moved_by`.
- `execution_embeds.py`: `ticket_band_line(plan)` returns `None` for `None`, else `band_stop_line(plan, currency=config.CURRENCY_SYMBOL)`; `_with_gap_line` appends every non-`None` of `(ticket_band_line(plan), ticket_gap_line(plan))`, band line first.
- `alert_embeds.py`: import `ticket_band_line` beside `ticket_gap_line`; `BAND_STOP_FIELD = "Stop band"`; `_gap_risk_fields(item)` returns the band field `(BAND_STOP_FIELD, line, False)` before the gap field when `ticket_band_line(_v2_plan(item))` is not `None`.
- `notifier.py`: `_gap_risk_lines(item)` returns `[band, gap]` filtered of `None`, band first.
- `trades.py`: `_band_stop_detail(plan: dict) -> str | None` = `band_stop_line(plan or {}, currency=config.CURRENCY_SYMBOL)`; `_plan_detail` adds `"band_stop_line": _band_stop_detail(plan)` after `"gap_sizing"`; `_legacy_detail` adds `"band_stop_line": None` at the same place (one detail shape). The SPA does not render the key yet (no frontend task in this plan).

- [ ] **Step 4: Run the tests and v183's line tests**

```bash
python scripts/dev/testrun.py file tests/presentation/test_band_stop_line.py
python scripts/dev/testrun.py file tests/presentation/test_gap_risk_line.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_detail.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_risk_notice.py
python scripts/dev/complexity_gate.py
```
Expected: `0 failed`; a non-band plan's alert text is unchanged on every channel.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/band_stop.py swingbot/core/scanning/execution_embeds.py swingbot/core/scanning/alert_embeds.py swingbot/core/infra/notifier.py swingbot/admin/api_v1/trades.py tests/presentation/test_band_stop_line.py
git commit -m "feat(alerts): v191 band stop line -- rounded stop, distance, real TP1 R:R, horizon and expiry on every channel

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
