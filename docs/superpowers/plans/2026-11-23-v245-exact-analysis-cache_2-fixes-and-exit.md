# v245 — Exact analysis caching — Part 2: byte-identical fixes and the exit gate

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V245-5" -A 400 <this file>`).

**Spec:** [2026-11-23-v245-exact-analysis-cache-design.md](../specs/2026-11-23-v245-exact-analysis-cache-design.md)
**Index:** [2026-11-23-v245-exact-analysis-cache_0-index.md](2026-11-23-v245-exact-analysis-cache_0-index.md) — Goal, Global Constraints, Parallelisation, the task ledger and the decisions this part relies on (Decision 9 deploys) live there.

This part covers spec § Task 0 steps 4–5: V245-4 and V245-5 ship the
byte-identical fixes ranked in V245-3's results doc
(`docs/superpowers/results/2026-11-23-v245-analysis-profile.md`,
`## Byte-identical fixes`), one commit per fix; V245-6 measures analysis time
per ticker on production and records the exit decision. All three run in id
order. **V245-6 is a stop gate:** if production p50 is at or under 0.7 s per
ticker, Parts 3–6 are not executed.

Every task here is gated by V245-1b's golden
(`tests/scanning/test_v245_scan_one_golden.py`): it must pass unchanged after
each commit. A fix that needs the golden regenerated has changed behaviour:
revert it, and report it instead of shipping it.

# Phase A — Fix and decide

### Task V245-4: Hot-spot fix slot 1 — one zigzag per trimmed frame for both trendline sides (doc `F1`)

**Model:** opus — behaviour-preserving refactor of two functions at the complexity cap on the hottest analysis path; any drift changes alerts.

Spec § Task 0 step 4, first fix. **The results doc decides what this slot
builds.** Read `## Byte-identical fixes` and `## What Part 2 takes` in
`docs/superpowers/results/2026-11-23-v245-analysis-profile.md` first:

- If `F1` is the duplicate zigzag in the trendline scan (the prepared design
  below), follow Steps 1–7 as written.
- If `F1` is another hot spot, build that instead with the same discipline:
  a failing test that counts the duplicated call and asserts the result
  equals the unshared path, the smallest change that removes the
  equal-input call, the golden unchanged, every touched function left < 15,
  one commit naming the doc's row. This prepared design then moves to
  V245-5's slot only if the doc ranks it among `F2..`.

**Why it is byte-identical.** `custom_scanner_levels` (trendlines.py:349)
calls `_find_best_trendline` once per side; each call trims the same frame
to its last `MAX_PIVOT_SCAN_BARS` (1500) rows and calls
`_volume_confirmed_pivots`, which runs
`zigzag_pivots(trimmed, threshold_pct=PIVOT_THRESHOLD_PCT)` over it. Both
zigzags read the same `Close` values with the same threshold, and
`zigzag_pivots` (indicators.py:73) is pure and returns a fresh list that
`_volume_confirmed_pivots` only iterates. Computing it once and handing the
list to both sides removes one call per ticker per scan. A zigzag failure
today makes each side return no pivots; computing `[]` once gives the same
result. `strongest_trendline_pair` (trendlines.py:419, the chart path) has
the same two-sided shape and gets the same sharing.

**Complexity.** `_volume_confirmed_pivots` and `_find_best_trendline` are at
15 (`scripts/dev/complexity_baseline.json:76-77`); touching them must leave
both < 15 (index § Global Constraints). The volume-average, zigzag and
per-pivot ratio logic move into three helpers, and the trim-back block of
`_find_best_trendline` into a fourth.

**Phase B note.** V245-8 later rewrites `_find_best_trendline` around a
`TrendlinePrefix`; it builds on this task's shape (keeps the keyword-only
`all_pivots` pass-through and the helpers below).

**Files:**
- Modify: `swingbot/core/market/trendlines.py` (`_volume_confirmed_pivots` 142-208, `_find_best_trendline` 271-323, `custom_scanner_levels` 349-377, `strongest_trendline_pair` 419-450)
- Create: `tests/market/test_trendline_shared_pivots.py`

**Interfaces:**
- Consumes: V245-1b's golden (`tests/scanning/test_v245_scan_one_golden.py`); V245-3's doc row `F1`.
- Produces: `trendlines._volume_confirmed_pivots(df, kind: str, all_pivots: list | None = None) -> list` (same result for every input; `all_pivots` = `zigzag_pivots(df, threshold_pct=PIVOT_THRESHOLD_PCT)` of the same `df`); `trendlines._find_best_trendline(df, current_price: float, side: str, *, all_pivots: list | None = None) -> dict | None` (`all_pivots` is the zigzag of the **trimmed** frame); `trendlines._trimmed_zigzag(df) -> list`; private helpers `_volume_average(df) -> pd.Series | None`, `_zigzag_or_empty(df) -> list`, `_pivot_ratio(df, vol_avg, bar_idx: int) -> float | None`, `_shift_to_full_frame(best: dict | None, trim_start: int) -> dict | None`. No other cross-task contract.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_trendline_shared_pivots.py`:

```python
"""v245 V245-4: both trendline sides share one zigzag of the trimmed frame.

The shared path must return exactly what each side computing its own zigzag
returns (the pre-V245-4 algorithm), and must run zigzag_pivots once.
"""
import pandas as pd
import pytest

from swingbot.core.market import trendlines
from swingbot.core.market.indicators import zigzag_pivots

_PERIOD = 20
_AMPLITUDE = 8.0
_VOLUME_SPIKE = 2.5


def _wave(n: int, drift: float = -0.3, volume: bool = True) -> pd.DataFrame:
    """Triangle wave on spiked turn volume (pattern: tests/charts/test_trendline_fit.py).

    Swings clear PIVOT_THRESHOLD_PCT and the turns carry VOL_MIN_RATIO-passing
    volume, so the custom scanner finds pivots instead of falling to trendln.
    """
    idx = pd.date_range("2018-01-01", periods=n, freq="B")
    values, volumes = [], []
    for i in range(n):
        phase = (i % _PERIOD) / _PERIOD
        triangle = 1.0 - abs(2.0 * phase - 1.0) * 2.0
        values.append(200.0 + drift * i + _AMPLITUDE * triangle + 0.37 * (i % 7))
        at_turn = i % _PERIOD in (0, _PERIOD // 2)
        volumes.append(1_000_000.0 * (_VOLUME_SPIKE if at_turn else 1.0) if volume else 0.0)
    close = pd.Series(values, index=idx)
    return pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                         "Close": close, "Volume": pd.Series(volumes, index=idx)}, index=idx)


FRAMES = {
    "short_140": lambda: _wave(140),
    "no_volume": lambda: _wave(160, volume=False),
    "long_1700": lambda: _wave(1700, drift=-0.01),      # > MAX_PIVOT_SCAN_BARS: the trim applies
    "exactly_1500": lambda: _wave(1500, drift=-0.02),
    "too_short": lambda: _wave(20),
}


def _count_zigzag(monkeypatch) -> dict:
    calls = {"n": 0}
    real = trendlines.zigzag_pivots

    def counting(df, threshold_pct):
        calls["n"] += 1
        return real(df, threshold_pct=threshold_pct)

    monkeypatch.setattr(trendlines, "zigzag_pivots", counting)
    return calls


def _unshared_levels(df: pd.DataFrame, price: float) -> list:
    """custom_scanner_levels as it was: each side runs its own zigzag."""
    if len(df) < trendlines.MIN_BARS_FOR_TRENDLINE or price <= 0:
        return []
    out = []
    for side in ("support", "resistance"):
        best = trendlines._find_best_trendline(df, price, side)
        if best:
            out.append((float(best["line_at_now"]), f"Trendline ({best['strength']}x touch)"))
    return [(p, s) for p, s in out if p and p > 0 and not pd.isna(p)]


@pytest.mark.parametrize("name", sorted(FRAMES))
@pytest.mark.parametrize("kind", ["low", "high"])
def test_given_pivots_equal_computed_pivots(name, kind):
    df = FRAMES[name]()
    given = zigzag_pivots(df, threshold_pct=trendlines.PIVOT_THRESHOLD_PCT)
    assert trendlines._volume_confirmed_pivots(df, kind, all_pivots=given) == \
        trendlines._volume_confirmed_pivots(df, kind)


@pytest.mark.parametrize("name", sorted(FRAMES))
@pytest.mark.parametrize("price_mult", [1.0, 0.9, 1.1, 0.5])   # at close, each price gate, far print
def test_custom_scanner_levels_equals_unshared(name, price_mult):
    df = FRAMES[name]()
    price = float(df["Close"].iloc[-1]) * price_mult
    assert trendlines.custom_scanner_levels(df, price) == _unshared_levels(df, price)


def test_fixture_exercises_the_custom_scanner():
    df = FRAMES["long_1700"]()
    assert _unshared_levels(df, float(df["Close"].iloc[-1])), \
        "the wave must yield custom-scanner lines, or the equality tests prove nothing"


@pytest.mark.parametrize("name", ["short_140", "long_1700"])
def test_custom_scanner_levels_runs_one_zigzag(monkeypatch, name):
    df = FRAMES[name]()
    calls = _count_zigzag(monkeypatch)
    trendlines.custom_scanner_levels(df, float(df["Close"].iloc[-1]))
    assert calls["n"] == 1


def test_strongest_pair_runs_one_zigzag_and_is_unchanged(monkeypatch):
    df = FRAMES["long_1700"]()
    price = float(df["Close"].iloc[-1])
    before = trendlines.strongest_trendline_pair(df, 120, price)
    calls = _count_zigzag(monkeypatch)
    assert trendlines.strongest_trendline_pair(df, 120, price) == before
    assert calls["n"] == 1


def test_trimmed_zigzag_is_the_zigzag_of_the_scanned_window():
    df = FRAMES["long_1700"]()
    assert trendlines._trimmed_zigzag(df) == zigzag_pivots(
        df.tail(trendlines.MAX_PIVOT_SCAN_BARS), threshold_pct=trendlines.PIVOT_THRESHOLD_PCT)


def test_zigzag_failure_still_yields_no_lines(monkeypatch):
    def boom(df, threshold_pct):
        raise ValueError("zigzag failed")

    monkeypatch.setattr(trendlines, "zigzag_pivots", boom)
    df = FRAMES["short_140"]()
    assert trendlines.custom_scanner_levels(df, float(df["Close"].iloc[-1])) == []
    assert trendlines._volume_confirmed_pivots(df, "low") == []


def test_best_line_touches_are_in_full_frame_coordinates():
    df = FRAMES["long_1700"]()
    zz = trendlines._trimmed_zigzag(df)
    price = float(df["Close"].iloc[-1])
    shared = trendlines._find_best_trendline(df, price, "support", all_pivots=zz)
    assert shared == trendlines._find_best_trendline(df, price, "support")
    if shared is not None:
        assert min(b for b, _, _ in shared["touches"]) >= len(df) - trendlines.MAX_PIVOT_SCAN_BARS
```

`strongest_trendline_pair`'s "before" value is computed on the same code as
the "after" value, so that test proves the call count; the equality with
the pre-change algorithm is carried by `test_custom_scanner_levels_equals_unshared`
(whose reference path still runs one zigzag per side) and by the golden.

- [ ] **Step 2: Run it to make sure it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_trendline_shared_pivots.py`
Expected: FAIL — `TypeError: _volume_confirmed_pivots() got an unexpected keyword argument 'all_pivots'`, `AttributeError: ... '_trimmed_zigzag'`, and the one-zigzag tests count 2.

- [ ] **Step 3: Split `_volume_confirmed_pivots` into helpers and take `all_pivots`**

In `swingbot/core/market/trendlines.py`, add the three helpers directly
above `_volume_confirmed_pivots` and replace its body (its docstring stays,
plus one paragraph):

```python
def _volume_average(df: pd.DataFrame) -> pd.Series | None:
    """The rolling volume mean the pivot filter compares against, or None
    when volume is absent or mostly zero (index symbols: filter bypassed)."""
    if "Volume" not in df.columns:
        return None
    vol = df["Volume"].replace(0, np.nan)
    if vol.count() <= len(df) * 0.3:             # need at least 30 % non-zero bars
        return None
    return vol.rolling(
        VOL_ROLLING_WINDOW,
        min_periods=max(3, VOL_ROLLING_WINDOW // 4),
    ).mean()


def _zigzag_or_empty(df: pd.DataFrame) -> list:
    """zigzag_pivots at the scanner's threshold; a failure means no pivots."""
    try:
        return zigzag_pivots(df, threshold_pct=PIVOT_THRESHOLD_PCT)
    except Exception:
        return []


def _pivot_ratio(df: pd.DataFrame, vol_avg: pd.Series | None, bar_idx: int) -> float | None:
    """The pivot's volume ratio, 1.0 when it cannot be judged, None when it fails."""
    if vol_avg is None:
        return 1.0                               # no volume data: accept ungated
    bar_vol = df["Volume"].iloc[bar_idx]
    avg_vol = vol_avg.iloc[bar_idx]
    if pd.isna(bar_vol) or pd.isna(avg_vol) or avg_vol <= 0:
        # Missing local average (can happen at the very start of the
        # series): accept without filtering rather than silently drop.
        return 1.0
    ratio = float(bar_vol / avg_vol)
    return ratio if ratio >= VOL_MIN_RATIO else None


def _volume_confirmed_pivots(df: pd.DataFrame, kind: str, all_pivots: list | None = None) -> list:
    """
    (existing docstring, unchanged, then:)

    ``all_pivots``: ``zigzag_pivots(df, threshold_pct=PIVOT_THRESHOLD_PCT)``
    of this same ``df`` when the caller already has it (both trendline sides
    share one, v245); None computes it here. The result is the same.
    """
    if len(df) < MIN_BARS_FOR_TRENDLINE:
        return []
    vol_avg = _volume_average(df)
    if all_pivots is None:
        all_pivots = _zigzag_or_empty(df)

    confirmed: list = []
    for bar_idx, _close_price, pkind in all_pivots:
        if pkind != kind or bar_idx >= len(df):
            continue
        # Use High/Low of the pivot bar for line fitting accuracy.
        price = float(df["High" if kind == "high" else "Low"].iloc[bar_idx])
        ratio = _pivot_ratio(df, vol_avg, bar_idx)
        if ratio is not None:
            confirmed.append((bar_idx, price, ratio))
    return confirmed
```

Order check against today's code: the volume average is still computed
before the zigzag, and an exception inside it still propagates as before
(it was never inside the `try`). `has_volume` was true exactly when
`vol_avg` was set, so `vol_avg is None` replaces
`not has_volume or vol_avg is None`; the accepted ratio is still the
literal `1.0` or `float(bar_vol / avg_vol)`.

- [ ] **Step 4: Thread `all_pivots` through `_find_best_trendline` and share it**

Add these two helpers above `_find_best_trendline`:

```python
def _trimmed_zigzag(df: pd.DataFrame) -> list:
    """The zigzag _find_best_trendline's pivot scan runs: over the last
    MAX_PIVOT_SCAN_BARS rows, at PIVOT_THRESHOLD_PCT. Computed once per frame
    and shared by both sides (v245); a failure gives [] (no pivots), as each
    side's own zigzag would."""
    trimmed = df.tail(MAX_PIVOT_SCAN_BARS) if len(df) > MAX_PIVOT_SCAN_BARS else df
    return _zigzag_or_empty(trimmed)


def _shift_to_full_frame(best: dict | None, trim_start: int) -> dict | None:
    """Pivot indices are relative to the trimmed frame. Convert the line
    back to the caller's full-frame coordinate system before any
    display-window conversion uses it."""
    if best is None or not trim_start:
        return best
    best["intercept"] -= best["slope"] * trim_start
    best["touches"] = [
        (bar_idx + trim_start, price, vol_ratio)
        for bar_idx, price, vol_ratio in best["touches"]
    ]
    return best
```

Then change `_find_best_trendline` in three places only — the signature
(plus one docstring paragraph), the pivots line, and the tail:

```python
def _find_best_trendline(df: pd.DataFrame, current_price: float, side: str, *,
                         all_pivots: list | None = None) -> dict | None:
    """
    (existing docstring, unchanged, then:)

    ``all_pivots``: ``_trimmed_zigzag(df)`` when the caller scans both sides
    of the same frame (v245); None computes it inside the pivot filter.
    """
    trim_start = max(len(df) - MAX_PIVOT_SCAN_BARS, 0)
    if trim_start:
        df = df.tail(MAX_PIVOT_SCAN_BARS)

    kind = "low" if side == "support" else "high"
    pivots = _volume_confirmed_pivots(df, kind, all_pivots=all_pivots)

    # `if len(pivots) < 2: return None`, n_bars, best and the i<j pair loop: unchanged.

    return _shift_to_full_frame(best, trim_start)
```

The removed code is the old `if best is not None and trim_start:` block,
now verbatim inside `_shift_to_full_frame`.

In `custom_scanner_levels`, compute the zigzag once before the side loop
(after the existing early return; the rest is unchanged):

```python
    shared = _trimmed_zigzag(df)
    candidates: list = []
    for side in ("support", "resistance"):
        try:
            result = _find_best_trendline(df, current_price, side, all_pivots=shared)
```

In `strongest_trendline_pair`, after the `display_bars`/`n_bars` lines:

```python
    shared = _trimmed_zigzag(df)
    support_raw: dict | None = None
    resistance_raw: dict | None = None
    try:
        support_raw = _find_best_trendline(df, current_price, "support", all_pivots=shared)
    except Exception:
        pass
    try:
        resistance_raw = _find_best_trendline(df, current_price, "resistance", all_pivots=shared)
    except Exception:
        pass
```

Both callers return early when `len(df) < MIN_BARS_FOR_TRENDLINE`, so the
shared zigzag is only computed on frames the pivot filter would scan.

- [ ] **Step 5: Run the new test, the golden and the neighbours**

```bash
python scripts/dev/testrun.py file tests/market/test_trendline_shared_pivots.py
python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py
python scripts/dev/testrun.py file tests/charts/test_trendline_fit.py
python scripts/dev/testrun.py file tests/charts/test_trade_chart_stored_fit.py
```

Expected: all PASS, `0 failed`, `0 xfailed`. The golden passing unchanged
is the proof the fix is byte-identical; never regenerate it.

- [ ] **Step 6: Complexity gate**

```bash
python scripts/dev/complexity_gate.py
python -m radon cc -s swingbot/core/market/trendlines.py | grep -E "_volume_confirmed_pivots|_find_best_trendline|_pivot_ratio|_volume_average|_trimmed_zigzag|_shift_to_full_frame|custom_scanner_levels|strongest_trendline_pair"
```

Expected: the gate passes; `_volume_confirmed_pivots` and
`_find_best_trendline` print below 15 (about 7 and 13). If the gate reports
a shrinkable baseline, run `python scripts/dev/complexity_gate.py --update`
(it only shrinks) and commit the baseline with the fix.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/market/trendlines.py tests/market/test_trendline_shared_pivots.py
git add scripts/dev/complexity_baseline.json   # only if Step 6 updated it
git commit -m "perf(v245): one zigzag per trimmed frame for both trendline sides (V245-4, doc F1)"
```

### Task V245-5: Hot-spot fix slot 2 — per-ticker indicator memo across horizons (doc `F2..`)

**Model:** opus — touches `_scan_one` (complexity 35, may not grow) and the level sources every alert reads; the memo must never serve a value computed from a different frame.

Spec § Task 0 step 4, the remaining fixes. **The results doc decides what
this slot builds:** take `F2`, then each further `F` row in rank order, one
commit per fix, for as long as each stays byte-identical (the golden
unchanged). A row the golden rejects is reverted and recorded in the doc's
`## Byte-identical fixes` table as `rejected: golden diff at <path>` in the
same commit as the next fix (or a docs-only commit). Rows not covered by the
prepared design below follow the same discipline as V245-4: failing test
counting the duplicated call plus equality with the unshared path, smallest
change, golden unchanged, touched functions < 15.

**Prepared design (the indicator memo).** For each horizon,
`_horizon_scenarios` calls `levels.collect_candidate_levels` and
`levels.atr_floor_pct` on the **same** `df` object. Several of their
indicator calls have parameters that do not depend on the horizon, or that
two horizons share:

| Call (levels.py) | Parameters | Repeats per ticker today |
|---|---|---|
| `bollinger_bands(df, window=20, num_std=2.0)` (:286) | fixed | once per horizon |
| `atr(df, 14)` in `atr_floor_pct` (:657) | fixed | once per horizon |
| `ema(close, h["ema_fast"])`, `ema(close, h["ema_slow"])` (:231, :238) | per horizon, shared values | once per distinct span would do |
| `rolling_vwap(df, h["vwap_window"])` (:245) | per horizon | once per distinct window would do |
| `fibonacci_levels(df, h["fib_lookback"])` (:252) | per horizon | once per distinct lookback would do |
| `zigzag_pivots(df, threshold_pct=h["max_risk_pct"])` (:276) | per horizon | once per distinct threshold would do |

A memo scoped to one `_scan_one` call returns the earlier result for a call
with the same function, the same parameters and the **same frame object**
(`is`, not equality): the same computation on the same input, so the same
floats. Exceptions are never stored, so the caller's existing `try/except`
sees exactly what it sees today. Every consumer above only reads the
returned object (`.iloc[-1]`, `.items()`, a slice), so sharing it cannot
leak a mutation; Step 3 has the implementer confirm that per call site.
Outside a `ticker_memo()` scope `memo` just calls the function, so
`rescenario`, outlook, replay, backtests and every other caller are
unchanged.

**Where the scope opens.** A decorator on `_scan_one`: radon measures the
undecorated source, so `_scan_one` stays at 35, and `functools.wraps` keeps
its name, docstring and signature (`inspect.signature` follows
`__wrapped__`). The SHORT lane's `scan_extra_candidate` calls `_scan_one`
and so gets its own scope too. The memo is thread-local, so a future
`SCAN_WORKERS > 1` never shares entries between tickers.

**Files:**
- Create: `swingbot/core/market/frame_memo.py`
- Modify: `swingbot/core/market/levels.py` (:231, :238, :245, :252, :276, :286 inside `collect_candidate_levels`; :657 in `atr_floor_pct`)
- Modify: `swingbot/core/scanning/analyze.py` (decorator on `_scan_one`, analyze.py:941; one import)
- Create: `tests/market/test_frame_memo.py`

**Interfaces:**
- Consumes: V245-1's helper `tests/scanning/v245_golden_cases.py` (`CASES`, `frozen_clock(monkeypatch)`, `run_case(case) -> dict`); V245-3's doc rows `F2..`; V245-4 (committed before this task).
- Produces: `frame_memo.ticker_memo() -> ContextManager[None]`; `frame_memo.memo(df, key: tuple, fn: Callable[[], T]) -> T` (computes directly when no memo is active); `frame_memo.with_ticker_memo(fn) -> fn` (decorator running `fn` inside `ticker_memo()`). Nothing later in the ledger consumes them.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_frame_memo.py`:

```python
"""v245 V245-5: a per-_scan_one memo for indicator calls repeated across horizons."""
import threading

import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import frame_memo, levels
from swingbot.core.market.strategy import HORIZONS
from swingbot.core.scanning import analyze
from tests.helpers import make_ohlcv
from tests.scanning.v245_golden_cases import CASES, frozen_clock, run_case


def _frame(n: int = 420) -> pd.DataFrame:
    i = np.arange(n)
    closes = 100.0 + 0.05 * i + 6.0 * np.sin(i / 9.0) + 2.0 * np.sin(i / 3.1)
    return make_ohlcv(list(closes))


def _count(monkeypatch, module, name) -> dict:
    calls = {"n": 0}
    real = getattr(module, name)

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, counting)
    return calls


def test_memo_without_a_scope_computes_every_time():
    df, calls = _frame(), []
    for _ in range(2):
        frame_memo.memo(df, ("k",), lambda: calls.append(1) or len(calls))
    assert len(calls) == 2


def test_memo_in_a_scope_returns_the_first_result():
    df, calls = _frame(), []
    with frame_memo.ticker_memo():
        first = frame_memo.memo(df, ("k", 1), lambda: calls.append(1) or object())
        second = frame_memo.memo(df, ("k", 1), lambda: calls.append(1) or object())
        other_key = frame_memo.memo(df, ("k", 2), lambda: calls.append(1) or object())
    assert first is second and other_key is not first
    assert len(calls) == 2


def test_memo_never_serves_another_frame():
    a, b = _frame(), _frame()            # equal values, different objects
    with frame_memo.ticker_memo():
        va = frame_memo.memo(a, ("atr", 14), lambda: "from a")
        vb = frame_memo.memo(b, ("atr", 14), lambda: "from b")
        again = frame_memo.memo(a, ("atr", 14), lambda: "recomputed")
    assert (va, vb, again) == ("from a", "from b", "from a")


def test_memo_does_not_store_exceptions():
    df = _frame()
    with frame_memo.ticker_memo():
        with pytest.raises(ValueError):
            frame_memo.memo(df, ("k",), lambda: (_ for _ in ()).throw(ValueError("x")))
        assert frame_memo.memo(df, ("k",), lambda: 7) == 7


def test_scopes_nest_and_restore():
    df = _frame()
    with frame_memo.ticker_memo():
        frame_memo.memo(df, ("k",), lambda: "outer")
        with frame_memo.ticker_memo():
            assert frame_memo.memo(df, ("k",), lambda: "inner") == "inner"
        assert frame_memo.memo(df, ("k",), lambda: "late") == "outer"
    assert frame_memo.memo(df, ("k",), lambda: "none") == "none"


def test_scope_is_thread_local():
    df, seen = _frame(), []
    with frame_memo.ticker_memo():
        frame_memo.memo(df, ("k",), lambda: "main")
        worker = threading.Thread(target=lambda: seen.append(frame_memo.memo(df, ("k",), lambda: "thread")))
        worker.start()
        worker.join()
    assert seen == ["thread"]


def test_decorator_keeps_the_function_identity():
    assert analyze._scan_one.__name__ == "_scan_one"
    assert hasattr(analyze._scan_one, "__wrapped__")


def test_levels_are_unchanged_and_shared_across_horizons(monkeypatch):
    df = _frame()
    price = float(df["Close"].iloc[-1])
    plain = [levels.collect_candidate_levels(df, h, price, trendline_candidates=[]) for h in HORIZONS.values()]
    plain_floors = [levels.atr_floor_pct(df, price, h) for h in HORIZONS.values()]
    bb = _count(monkeypatch, levels, "bollinger_bands")
    atr = _count(monkeypatch, levels, "atr")
    with frame_memo.ticker_memo():
        memoed = [levels.collect_candidate_levels(df, h, price, trendline_candidates=[]) for h in HORIZONS.values()]
        floors = [levels.atr_floor_pct(df, price, h) for h in HORIZONS.values()]
    assert memoed == plain and floors == plain_floors
    assert (bb["n"], atr["n"]) == (1, 1)


def test_scan_one_opens_the_memo(monkeypatch):
    frozen_clock(monkeypatch)
    case = next(c for c in CASES if len(c.horizons) > 1 and c.frame() is not None)
    bb = _count(monkeypatch, levels, "bollinger_bands")
    run_case(case)
    assert bb["n"] == 1
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_frame_memo.py`
Expected: FAIL — `ImportError: cannot import name 'frame_memo'`.

- [ ] **Step 3: Write `frame_memo.py`, wire the level sources, decorate `_scan_one`**

Create `swingbot/core/market/frame_memo.py`:

```python
"""Per-ticker memo for indicator calls repeated on one frame (v245 V245-5).

_scan_one builds every horizon from the same frame object, and several
indicator calls repeat across horizons with equal parameters (Bollinger 20/2,
ATR 14, EMA spans two horizons share). Inside a ticker_memo() scope, memo()
returns the earlier result for the same key on the same frame object -- the
same computation on the same input, so the same floats. Outside a scope it
just calls fn(), so every other caller behaves exactly as before.

Entries hold a reference to their frame, so an id() is never reused while
its entry lives; the scope ends with the _scan_one call. Exceptions are not
stored. The state is thread-local.
"""
from __future__ import annotations

import functools
import threading
from contextlib import contextmanager
from typing import Callable, Iterator, TypeVar

T = TypeVar("T")
_state = threading.local()


@contextmanager
def ticker_memo() -> Iterator[None]:
    """A fresh memo for the duration of one ticker's analysis; nests."""
    previous = getattr(_state, "entries", None)
    _state.entries = {}
    try:
        yield
    finally:
        _state.entries = previous


def memo(df, key: tuple, fn: Callable[[], T]) -> T:
    """fn()'s result, shared within the active scope for (df object, key)."""
    entries = getattr(_state, "entries", None)
    if entries is None:
        return fn()
    slot = (id(df), *key)
    hit = entries.get(slot)
    if hit is not None and hit[0] is df:
        return hit[1]
    value = fn()
    entries[slot] = (df, value)
    return value


def with_ticker_memo(fn: Callable[..., T]) -> Callable[..., T]:
    """Decorator: run fn inside its own ticker_memo() scope."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with ticker_memo():
            return fn(*args, **kwargs)
    return wrapper
```

In `swingbot/core/market/levels.py` add
`from swingbot.core.market import frame_memo` beside the other
`swingbot.core.market` imports (frame_memo imports nothing from the
package, so there is no cycle), then wrap the seven calls; each line keeps
its surrounding `try`, condition and append exactly as today:

```python
        fast = float(frame_memo.memo(df, ("ema", h["ema_fast"]), lambda: ema(close, h["ema_fast"])).iloc[-1])
        slow = float(frame_memo.memo(df, ("ema", h["ema_slow"]), lambda: ema(close, h["ema_slow"])).iloc[-1])
        vwap = float(frame_memo.memo(df, ("vwap", h["vwap_window"]),
                                     lambda: rolling_vwap(df, h["vwap_window"])).iloc[-1])
        fib = frame_memo.memo(df, ("fib", h["fib_lookback"]), lambda: fibonacci_levels(df, h["fib_lookback"]))
        pivots = frame_memo.memo(df, ("zigzag", h["max_risk_pct"]),
                                 lambda: zigzag_pivots(df, threshold_pct=h["max_risk_pct"]))
        bb = frame_memo.memo(df, ("bollinger", 20, 2.0), lambda: bollinger_bands(df, window=20, num_std=2.0))
```

and in `atr_floor_pct`:

```python
        atr_value = float(frame_memo.memo(df, ("atr", 14), lambda: atr(df, 14)).iloc[-1])
```

`close` is `df["Close"]` (levels.py:228), so keying the EMA on `df` is
keying it on that column. Before moving on, confirm read-only use with
`git grep -n "fib\[\|pivots\[\|bb\[" swingbot/core/market/levels.py`: every hit
must be inside `collect_candidate_levels` and only read. Lambdas are not
branches, so `collect_candidate_levels` stays at 42 and `atr_floor_pct`
does not grow.

In `swingbot/core/scanning/analyze.py`, add
`from swingbot.core.market import frame_memo` next to the existing
`from swingbot.core.market import atr_band, earnings_calendar, levels, trendlines`
line (analyze.py:27), and put the decorator directly on the definition:

```python
@frame_memo.with_ticker_memo
def _scan_one(ticker: str, df, horizons_to_scan: list, progress: "ScanProgress",
```

Nothing else in `_scan_one` changes. Check that no test or caller depends
on `_scan_one` being an undecorated function:
`git grep -n "_scan_one.__\|getsource(.*_scan_one" -- tests swingbot scripts`
(expected: only the new test).

- [ ] **Step 4: Run the new test, the golden and the neighbours**

```bash
python scripts/dev/testrun.py file tests/market/test_frame_memo.py
python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py
python scripts/dev/testrun.py file tests/market/test_levels_params.py
python scripts/dev/testrun.py file tests/market/test_levels_scenarios.py
python scripts/dev/testrun.py file tests/scanning/test_rescenario.py
python scripts/dev/testrun.py file tests/scanning/test_short_lane_scan.py
```

Expected: all PASS, `0 failed`, `0 xfailed`, the golden unchanged.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: passes; `_scan_one` 35 and `collect_candidate_levels` 42 unchanged,
the new functions in `frame_memo.py` all below 5.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/market/frame_memo.py swingbot/core/market/levels.py swingbot/core/scanning/analyze.py tests/market/test_frame_memo.py
git commit -m "perf(v245): per-ticker memo for indicator calls repeated across horizons (V245-5, doc F2)"
```

- [ ] **Step 7: The remaining doc rows**

For each further `F` row the doc ranks (`F3`, …), in order: test, change,
golden, gate, then one commit
`perf(v245): <hot spot> (V245-5, doc F<n>)`. When the list is exhausted (or
the doc has no row past `F2`), add one line to the doc's
`## Byte-identical fixes` table naming the commit of each shipped row and
any row rejected by the golden, and commit it:

```bash
git add docs/superpowers/results/2026-11-23-v245-analysis-profile.md
git commit -m "docs(v245): record shipped and rejected byte-identical fixes (V245-5)"
```

### Task V245-6: Production measurement and exit decision (stop gate)

**Model:** sonnet — a small pure report script plus read-only production commands and a results paragraph; the decision rule is fixed by the spec.

Spec § Task 0 step 5: after V245-4 and V245-5 are deployed, measure
analysis time per ticker on production and decide. **Met** (p50 ≤ 0.7 s):
the spec closes with its results, Parts 3–6 are not executed, `/close-out`
follows. **Missed:** Phase B (Part 3) starts. The laptop never gives this
verdict (index § Global Constraints): only production `phases_s` does.

The script reads `data/scan_telemetry.jsonl` rows as
`telemetry.log_scan_telemetry` writes them (`{"at": ISO, "duration_s", "tickers",
"phases_s": {"analysis": ...}, ...}`) and skips the deploy markers that share
the file (`{"type": "deploy", "component", "sha", "at": "...Z"}`,
`swingbot/core/infra/deploy_marker.py:54`). It imports nothing from
`swingbot`, so it can be piped to the bot container over SSH unchanged.
Its cache keys (`analysis_prefix`, `cache_hits`, `cache_misses`, `rss_mb`)
read as absent today and are filled once V245-12 ships; V245-16 reuses the
script for the `on` measurement.

**Files:**
- Create: `scripts/perf/analysis_phase_report.py` (`scripts/perf/__init__.py` exists from V245-2)
- Create: `tests/scripts/test_analysis_phase_report.py`
- Modify: `docs/superpowers/specs/2026-11-23-v245-exact-analysis-cache-design.md` (new `## Results` section between `## Rollout` and `## Deferred alternative: frozen completed-bar structure`)

**Interfaces:**
- Consumes: V245-4/V245-5 merged to `main` and deployed (index Decision 9); the spec's baseline (293.5 s analysis median over 92 tickers, ~3.2 s per ticker).
- Produces (ledger): `per_ticker_seconds(row: dict, phase: str = "analysis") -> float | None`; `summarise(rows: list[dict], since: str | None = None) -> dict` with keys `scans, p50, p90, prefix_p50, cache_hit_rate, rss_mb_max`; `main(argv=None) -> int` (`--since ISO`, `--since-deploy`, `--path`); `TARGET_S = 0.7`; `verdict(summary: dict) -> str` (`MET` / `MISSED` / `NO DATA`); `last_deploy_at(rows: list[dict], component: str = "bot") -> str | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_analysis_phase_report.py`:

```python
"""v245 V245-6: analysis seconds per ticker from scan telemetry."""
import json

import pytest

from scripts.perf import analysis_phase_report as apr


def _scan(at, analysis, tickers=92, **extra):
    return {"at": at, "duration_s": analysis + 90.0, "tickers": tickers,
            "phases_s": {"analysis": analysis, **extra.pop("phases", {})}, **extra}


DEPLOY = {"type": "deploy", "component": "bot", "sha": "abc", "at": "2026-11-25T14:00:00Z"}


def test_per_ticker_seconds():
    assert apr.per_ticker_seconds(_scan("2026-11-25T15:00:00+00:00", 46.0)) == pytest.approx(0.5)
    assert apr.per_ticker_seconds({"tickers": 92}) is None
    assert apr.per_ticker_seconds(_scan("2026-11-25T15:00:00+00:00", 46.0, tickers=0)) is None
    assert apr.per_ticker_seconds(DEPLOY) is None
    row = _scan("2026-11-25T15:00:00+00:00", 46.0, phases={"analysis_prefix": 9.2})
    assert apr.per_ticker_seconds(row, "analysis_prefix") == pytest.approx(0.1)


def test_summarise_percentiles_and_filters():
    rows = [DEPLOY] + [_scan(f"2026-11-25T15:{m:02d}:00+00:00", 9.2 * k) for k, m in enumerate(range(1, 11), 1)]
    s = apr.summarise(rows)
    assert s["scans"] == 10                              # the deploy marker is not a scan
    assert s["p50"] == pytest.approx((0.5 + 0.6) / 2)    # median of 0.1 .. 1.0
    assert s["p90"] == pytest.approx(0.9)                # nearest rank: ceil(0.9 * 10) = 9th
    assert s["prefix_p50"] is None and s["cache_hit_rate"] is None and s["rss_mb_max"] is None


def test_summarise_since_accepts_dates_and_z_suffix():
    rows = [_scan("2026-11-24T20:00:00+00:00", 276.0), _scan("2026-11-25T15:00:00+00:00", 46.0)]
    assert apr.summarise(rows, since="2026-11-25")["scans"] == 1
    assert apr.summarise(rows, since="2026-11-25T14:00:00Z")["p50"] == pytest.approx(0.5)


def test_summarise_cache_fields():
    rows = [_scan("2026-11-25T15:00:00+00:00", 46.0, cache_hits=180, cache_misses=20, rss_mb=410.5,
                  phases={"analysis_prefix": 4.6}),
            _scan("2026-11-25T15:06:00+00:00", 46.0, cache_hits=20, cache_misses=180, rss_mb=None)]
    s = apr.summarise(rows)
    assert s["cache_hit_rate"] == pytest.approx(0.5)
    assert s["rss_mb_max"] == 410.5
    assert s["prefix_p50"] == pytest.approx(0.05)


def test_summarise_empty():
    assert apr.summarise([]) == {"scans": 0, "p50": None, "p90": None, "prefix_p50": None,
                                 "cache_hit_rate": None, "rss_mb_max": None}


def test_verdict():
    assert apr.verdict({"scans": 80, "p50": 0.7}) == "MET"
    assert apr.verdict({"scans": 80, "p50": 0.71}) == "MISSED"
    assert apr.verdict({"scans": 0, "p50": None}) == "NO DATA"


def test_last_deploy_at():
    admin = {**DEPLOY, "component": "admin", "at": "2026-11-26T09:00:00Z"}
    assert apr.last_deploy_at([DEPLOY, _scan("2026-11-25T15:00:00+00:00", 46.0), admin]) == DEPLOY["at"]
    assert apr.last_deploy_at([]) is None


def test_main_prints_summary_and_verdict(tmp_path, capsys):
    path = tmp_path / "scan_telemetry.jsonl"
    lines = [json.dumps(DEPLOY), "{not json", "",
             json.dumps(_scan("2026-11-24T20:00:00+00:00", 276.0)),
             json.dumps(_scan("2026-11-25T15:00:00+00:00", 46.0))]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert apr.main(["--path", str(path), "--since-deploy"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scans"] == 1 and out["verdict"] == "MET"
    assert out["since"] == DEPLOY["at"] and out["bad_lines"] == 1


def test_main_missing_file(tmp_path, capsys):
    assert apr.main(["--path", str(tmp_path / "absent.jsonl")]) == 1
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_analysis_phase_report.py`
Expected: FAIL — `ImportError: cannot import name 'analysis_phase_report'`.

- [ ] **Step 3: Write the script**

Create `scripts/perf/analysis_phase_report.py`:

```python
"""Analysis seconds per ticker from scan telemetry (v245, spec § Task 0 step 5).

Usage:
    python scripts/perf/analysis_phase_report.py [--since ISO | --since-deploy] [--path FILE]
On production, read-only, piped to the bot container (no swingbot import):
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since-deploy" < scripts/perf/analysis_phase_report.py

Prints one JSON object: scans, p50 and p90 of phases_s.analysis / tickers
(p50 = median, p90 = nearest rank), the same p50 for analysis_prefix, the
cache hit rate, the largest rss_mb, and the verdict against TARGET_S.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from datetime import datetime, timezone

DEFAULT_PATH = os.path.join("data", "scan_telemetry.jsonl")
TARGET_S = 0.7


def _when(stamp: str) -> datetime:
    """An ISO stamp or date as an aware UTC datetime ("Z" and naive accepted)."""
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def per_ticker_seconds(row: dict, phase: str = "analysis") -> float | None:
    """phases_s[phase] / tickers for one scan row, None when not measurable."""
    value = (row.get("phases_s") or {}).get(phase)
    tickers = row.get("tickers")
    if not isinstance(value, (int, float)) or not tickers:
        return None
    return value / tickers


def _p90(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)]


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _scans(rows: list[dict], since: str | None) -> list[dict]:
    start = _when(since) if since else None
    out = [r for r in rows if "duration_s" in r and r.get("at")]
    return out if start is None else [r for r in out if _when(r["at"]) >= start]


def _hit_rate(scans: list[dict]) -> float | None:
    hits = sum(r.get("cache_hits") or 0 for r in scans)
    misses = sum(r.get("cache_misses") or 0 for r in scans)
    return hits / (hits + misses) if hits + misses else None


def summarise(rows: list[dict], since: str | None = None) -> dict:
    scans = _scans(rows, since)
    seconds = [s for s in map(per_ticker_seconds, scans) if s is not None]
    prefix = [s for s in (per_ticker_seconds(r, "analysis_prefix") for r in scans) if s is not None]
    rss = [r["rss_mb"] for r in scans if isinstance(r.get("rss_mb"), (int, float))]
    return {"scans": len(scans), "p50": _median(seconds), "p90": _p90(seconds),
            "prefix_p50": _median(prefix), "cache_hit_rate": _hit_rate(scans),
            "rss_mb_max": max(rss) if rss else None}


def verdict(summary: dict) -> str:
    if not summary.get("scans") or summary.get("p50") is None:
        return "NO DATA"
    return "MET" if summary["p50"] <= TARGET_S else "MISSED"


def last_deploy_at(rows: list[dict], component: str = "bot") -> str | None:
    stamps = [r["at"] for r in rows
              if r.get("type") == "deploy" and r.get("component") == component and r.get("at")]
    return max(stamps, key=_when) if stamps else None


def _read(path: str) -> tuple[list[dict], int]:
    rows, bad = [], 0
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
    return rows, bad


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--since", default=None, help="ISO timestamp or date (UTC)")
    parser.add_argument("--since-deploy", action="store_true", help="from the last bot deploy marker")
    args = parser.parse_args(argv)
    if not os.path.exists(args.path):
        print(f"no telemetry file at {args.path}", file=sys.stderr)
        return 1
    rows, bad = _read(args.path)
    since = last_deploy_at(rows) if args.since_deploy else args.since
    summary = summarise(rows, since)
    print(json.dumps({**summary, "since": since, "bad_lines": bad,
                      "target_s": TARGET_S, "verdict": verdict(summary)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

When piped as `python - --since-deploy`, `sys.argv[1:]` is
`["--since-deploy"]` and `__name__` is `"__main__"`, so the same file runs
locally and on the VM.

- [ ] **Step 4: Run the test and the gate**

```bash
python scripts/dev/testrun.py file tests/scripts/test_analysis_phase_report.py
python scripts/dev/complexity_gate.py
```

Expected: PASS, `0 failed`; every function in the script below 6.

- [ ] **Step 5: Commit the script**

```bash
git add scripts/perf/analysis_phase_report.py tests/scripts/test_analysis_phase_report.py
git commit -m "feat(v245): analysis seconds-per-ticker report from scan telemetry (V245-6)"
```

- [ ] **Step 6: Controller — merge Phase A and deploy**

The controller merges V245-1..V245-6 (code) to `main`, then deploys per
`docs/deploy/DEPLOY_HETZNER.md` (index Decision 9: bump `VERSION.json` here
only if the deploy procedure demands it; then close-out does not bump
again). The `.env` is not touched. The implementer waits here.

Check the deploy landed and wrote its marker (read-only):

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && git log -1 --format=%h && tail -n 300 data/scan_telemetry.jsonl | grep -c '\"type\":\"deploy\"'"
```

Expected: the merged `main` short sha, and a count of at least 1.

- [ ] **Step 7: Wait one full trading day, then measure**

Wait until the first full NYSE regular session after the deploy has closed
(16:00 New York; from this machine compute Berlin time from `date -u`, Git
Bash has no timezone data). Then:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since-deploy" < scripts/perf/analysis_phase_report.py > logs/v245-exit-report.json
cat logs/v245-exit-report.json
```

Expected: one JSON object with `scans` ≥ 50 and a `verdict`. Fewer than 50
scans: wait another session and rerun (the measurement window is never cut
short to reach a verdict). `NO DATA` or an exit code 1: stop and report
(the telemetry path or the deploy marker is wrong).

- [ ] **Step 8: Record `## Results` in the spec**

Insert this section between `## Rollout` and
`## Deferred alternative: frozen completed-bar structure` in
`docs/superpowers/specs/2026-11-23-v245-exact-analysis-cache-design.md`,
with every value from `logs/v245-exit-report.json` and the commit log:

```markdown
## Results

### Phase A (V245-6, <YYYY-MM-DD>)

Byte-identical fixes shipped: <F1 commit sha and one-line name>, <F2 ...>
(rejected by the golden: <rows or "none">). Deployed <deploy marker `at`>,
bot <version>, sha <sha>. Measured over <scans> production scans from the
deploy to <last row `at`>, 92 tickers, `SCAN_WORKERS=1`, `cpus: 1.0`.

| Measure | Before (spec § Why) | After Phase A |
|---|---|---|
| Analysis per ticker, p50 | ~3.2 s (293.5 s / 92) | <p50> s |
| Analysis per ticker, p90 | — | <p90> s |

**Verdict: <MET | MISSED>** against 0.7 s per ticker (p50).
<MET: "The exit criterion is met: the prefix cache (Phases B and C) is not
built, and this spec closes with these results." MISSED: "The exit criterion
is missed by <p50 - 0.7> s: Phase B (plan Part 3, V245-7) starts.">
```

- [ ] **Step 9: Commit the results**

```bash
git add docs/superpowers/specs/2026-11-23-v245-exact-analysis-cache-design.md
git commit -m "docs(v245): Phase A production results and exit verdict (V245-6)"
```

Report the verdict to the controller. **MET:** stop; V245-7..17 are not
executed and the controller runs `/close-out`. **MISSED:** Part 3 starts
at V245-7.

