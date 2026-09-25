# v104 Part 1b — Three short strategies (same worktree branch)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Global Constraints, Review Focus and Parallelisation live in `2026-09-25-v104-structural-stops-and-shorts_0-index.md` and bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-25-v104-structural-stops-and-shorts-design.md` §3 (with the §3.4 amendment in the index)

**Load the `no-lookahead` skill before starting V104-7.** Every task here computes per-bar series that decide what a bar knew.

---

### Task V104-7: SPY trend and return columns in the market context

**Files:**
- Modify: `swingbot/core/market/market_context.py` (`CTX_COLUMNS`, two helpers, `attach`)
- Test: `tests/market/test_market_context.py` (append)

**Interfaces:**
- Produces two new context columns on every attached frame:
  - `ctx_spy_down`: `1.0` when SPY `close < MA50` and `MA50 < MA50[t−20]`, `0.0` otherwise, `NaN` until MA50 is 20 bars old.
  - `ctx_spy_ret63`: SPY `close / close[t−63] − 1`.
- `has_context()` now requires all five columns.

- [ ] **Step 1: Write the failing tests**

Append to `tests/market/test_market_context.py`:

```python
# --- v104 B2 columns -----------------------------------------------------------

def test_spy_down_flags_a_falling_market_only():
    falling = mc.attach(make_trend_df(200, -0.3), spy_df=make_trend_df(200, -0.3))
    rising = mc.attach(make_trend_df(200, 0.3), spy_df=make_trend_df(200, 0.3))
    assert falling["ctx_spy_down"].iloc[-1] == 1.0
    assert rising["ctx_spy_down"].iloc[-1] == 0.0
    assert falling["ctx_spy_down"].iloc[:69].isna().all()      # MA50 needs 50 bars, its shift 20 more


def test_spy_ret63_is_the_63_bar_return():
    spy = _spy(200)
    out = mc.attach(spy.copy(), spy_df=spy)
    expected = spy["Close"].iloc[-1] / spy["Close"].iloc[-64] - 1.0
    assert out["ctx_spy_ret63"].iloc[-1] == pytest.approx(expected)


def test_new_spy_columns_are_truncation_invariant():
    spy = _spy(400)
    df = make_trend_df(400, 0.10)
    i = 350
    full = mc.attach(df, spy_df=spy).iloc[i]
    truncated = mc.attach(df.iloc[:i + 1], spy_df=spy.iloc[:i + 1]).iloc[i]
    for col in ("ctx_spy_down", "ctx_spy_ret63"):
        assert full[col] == pytest.approx(truncated[col], nan_ok=True)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_market_context.py`
Expected: the three new tests FAIL with `KeyError: 'ctx_spy_down'`.

- [ ] **Step 3: Implement**

In `swingbot/core/market/market_context.py`:

```python
CTX_COLUMNS: tuple[str, ...] = ("ctx_regime", "ctx_rv_pct", "ctx_cot_z",
                                "ctx_spy_down", "ctx_spy_ret63")
```

Add below `_rv_percentile`:

```python
def _spy_down(spy_df: pd.DataFrame) -> pd.Series:
    """v104 B2: 1.0 when SPY is below a FALLING 50-day average, else 0.0.

    Trailing windows only; NaN until MA50 has a 20-bar-old value to compare."""
    close = spy_df["Close"]
    ma50 = close.rolling(50).mean()
    down = (close < ma50) & (ma50 < ma50.shift(20))
    return down.astype(float).where(ma50.shift(20).notna())


def _spy_ret63(spy_df: pd.DataFrame) -> pd.Series:
    """v104 B2: SPY's trailing 63-bar return, the relative-weakness benchmark."""
    close = spy_df["Close"]
    return close / close.shift(63) - 1.0
```

In `attach`, extend the loop tuple:

```python
    for col, series in (("ctx_regime", regime_series(spy_df)),
                        ("ctx_rv_pct", _rv_percentile(spy_df)),
                        ("ctx_spy_down", _spy_down(spy_df)),
                        ("ctx_spy_ret63", _spy_ret63(spy_df))):
        out[col] = series.reindex(out.index, method="ffill")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_market_context.py`. Expected: PASS.
Then `git grep -ln "ctx_rv_pct\|has_context" -- tests` and run every file listed. Any test that builds the context block **by hand** (setting `ctx_regime`/`ctx_rv_pct`/`ctx_cot_z` columns itself) now fails `has_context`. Add `ctx_spy_down = np.nan` and `ctx_spy_ret63 = np.nan` to that fixture. Never loosen an assertion.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/market_context.py tests/market/test_market_context.py
git commit -m "feat(v104): SPY trend and 63-bar return in the market context block (B2 inputs)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

If Step 4 touched other test fixtures, add them to this commit by explicit path.

---

### Task V104-8: Earnings context columns and a per-plan hold cap

**Files:**
- Create: `swingbot/core/market/earnings_context.py`
- Modify: `swingbot/core/planning/plan_types.py` (new field `hold_cap_bars` directly after `stall_exit_day`)
- Modify: `swingbot/core/planning/exit_sim.py` (`simulate_exit` honours it)
- Test: `tests/market/test_earnings_context.py`, `tests/planning/test_exit_sim_hold_cap.py`

**Interfaces:**
- Produces:
  - `earnings_context.EVT_COLUMNS = ("evt_reaction", "evt_bars_to_next")`
  - `earnings_context.reaction_positions(index: pd.DatetimeIndex, reports) -> list[int]`: positions on the frame's bar grid. Positions ≥ `len(index)` are reports after the last bar, counted in business days.
  - `earnings_context.attach(df, ticker, *, source=None) -> pd.DataFrame`. `source` defaults to `earnings_calendar.CsvSource()`.
  - `TradePlanV2.hold_cap_bars: int | None = None`
  - `simulate_exit` uses `min(max_holding_days, plan.hold_cap_bars)` when the field is set.

- [ ] **Step 1: Write the failing tests**

```python
# tests/market/test_earnings_context.py
"""v104 §3.3/§3.4: earnings reaction sessions on the frame's own bar grid."""
import datetime as dt
from types import SimpleNamespace

import numpy as np
import pytest

from swingbot.core.market import earnings_calendar as ec
from swingbot.core.market import earnings_context as evt
from tests.helpers import make_ohlcv


def _source(*reports):
    return SimpleNamespace(reports=lambda ticker: list(reports))


def _df(n=30):
    return make_ohlcv([100.0] * n, start="2024-01-02")      # business days from Tue 2024-01-02


def test_before_open_reacts_the_same_day_after_close_the_next():
    df = _df()
    day = df.index[10].date()
    before = evt.reaction_positions(df.index, [ec.Report(day, ec.BEFORE_OPEN)])
    after = evt.reaction_positions(df.index, [ec.Report(day, ec.AFTER_CLOSE)])
    unconfirmed = evt.reaction_positions(df.index, [ec.Report(day, ec.UNCONFIRMED)])
    assert before == [10] and after == [11] and unconfirmed == [11]


def test_columns_mark_the_reaction_and_count_down_to_it():
    df = _df()
    out = evt.attach(df, "AAPL", source=_source(ec.Report(df.index[10].date(), ec.BEFORE_OPEN)))
    assert out["evt_reaction"].tolist().count(1.0) == 1 and out["evt_reaction"].iloc[10] == 1.0
    assert out["evt_bars_to_next"].iloc[7] == 3 and out["evt_bars_to_next"].iloc[10] == 0
    assert np.isnan(out["evt_bars_to_next"].iloc[11])            # no later report known


def test_a_report_after_the_last_bar_still_counts_down():
    df = _df(30)
    last = df.index[-1].date()                                   # a business day
    report_day = last + dt.timedelta(days=7)                     # one calendar week later
    out = evt.attach(df, "AAPL", source=_source(ec.Report(report_day, ec.BEFORE_OPEN)))
    assert out["evt_bars_to_next"].iloc[-1] == 5                 # 5 business days ahead
    assert out["evt_reaction"].sum() == 0


def test_no_reports_means_no_reaction_and_nan_distance():
    out = evt.attach(_df(), "SPY", source=_source())
    assert out["evt_reaction"].sum() == 0 and out["evt_bars_to_next"].isna().all()


@pytest.mark.parametrize("k", [5, 10, 20, 29])
def test_attach_is_truncation_invariant(k):
    df = _df(30)
    reports = (ec.Report(df.index[12].date(), ec.AFTER_CLOSE),
               ec.Report(df.index[-1].date() + dt.timedelta(days=14), ec.BEFORE_OPEN))
    full = evt.attach(df, "AAPL", source=_source(*reports)).iloc[k]
    cut = evt.attach(df.iloc[:k + 1], "AAPL", source=_source(*reports)).iloc[k]
    for col in evt.EVT_COLUMNS:
        assert full[col] == pytest.approx(cut[col], nan_ok=True)
```

```python
# tests/planning/test_exit_sim_hold_cap.py
"""v104 §3.4: a plan's hold_cap_bars shortens the timeout, nothing else."""
from swingbot.core.planning.exit_sim import simulate_exit
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan


def _flat():
    return make_ohlcv([100.0] * 80, start="2024-01-02")


def _short(**kw):
    return _plan(direction="bearish", entry_type="market", trigger_price=100.0,
                 stop_loss=110.0, tp1=80.0, tp2=None, horizon_key="4w", **kw)


def test_hold_cap_times_out_early():
    capped = simulate_exit(_flat(), 30, _short(hold_cap_bars=3))
    free = simulate_exit(_flat(), 30, _short())
    assert capped.outcome == "timeout" and free.outcome == "timeout"
    assert capped.exit_index < free.exit_index
    assert capped.exit_index - capped.entry_index <= 3


def test_hold_cap_never_lengthens_the_horizon_default():
    capped = simulate_exit(_flat(), 30, _short(hold_cap_bars=999))
    free = simulate_exit(_flat(), 30, _short())
    assert capped.exit_index == free.exit_index
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_earnings_context.py` (FAIL: module missing), then `tests/planning/test_exit_sim_hold_cap.py` (FAIL: `TradePlanV2` has no `hold_cap_bars`).

- [ ] **Step 3: Implement**

Create `swingbot/core/market/earnings_context.py`:

```python
"""v104: per-bar earnings columns for the short strategies (spec §3.3, §3.4).

evt_reaction      1.0 on a reaction session (the first session that trades on
                  the report), else 0.0.
evt_bars_to_next  bars from this bar to the next reaction session (0 = this bar
                  is one); NaN when no later report is known.

Reaction mapping follows earnings_calendar.reaction_session on the frame's OWN
bar grid -- before_open reacts on the report date's bar, after_close and
unconfirmed on the next bar -- so it needs no exchange calendar and runs
offline. A report after the last bar is placed by business days past it.

LOOKAHEAD NOTE (deliberate, spec §3.4 / v82 precedent): evt_bars_to_next reads
the next SCHEDULED report date. Companies announce dates weeks ahead, so the
date is knowable at the bar; the report's CONTENT is never read. evt_reaction
looks at the current bar only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.market import earnings_calendar as ec

EVT_COLUMNS = ("evt_reaction", "evt_bars_to_next")


def _position(days: pd.DatetimeIndex, report) -> int:
    ts = pd.Timestamp(report.date)
    side = "left" if report.timing == ec.BEFORE_OPEN else "right"
    pos = int(days.searchsorted(ts, side=side))
    if pos < len(days):
        return pos
    first_after = days[-1] + pd.offsets.BDay(1)
    reaction = ts if report.timing == ec.BEFORE_OPEN else ts + pd.offsets.BDay(1)
    return len(days) - 1 + len(pd.bdate_range(first_after, reaction))


def reaction_positions(index: pd.DatetimeIndex, reports) -> list[int]:
    days = pd.DatetimeIndex(index).normalize()
    if len(days) == 0:
        return []
    return sorted({_position(days, report) for report in reports})


def attach(df: pd.DataFrame, ticker: str, *, source=None) -> pd.DataFrame:
    """Return a copy of `df` carrying EVT_COLUMNS for `ticker`."""
    source = source if source is not None else ec.CsvSource()
    out = df.copy()
    n = len(out)
    positions = np.asarray(reaction_positions(out.index, source.reports(ticker)), dtype=int)
    reaction = np.zeros(n)
    reaction[positions[positions < n]] = 1.0
    bars = np.full(n, np.nan)
    if len(positions):
        here = np.arange(n)
        nxt = np.searchsorted(positions, here, side="left")
        known = nxt < len(positions)
        bars[known] = positions[nxt[known]] - here[known]
    out["evt_reaction"] = reaction
    out["evt_bars_to_next"] = bars
    return out
```

In `swingbot/core/planning/plan_types.py`, directly after the `stall_exit_day: int | None = None` line:

```python
    # v104 §3.4: bars after entry at which a short on its `exit_before`
    # earnings setting is closed -- the bar before the report reacts. None =
    # the horizon's own max_holding_days. Only ever SHORTENS the hold.
    hold_cap_bars: int | None = None
```

In `swingbot/core/planning/exit_sim.py`, `simulate_exit`, directly after

```python
    if max_holding_days is None:
        max_holding_days = HORIZONS[plan.horizon_key]["max_holding_days"]
```

add

```python
    hold_cap = getattr(plan, "hold_cap_bars", None)
    if hold_cap is not None:
        max_holding_days = min(max_holding_days, int(hold_cap))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_earnings_context.py` (PASS), `tests/planning/test_exit_sim_hold_cap.py` (PASS), then `tests/planning/test_plan_serialization.py`, `tests/planning/test_exit_sim_single.py` and `tests/planning/test_exit_sim_scaleout.py` (PASS, unchanged).

If `test_plan_serialization.py` pins the exact field set of `TradePlanV2`, add `hold_cap_bars` to its expected set. That is a schema pin, not a loosened assertion. Then read v67's plans task (`grep -n "stall_exit_day" docs/superpowers/plans/2026-08-29-v67-json-to-postgres_2b-trading-state-plans.md`). If it lists plan columns, add `hold_cap_bars` beside `stall_exit_day` in that plan file in the same commit (memory: v67 parallel-plan rule).

- [ ] **Step 5: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/core/market/earnings_context.py swingbot/core/planning/exit_sim.py`. Expected: no new entry at or above C, and `simulate_exit` grows by at most 1.

```bash
git add swingbot/core/market/earnings_context.py swingbot/core/planning/plan_types.py swingbot/core/planning/exit_sim.py tests/market/test_earnings_context.py tests/planning/test_exit_sim_hold_cap.py
git commit -m "feat(v104): earnings context columns (reaction, bars to next) and a per-plan hold cap in simulate_exit

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V104-9: B1 Bull Trap entries, the short-entries module, masked registration

**Files:**
- Create: `swingbot/core/market/short_entries.py`
- Modify: `swingbot/core/market/entry_filters.py` (one import at the very end of the file)
- Modify: `swingbot/core/market/strategy_types.py` (`STRATEGY_GATES`: three masked entries)
- Test: `tests/market/test_short_entries.py`

**Interfaces:**
- Consumes: `strategy_types.SHORT_STRATEGIES` (V104-1); `entry_filters.DEFAULT_PARAMS`, `ENTRY_FUNCS`, `_params`, `compute_shared_gates`.
- Produces:
  - `short_entries.BULL_TRAP, VOL_BREAKDOWN, GAP_DRIFT` (the three names, in `SHORT_STRATEGIES` order)
  - `short_entries.STOP_ATR = 0.25`
  - `short_entries.bull_trap_frame(df, horizon_key, params=None) -> pd.DataFrame` with columns `signal` (bool), `level`, `stop`, `target_a`, `target_b` (float)
  - `short_entries.FRAMES: dict[str, callable]`, and `short_entries.structure_at(strategy, df, index, horizon_key, params=None) -> dict | None` (keys `stop`, `target_a`, `target_b`)
  - `short_entries.earnings_ok(df, params) -> pd.Series`: raises `ValueError` for `exit_before` without `evt_bars_to_next`
  - `DEFAULT_PARAMS["Bull Trap"] == {"k": 3, "earnings": "hold"}`
  - `ENTRY_FUNCS["Bull Trap"]` returns `(all-False, signal)`
  - `STRATEGY_GATES[name] == {"directions": ()}` for all three

- [ ] **Step 1: Write the failing tests**

```python
# tests/market/test_short_entries.py
"""v104 §3.1: B1 Bull Trap -- a breakout that closes back below its level within k bars."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import entry_filters as ef
from swingbot.core.market import short_entries as se
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import SHORT_STRATEGIES, STRATEGY_GATES
from swingbot.core.planning.params import STRUCTURE_BUFFER_ATR
from tests.helpers import make_ohlcv

HZ = "2w"                              # sr_lookback 10
PAD = [(100.0, 101.0, 99.0, 100.0)] * 40
FLAT = [(100.0, 101.0, 99.0, 100.0)] * 3


def _frame(tail):
    return make_ohlcv(PAD + tail + FLAT, start="2015-01-02")


def _trap_next_bar():
    # b=40 closes 102 > R=101; b+1 closes 100.5 < 101 -> trap at 41
    return _frame([(100.5, 102.5, 100.0, 102.0), (101.5, 102.0, 100.0, 100.5)]), 41


def test_trap_fires_once_with_its_structure():
    df, t = _trap_next_bar()
    frame = se.bull_trap_frame(df, HZ)
    assert frame["signal"].tolist().count(True) == 1 and bool(frame["signal"].iloc[t])
    row = frame.iloc[t]
    assert row["level"] == 101.0
    assert row["stop"] == pytest.approx(102.5 + se.STOP_ATR * float(atr(df, 14).iloc[t]))
    assert row["target_a"] == 99.0 and row["target_b"] == 99.0


def test_k_bounds_how_late_the_failure_may_come():
    df = _frame([(100.5, 102.5, 100.0, 102.0), (101.8, 102.2, 101.2, 101.5),
                 (101.2, 101.6, 100.0, 100.5)])              # fails at b+2
    assert not se.bull_trap_frame(df, HZ, params={"k": 1})["signal"].any()
    assert bool(se.bull_trap_frame(df, HZ, params={"k": 2})["signal"].iloc[42])


def test_consecutive_breakouts_fire_on_distinct_bars_only():
    df = _frame([(100.5, 102.5, 100.0, 102.0),              # b1: level 101
                 (102.2, 103.5, 102.0, 103.0),              # b2: level 102.5
                 (102.4, 102.8, 101.6, 102.0),              # < 102.5 -> trap of b2 at 42
                 (101.2, 101.4, 99.5, 100.0)])              # < 101   -> trap of b1 at 43
    frame = se.bull_trap_frame(df, HZ)
    fired = list(np.flatnonzero(frame["signal"].to_numpy()))
    assert fired == [42, 43]
    assert frame["level"].iloc[42] == 102.5 and frame["level"].iloc[43] == 101.0


@pytest.mark.parametrize("k", [40, 41, 42, 45])
def test_bull_trap_frame_is_truncation_invariant(k):
    df, _ = _trap_next_bar()
    full = se.bull_trap_frame(df, HZ).iloc[k]
    cut = se.bull_trap_frame(df.iloc[:k + 1], HZ).iloc[k]
    assert bool(full["signal"]) == bool(cut["signal"])
    for col in ("level", "stop", "target_a", "target_b"):
        assert full[col] == pytest.approx(cut[col], nan_ok=True)


def test_exit_before_blocks_a_report_within_one_bar_and_needs_the_column():
    df, t = _trap_next_bar()
    with pytest.raises(ValueError):
        se.bull_trap_frame(df, HZ, params={"earnings": "exit_before"})
    df["evt_bars_to_next"] = np.nan
    assert bool(se.bull_trap_frame(df, HZ, params={"earnings": "exit_before"})["signal"].iloc[t])
    df.loc[df.index[t], "evt_bars_to_next"] = 1
    assert not se.bull_trap_frame(df, HZ, params={"earnings": "exit_before"})["signal"].any()


def test_registered_short_only_and_masked():
    df, t = _trap_next_bar()
    bull, bear = ef.ENTRY_FUNCS["Bull Trap"](df, HZ)
    assert not bull.any() and bool(bear.iloc[t])
    assert ef.DEFAULT_PARAMS["Bull Trap"] == {"k": 3, "earnings": "hold"}
    for name in SHORT_STRATEGIES:
        assert STRATEGY_GATES[name] == {"directions": ()}
    masked_bull, masked_bear = ef.entries_for("Bull Trap", df, HZ)
    assert not masked_bull.any() and not masked_bear.any()


def test_structure_at_matches_the_frame_row():
    df, t = _trap_next_bar()
    structure = se.structure_at("Bull Trap", df, t, HZ)
    assert structure["stop"] == pytest.approx(se.bull_trap_frame(df, HZ)["stop"].iloc[t])
    assert se.structure_at("Bull Trap", df, t - 1, HZ) is None
    assert se.structure_at("Bull Trap", df, -len(FLAT) - 1, HZ) is not None   # negative index


def test_stop_buffer_is_the_planning_structure_buffer():
    assert se.STOP_ATR == STRUCTURE_BUFFER_ATR
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_short_entries.py`
Expected: FAIL at import (`short_entries` is missing).

- [ ] **Step 3: Implement**

Create `swingbot/core/market/short_entries.py`:

```python
"""v104 Part B: three short-only strategies that are not mirrors of long rules.

Each strategy is a `*_frame(df, horizon_key, params)` returning per-bar
columns -- `signal` plus the structure its sizing needs -- computed from bars
<= t only (tests pin truncation invariance). ENTRY_FUNCS gets a short-only
wrapper; STRATEGY_GATES ships every name masked until its holdout shot passes.
Market layer: this module never imports planning.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.market.entry_filters import (DEFAULT_PARAMS, ENTRY_FUNCS, _params,
                                                compute_shared_gates)
from swingbot.core.market.strategy_types import HORIZONS, SHORT_STRATEGIES

BULL_TRAP, VOL_BREAKDOWN, GAP_DRIFT = SHORT_STRATEGIES
# Pinned to planning.params.STRUCTURE_BUFFER_ATR by a test (market never imports planning).
STOP_ATR = 0.25

DEFAULT_PARAMS[BULL_TRAP] = {"k": 3, "earnings": "hold"}

_COLUMNS = ("signal", "level", "stop", "target_a", "target_b")


def earnings_ok(df: pd.DataFrame, params: dict) -> pd.Series:
    """`exit_before` blocks an entry whose report reacts within one bar
    (index amendment 1); otherwise every bar is allowed. Fail-closed on a
    missing column: silently holding through would measure the wrong arm."""
    if params.get("earnings", "hold") != "exit_before":
        return pd.Series(True, index=df.index)
    if "evt_bars_to_next" not in df.columns:
        raise ValueError("exit_before needs earnings_context.attach(df, ticker) first (v104)")
    return ~(df["evt_bars_to_next"] <= 1)


def _empty(df: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame({col: np.nan for col in _COLUMNS[1:]}, index=df.index)
    frame.insert(0, "signal", False)
    return frame


def _first_traps(close, level, high, k):
    """For each breakout bar b (close > level[b]) find the first t in (b, b+k]
    closing below level[b]. The first trap claiming a bar keeps it."""
    n = len(close)
    signal = np.zeros(n, dtype=bool)
    trap_level = np.full(n, np.nan)
    peak = np.full(n, np.nan)
    source = np.full(n, -1)
    with np.errstate(invalid="ignore"):
        breakouts = np.flatnonzero(close > level)
    for b in breakouts:
        for t in range(b + 1, min(b + k, n - 1) + 1):
            if close[t] < level[b]:
                if not signal[t]:
                    signal[t], trap_level[t] = True, level[b]
                    peak[t], source[t] = high[b:t + 1].max(), b
                break
    return signal, trap_level, peak, source


def bull_trap_frame(df: pd.DataFrame, horizon_key: str, params: dict | None = None) -> pd.DataFrame:
    """B1: a close above the prior sr_lookback high that closes back below it
    within k bars. Stop above the failed high; targets the pre-breakout base."""
    p = _params(BULL_TRAP, params)
    lookback = HORIZONS[horizon_key]["sr_lookback"]
    high, low = df["High"], df["Low"]
    level = high.rolling(lookback).max().shift(1).to_numpy(dtype=float)
    signal, trap_level, peak, source = _first_traps(
        df["Close"].to_numpy(dtype=float), level, high.to_numpy(dtype=float), int(p["k"]))
    gates = compute_shared_gates(df)
    base_low = low.rolling(10).min().shift(1).to_numpy(dtype=float)
    target_a = np.where(source >= 0, base_low[np.clip(source, 0, None)], np.nan)
    keep = pd.Series(signal, index=df.index) & gates["atr_floor"] & gates["vol_ok"] & earnings_ok(df, p)
    return pd.DataFrame({
        "signal": keep.fillna(False).astype(bool),
        "level": trap_level,
        "stop": peak + STOP_ATR * gates["atr14"].to_numpy(dtype=float),
        "target_a": target_a,
        "target_b": low.rolling(lookback).min().shift(1).to_numpy(dtype=float),
    }, index=df.index)


FRAMES = {BULL_TRAP: bull_trap_frame}


def _short_only(frame_fn):
    def entries(df, horizon_key, params=None):
        bearish = frame_fn(df, horizon_key, params)["signal"]
        return pd.Series(False, index=df.index), bearish
    return entries


def structure_at(strategy: str, df: pd.DataFrame, index: int, horizon_key: str,
                 params: dict | None = None) -> dict | None:
    """The signal bar's structure computed from bars <= index, else None."""
    if index < 0:
        index += len(df)
    row = FRAMES[strategy](df.iloc[:index + 1], horizon_key, params).iloc[-1]
    if not bool(row["signal"]):
        return None
    return {key: float(row[key]) for key in ("stop", "target_a", "target_b")}


def _register() -> None:
    for name, frame_fn in FRAMES.items():
        ENTRY_FUNCS[name] = _short_only(frame_fn)


_register()
```

In `swingbot/core/market/entry_filters.py`, at the **very end** of the file:

```python


# v104 Part B registers its short-only strategies into ENTRY_FUNCS and
# DEFAULT_PARAMS. Imported last: short_entries imports names defined above.
from swingbot.core.market import short_entries  # noqa: E402,F401
```

In `swingbot/core/market/strategy_types.py`, inside `STRATEGY_GATES`, directly after the `"Fibonacci Continuation": {"directions": ()},` line:

```python
    # v104 Part B shorts ship masked until their 2026 holdout shot passes.
    "Bull Trap": {"directions": ()},
    "Vol Expansion Breakdown": {"directions": ()},
    "Earnings Gap Drift": {"directions": ()},
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_short_entries.py`. Expected: PASS (11).
Then `git grep -ln "ENTRY_FUNCS" -- swingbot tests scripts`. Run each **test** file listed. If one asserts the exact set or count of `ENTRY_FUNCS` keys, add the new name(s) to its expected set, as a registry pin. If a non-test module iterates `ENTRY_FUNCS` to render something user-visible (a list in the admin or a Discord command), note the file in the commit body. The masked gate means those surfaces see no signals, but a name may appear in a list; that is acceptable while masked, and V104-19 revisits it if a short ships.

- [ ] **Step 5: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/core/market/short_entries.py`. Expected: no output.

```bash
git add swingbot/core/market/short_entries.py swingbot/core/market/entry_filters.py swingbot/core/market/strategy_types.py tests/market/test_short_entries.py
git commit -m "feat(v104): B1 Bull Trap -- failed-breakout short entries, masked (short_entries module)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V104-10: B2 Vol Expansion Breakdown and B3 Earnings Gap Drift entries

**Files:**
- Modify: `swingbot/core/market/short_entries.py`
- Test: `tests/market/test_short_entries_b2_b3.py`

**Interfaces:**
- Consumes: `ctx_spy_down`, `ctx_spy_ret63` (V104-7); `evt_reaction`, `evt_bars_to_next` (V104-8); `earnings_ok`, `_empty`, `FRAMES`, `_register` (V104-9).
- Produces:
  - `short_entries.vol_breakdown_frame(df, horizon_key, params=None)` and `short_entries.gap_drift_frame(df, horizon_key, params=None)`, same columns as B1. `target_a` and `target_b` are `NaN`: B2 and B3 take swing lows in sizing (V104-11).
  - `DEFAULT_PARAMS["Vol Expansion Breakdown"] == {"m": 1.0, "earnings": "hold"}`
  - `DEFAULT_PARAMS["Earnings Gap Drift"] == {"g": 0.05}`
  - Both registered in `FRAMES` and `ENTRY_FUNCS`. Without their context columns they return no signals (Review Focus 2).

- [ ] **Step 1: Write the failing tests**

```python
# tests/market/test_short_entries_b2_b3.py
"""v104 §3.2 B2 Vol Expansion Breakdown and §3.3 B3 Earnings Gap Drift."""
import numpy as np
import pytest

from swingbot.core.market import entry_filters as ef
from swingbot.core.market import short_entries as se
from swingbot.core.market.indicators import atr
from tests.helpers import make_ohlcv

HZ = "2w"                                          # sr_lookback 10


def _breakdown():
    """80 flat bars, a 20-bar grind lower, then a wide high-volume breakdown bar."""
    pad = [(100.0, 101.0, 99.0, 100.0)] * 80
    grind = []
    close = 100.0
    for _ in range(20):
        close -= 0.5
        grind.append((close + 0.3, close + 1.0, close - 1.0, close))
    crash = [(89.0, 89.5, 84.0, 84.5)]
    df = make_ohlcv(pad + grind + crash, start="2015-01-02")
    df.loc[df.index[-1], "Volume"] = 3_000_000.0
    df["ctx_spy_down"] = 1.0
    df["ctx_spy_ret63"] = 0.0
    return df, len(df) - 1


def test_breakdown_fires_on_the_crash_bar_only():
    df, t = _breakdown()
    frame = se.vol_breakdown_frame(df, HZ)
    assert list(np.flatnonzero(frame["signal"].to_numpy())) == [t]
    support = df["Low"].rolling(10).min().shift(1).iloc[t]
    assert frame["stop"].iloc[t] == pytest.approx(support + se.STOP_ATR * float(atr(df, 14).iloc[t]))


def test_breakdown_needs_expanding_volatility_per_m():
    df, t = _breakdown()
    ratio = float(atr(df, 14).iloc[t] / atr(df, 14).rolling(60).mean().iloc[t])
    assert 1.0 <= ratio < 1.4, "fixture must sit between the loosest and tightest m"
    assert bool(se.vol_breakdown_frame(df, HZ, params={"m": 1.0})["signal"].iloc[t])
    assert not se.vol_breakdown_frame(df, HZ, params={"m": 1.4})["signal"].any()


@pytest.mark.parametrize("change", [
    {"ctx_spy_down": 0.0},                         # market not falling
    {"ctx_spy_ret63": -0.50},                      # stock not weaker than SPY
])
def test_breakdown_needs_a_falling_market_and_relative_weakness(change):
    df, _ = _breakdown()
    for col, value in change.items():
        df[col] = value
    assert not se.vol_breakdown_frame(df, HZ)["signal"].any()


def test_breakdown_without_market_context_is_silent():
    df, _ = _breakdown()
    df = df.drop(columns=["ctx_spy_down", "ctx_spy_ret63"])
    assert not se.vol_breakdown_frame(df, HZ)["signal"].any()


def _gap(open_=93.0, next_close=91.0):
    pad = [(100.0, 101.0, 99.0, 100.0)] * 80
    gap_day = (open_, 94.0, 91.5, 92.0)
    after = [(92.0, 92.5, 90.5, next_close), (91.0, 91.5, 90.0, 90.5)]
    df = make_ohlcv(pad + [gap_day] + after, start="2015-01-02")
    df["evt_reaction"] = 0.0
    df.loc[df.index[80], "evt_reaction"] = 1.0
    df["evt_bars_to_next"] = np.nan
    return df, 81


def test_gap_drift_enters_the_day_after_a_held_gap():
    df, t = _gap()
    frame = se.gap_drift_frame(df, HZ)
    assert list(np.flatnonzero(frame["signal"].to_numpy())) == [t]
    assert frame["stop"].iloc[t] == pytest.approx(94.0 + se.STOP_ATR * float(atr(df, 14).iloc[t]))


def test_gap_drift_grid_and_recovery():
    df, _ = _gap(open_=93.0)
    assert not se.gap_drift_frame(df, HZ, params={"g": 0.08})["signal"].any()    # 7% gap < 8%
    df, _ = _gap(next_close=92.5)                                                # recovered
    assert not se.gap_drift_frame(df, HZ)["signal"].any()


def test_gap_drift_needs_earnings_context_and_a_reaction_day():
    df, _ = _gap()
    assert not se.gap_drift_frame(df.drop(columns=["evt_reaction"]), HZ)["signal"].any()
    df["evt_reaction"] = 0.0
    assert not se.gap_drift_frame(df, HZ)["signal"].any()


@pytest.mark.parametrize("builder,cut", [(_breakdown, 95), (_breakdown, 100), (_gap, 80), (_gap, 81)])
def test_b2_b3_are_truncation_invariant(builder, cut):
    df, _ = builder()
    frame_fn = se.vol_breakdown_frame if builder is _breakdown else se.gap_drift_frame
    full = frame_fn(df, HZ).iloc[cut]
    part = frame_fn(df.iloc[:cut + 1], HZ).iloc[cut]
    assert bool(full["signal"]) == bool(part["signal"])
    assert full["stop"] == pytest.approx(part["stop"], nan_ok=True)


def test_registration():
    assert ef.DEFAULT_PARAMS["Vol Expansion Breakdown"] == {"m": 1.0, "earnings": "hold"}
    assert ef.DEFAULT_PARAMS["Earnings Gap Drift"] == {"g": 0.05}
    for name in ("Vol Expansion Breakdown", "Earnings Gap Drift"):
        assert name in ef.ENTRY_FUNCS and name in se.FRAMES
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_short_entries_b2_b3.py`
Expected: FAIL (`vol_breakdown_frame` is missing).

- [ ] **Step 3: Implement**

In `swingbot/core/market/short_entries.py`:
- Add `SR_VOLUME_MULTIPLE` to the `strategy_types` import.
- Next to `DEFAULT_PARAMS[BULL_TRAP] = ...`, add:

```python
DEFAULT_PARAMS[VOL_BREAKDOWN] = {"m": 1.0, "earnings": "hold"}
DEFAULT_PARAMS[GAP_DRIFT] = {"g": 0.05}
_SPY_COLUMNS = ("ctx_spy_down", "ctx_spy_ret63")
```

Add below `bull_trap_frame`:

```python
def vol_breakdown_frame(df: pd.DataFrame, horizon_key: str, params: dict | None = None) -> pd.DataFrame:
    """B2: a close under the prior sr_lookback low, in a falling market (SPY below
    a falling MA50), on heavy volume, with ATR EXPANDING (>= m x its 60-bar mean,
    the reverse of atr_calm), by a name weaker than SPY over 63 bars. Without the
    market-context block there is no signal (silent while masked)."""
    p = _params(VOL_BREAKDOWN, params)
    if not all(col in df.columns for col in _SPY_COLUMNS):
        return _empty(df)
    lookback = HORIZONS[horizon_key]["sr_lookback"]
    gates = compute_shared_gates(df)
    close, atr14 = df["Close"], gates["atr14"]
    support = df["Low"].rolling(lookback).min().shift(1)
    market_down = df["ctx_spy_down"] == 1.0
    weaker = (close / close.shift(63) - 1.0) < df["ctx_spy_ret63"]
    heavy = df["Volume"] >= SR_VOLUME_MULTIPLE * df["Volume"].rolling(20).mean()
    expanding = atr14 >= float(p["m"]) * atr14.rolling(60).mean()
    signal = ((close < support) & market_down & weaker & heavy & expanding
              & gates["atr_floor"] & earnings_ok(df, p))
    frame = _empty(df)
    frame["signal"] = signal.fillna(False).astype(bool)
    frame["level"] = support.to_numpy(dtype=float)
    frame["stop"] = (support + STOP_ATR * atr14).to_numpy(dtype=float)
    return frame


def gap_drift_frame(df: pd.DataFrame, horizon_key: str, params: dict | None = None) -> pd.DataFrame:
    """B3: the session after an earnings reaction that gapped down >= g and did
    not recover (close below the reaction day's close). Stop above the reaction
    day's high. Horizon-independent entry. Without earnings context, no signal."""
    p = _params(GAP_DRIFT, params)
    if "evt_reaction" not in df.columns:
        return _empty(df)
    close = df["Close"]
    gap_day = (df["evt_reaction"] == 1.0) & (df["Open"] <= close.shift(1) * (1.0 - float(p["g"])))
    after_gap = gap_day.shift(1, fill_value=False).astype(bool)
    signal = after_gap & (close < close.shift(1))
    gates = compute_shared_gates(df)
    frame = _empty(df)
    frame["signal"] = signal.fillna(False).astype(bool)
    frame["level"] = close.shift(1).to_numpy(dtype=float)
    frame["stop"] = (df["High"].shift(1) + STOP_ATR * gates["atr14"]).to_numpy(dtype=float)
    return frame
```

Change `FRAMES = {BULL_TRAP: bull_trap_frame}` to:

```python
FRAMES = {BULL_TRAP: bull_trap_frame, VOL_BREAKDOWN: vol_breakdown_frame, GAP_DRIFT: gap_drift_frame}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_short_entries_b2_b3.py` (PASS), then `tests/market/test_short_entries.py` (PASS, unchanged).

- [ ] **Step 5: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/core/market/short_entries.py`. Expected: no output.

```bash
git add swingbot/core/market/short_entries.py tests/market/test_short_entries_b2_b3.py
git commit -m "feat(v104): B2 Vol Expansion Breakdown and B3 Earnings Gap Drift short entries, masked

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V104-11: Short sizing, builder and backtest wiring, hold cap

**Files:**
- Create: `swingbot/core/planning/short_builders.py`
- Modify: `swingbot/core/planning/builders.py` (`_short_branch`, registered in `_STRUCTURAL_BRANCHES`)
- Modify: `swingbot/core/backtesting/backtest.py` (`_trade_plan_at` gets one `elif`, plus a helper `_short_plan_at`; the `TradePlanV2(...)` call in `run_backtest` gets one keyword)
- Modify: `swingbot/core/planning/params.py` (`EXIT_V2_PARAMS`: three rows. Without them the shorts would inherit the default `tp2: True`, and the spec fixes TP2 off.)
- Test: `tests/planning/test_short_builders.py`

**Interfaces:**
- Consumes: `short_entries.structure_at`, `short_entries.BULL_TRAP` (V104-9/10); `stop_scope.stop_ceiling` (V104-1); `TradePlanV2.hold_cap_bars` (V104-8).
- Produces:
  - `short_builders.plan_short(df, index, strategy, horizon_key, direction, *, entry, atr_val, scan_params=None) -> tuple[float, float, list[float]] | None`, i.e. `(stop, tp1, candidates)`. It is `None` for bullish, for no structure, or for a stop beyond the ceiling or on the wrong side.
  - `short_builders.short_hold_cap(df, index, strategy) -> int | None`
  - `builders._short_branch(inputs)`
  - `backtest._short_plan_at(df, i, strategy, horizon_key, direction, entry, atr_val) -> tuple[tuple | None, list]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/planning/test_short_builders.py
"""v104 §3 sizing: structure stop verbatim (<= max_risk_pct) or no plan; targets below entry."""
import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting.backtest import run_backtest
from swingbot.core.market import short_entries as se
from swingbot.core.market.entry_filters import DEFAULT_PARAMS, gate_override
from swingbot.core.market.indicators import atr
from swingbot.core.planning import short_builders as sb
from swingbot.core.planning.builders import build_strategy_plan
from tests.helpers import make_ohlcv
from tests.market.test_short_entries import HZ, PAD

# b=40 breaks out, t=41 traps; 20 quiet bars after so an uncapped short can
# run to its 14-bar 2w timeout inside the frame (stop 103 and TP1 ~96.5 are never touched).
TRAP = [(100.5, 102.5, 100.0, 102.0), (101.5, 102.0, 100.0, 100.5)]


@pytest.fixture(autouse=True)
def rr(monkeypatch):
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5, raising=False)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5, raising=False)
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)


def _inputs():
    df = make_ohlcv(PAD + TRAP + [(100.0, 101.0, 99.0, 100.0)] * 20, start="2015-01-02")
    t = 41
    return df, t, float(df["Close"].iloc[t]), float(atr(df, 14).iloc[t])


def test_plan_short_uses_the_structure_stop_and_a_lower_target():
    df, t, entry, atr_val = _inputs()
    stop, tp1, candidates = sb.plan_short(df, t, "Bull Trap", HZ, "bearish", entry=entry, atr_val=atr_val)
    assert stop == pytest.approx(se.structure_at("Bull Trap", df, t, HZ)["stop"])
    risk = stop - entry
    assert entry - tp1 >= 1.5 * risk - 1e-9 and entry - tp1 <= 2.5 * risk + 1e-9
    assert 99.0 in candidates


def test_plan_short_refuses_bullish_and_non_signal_bars():
    df, t, entry, atr_val = _inputs()
    assert sb.plan_short(df, t, "Bull Trap", HZ, "bullish", entry=entry, atr_val=atr_val) is None
    assert sb.plan_short(df, t - 1, "Bull Trap", HZ, "bearish", entry=entry, atr_val=atr_val) is None


def test_plan_short_drops_a_stop_beyond_max_risk_pct(monkeypatch):
    df, t, entry, atr_val = _inputs()
    monkeypatch.setattr(sb, "structure_at", lambda *a, **k: {"stop": entry * 1.05, "target_a": np.nan,
                                                             "target_b": np.nan})
    assert sb.plan_short(df, t, "Bull Trap", HZ, "bearish", entry=entry, atr_val=atr_val) is None  # 5% > 3% (2w)


def test_hold_cap_reads_the_earnings_setting(monkeypatch):
    df, t, _, _ = _inputs()
    assert sb.short_hold_cap(df, t, "Bull Trap") is None                        # hold
    assert sb.short_hold_cap(df, t, "MACD") is None
    monkeypatch.setitem(DEFAULT_PARAMS["Bull Trap"], "earnings", "exit_before")
    with pytest.raises(ValueError):
        sb.short_hold_cap(df, t, "Bull Trap")
    df["evt_bars_to_next"] = np.nan
    assert sb.short_hold_cap(df, t, "Bull Trap") is None
    df.loc[df.index[t], "evt_bars_to_next"] = 4
    assert sb.short_hold_cap(df, t, "Bull Trap") == 3


def test_build_strategy_plan_builds_the_short():
    df, t, _, _ = _inputs()
    plan = build_strategy_plan(df, t, ticker="TEST", strategy="Bull Trap", horizon_key=HZ, direction="bearish")
    assert plan is not None and plan.direction == "bearish" and plan.stop_loss > plan.trigger_price > plan.tp1
    assert plan.trail_atr_mult == 2.5 and plan.tp2 is None          # spec §3: trail 2.5, TP2 off


def test_backtest_trades_the_short_and_honours_the_hold_cap(monkeypatch):
    df, t, _, _ = _inputs()
    with gate_override("Bull Trap", {"directions": ("bearish",)}):
        free = run_backtest("TEST", df, "Bull Trap", HZ, exit_model="v2", scale_out=True)
        monkeypatch.setitem(DEFAULT_PARAMS["Bull Trap"], "earnings", "exit_before")
        df["evt_bars_to_next"] = np.nan
        df.loc[df.index[t], "evt_bars_to_next"] = 3
        capped = run_backtest("TEST", df, "Bull Trap", HZ, exit_model="v2", scale_out=True)
    assert len(free.trades) == 1 and free.trades[0].direction == "bearish"
    assert len(capped.trades) == 1 and capped.trades[0].holding_days <= 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_short_builders.py`
Expected: FAIL at import (`short_builders` is missing).

- [ ] **Step 3: Implement**

Create `swingbot/core/planning/short_builders.py`:

```python
"""v104 Part B sizing: the structure stop verbatim (drop, never cap), TP1 from
the ATR ladder plus each strategy's own lower levels. Shared by the live
builder branch and backtest._trade_plan_at, so the two cannot diverge."""
from __future__ import annotations

import math

import pandas as pd

from swingbot.core.market.entry_filters import DEFAULT_PARAMS
from swingbot.core.market.indicators import zigzag_pivots
from swingbot.core.market.short_entries import BULL_TRAP, structure_at
from swingbot.core.market.strategy_types import HORIZONS, SHORT_STRATEGIES
from swingbot.core.risk_limits import planned_loss_pct
from .stop_scope import stop_ceiling
from .targets import atr_target_candidates, select_structural_target


def _swing_lows_below(df, index, horizon_key, entry):
    pivots = zigzag_pivots(df.iloc[:index + 1], HORIZONS[horizon_key]["max_risk_pct"])
    return [float(price) for _, price, kind in pivots if kind == "low" and price < entry]


def _candidates(strategy, df, index, horizon_key, entry, atr_val, structure):
    candidates = atr_target_candidates(entry, atr_val, "bearish")
    if strategy == BULL_TRAP:
        return candidates + [v for v in (structure["target_a"], structure["target_b"]) if math.isfinite(v)]
    return candidates + _swing_lows_below(df, index, horizon_key, entry)


def _valid_stop(strategy, horizon_key, entry, stop):
    if not math.isfinite(stop) or stop <= entry:
        return False
    ceiling_pct, _ = stop_ceiling(strategy, "bearish", horizon_key)
    return planned_loss_pct(entry, stop) <= ceiling_pct + 1e-9


def plan_short(df, index, strategy, horizon_key, direction, *, entry, atr_val, scan_params=None):
    """(stop, tp1, candidates) for a v104 short at `index`, else None."""
    if direction != "bearish" or strategy not in SHORT_STRATEGIES:
        return None
    structure = structure_at(strategy, df, index, horizon_key)
    if structure is None or not _valid_stop(strategy, horizon_key, entry, structure["stop"]):
        return None
    if scan_params is None:
        from swingbot.scan_params import ScanParams
        scan_params = ScanParams.from_config()
    candidates = _candidates(strategy, df, index, horizon_key, entry, atr_val, structure)
    tp1 = select_structural_target(entry, structure["stop"], False, candidates,
                                   scan_params.min_risk_reward_ratio, scan_params.max_risk_reward_ratio)
    return None if tp1 is None else (structure["stop"], tp1, candidates)


def short_hold_cap(df, index, strategy):
    """Bars to hold a short on its `exit_before` setting: the bar before the
    next report reacts. None when holding through or no report is known."""
    if strategy not in SHORT_STRATEGIES:
        return None
    if DEFAULT_PARAMS[strategy].get("earnings", "hold") != "exit_before":
        return None
    if "evt_bars_to_next" not in df.columns:
        raise ValueError(f"{strategy} exit_before needs earnings_context.attach(df, ticker) (v104)")
    bars = df["evt_bars_to_next"].iloc[index]
    return None if pd.isna(bars) else max(int(bars) - 1, 1)
```

In `swingbot/core/planning/params.py`, add these rows at the end of `EXIT_V2_PARAMS`, after the `"Fibonacci Continuation"` row. They are fixed by the spec, not a TRAIN grid:

```python
    # v104 Part B shorts: fixed by spec §3 (not a TRAIN-grid result).
    "Bull Trap":               {"trail_atr_mult": 2.5, "tp2": False},
    "Vol Expansion Breakdown": {"trail_atr_mult": 2.5, "tp2": False},
    "Earnings Gap Drift":      {"trail_atr_mult": 2.5, "tp2": False},
```

In `swingbot/core/planning/builders.py`:
- Add `SHORT_STRATEGIES` to the `strategy_types` import.
- Add this directly above `_STRUCTURAL_BRANCHES = {`:

```python
def _short_branch(inputs):
    """v104 Part B shorts: planning/short_builders.py."""
    from .short_builders import plan_short

    picked = plan_short(inputs.df, inputs.index, inputs.strategy, inputs.horizon_key,
                        inputs.direction, entry=inputs.close, atr_val=inputs.atr_val,
                        scan_params=inputs.scan_params)
    if picked is None:
        return None
    return _branch_result(picked[:2], picked[2])
```

- Add this directly below the `_STRUCTURAL_BRANCHES = {...}` literal:

```python
_STRUCTURAL_BRANCHES.update({name: _short_branch for name in SHORT_STRATEGIES})
```

In `swingbot/core/backtesting/backtest.py`:
- Add `SHORT_STRATEGIES` to the `strategy_types` import.
- Add this helper directly above `_trade_plan_at`:

```python
def _short_plan_at(df, i, strategy, horizon_key, direction, entry, atr_val):
    """((stop, tp1) | None, candidates) for a v104 short -- one call site keeps
    _trade_plan_at's complexity flat."""
    from swingbot.core.planning.short_builders import plan_short
    picked = plan_short(df, i, strategy, horizon_key, direction, entry=entry, atr_val=atr_val)
    if picked is None:
        return None, []
    return picked[:2], picked[2]
```

- In `_trade_plan_at`, directly before the final `else:` (the ATR branch):

```python
    elif strategy in SHORT_STRATEGIES:
        result, candidates = _short_plan_at(df, i, strategy, horizon_key, direction, entry, atr_val)
```

- In `run_backtest`, in the v2 `TradePlanV2(` call, add one keyword after `trail_atr_mult=_exit_params["trail_atr_mult"],`:

```python
                hold_cap_bars=short_hold_cap(df, i, strategy),
```

  with the import `from swingbot.core.planning.short_builders import short_hold_cap` added to that block's existing lazy `from swingbot.core.planning.plan_engine import (...)` line group (a separate `from ... import` line directly below it). This adds no branch to `run_backtest`.

- [ ] **Step 4: Run the tests to verify they pass**

Run each with `python scripts/dev/testrun.py file <path>`:
- `tests/planning/test_short_builders.py`: PASS (6).
- `tests/backtesting/test_sizing_parity.py`, `tests/planning/test_build_strategy_plan.py`, `tests/planning/test_fib_continuation_builder.py`, `tests/backtesting/test_backtest_engine.py`: PASS, unchanged.

- [ ] **Step 5: Complexity, commit, fast tier**

Run: `python -m radon cc -s -n C swingbot/core/planning/short_builders.py swingbot/core/planning/builders.py swingbot/core/backtesting/backtest.py`.
Expected: `_trade_plan_at` at most 13, `run_backtest` unchanged at 59, nothing new at or above 15.

```bash
git add swingbot/core/planning/short_builders.py swingbot/core/planning/builders.py swingbot/core/planning/params.py swingbot/core/backtesting/backtest.py tests/planning/test_short_builders.py
git commit -m "feat(v104): short sizing (structure stop or no plan) wired into live builders and the backtest, with the earnings hold cap

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Run: `python scripts/dev/testrun.py fast`. Expected: `0 failed`, `0 xfailed`, before V104-12 starts.
