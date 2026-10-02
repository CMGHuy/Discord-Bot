# Causal structure and volume-in-context entry features — implementation plan

> **For agentic workers:** Use the repo's `task-brief` and one-task implement/review cycle. Steps use `- [ ]` for tracking; read the spec with the task.

**Goal:** Stamp causal swing-structure and volume-in-context features onto every entry snapshot (live and replay), fill the two dead `swing_*_atr` keys, and ship a descriptive TRAIN-only / live-monitoring bucket report.
**Architecture:** One pure module `swingbot/core/market/structure.py` owns the confirmed-pivot contract (`k = 3`, the only place the confirmation lag lives) and the feature dict. `edge/context.py:entry_context` merges `structure_features(df, direction)`, so live (`planning/params.py:stamp_entry_context`) and replay (`backtesting/backtest.py`, `backtest_scenarios.py`) gain the keys with no new wiring. The snapshot already rides in the trades table's `doc` JSONB, so storage needs no revision.
**Tech Stack:** Python 3.11, pandas/numpy, existing `market.indicators.atr`, existing arm engines, pytest (real-Postgres `db_conn` fixture for the storage task).
**Spec:** `docs/superpowers/specs/2026-10-02-v121-structure-volume-context-design.md`
**Bump:** bot patch
**Edge:** none (integrity)
**Progress:** planning complete; implementation not started. Amended 2026-10-02 (before any implementation): four leg-shape keys added to V121-2 (spec § Features, "Leg-shape keys"); code and expected values prototyped against the fixtures, 35 tests passing.

## Global constraints

- Measurement only: no gate, score weight, exit rule, alert text, chart or plan change. v122/v123 consume `structure.py` later and must not start until this merges.
- Pivot contract (load-bearing): bar `i` is a swing high when `High[i]` is strictly greater than the `k` highs before it and `>=` the `k` highs after it (mirror for lows), `k = 3`. A pivot at `i` is knowable only from bar `i + k`; at decision bar `t` only pivots with `i <= t - k` exist. `k` is frozen at 3, not a search knob. Do not reuse `indicators.zigzag_pivots` or the private `signals._swing_highs`.
- Frozen descriptive constants: absorption volume multiple `1.5` (vs mean of the 20 *prior* bars), absorption range `<= 0.6` ATR14, trend windows `10`/`50`, progress lookback `10`, impulse-decay minimum of `2` bars per third. Changing one is a new spec.
- Frames shorter than 60 bars return `None` for every new key and never raise.
- Every pre-existing `entry_context` key keeps its value byte-identical, except the two dead keys `swing_high_atr`/`swing_low_atr`, which the spec fills on purpose.
- No backfill of historical trade records. No read-time upcasting: a missing key on an old record reads `None` through `dict.get`, which is the existing default.
- The report is descriptive. `--source replay` reads TRAIN `2020-01-01..2023-12-31` only and refuses any other window; `--source live` is monitoring only, says it overlaps the 2026 holdout (v104), and prints no inferential statistic. It must not be used to choose v122/v123 grid values.
- Invoke `no-lookahead` on `structure.py` and `context.py` (Task V121-3) and `backtest-gate` before any real replay run of the report. Read `architecture.md`, `known-traps.md`, `code-complexity.md`, `schema-evolution.md` before editing.
- Every function written or changed stays below CC 15 (`python -m radon cc -s -n C <files>`). `entry_context` is already C (17): add **no branch** to it — the merge is one unconditional statement.
- Each task uses its narrow test file and a focused commit. The full Python suite runs once, in the final task.

## File map and interfaces

| File | Responsibility |
|---|---|
| `swingbot/core/market/structure.py` (new) | `confirmed_pivots`, leg/absorption helpers, `structure_features(df, direction) -> dict`, `STRUCTURE_KEYS`. Pure, causal, reads only the frame it is given. |
| `swingbot/core/edge/context.py` | Append the fourteen new keys to `FEATURE_KEYS`; merge `structure_features` into `entry_context`. |
| `tests/market/structure_fixtures.py` (new) | Shared hand-built frames (zigzag trends, mirrors, pullback, wavy). |
| `tests/market/test_structure_pivots.py`, `tests/market/test_structure_features.py` (new) | Pivot truncation/lag/tie tests; per-feature known answers and bearish mirrors. |
| `tests/edge/test_edge_context_structure.py` (new) | Witness of pre-existing keys, new-key merge, short-frame `None`, stamp path. |
| `tests/db/test_entry_context_doc.py` (new) | `entry_context` is a `doc` JSONB payload; new keys round-trip; old records read `None`. |
| `scripts/reports/volume_context_report.py` (new), `tests/scripts/test_volume_context_report.py` (new) | Descriptive bucket report and its refusal/bucketing tests. |
| `.gitignore` | `data/v121_*.json` (the TRAIN quintile-edge file the report writes). |

Verified anchors (HEAD `c5af1b92`): `edge/context.py:11` `FEATURE_KEYS`, `:29` `entry_context(df, *, direction, horizon_key, stop, target, asof=None)`; `market/indicators.py:62` `atr(df, period=14)` (Wilder EWM, causal); `planning/params.py:190` `stamp_entry_context(plan, df, asof)` (swallows exceptions into `{}`); callers `scanning/strategy_pass.py:70`, `scanning/analyze.py:390`, `backtesting/backtest_scenarios.py:155`; direct replay calls `backtesting/backtest.py:417`, `:495` (not wrapped in try — a raise would crash a backtest); `tracking/performance.py:605` stores `"entry_context"` on the record, `:468` `_db_record`, `:475` `_json_record`; `db/schema.py:70` `trades` has no `entry_context` column (lives in `doc`); `analytics/journal.py:177` copies it; `arms/confluence_engine.py` `SKIPPED`, `replay_scenarios(...)` yields `(index, plan)` with `plan.entry_context` stamped; `arms/strategy_engine.py` `StrategyEngine().iter_trades(ticker, df, strategy, horizon_key, signal_window, params)` yields `(date, plan, result)` and does **not** stamp `entry_context`; `arms/windows.py` `ALL_HORIZONS`; `scripts/backtest/measure_arms.py` `cached_universe()`, `load_frame(ticker)`; `swingbot/scan_params.py` `ScanParams.from_config()`; `analytics/scope.py:78` `closed_only`; `analytics/metrics.py:172` `r_multiple(trade)`; `tracking/performance.py:1108` `TradeLog().get_trades(status=None, limit=None)`; `backtesting/acceptance.py` `win_rate`, `expectancy_r`, `DECIDED`.

## Review focus

1. Zero or NaN volume (index proxies, thin ETFs) must give `None`/`False`, never raise or divide by zero — Task V121-2 tests zero-volume and NaN-bar frames.
2. Equal highs (a flat double top) must label only the first bar a pivot, per "strictly greater before, `>=` after" — Task V121-1 tests the tie.
3. A frame with no range (High == Low == Close, ATR 0) must give `None` for every ATR-scaled key and no structure — Task V121-2 tests the flat frame.
4. A raise inside `structure_features` would blank the whole live snapshot (via `stamp_entry_context`'s `except`) and crash replay (`backtest.py` calls `entry_context` bare) — Task V121-2's NaN-bar test and Task V121-3's stamp test pin "never raises".
5. Old live records carry no new keys; the report must bucket them as `"None"`, not KeyError — Task V121-5 tests it.
6. `pullback_legs` is a pure extraction from `pullback_vol_ratio`: every pre-existing `pullback_vol_ratio` test must still pass unchanged, and v122 depends on its signature — Task V121-2 keeps both.

## Parallelisation

- **Group A (parallel):** V121-1 and V121-4 — disjoint files (`market/structure.py` + `tests/market/*` vs `tests/db/test_entry_context_doc.py`); V121-4 consumes only the existing `FEATURE_KEYS` and literal key names, no symbol V121-1 introduces.
- **Sequential:** V121-2 after V121-1 (extends `structure.py`, consumes `confirmed_pivots`, `pivot_confirmations`, `_num`, and the shared fixtures file). V121-3 after V121-2 (consumes `structure_features`, `STRUCTURE_KEYS`). V121-5 after V121-3 (buckets the keys `entry_context` now emits; its strategy-row stamping relies on the merged snapshot). V121-6 last (the single full-suite run).

# Phase 1 — Causal pivots and features

### Task V121-1: Confirmed fractal pivots

**Files:** Create `swingbot/core/market/structure.py`, `tests/market/structure_fixtures.py`, `tests/market/test_structure_pivots.py`.

**Interfaces:**
- Produces: `PIVOT_K = 3`; `PIVOT_COLUMNS = ("last_sh_pos", "last_sh", "prior_sh_pos", "prior_sh", "last_sl_pos", "last_sl", "prior_sl_pos", "prior_sl")`; `pivot_confirmations(df, k=PIVOT_K) -> tuple[np.ndarray, np.ndarray]` (boolean arrays indexed by **confirmation** bar `j`: True when bar `j - k` is a swing high / low); `confirmed_pivots(df, k=PIVOT_K) -> pd.DataFrame` with `PIVOT_COLUMNS`, positional indices as floats, NaN where fewer pivots exist; `_num(value) -> float | None` (finite, rounded to 6). Positions are positional (`0..len-1`) so they are identical on a prefix.
- Fixtures produced: `UP`, `MIXED`, `BROKEN`, `zigzag(points, leg=8)`, `frame(points, *, mirror=False)`, `pullback_frame()`, `wavy_frame(n=300)`, `slowing_pullback_frame()`, `short_impulse_frame()` (the last two for V121-2's leg-shape keys).

- [ ] **Step 1: Write the shared fixtures.**

```python
# tests/market/structure_fixtures.py
"""Hand-built OHLCV frames with known swing structure (v121)."""
import numpy as np

from tests.conftest import make_ohlcv

UP = [100, 110, 105, 115, 110, 120, 115, 125, 120, 130, 124, 127]   # HH/HL, ends mid-leg up
MIXED = UP + [125, 126]          # last SH 127 < 130 but last SL 125 > 124
BROKEN = UP + [118]              # close falls through the last confirmed SL (124)


def zigzag(points, leg=8):
    """Linear legs between turning points; each turning point is a unique extreme."""
    closes = [float(points[0])]
    for a, b in zip(points, points[1:]):
        closes.extend(np.linspace(a, b, leg + 1)[1:].tolist())
    return np.array(closes)


def frame(points, *, mirror=False):
    pts = [250 - p for p in points] if mirror else points
    return make_ohlcv(zigzag(pts), spread_pct=1.0)


def pullback_frame():
    """Swing low at bar 48, impulse to a swing high at bar 58 on 2M volume,
    then a 3-bar pullback (the minimum: the SH is confirmed at t-3) on 1M."""
    pre = zigzag([100, 112, 100, 110, 100], leg=12)      # 49 bars, low at 48
    impulse = np.linspace(100, 120, 11)[1:]             # bars 49..58
    pullback = np.array([118.0, 116.0, 114.0])          # bars 59..61
    closes = np.concatenate([pre, impulse, pullback])
    volumes = np.full(len(closes), 1_000_000.0)
    volumes[48:59] = 2_000_000.0                        # impulse leg SL0..SH inclusive
    return make_ohlcv(closes, spread_pct=1.0, volumes=volumes)


def wavy_frame(n=300):
    i = np.arange(n)
    closes = 100 + 0.05 * i + 6 * np.sin(i / 7.0) + 2 * np.sin(i / 2.3)
    volumes = 1_000_000 + 300_000 * np.sin(i / 3.1) + 5_000 * i
    return make_ohlcv(closes, spread_pct=1.5, volumes=volumes)


def _leg_frame(impulse_steps, pre_leg=12):
    """A swing low (bar 48 at pre_leg=12), an impulse built from `impulse_steps`
    close-to-close rises, then the same 3-bar pullback as `pullback_frame`."""
    pre = zigzag([100, 112, 100, 110, 100], leg=pre_leg)  # 4*pre_leg + 1 bars, low last
    impulse = 100 + np.cumsum(impulse_steps)
    pullback = impulse[-1] - np.array([2.0, 4.0, 6.0])
    return make_ohlcv(np.concatenate([pre, impulse, pullback]), spread_pct=1.0)


def slowing_pullback_frame():
    """Ten-bar impulse whose steps shrink 4 -> 0.5: momentum fading into the high."""
    return _leg_frame([4.0, 4.0, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.5])


def short_impulse_frame():
    """Four-bar impulse (base at 56, high at 60): a 5-bar leg is too short for a
    range decay (< 2 bars per third). pre_leg=14 keeps the frame >= 60 bars."""
    return _leg_frame([5.0, 5.0, 5.0, 5.0], pre_leg=14)
```

- [ ] **Step 2: Write the failing pivot tests.**

```python
# tests/market/test_structure_pivots.py
import numpy as np
import pandas as pd

from swingbot.core.market import structure as st
from tests.conftest import make_ohlcv
from tests.market.structure_fixtures import UP, frame, wavy_frame


def _same(a, b):
    return all((pd.isna(x) and pd.isna(y)) or x == y for x, y in zip(a, b))


def test_pivots_are_truncation_stable_on_every_cut():
    df = wavy_frame()
    full = st.confirmed_pivots(df)
    for t in range(len(df)):
        assert _same(st.confirmed_pivots(df.iloc[:t + 1]).iloc[-1], full.iloc[t]), t


def test_a_pivot_appears_exactly_k_bars_after_it_forms():
    pivots = st.confirmed_pivots(frame(UP))
    assert pivots["last_sh_pos"].iloc[8:11].isna().all()   # peak at bar 8 not yet known
    assert pivots["last_sh_pos"].iloc[11] == 8              # known from bar 8 + k
    assert pivots["last_sl_pos"].iloc[16:19].isna().all()
    assert pivots["last_sl_pos"].iloc[19] == 16


def test_no_pivot_is_ever_newer_than_t_minus_k():
    pivots = st.confirmed_pivots(wavy_frame())
    rows = np.arange(len(pivots))
    for column in ("last_sh_pos", "prior_sh_pos", "last_sl_pos", "prior_sl_pos"):
        known = pivots[column].notna().to_numpy()
        assert (pivots[column].to_numpy()[known] <= rows[known] - st.PIVOT_K).all(), column


def test_prior_is_the_pivot_before_last():
    pivots = st.confirmed_pivots(frame(UP)).iloc[-1]
    assert pivots["prior_sh_pos"] < pivots["last_sh_pos"]
    assert pivots["prior_sh"] < pivots["last_sh"]             # higher highs
    assert pivots["prior_sl"] < pivots["last_sl"]             # higher lows


def test_equal_highs_label_the_first_bar_only():
    closes = np.array([100, 101, 102, 103, 105, 105, 103, 102, 101, 100, 99, 98], dtype=float)
    pivots = st.confirmed_pivots(make_ohlcv(closes, spread_pct=1.0))
    assert pivots["last_sh_pos"].iloc[:7].isna().all()
    assert pivots["last_sh_pos"].iloc[7:].tolist() == [4.0] * 5


def test_columns_and_index_match_the_contract():
    df = frame(UP)
    pivots = st.confirmed_pivots(df)
    assert tuple(pivots.columns) == st.PIVOT_COLUMNS
    assert pivots.index.equals(df.index)
    assert st.PIVOT_K == 3
```

- [ ] **Step 3:** Run `python scripts/dev/testrun.py file tests/market/test_structure_pivots.py`; expect FAIL (`ImportError: cannot import name 'structure'`).

- [ ] **Step 4: Implement the pivot half of the module.**

```python
# swingbot/core/market/structure.py
"""Causal swing structure and volume-in-context features (v121).

The pivot contract: bar ``i`` is a swing high when ``High[i]`` is strictly
greater than the ``k`` highs before it and >= the ``k`` highs after it
(mirror for lows). A pivot at ``i`` is knowable only from bar ``i + k``; at
decision bar ``t`` only pivots with ``i <= t - k`` exist. Every consumer
(v121 snapshot, v122 gate, v123 exit) calls ``confirmed_pivots`` -- this is
the single place the confirmation lag lives. ``k`` is frozen at 3.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

PIVOT_K = 3   # frozen; not a search knob
PIVOT_COLUMNS = ("last_sh_pos", "last_sh", "prior_sh_pos", "prior_sh",
                 "last_sl_pos", "last_sl", "prior_sl_pos", "prior_sl")


def _num(value) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return round(value, 6) if math.isfinite(value) else None


def pivot_confirmations(df: pd.DataFrame, k: int = PIVOT_K) -> tuple[np.ndarray, np.ndarray]:
    """Boolean arrays indexed by CONFIRMATION bar ``j``: True when bar ``j - k``
    is a swing high / swing low. Row ``j`` reads only bars ``j - 2k .. j``."""
    high, low = df["High"], df["Low"]
    pivot_high, pivot_low = high.shift(k), low.shift(k)
    sh = (pivot_high > high.shift(k + 1).rolling(k).max()) & (pivot_high >= high.rolling(k).max())
    sl = (pivot_low < low.shift(k + 1).rolling(k).min()) & (pivot_low <= low.rolling(k).min())
    return sh.fillna(False).to_numpy(bool), sl.fillna(False).to_numpy(bool)


def _last_two(flags: np.ndarray, prices: np.ndarray, k: int) -> tuple[np.ndarray, ...]:
    """Per bar: (last_pos, last_price, prior_pos, prior_price) of confirmed pivots."""
    n = len(flags)
    events = np.flatnonzero(flags) - k
    count = np.cumsum(flags)
    out = [np.full(n, np.nan) for _ in range(4)]
    for slot, back in ((0, 1), (2, 2)):
        has = count >= back
        pos = events[count[has] - back]
        out[slot][has] = pos
        out[slot + 1][has] = prices[pos]
    return tuple(out)


def confirmed_pivots(df: pd.DataFrame, k: int = PIVOT_K) -> pd.DataFrame:
    """Per bar ``t``: positional index and price of the last two confirmed swing
    highs and lows known at ``t`` (NaN where fewer exist). Truncation-stable:
    row ``t`` equals the last row of ``confirmed_pivots(df.iloc[:t + 1])``."""
    sh, sl = pivot_confirmations(df, k)
    highs = _last_two(sh, df["High"].to_numpy(float), k)
    lows = _last_two(sl, df["Low"].to_numpy(float), k)
    return pd.DataFrame(dict(zip(PIVOT_COLUMNS, highs + lows)), index=df.index)
```

- [ ] **Step 5:** Run `python scripts/dev/testrun.py file tests/market/test_structure_pivots.py`; expect PASS. Run `python -m radon cc -s -n C swingbot/core/market/structure.py` (expect no output).
- [ ] **Step 6:** Commit.

```bash
git add swingbot/core/market/structure.py tests/market/structure_fixtures.py tests/market/test_structure_pivots.py
git commit -m "feat(v121): causal confirmed fractal pivots (k=3) in market/structure.py"
```

### Task V121-2: Structure and volume-in-context features

**Files:** Modify `swingbot/core/market/structure.py`; create `tests/market/test_structure_features.py`.

**Interfaces:**
- Consumes (V121-1): `PIVOT_K`, `pivot_confirmations`, `confirmed_pivots`, `_num`, fixtures `UP`, `MIXED`, `BROKEN`, `frame`, `pullback_frame`, `slowing_pullback_frame`, `short_impulse_frame`.
- Produces: `STRUCTURE_KEYS` (16-tuple below, spec table order); `LEG_SHAPE_KEYS` (its last 4); `MIN_BARS = 60`; `MIN_LEG_THIRD = 2`; `true_range(df) -> pd.Series`; `absorption_series(df, atr_series) -> pd.Series[bool]`; `pullback_legs(df, direction, k=PIVOT_K) -> tuple[int, int, int] | None` (`(base, turn, t)` positions); `pullback_vol_ratio(df, direction, k=PIVOT_K) -> float | None` (signature unchanged: v122 consumes it); `leg_shape_features(df, direction, atr_value) -> dict`; `structure_features(df, direction) -> dict` with exactly `STRUCTURE_KEYS`. Booleans are Python `bool`, `absorption_count_10` is `int`, `structure_state` is `"up" | "down" | "mixed" | None`, floats rounded to 6.

Definitions (bullish; bearish mirrors where the spec says so): `structure_state` from last vs prior SH and SL; `structure_aligned` = state is `"up"` (bullish) / `"down"` (bearish); `last_pivot_held` = `Close[t] > last SL` (bullish) / `< last SH` (bearish); `hh_failed` = last SH `<=` prior SH (bullish) / last SL `>=` prior SL (bearish); `swing_high_atr = (last SH − Close)/ATR14`, `swing_low_atr = (Close − last SL)/ATR14` (not direction-signed, named by side); `vol_trend_10_50`, `range_trend_10_50` = mean over last 10 ÷ mean over last 50 bars; `progress_atr_10` = direction-signed `(Close[t] − Close[t-10])/ATR14`; `absorption_bar` = `Volume/mean20(prior 20 bars) >= 1.5` and `(High−Low)/ATR14 <= 0.6`; `absorption_count_10` = absorption bars in the last 10; `pullback_vol_ratio` per the spec's legs (impulse `SL0..SH` inclusive, pullback `SH+1..t`, `None` if a leg has < 2 bars, a mean is zero/NaN, or `Close[t] > High[SH]`). Leg-shape keys on the same `pullback_legs` (bullish; mirror for bearish), all `None` when the legs are undefined or the impulse height `High[SH] − Low[SL0]` is not `> 0`: `pullback_depth_frac = (High[SH] − min Low[SH+1..t]) / height`; `pullback_bars_ratio = (t − SH) / (SH − SL0)`; `impulse_atr_per_bar = height / (SH − SL0) / ATR14[t]` (`None` if ATR is 0/None); `impulse_range_decay` = mean true range of the last third of bars `SL0..SH` ÷ mean of the first third (third = `len // 3`; `None` below `MIN_LEG_THIRD` bars per third or a zero/NaN first-third mean). Depth above 1 is legitimate: the pullback took out the impulse's origin.

- [ ] **Step 1: Write the failing feature tests.**

```python
# tests/market/test_structure_features.py
import numpy as np
import pytest

from swingbot.core.market import structure as st
from swingbot.core.market.indicators import atr
from tests.conftest import make_ohlcv
from tests.market.structure_fixtures import (BROKEN, MIXED, UP, frame, pullback_frame, short_impulse_frame,
                                               slowing_pullback_frame)


@pytest.mark.parametrize("mirror,direction", [(False, "bullish"), (True, "bearish")])
def test_clean_trend_is_aligned_and_held(mirror, direction):
    out = st.structure_features(frame(UP, mirror=mirror), direction)
    assert out["structure_state"] == ("down" if mirror else "up")
    assert out["structure_aligned"] is True
    assert out["last_pivot_held"] is True
    assert out["hh_failed"] is False
    assert out["progress_atr_10"] > 0


@pytest.mark.parametrize("mirror,direction", [(False, "bearish"), (True, "bullish")])
def test_counter_trend_direction_is_not_aligned(mirror, direction):
    out = st.structure_features(frame(UP, mirror=mirror), direction)
    assert out["structure_aligned"] is False
    assert out["hh_failed"] is True
    assert out["progress_atr_10"] < 0


@pytest.mark.parametrize("mirror,direction", [(False, "bullish"), (True, "bearish")])
def test_lower_high_is_mixed_and_hh_failed(mirror, direction):
    out = st.structure_features(frame(MIXED, mirror=mirror), direction)
    assert out["structure_state"] == "mixed"
    assert out["structure_aligned"] is False
    assert out["hh_failed"] is True
    assert out["last_pivot_held"] is True


@pytest.mark.parametrize("mirror,direction", [(False, "bullish"), (True, "bearish")])
def test_close_through_last_pivot_is_not_held(mirror, direction):
    assert st.structure_features(frame(BROKEN, mirror=mirror), direction)["last_pivot_held"] is False


def test_swing_distances_fill_the_dead_keys():
    df = frame(UP)
    out = st.structure_features(df, "bullish")
    pivots = st.confirmed_pivots(df).iloc[-1]
    atr14 = float(atr(df, 14).iloc[-1])
    close = float(df["Close"].iloc[-1])
    assert out["swing_high_atr"] == pytest.approx((pivots["last_sh"] - close) / atr14, abs=1e-6)
    assert out["swing_low_atr"] == pytest.approx((close - pivots["last_sl"]) / atr14, abs=1e-6)
    assert out["swing_high_atr"] == st.structure_features(df, "bearish")["swing_high_atr"]


def test_progress_is_direction_signed():
    df = frame(UP)
    assert st.structure_features(df, "bearish")["progress_atr_10"] == \
        -st.structure_features(df, "bullish")["progress_atr_10"]


def test_pullback_on_half_the_impulse_volume():
    df = pullback_frame()
    assert st.pullback_vol_ratio(df, "bullish") == 0.5
    assert st.structure_features(df, "bullish")["pullback_vol_ratio"] == 0.5


def test_bearish_pullback_mirror():
    df = pullback_frame()
    mirrored = make_ohlcv((250 - df["Close"]).to_numpy(), spread_pct=1.0, volumes=df["Volume"].to_numpy())
    assert st.pullback_vol_ratio(mirrored, "bearish") == 0.5


def test_price_back_above_the_high_is_not_a_pullback():
    df = pullback_frame()
    closes = df["Close"].to_numpy().copy()
    closes[-1] = 125.0
    beyond = make_ohlcv(closes, spread_pct=1.0, volumes=df["Volume"].to_numpy())
    assert st.pullback_vol_ratio(beyond, "bullish") is None


def _absorption_frame():
    df = frame(UP).copy()
    last = df.index[-1]
    mid = float(df.loc[last, "Close"])
    df.loc[last, ["High", "Low", "Volume"]] = [mid + 0.2, mid - 0.2, 3_000_000.0]   # inside, 3x volume
    return df


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_high_volume_narrow_bar_is_absorption(direction):
    out = st.structure_features(_absorption_frame(), direction)
    assert out["absorption_bar"] is True
    assert out["absorption_count_10"] == 1


def test_ordinary_bars_are_not_absorption():
    out = st.structure_features(frame(UP), "bullish")
    assert (out["absorption_bar"], out["absorption_count_10"]) == (False, 0)


def test_trend_ratios_on_uniform_volume():
    out = st.structure_features(frame(UP), "bullish")
    assert out["vol_trend_10_50"] == 1.0
    assert 0 < out["range_trend_10_50"] < 2


def test_short_frame_returns_all_none():
    out = st.structure_features(frame(UP).iloc[:59], "bullish")
    assert set(out) == set(st.STRUCTURE_KEYS)
    assert all(value is None for value in out.values())
    assert st.structure_features(frame(UP).iloc[:60], "bullish")["structure_state"] == "up"


def test_zero_volume_gives_none_not_an_error():
    df = frame(UP).copy()
    df["Volume"] = 0.0
    out = st.structure_features(df, "bullish")
    assert out["vol_trend_10_50"] is None and out["pullback_vol_ratio"] is None
    assert out["absorption_bar"] is False


def test_flat_prices_give_no_structure_and_no_atr_keys():
    out = st.structure_features(make_ohlcv(np.full(80, 100.0), spread_pct=0.0), "bullish")
    assert out["structure_state"] is None and out["structure_aligned"] is None
    assert out["swing_high_atr"] is None and out["progress_atr_10"] is None
    assert out["range_trend_10_50"] is None
    assert all(out[key] is None for key in st.LEG_SHAPE_KEYS)


def test_nan_bars_do_not_raise():
    df = frame(UP).copy()
    df.iloc[40:42, df.columns.get_loc("High")] = np.nan
    df.iloc[50, df.columns.get_loc("Volume")] = np.nan
    assert st.structure_features(df, "bullish")["structure_state"] == "up"


def test_a_peak_younger_than_k_bars_is_not_used():
    df = frame(UP)                                   # peak 130 at bar 72, prior peak 125 at bar 56
    assert st.confirmed_pivots(df.iloc[:75]).iloc[-1]["last_sh_pos"] == 56   # t=74: 72 > t-k
    assert st.confirmed_pivots(df.iloc[:76]).iloc[-1]["last_sh_pos"] == 72   # t=75: confirmed
    close, atr14 = float(df["Close"].iloc[74]), float(atr(df.iloc[:75], 14).iloc[-1])
    expected = round((float(df["High"].iloc[56]) - close) / atr14, 6)
    assert st.structure_features(df.iloc[:75], "bullish")["swing_high_atr"] == expected


def test_pullback_shape_on_hand_derived_legs():
    df = pullback_frame()                            # SL0 bar 48, SH bar 58, t = 61
    assert st.pullback_legs(df, "bullish") == (48, 58, 61)
    out = st.structure_features(df, "bullish")
    # depth = (High[58] - min Low[59..61]) / (High[58] - Low[48]) = (120.6 - 113.43) / (120.6 - 99.5)
    assert out["pullback_depth_frac"] == round(7.17 / 21.1, 6)
    assert out["pullback_bars_ratio"] == 0.3         # 3 pullback bars / 10 impulse bars


def test_bearish_pullback_shape_mirror():
    df = pullback_frame()
    mirrored = make_ohlcv((250 - df["Close"]).to_numpy(), spread_pct=1.0, volumes=df["Volume"].to_numpy())
    high, low = mirrored["High"].to_numpy(), mirrored["Low"].to_numpy()
    out = st.structure_features(mirrored, "bearish")
    assert st.pullback_legs(mirrored, "bearish") == (48, 58, 61)
    assert out["pullback_depth_frac"] == round((high[59:62].max() - low[58]) / (high[48] - low[58]), 6)
    assert out["pullback_bars_ratio"] == 0.3


def test_impulse_speed_is_height_per_bar_in_atr():
    df = pullback_frame()
    atr14 = float(atr(df, 14).iloc[-1])
    assert st.structure_features(df, "bullish")["impulse_atr_per_bar"] == pytest.approx(21.1 / 10 / atr14, abs=1e-6)


def test_slowing_impulse_has_range_decay_below_one():
    assert st.structure_features(slowing_pullback_frame(), "bullish")["impulse_range_decay"] < 0.5
    assert st.structure_features(pullback_frame(), "bullish")["impulse_range_decay"] > 1.0


def test_short_impulse_has_no_range_decay_but_keeps_the_rest():
    out = st.structure_features(short_impulse_frame(), "bullish")
    assert st.pullback_legs(short_impulse_frame(), "bullish") == (56, 60, 63)
    assert out["impulse_range_decay"] is None
    assert out["pullback_bars_ratio"] == 0.75        # 3 / 4
    assert out["pullback_depth_frac"] is not None and out["impulse_atr_per_bar"] is not None


def test_no_pullback_leaves_every_leg_shape_key_none():
    df = pullback_frame()
    closes = df["Close"].to_numpy().copy()
    closes[-1] = 125.0                               # back above the swing high
    beyond = make_ohlcv(closes, spread_pct=1.0, volumes=df["Volume"].to_numpy())
    out = st.structure_features(beyond, "bullish")
    assert st.pullback_legs(beyond, "bullish") is None
    assert all(out[key] is None for key in st.LEG_SHAPE_KEYS)


def test_leg_shape_keys_ignore_volume():
    df = pullback_frame().copy()
    df["Volume"] = 0.0
    out = st.structure_features(df, "bullish")
    assert out["pullback_vol_ratio"] is None
    assert out["pullback_bars_ratio"] == 0.3
```

- [ ] **Step 2:** Run `python scripts/dev/testrun.py file tests/market/test_structure_features.py`; expect FAIL (`AttributeError: module ... has no attribute 'structure_features'`).

- [ ] **Step 3: Implement the feature half.** Add the import beside the existing ones and append below `confirmed_pivots`:

```python
# swingbot/core/market/structure.py -- add to the imports
from swingbot.core.market.indicators import atr
```

```python
# swingbot/core/market/structure.py -- append
MIN_BARS = 60               # below this every feature is None
ABSORPTION_VOL_MULT = 1.5   # frozen descriptive definition
ABSORPTION_RANGE_ATR = 0.6  # frozen descriptive definition
SHORT_WINDOW, LONG_WINDOW = 10, 50
PROGRESS_LOOKBACK = 10
MIN_LEG_THIRD = 2           # impulse_range_decay needs >= 2 bars per third (a leg of >= 6 bars)
LEG_SHAPE_KEYS = ("pullback_depth_frac", "pullback_bars_ratio", "impulse_atr_per_bar", "impulse_range_decay")
STRUCTURE_KEYS = ("structure_state", "structure_aligned", "last_pivot_held", "hh_failed",
                  "swing_high_atr", "swing_low_atr", "vol_trend_10_50", "range_trend_10_50",
                  "progress_atr_10", "absorption_bar", "absorption_count_10", "pullback_vol_ratio",
                  *LEG_SHAPE_KEYS)


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["Close"].shift(1)
    return pd.concat([df["High"] - df["Low"], (df["High"] - prev_close).abs(),
                      (df["Low"] - prev_close).abs()], axis=1).max(axis=1)


def absorption_series(df: pd.DataFrame, atr_series: pd.Series) -> pd.Series:
    """True where Volume / mean20(prior bars) >= 1.5 and (High-Low)/ATR14 <= 0.6."""
    prior = df["Volume"].rolling(20).mean().shift(1)
    heavy = df["Volume"] / prior.where(prior > 0) >= ABSORPTION_VOL_MULT
    narrow = (df["High"] - df["Low"]) / atr_series.where(atr_series > 0) <= ABSORPTION_RANGE_ATR
    return (heavy & narrow).fillna(False)


def _last_pivot_before(flags: np.ndarray, before: int, k: int) -> int | None:
    positions = np.flatnonzero(flags) - k
    earlier = positions[positions < before]
    return int(earlier[-1]) if len(earlier) else None


def pullback_legs(df: pd.DataFrame, direction: str, k: int = PIVOT_K) -> tuple[int, int, int] | None:
    """Positional ``(base, turn, t)`` of the impulse/pullback legs at the final bar.

    Bullish: turn = SH, the last confirmed swing high; base = SL0, the last
    swing low before SH; impulse = base..turn, pullback = turn+1..t. None when
    either pivot is missing or Close[t] > High[SH] (not a pullback). Bearish
    mirrors with lows. Bars turn+1..turn+3 are ordinary, knowable bars: only
    the pivot label is lagged."""
    sh, sl = pivot_confirmations(df, k)
    bullish = direction == "bullish"
    turn_flags, base_flags = (sh, sl) if bullish else (sl, sh)
    t = len(df) - 1
    turn = _last_pivot_before(turn_flags, t + 1, k)
    if turn is None:
        return None
    base = _last_pivot_before(base_flags, turn, k)
    if base is None:
        return None
    close = float(df["Close"].iloc[t])
    beyond = close > float(df["High"].iloc[turn]) if bullish else close < float(df["Low"].iloc[turn])
    return None if beyond else (base, turn, t)


def _leg_ratio(volume: np.ndarray, start: int, pivot: int, t: int) -> float | None:
    impulse, pullback = volume[start:pivot + 1], volume[pivot + 1:t + 1]
    if len(impulse) < 2 or len(pullback) < 2:
        return None
    impulse_mean, pullback_mean = float(np.mean(impulse)), float(np.mean(pullback))
    if not (impulse_mean > 0 and pullback_mean > 0):
        return None
    return _num(pullback_mean / impulse_mean)


def pullback_vol_ratio(df: pd.DataFrame, direction: str, k: int = PIVOT_K) -> float | None:
    """Mean pullback-leg volume / mean impulse-leg volume at the final bar
    (legs per ``pullback_legs``)."""
    legs = pullback_legs(df, direction, k)
    return None if legs is None else _leg_ratio(df["Volume"].to_numpy(float), *legs)


def _impulse_height(high: np.ndarray, low: np.ndarray, base: int, turn: int, bullish: bool) -> float:
    return float(high[turn] - low[base]) if bullish else float(high[base] - low[turn])


def _pullback_give(high: np.ndarray, low: np.ndarray, turn: int, t: int, bullish: bool) -> float:
    """How far the pullback leg's extreme has retraced from the turn pivot."""
    if bullish:
        return float(high[turn] - np.min(low[turn + 1:t + 1]))
    return float(np.max(high[turn + 1:t + 1]) - low[turn])


def _range_decay(tr: np.ndarray, base: int, turn: int) -> float | None:
    """Mean true range of the impulse leg's last third / its first third."""
    leg = tr[base:turn + 1]
    third = len(leg) // 3
    if third < MIN_LEG_THIRD:
        return None
    first = float(np.mean(leg[:third]))
    return _num(float(np.mean(leg[-third:])) / first) if first > 0 else None


def leg_shape_features(df: pd.DataFrame, direction: str, atr_value: float | None) -> dict:
    """Pullback depth/duration and impulse speed/decay on the ``pullback_legs``
    legs. All None when the legs are undefined or the impulse has no height."""
    out = dict.fromkeys(LEG_SHAPE_KEYS)
    legs = pullback_legs(df, direction)
    if legs is None:
        return out
    base, turn, t = legs
    bullish = direction == "bullish"
    high, low = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    height = _impulse_height(high, low, base, turn, bullish)
    if not height > 0:
        return out
    impulse_bars = turn - base
    out.update(pullback_depth_frac=_num(_pullback_give(high, low, turn, t, bullish) / height),
               pullback_bars_ratio=_num((t - turn) / impulse_bars),
               impulse_atr_per_bar=_num(height / impulse_bars / atr_value) if atr_value else None,
               impulse_range_decay=_range_decay(true_range(df).to_numpy(float), base, turn))
    return out


def _state(piv) -> str | None:
    if any(pd.isna(piv[c]) for c in ("last_sh", "prior_sh", "last_sl", "prior_sl")):
        return None
    if piv["last_sh"] > piv["prior_sh"] and piv["last_sl"] > piv["prior_sl"]:
        return "up"
    if piv["last_sh"] < piv["prior_sh"] and piv["last_sl"] < piv["prior_sl"]:
        return "down"
    return "mixed"


def _structure_keys(piv, close: float, direction: str) -> dict:
    bullish = direction == "bullish"
    state = _state(piv)
    pivot, side = (piv["last_sl"], 1) if bullish else (piv["last_sh"], -1)
    last, prior = (piv["last_sh"], piv["prior_sh"]) if bullish else (piv["last_sl"], piv["prior_sl"])
    return {
        "structure_state": state,
        "structure_aligned": None if state is None else state == ("up" if bullish else "down"),
        "last_pivot_held": None if pd.isna(pivot) else bool(side * (close - pivot) > 0),
        "hh_failed": None if pd.isna(last) or pd.isna(prior) else bool(side * (last - prior) <= 0),
    }


def _ratio_of_means(series: pd.Series) -> float | None:
    long_mean = series.iloc[-LONG_WINDOW:].mean()
    return _num(series.iloc[-SHORT_WINDOW:].mean() / long_mean) if long_mean else None


def _atr_keys(df: pd.DataFrame, piv, atr_value: float | None, direction: str) -> dict:
    if not atr_value:
        return {"swing_high_atr": None, "swing_low_atr": None, "progress_atr_10": None}
    close = float(df["Close"].iloc[-1])
    sign = 1 if direction == "bullish" else -1
    move = close - float(df["Close"].iloc[-1 - PROGRESS_LOOKBACK])
    return {"swing_high_atr": _num((piv["last_sh"] - close) / atr_value),
            "swing_low_atr": _num((close - piv["last_sl"]) / atr_value),
            "progress_atr_10": _num(sign * move / atr_value)}


def structure_features(df: pd.DataFrame, direction: str) -> dict:
    """Every STRUCTURE_KEYS value at ``df``'s final bar, expressed for the
    trade's direction. Reads only ``df``; < 60 bars returns all None."""
    out = {key: None for key in STRUCTURE_KEYS}
    if df is None or len(df) < MIN_BARS:
        return out
    piv = confirmed_pivots(df).iloc[-1]
    atr_series = atr(df, 14)
    atr_value = _num(atr_series.iloc[-1])
    absorption = absorption_series(df, atr_series)
    out.update(_structure_keys(piv, float(df["Close"].iloc[-1]), direction))
    out.update(_atr_keys(df, piv, atr_value, direction))
    out.update(vol_trend_10_50=_ratio_of_means(df["Volume"].astype(float)),
               range_trend_10_50=_ratio_of_means(true_range(df)),
               absorption_bar=bool(absorption.iloc[-1]),
               absorption_count_10=int(absorption.iloc[-SHORT_WINDOW:].sum()),
               pullback_vol_ratio=pullback_vol_ratio(df, direction))
    out.update(leg_shape_features(df, direction, atr_value))
    return out
```

- [ ] **Step 4:** Run `python scripts/dev/testrun.py file tests/market/test_structure_features.py` and `... file tests/market/test_structure_pivots.py`; expect PASS. Run `python -m radon cc -s -n C swingbot/core/market/structure.py` (expect no output; the prototype scored at most B (8)).
- [ ] **Step 5:** Commit.

```bash
git add swingbot/core/market/structure.py tests/market/test_structure_features.py
git commit -m "feat(v121): structure, absorption, pullback-volume and leg-shape entry features"
```

**Implementation detail.** Every value is computed at the final row from the frame passed in, so the caller's slicing (`df.iloc[:i + 1]` in replay, the completed frame live) is the only time boundary. `_num(nan)` returns `None`, which is how a missing pivot becomes `None` for `swing_*_atr` without a branch. `absorption_series` compares against `mean20` of the **prior** 20 bars (`shift(1)`), matching the spec's "mean20(prior)". Do not add any parameter that lets a caller change `k` or a constant at call time beyond `pivot_confirmations`'s existing `k` argument (kept for testability; production callers never pass it). The leg-shape keys reuse `pullback_legs` — the same legs `pullback_vol_ratio` measures — so no second leg definition exists; they read only High/Low/Close (zero volume leaves them defined) and the ATR value `structure_features` already computed.

# Phase 2 — Snapshot integration and storage

### Task V121-3: Merge structure features into the entry snapshot

**Files:** Modify `swingbot/core/edge/context.py`; create `tests/edge/test_edge_context_structure.py`.

**Interfaces:**
- Consumes (V121-2): `structure_features(df, direction) -> dict`, `STRUCTURE_KEYS`.
- Produces: `FEATURE_KEYS` = the existing 20 keys in their current order, then `"structure_state", "structure_aligned", "last_pivot_held", "hh_failed", "vol_trend_10_50", "range_trend_10_50", "progress_atr_10", "absorption_bar", "absorption_count_10", "pullback_vol_ratio", "pullback_depth_frac", "pullback_bars_ratio", "impulse_atr_per_bar", "impulse_range_decay"` (34 total; `swing_high_atr`/`swing_low_atr` keep their existing positions). `entry_context(...)` signature unchanged.

- [ ] **Step 1: Write the witness test FIRST and run it on the unchanged code.** The literal values below are what `entry_context` returned at HEAD `c5af1b92` on this fixture. If any differs on your machine, recapture from the **unchanged** code before Step 3 and record why — never edit the witness after touching `context.py`.

```python
# tests/edge/test_edge_context_structure.py
import numpy as np
import pytest

from swingbot.core.edge.context import FEATURE_KEYS, entry_context
from tests.conftest import make_ohlcv

STRUCTURE_NEW = ("structure_state", "structure_aligned", "last_pivot_held", "hh_failed",
                 "vol_trend_10_50", "range_trend_10_50", "progress_atr_10", "absorption_bar",
                 "absorption_count_10", "pullback_vol_ratio", "pullback_depth_frac", "pullback_bars_ratio",
                 "impulse_atr_per_bar", "impulse_range_decay")
FILLED_DEAD = ("swing_high_atr", "swing_low_atr")
ASOF = {"regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": None, "rs_combined": 61.0}
WITNESS = {
    "stop_atr": 3.389932, "stop_pct": 5.588532, "planned_rr": 2.0, "horizon_key": "2w",
    "atr_pctile_250": 36.0, "vol_ratio_20": 1.115516, "rsi_14": 19.789007, "adx_14": 42.545477,
    "bb_width_pctile_250": None, "gap_p90_pct": 0.0, "gap_fragile": False, "dow": 0,
    "regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": None, "rs_combined": 61.0,
}


def _wavy(n=300):
    i = np.arange(n)
    closes = 100 + 0.05 * i + 6 * np.sin(i / 7.0) + 2 * np.sin(i / 2.3)
    return make_ohlcv(closes, spread_pct=1.5, volumes=1_000_000 + 300_000 * np.sin(i / 3.1) + 5_000 * i)


def _context(df, direction):
    close = float(df["Close"].iloc[-1])
    sign = 1 if direction == "bullish" else -1
    return entry_context(df, direction=direction, horizon_key="2w",
                         stop=close - sign * 6.0, target=close + sign * 12.0, asof=ASOF)


@pytest.mark.parametrize("direction,htf_aligned", [("bullish", False), ("bearish", True)])
def test_pre_existing_keys_are_unchanged(direction, htf_aligned):
    out = _context(_wavy(), direction)
    kept = {key: out[key] for key in WITNESS}
    assert kept == WITNESS
    assert (out["direction"], out["htf_aligned"]) == (direction, htf_aligned)
```

Run `python scripts/dev/testrun.py file tests/edge/test_edge_context_structure.py`; expect **PASS** on the unchanged code (the witness is a characterisation, not a red test). Commit it on its own so the before-state is in history:

```bash
git add tests/edge/test_edge_context_structure.py
git commit -m "test(v121): witness entry_context values before the structure merge"
```

- [ ] **Step 2: Add the failing merge tests** to the same file; put the new import with the others at the top.

```python
from swingbot.core.market.structure import STRUCTURE_KEYS, structure_features   # top of file


def test_feature_keys_append_the_new_keys_in_order():
    assert FEATURE_KEYS[:20] == (
        "stop_atr", "stop_pct", "planned_rr", "swing_high_atr", "swing_low_atr", "horizon_key", "direction",
        "atr_pctile_250", "vol_ratio_20", "rsi_14", "adx_14", "bb_width_pctile_250", "htf_aligned",
        "gap_p90_pct", "gap_fragile", "dow", "regime2_state", "rs_pctile", "sector_pctile", "rs_combined")
    assert FEATURE_KEYS[20:] == STRUCTURE_NEW
    assert set(STRUCTURE_KEYS) <= set(FEATURE_KEYS)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_snapshot_carries_structure_features(direction):
    df = _wavy()
    out = _context(df, direction)
    assert set(out) == set(FEATURE_KEYS)
    expected = structure_features(df, direction)
    assert {key: out[key] for key in STRUCTURE_KEYS} == expected
    assert out["swing_high_atr"] is not None and out["swing_low_atr"] is not None


@pytest.mark.parametrize("bars", [10, 40, 59])
def test_short_frames_leave_every_new_key_none(bars):
    out = _context(_wavy().iloc[:bars], "bullish")
    assert set(out) == set(FEATURE_KEYS)
    assert all(out[key] is None for key in STRUCTURE_NEW + FILLED_DEAD)


def test_live_stamp_carries_the_new_keys():
    from types import SimpleNamespace

    from swingbot.core.planning.params import stamp_entry_context
    df = _wavy()
    close = float(df["Close"].iloc[-1])
    plan = SimpleNamespace(direction="bearish", horizon_key="2w", stop_loss=close + 6.0,
                           tp1=close - 12.0, entry_context=None)
    stamp_entry_context(plan, df, ASOF)
    assert plan.entry_context["structure_state"] == structure_features(df, "bearish")["structure_state"]
    assert set(plan.entry_context) == set(FEATURE_KEYS)
```

- [ ] **Step 3:** Run `python scripts/dev/testrun.py file tests/edge/test_edge_context_structure.py`; expect the witness PASS and the four new tests FAIL (`FEATURE_KEYS[20:]` empty, missing keys).

- [ ] **Step 4: Implement.** In `swingbot/core/edge/context.py`:

```python
# imports -- add
from swingbot.core.market.structure import structure_features
```

```python
FEATURE_KEYS = ("stop_atr", "stop_pct", "planned_rr", "swing_high_atr", "swing_low_atr", "horizon_key", "direction",
                "atr_pctile_250", "vol_ratio_20", "rsi_14", "adx_14", "bb_width_pctile_250", "htf_aligned",
                "gap_p90_pct", "gap_fragile", "dow", "regime2_state", "rs_pctile", "sector_pctile", "rs_combined",
                # v121: causal structure / volume-in-context (market/structure.py); swing_*_atr above are now filled
                "structure_state", "structure_aligned", "last_pivot_held", "hh_failed", "vol_trend_10_50",
                "range_trend_10_50", "progress_atr_10", "absorption_bar", "absorption_count_10",
                "pullback_vol_ratio", "pullback_depth_frac", "pullback_bars_ratio", "impulse_atr_per_bar",
                "impulse_range_decay")
```

Inside `entry_context`, directly after the `out.update(stop_pct=..., ..., dow=...)` statement and before `volume_mean = ...`, add one unconditional line:

```python
    out.update(structure_features(df, direction))   # v121; all None below 60 bars
```

The `len(df) < 20` early return already leaves every new key `None` via the `{key: None for key in FEATURE_KEYS}` default; `structure_features` covers 20..59 bars itself. No branch is added, so `entry_context` stays at its current score.

- [ ] **Step 5:** Run `python scripts/dev/testrun.py file tests/edge/test_edge_context_structure.py`, then the existing context suites: `... file tests/backtesting/test_backtest_context.py`, `... file tests/backtesting/test_replay_context.py`, `... file tests/scanning/test_live_context_stamp.py`, `... file tests/scanning/test_strategy_pass_emit.py`. Expect PASS (they assert `set(context) == set(FEATURE_KEYS)` and stamper identity, both still true). Run `python -m radon cc -s swingbot/core/edge/context.py` and confirm `entry_context` is still `C (17)`, not higher.
- [ ] **Step 6: No-lookahead review.** Invoke the `no-lookahead` skill on `swingbot/core/market/structure.py` and `swingbot/core/edge/context.py`. Confirm in the review note: pivots come only from `pivot_confirmations` (row `j` reads bars `<= j`); every feature reads the final row of the frame given; `absorption_series` uses `shift(1)` for the prior mean; no `shift(-n)`, `iloc[t+…]`, or centred rolling window anywhere. Fix any finding before committing.
- [ ] **Step 7:** Commit.

```bash
git add swingbot/core/edge/context.py tests/edge/test_edge_context_structure.py
git commit -m "feat(v121): entry_context carries structure/volume features and fills swing_*_atr"
```

### Task V121-4: Confirm the snapshot's storage shape (JSONB doc, no revision)

**Files:** Create `tests/db/test_entry_context_doc.py`. No schema, migration or repository change.

**Finding (verified):** `trades` is a hybrid table (`db/schema.py:70`, `migrations/versions/p1_002_create_trades.py`): promoted columns are `trade_id, ticker, strategy, horizon, direction, status, opened_at, closed_at, entry, stop_loss`; everything else, including `entry_context`, lives in `doc JSONB`. Per `schema-evolution.md` an added field "lands in `doc`. Migration: None." So this task adds **no Alembic revision**; it pins the finding with tests. Invoke the `schema-change` skill to confirm before writing the test, and record "add → doc, no revision" in the commit body.

**Interfaces:** Consumes existing `TradeRepository` (`db/repositories/trades.py`), `tracking.performance._db_record` / `_json_record`, `db.schema.trades`, the `db_conn` fixture (`tests/db/conftest.py:127`). Produces nothing later tasks import.

- [ ] **Step 1: Write the tests.**

```python
# tests/db/test_entry_context_doc.py
"""v121: entry_context is a doc JSONB payload, so new snapshot keys need no revision."""
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.db.schema import trades
from swingbot.core.edge.context import FEATURE_KEYS
from swingbot.core.tracking.performance import _db_record, _json_record

NEW = {"structure_state": "up", "structure_aligned": True, "last_pivot_held": True, "hh_failed": False,
       "swing_high_atr": 1.25, "swing_low_atr": 0.75, "vol_trend_10_50": 0.8, "range_trend_10_50": 0.9,
       "progress_atr_10": -0.5, "absorption_bar": False, "absorption_count_10": 2, "pullback_vol_ratio": 0.5,
       "pullback_depth_frac": 0.4, "pullback_bars_ratio": 0.3, "impulse_atr_per_bar": 1.1, "impulse_range_decay": 0.8}


def _trade(trade_id, context):
    return {"id": trade_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
            "direction": "bullish", "status": "open", "opened_at": "2026-10-02T15:00:00+00:00",
            "entry_context": context}


def test_entry_context_is_a_doc_payload_not_a_column():
    assert "entry_context" not in trades.c


def test_new_keys_round_trip_with_their_types(db_conn):
    context = {key: None for key in FEATURE_KEYS} | NEW
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V121-T1", context)), conn=db_conn)
    back = _json_record(repository.get("V121-T1", conn=db_conn))["entry_context"]
    assert back == context
    assert type(back["absorption_count_10"]) is int
    assert back["structure_aligned"] is True and back["pullback_vol_ratio"] == 0.5


def test_an_old_record_reads_every_new_key_as_none(db_conn):
    repository = TradeRepository()
    repository.insert(_db_record(_trade("V121-T0", {"vol_ratio_20": 1.2})), conn=db_conn)
    back = _json_record(repository.get("V121-T0", conn=db_conn))["entry_context"]
    assert all(back.get(key) is None for key in NEW)
    assert back == {"vol_ratio_20": 1.2}       # nothing upcast on read
```

- [ ] **Step 2:** Run `python scripts/dev/testrun.py file tests/db/test_entry_context_doc.py`; expect PASS immediately (it characterises the existing storage; it would only fail if `entry_context` were a column or the codec mangled bools/ints). It needs the Compose test Postgres (`TEST_DATABASE_URL`, default `127.0.0.1:55432`); if the container is down, start it per `tests/db/conftest.py` rather than skipping. If a test FAILS, stop: the storage assumption is wrong and the plan needs an additive revision per `schema-evolution.md` — report BLOCKED to the controller.
- [ ] **Step 3:** Commit.

```bash
git add tests/db/test_entry_context_doc.py
git commit -m "test(v121): entry_context new keys live in trades.doc -- add, no revision"
```

# Phase 3 — Descriptive report

### Task V121-5: `volume_context_report.py`

**Files:** Create `scripts/reports/volume_context_report.py`, `tests/scripts/test_volume_context_report.py`; modify `.gitignore` (add `data/v121_*.json` beside the `data/v104_*.json` / `data/v113_*.json` lines).

**Interfaces:**
- Consumes: `entry_context` keys (V121-3); `acceptance.win_rate`, `acceptance.expectancy_r`, `acceptance.DECIDED`; `replay_scenarios`, `SKIPPED`, `simulate_exit` (`planning/plan_engine.py`); `StrategyEngine().iter_trades`, `.strategies`; `planning.params.stamp_entry_context`; `windows.ALL_HORIZONS`; `measure_arms.cached_universe`, `measure_arms.load_frame`; `ScanParams.from_config()`; `TradeLog().get_trades`, `scope.closed_only`, `metrics.r_multiple`.
- Produces: `ReportRow(source, direction, outcome, r_multiple, context)`; `window_refusal(start, end) -> str | None`; `quintile_edges(rows, key) -> list[float] | None`; `bucket_of(value, edges) -> str`; `bucket_table(rows, key, edges) -> list[dict]`; `live_rows(trades) -> list[ReportRow]`; `confluence_rows(...)`, `strategy_rows(...)`, `replay_ticker(task)`, `replay_all(tickers, horizons, window, *, workers=1)`; `main(argv) -> int`.

Design: categorical keys (`structure_state`, `structure_aligned`, `last_pivot_held`, `hh_failed`, `absorption_bar`, `absorption_count_10`) bucket as-is; continuous keys (`swing_high_atr`, `swing_low_atr`, `vol_trend_10_50`, `range_trend_10_50`, `progress_atr_10`, `pullback_vol_ratio`, `pullback_depth_frac`, `pullback_bars_ratio`, `impulse_atr_per_bar`, `impulse_range_decay`) bucket by quintile edges fixed from the TRAIN replay population. A replay run writes the edges file (`--edges`, default `data/v121_train_quintiles.json`); a live run **requires** it and refuses without it, so live buckets are always TRAIN-fixed. Rows split by `(source, direction, bucket)`. Live outcome: `win`/`loss` as stored, any other closed status counts as `scratch` (in ExpR, not in the win-rate denominator — the `acceptance` convention). Strategy-sourced replay plans are not stamped by `StrategyEngine`, so the report stamps them at the **signal** bar with the live stamper; confluence plans arrive stamped from `replay_scenarios`. The engines themselves are not modified.

- [ ] **Step 1: Write the failing tests.**

```python
# tests/scripts/test_volume_context_report.py
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import volume_context_report as vcr  # noqa: E402

from tests.conftest import make_ohlcv  # noqa: E402


@pytest.mark.parametrize("start,end", [("2020-01-01", "2024-01-01"), ("2020-01-01", "2025-06-30"),
                                       ("2019-06-01", "2023-12-31"), ("2023-06-01", "2023-01-01")])
def test_replay_refuses_any_window_outside_train(start, end, monkeypatch, capsys):
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: pytest.fail("computed"))
    assert vcr.main(["--source", "replay", "--start", start, "--end", end]) == 1
    assert "refused" in capsys.readouterr().out


def test_train_window_is_accepted():
    assert vcr.window_refusal("2020-01-01", "2023-12-31") is None


def _row(source, direction, outcome, r, **context):
    return vcr.ReportRow(source=source, direction=direction, outcome=outcome, r_multiple=r, context=context)


def test_categorical_buckets_split_by_source_and_direction():
    rows = [_row("confluence", "bullish", "win", 2.0, structure_state="up"),
            _row("confluence", "bullish", "loss", -1.0, structure_state="up"),
            _row("strategy", "bearish", "loss", -1.0, structure_state="down"),
            _row("confluence", "bullish", "timeout", 0.0)]
    table = {(line["source"], line["direction"], line["bucket"]): line
             for line in vcr.bucket_table(rows, "structure_state", None)}
    up = table[("confluence", "bullish", "up")]
    assert (up["n"], up["win_rate"], up["expectancy_r"]) == (2, 50.0, 0.5)
    assert table[("confluence", "bullish", "None")]["n"] == 1
    assert table[("strategy", "bearish", "down")]["win_rate"] == 0.0


def test_continuous_buckets_use_fixed_edges():
    rows = [_row("confluence", "bullish", "win", 1.0, vol_trend_10_50=v) for v in (0.1, 0.3, 0.5, 0.7, 0.9)]
    edges = vcr.quintile_edges(rows, "vol_trend_10_50")
    assert edges == [0.26, 0.42, 0.58, 0.74]
    assert [vcr.bucket_of(v, edges) for v in (0.1, 0.3, 0.5, 0.7, 0.9, None)] == \
        ["Q1", "Q2", "Q3", "Q4", "Q5", "None"]
    assert vcr.quintile_edges(rows[:4], "vol_trend_10_50") is None


def test_live_rows_read_old_records_without_new_keys():
    trades = [{"status": "win", "source": "strategy", "direction": "bullish", "entry": 100.0,
               "stop_loss": 95.0, "exit_price": 110.0, "entry_context": {"vol_ratio_20": 1.2}},
              {"status": "open", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0},
              {"status": "closed", "direction": "bearish", "entry": 100.0, "stop_loss": 105.0,
               "exit_price": 100.0}]
    rows = vcr.live_rows(trades)
    assert [(r.source, r.outcome) for r in rows] == [("strategy", "win"), ("unknown", "scratch")]
    assert rows[0].r_multiple == pytest.approx(2.0)
    assert vcr.bucket_of(rows[1].context.get("structure_state"), None) == "None"


def test_live_refuses_without_train_edges(tmp_path, capsys):
    assert vcr.main(["--source", "live", "--edges", str(tmp_path / "missing.json")]) == 1
    assert "refused" in capsys.readouterr().out


def test_live_render_carries_the_holdout_warning(tmp_path, monkeypatch, capsys):
    edges = tmp_path / "edges.json"
    edges.write_text('{"window": ["2020-01-01", "2023-12-31"], "edges": {}}', encoding="utf-8")
    monkeypatch.setattr(vcr, "load_live_trades", lambda: [])
    assert vcr.main(["--source", "live", "--edges", str(edges)]) == 0
    out = capsys.readouterr().out
    assert "DESCRIPTIVE ONLY" in out and "holdout" in out and "p=" not in out


def test_strategy_rows_stamp_context_at_the_signal_bar(monkeypatch):
    df = make_ohlcv(np.linspace(100, 130, 120), spread_pct=1.0)
    signal_date = str(df.index[90].date())
    plan = SimpleNamespace(source="strategy", direction="bullish", horizon_key="2w",
                           stop_loss=110.0, tp1=140.0, entry_context={})
    result = SimpleNamespace(outcome="win", r_total=1.5)
    seen = {}

    class FakeEngine:
        strategies = ("RSI",)

        def iter_trades(self, *args):
            yield signal_date, plan, result

    import swingbot.core.backtesting.arms.strategy_engine as strategy_engine
    import swingbot.core.planning.params as params
    monkeypatch.setattr(strategy_engine, "StrategyEngine", FakeEngine)
    monkeypatch.setattr(params, "stamp_entry_context",
                        lambda p, window, asof: (seen.update(last=window.index[-1]),
                                                 setattr(p, "entry_context", {"ok": 1})))
    rows = vcr.strategy_rows("TEST", df, ("2w",), ("2020-01-01", "2023-12-31"), None)
    assert seen["last"] == df.index[90]
    assert rows == [vcr.ReportRow("strategy", "bullish", "win", 1.5, {"ok": 1})]


def test_replay_writes_train_edges(tmp_path, monkeypatch, capsys):
    rows = [_row("confluence", "bullish", "win", 1.0, pullback_vol_ratio=v) for v in (0.2, 0.4, 0.6, 0.8, 1.0)]
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: rows)
    out_path = tmp_path / "edges.json"
    assert vcr.main(["--source", "replay", "--tickers", "AAA", "--edges", str(out_path)]) == 0
    import json
    blob = json.loads(out_path.read_text(encoding="utf-8"))
    assert blob["window"] == ["2020-01-01", "2023-12-31"]
    assert blob["edges"]["pullback_vol_ratio"] == [0.36, 0.52, 0.68, 0.84]
```

- [ ] **Step 2:** Run `python scripts/dev/testrun.py file tests/scripts/test_volume_context_report.py`; expect FAIL (`ModuleNotFoundError: volume_context_report`).

- [ ] **Step 3: Implement the script.**

```python
#!/usr/bin/env python3
"""v121 descriptive report: closed trades bucketed by entry-structure features.

DESCRIPTIVE ONLY. It must not be used to choose v122's or v123's grid values --
both grids are frozen in their own specs. ``--source replay`` is TRAIN-only
(2020-01-01..2023-12-31) and refuses any other window. ``--source live`` reads
the production book, which overlaps the 2026 holdout other pre-registrations
(v104) are waiting on: monitoring only, and no inferential statistic is printed.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot.core.backtesting import acceptance  # noqa: E402

TRAIN_START, TRAIN_END = "2020-01-01", "2023-12-31"
DEFAULT_EDGES = ROOT / "data" / "v121_train_quintiles.json"
PROGRESS = ROOT / "logs" / "volume_context_report.progress"
CATEGORICAL = ("structure_state", "structure_aligned", "last_pivot_held", "hh_failed",
               "absorption_bar", "absorption_count_10")
CONTINUOUS = ("swing_high_atr", "swing_low_atr", "vol_trend_10_50", "range_trend_10_50",
              "progress_atr_10", "pullback_vol_ratio", "pullback_depth_frac", "pullback_bars_ratio",
              "impulse_atr_per_bar", "impulse_range_decay")
QUINTILES = (0.2, 0.4, 0.6, 0.8)
HEADER = ("v121 volume-in-context report -- DESCRIPTIVE ONLY. Not for choosing v122/v123 "
          "grid values (both frozen in their specs). No inferential statistic is printed.")
LIVE_WARNING = ("--source live overlaps the 2026 holdout that open pre-registrations (v104) "
                "are waiting on: monitoring only.")


@dataclass(frozen=True)
class ReportRow:
    source: str
    direction: str
    outcome: str
    r_multiple: float | None
    context: dict = field(default_factory=dict)


def window_refusal(start: str, end: str) -> str | None:
    """Replay may only read TRAIN; anything touching 2024-01-01+ is refused."""
    if start < TRAIN_START or end > TRAIN_END or start > end:
        return (f"refused: replay window {start}..{end} is outside TRAIN "
                f"{TRAIN_START}..{TRAIN_END}")
    return None


def quintile_edges(rows, key: str) -> list[float] | None:
    values = [float(v) for v in (row.context.get(key) for row in rows) if v is not None]
    if len(values) < len(QUINTILES) + 1:
        return None
    return [round(float(edge), 6) for edge in np.quantile(values, QUINTILES)]


def all_edges(rows) -> dict:
    return {key: quintile_edges(rows, key) for key in CONTINUOUS}


def bucket_of(value, edges) -> str:
    if value is None:
        return "None"
    if edges is None:
        return str(value)
    return f"Q{int(np.searchsorted(edges, float(value), side='right')) + 1}"


def bucket_table(rows, key: str, edges) -> list[dict]:
    """One line per (source, direction, bucket): N, win rate, ExpR."""
    groups: dict[tuple, list] = {}
    for row in rows:
        bucket = bucket_of(row.context.get(key), edges)
        groups.setdefault((row.source, row.direction, bucket), []).append(row)
    return [{"feature": key, "source": source, "direction": direction, "bucket": bucket,
             "n": len(members), "win_rate": acceptance.win_rate(members),
             "expectancy_r": acceptance.expectancy_r(members)}
            for (source, direction, bucket), members in sorted(groups.items())]


def _fmt(value, spec: str) -> str:
    return "  n/a" if value is None else format(value, spec)


def render(rows, edges: dict, *, source: str) -> str:
    lines = [HEADER] + ([LIVE_WARNING] if source == "live" else []) + [f"closed trades: {len(rows)}"]
    for key in CATEGORICAL + CONTINUOUS:
        lines.append(f"\n== {key} ==  edges={edges.get(key)}")
        for line in bucket_table(rows, key, edges.get(key) if key in CONTINUOUS else None):
            lines.append(f"{line['source']:<10} {line['direction']:<8} {line['bucket']:<7} "
                         f"N={line['n']:>5}  WR {_fmt(line['win_rate'], '6.2f')}%  "
                         f"ExpR {_fmt(line['expectancy_r'], '+.4f')}")
    return "\n".join(lines)


def _live_outcome(status: str) -> str:
    return status if status in acceptance.DECIDED else "scratch"


def live_rows(trades) -> list[ReportRow]:
    from swingbot.core.analytics.metrics import r_multiple
    from swingbot.core.analytics.scope import closed_only
    return [ReportRow(source=trade.get("source") or "unknown",
                      direction=trade.get("direction") or "unknown",
                      outcome=_live_outcome(trade.get("status")), r_multiple=r_multiple(trade),
                      context=trade.get("entry_context") or {})
            for trade in closed_only(trades)]


def load_live_trades() -> list[dict]:
    from swingbot.core.tracking.performance import TradeLog
    return TradeLog().get_trades(status=None, limit=None)


def _row(plan, result) -> ReportRow:
    return ReportRow(source=plan.source or "unknown", direction=plan.direction,
                     outcome=result.outcome, r_multiple=result.r_total,
                     context=dict(plan.entry_context or {}))


def confluence_rows(ticker, df, horizons, window, params) -> list[ReportRow]:
    """Mirrors ConfluenceEngine.run_ticker, keeping each plan's stamped snapshot."""
    from swingbot.core.backtesting.arms.confluence_engine import SKIPPED
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    from swingbot.core.planning.plan_engine import simulate_exit
    start, end = window
    out = []
    for horizon_key in horizons:
        for index, plan in replay_scenarios(ticker, df.loc[:end], horizon_key, params=params):
            if str(df.index[index].date()) < start:
                continue
            result = simulate_exit(df, index, plan, scale_out=True)
            if result.outcome not in SKIPPED:
                out.append(_row(plan, result))
    return out


def strategy_rows(ticker, df, horizons, window, params) -> list[ReportRow]:
    """StrategyEngine plans are unstamped; stamp at the SIGNAL bar, as live does."""
    from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
    from swingbot.core.planning.params import stamp_entry_context
    engine, out = StrategyEngine(), []
    for horizon_key in horizons:
        for strategy in engine.strategies:
            for date, plan, result in engine.iter_trades(ticker, df, strategy, horizon_key, window, params):
                index = int(df.index.searchsorted(pd.Timestamp(date)))
                stamp_entry_context(plan, df.iloc[:index + 1], None)
                out.append(_row(plan, result))
    return out


def load_frame(ticker):
    from measure_arms import load_frame as _load
    return _load(ticker)


def cached_universe() -> list[str]:
    from measure_arms import cached_universe as _universe
    return _universe()


def replay_ticker(task) -> list[ReportRow]:
    ticker, horizons, window = task
    from swingbot.scan_params import ScanParams
    df = load_frame(ticker)
    if df is None:
        return []
    params = ScanParams.from_config()
    return (confluence_rows(ticker, df, horizons, window, params)
            + strategy_rows(ticker, df, horizons, window, params))


def _progress(done: int, total: int) -> None:
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(f"{100.0 * done / total:.1f}% ({done}/{total})\n", encoding="utf-8")
    print(f"[{done}/{total}] {100.0 * done / total:.1f}%", flush=True)


def _results(tasks, workers: int):
    if workers <= 1:
        yield from map(replay_ticker, tasks)
        return
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(replay_ticker, tasks)


def replay_all(tickers, horizons, window, *, workers: int = 1) -> list[ReportRow]:
    tasks = [(ticker, tuple(horizons), window) for ticker in tickers]
    rows: list[ReportRow] = []
    for done, chunk in enumerate(_results(tasks, workers), start=1):
        rows.extend(chunk)
        _progress(done, len(tasks))
    PROGRESS.unlink(missing_ok=True)
    return rows


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", choices=("replay", "live"), required=True)
    ap.add_argument("--start", default=TRAIN_START)
    ap.add_argument("--end", default=TRAIN_END)
    ap.add_argument("--tickers", default=None, help="comma list; default every cached ticker")
    ap.add_argument("--edges", default=str(DEFAULT_EDGES),
                    help="TRAIN quintile edges: written by replay, required by live")
    ap.add_argument("--workers", type=int, default=1)
    return ap


def _run_replay(args) -> tuple[list, dict] | None:
    refusal = window_refusal(args.start, args.end)
    if refusal:
        print(refusal)
        return None
    from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
    tickers = args.tickers.split(",") if args.tickers else cached_universe()
    rows = replay_all(tickers, ALL_HORIZONS, (args.start, args.end), workers=args.workers)
    edges = all_edges(rows)
    path = Path(args.edges)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"window": [args.start, args.end], "edges": edges}, indent=1),
                    encoding="utf-8")
    return rows, edges


def _run_live(args) -> tuple[list, dict] | None:
    path = Path(args.edges)
    if not path.exists():
        print(f"refused: live needs TRAIN quintile edges at {path}; run --source replay first")
        return None
    return live_rows(load_live_trades()), json.loads(path.read_text(encoding="utf-8"))["edges"]


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    result = (_run_replay if args.source == "replay" else _run_live)(args)
    if result is None:
        return 1
    rows, edges = result
    print(render(rows, edges, source=args.source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Add to `.gitignore`, next to `data/v113_*.json`:

```
data/v121_*.json
```

- [ ] **Step 4:** Run `python scripts/dev/testrun.py file tests/scripts/test_volume_context_report.py`; expect PASS. Run `python -m radon cc -s -n C scripts/reports/volume_context_report.py` (expect no output; prototype max B (6)).
- [ ] **Step 5 (optional smoke, not a result):** only if the CSV cache exists, invoke `backtest-gate` first, then `python scripts/reports/volume_context_report.py --source replay --tickers AAPL,MSFT --edges logs/v121_smoke_edges.json`. Expect the header, per-feature tables, and an edges file under `logs/`. Do not quote, commit or act on any bucket figure; a full-universe run goes to `backtest-runner` and is not part of this plan.
- [ ] **Step 6:** Commit.

```bash
git add scripts/reports/volume_context_report.py tests/scripts/test_volume_context_report.py .gitignore
git commit -m "feat(v121): descriptive volume-in-context report (TRAIN-only replay, live monitoring)"
```

# Phase 4 — Verification

### Task V121-6: Full-suite verification and release

**Files:** No new feature files; fix only failures attributable to this plan, with their narrow tests. Release commit touches `VERSION.json` and `swingbot/admin/version_history.json` only.

- [ ] Run `python scripts/dev/testrun.py full` once (or dispatch the `test-runner` subagent) over everything this plan implemented. Green requires `0 failed`, `0 xfailed`. **If it is not green, fix forward from the failures it names** — they are this plan's regressions. A changed pass count alone is not a failure. Before blaming this plan for an unrelated red test, check the diff scope and run that file alone (shared-DB flakiness is known on this machine; `testing-cost.md`).
- [ ] Watch specifically for slower replay-heavy tests: `entry_context` now computes pivots per stamped trade. If a test's runtime regresses noticeably, measure before optimising; do not change feature semantics to save time.
- [ ] Run `python -m radon cc -s -n C swingbot/core/market/structure.py swingbot/core/edge/context.py scripts/reports/volume_context_report.py`; only the pre-existing `entry_context C (17)` may appear.
- [ ] After green, release per `working-conventions.md` § Versioning: bump the **bot** line at **patch** level from the then-current `VERSION.json`, set `bot_updated` (UTC `YYYY-MM-DD HH-MM-SS`), commit `release(bot): <new> -- v121 structure/volume entry snapshot`, then run `python scripts/dev/build_version_matrix.py`, commit `swingbot/admin/version_history.json`, and run `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`.
- [ ] Close the plan out per `document-lifecycle.md`. v122 and v123 may start implementation only after this branch is merged to `main`.
