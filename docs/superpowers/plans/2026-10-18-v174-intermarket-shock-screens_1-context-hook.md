# v174 Intermarket shock screens, part 1: context hook (V174-1..V174-5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: pull one task with `grep -n "^### Task V174-3:" -A 400 <this file>`.

**Spec:** [`docs/superpowers/specs/2026-10-18-v174-intermarket-shock-screens-design.md`](../specs/2026-10-18-v174-intermarket-shock-screens-design.md)
**Index:** [`2026-10-18-v174-intermarket-shock-screens_0-index.md`](2026-10-18-v174-intermarket-shock-screens_0-index.md) holds the Goal, Global Constraints, Parallelisation, Where to work and the task ledger. Every task below implicitly includes the index's Global Constraints.

Scope of this part: the worktree; the point-in-time context math and load checks in a new pure module `swingbot/core/backtesting/screen/context.py`; the registry field `Idea.context` and the table-driven `events` seam in `scripts/backtest/screen_idea.py`, pinned by a real-call-path parity test; context loading once per universe with load and hash refusals in `main`; the one-off TLT/UUP fetch.

Shorthand used in every task: `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens`. Never `cd`; use absolute paths and `git -C $WT`. A PreToolUse hook rejects Bash commands that contain the runner's file name with an unbalanced quote: create and edit files with Write/Edit only, and keep Bash commands that name the runner free of apostrophes.

# Phase 1: context math and the call seam

### Task V174-1: Worktree; point-in-time context math

**Model:** opus — no-lookahead territory: trailing z and exact-date alignment

**Files:**
- Create: `swingbot/core/backtesting/screen/context.py`
- Create: `tests/backtesting/screen/test_context.py`

**Interfaces:**
- Consumes: `tests.backtesting.screen.helpers.random_walk`, `assert_prefix_stable` (exist, `tests/backtesting/screen/helpers.py`).
- Produces (all in `swingbot/core/backtesting/screen/context.py`):
  - `CONTEXT_START = "2009-06-01"`, `LOOKBACK = 5`, `Z_WINDOW = 252`, `STD_FLOOR = 1e-12`
  - `r_lookback(close: pd.Series, lookback: int = LOOKBACK) -> pd.Series` — `close(t) / close(t - lookback) - 1` by row offset, float.
  - `trailing_z(close: pd.Series, lookback: int = LOOKBACK, window: int = Z_WINDOW) -> pd.Series` — float, index `close.index`, name `"z"`; NaN where W has < `window` values, any NaN in W or `r(t)`, or `std(W, ddof=0) <= STD_FLOOR`. W = `r[t-window .. t-1]`, never t.
  - `z_gate(z: pd.Series, threshold: float) -> pd.Series` — `z >= threshold` when `threshold > 0`, else `z <= threshold`; `.fillna(False)`, `bool` dtype.
  - `context_on(df_index: pd.DatetimeIndex, series: pd.Series) -> pd.Series` — exact-date reindex onto `df_index`, missing date `False`, never forward-filled, `bool` dtype.
  - `near_mask(raw: np.ndarray, cap: int) -> np.ndarray` — `bool`, True at i when some True position p in `raw` has `|i - p| < cap`.
- V174-2 appends load checks and `ContextData` to the same module; V174-6 (part 2) builds both ideas from `trailing_z`, `z_gate`, `context_on`; V174-7/V174-8 use `r_lookback` and `near_mask`.

- [ ] **Step 1: Create the worktree**

Invoke the `worktree-lifecycle` skill first. If `git -C E:/Documents/Private/Projects/Discord-Bot worktree list` already shows `.claude/worktrees/2026-10-18-v174-intermarket-shock-screens`, reuse it and skip the add. Otherwise:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens -b 2026-10-18-v174-intermarket-shock-screens main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens status --short
```

Expected: the add prints `Preparing worktree (new branch ...)`; status prints nothing.

- [ ] **Step 2: Write the failing tests**

Create `$WT/tests/backtesting/screen/test_context.py` with the Write tool:

```python
"""v174 context hook: point-in-time r5, trailing z, gates and exact-date alignment."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import context
from tests.backtesting.screen.helpers import assert_prefix_stable, random_walk


def _closes(values, start="2010-01-04"):
    return pd.Series(np.asarray(values, dtype=float),
                     index=pd.bdate_range(start, periods=len(values)))


# --- frozen constants -------------------------------------------------------

def test_the_frozen_constants():
    assert context.CONTEXT_START == "2009-06-01"
    assert (context.LOOKBACK, context.Z_WINDOW) == (5, 252)
    assert context.STD_FLOOR == 1e-12


# --- r_lookback -------------------------------------------------------------

def test_r_lookback_is_a_row_offset_return():
    r = context.r_lookback(_closes([100.0, 110.0, 121.0, 60.5]), lookback=1)
    assert np.isnan(r.iloc[0])
    assert r.iloc[1:].tolist() == pytest.approx([0.1, 0.1, -0.5])


def test_r_lookback_defaults_to_five_bars():
    close = _closes(np.arange(1.0, 12.0))
    r = context.r_lookback(close)
    assert r.iloc[:5].isna().all()
    assert r.iloc[5] == pytest.approx(6.0 / 1.0 - 1.0)
    assert r.iloc[10] == pytest.approx(11.0 / 6.0 - 1.0)


# --- trailing_z: hand-computed values ---------------------------------------

def test_trailing_z_matches_hand_computed_values_and_excludes_t():
    # lookback 1: r = [nan, 1, 1, 0, -0.5, 2]
    z = context.trailing_z(_closes([1.0, 2.0, 4.0, 4.0, 2.0, 6.0]), lookback=1, window=3)
    # t = 4: W = r[1..3] = [1, 1, 0] (t itself is NOT in W)
    w4 = np.array([1.0, 1.0, 0.0])
    assert z.iloc[4] == pytest.approx((-0.5 - w4.mean()) / w4.std(ddof=0))
    assert z.iloc[4] == pytest.approx((-0.5 - 2.0 / 3.0) / np.sqrt(2.0 / 9.0))
    # t = 5: W = r[2..4] = [1, 0, -0.5]
    w5 = np.array([1.0, 0.0, -0.5])
    assert z.iloc[5] == pytest.approx((2.0 - w5.mean()) / w5.std(ddof=0))
    # had t been inside W, z(5) would use [0, -0.5, 2]: a different number
    inside = np.array([0.0, -0.5, 2.0])
    assert z.iloc[5] != pytest.approx((2.0 - inside.mean()) / inside.std(ddof=0))
    # t <= 3: W reaches the NaN r(0) or is short
    assert z.iloc[:4].isna().all()


def test_trailing_z_is_float_named_z_on_the_close_index():
    close = random_walk(300)["Close"]
    z = context.trailing_z(close)
    assert z.dtype == float and z.name == "z"
    assert z.index.equals(close.index)


# --- trailing_z: every undefined case is NaN --------------------------------

def test_fewer_than_252_window_values_give_nan():
    z = context.trailing_z(random_walk(300)["Close"])
    # r5 is defined from bar 5; W = r5[t-252..t-1] is full from t = 257
    assert z.iloc[:257].isna().all()
    assert z.iloc[257:].notna().all()


def test_a_nan_inside_the_window_gives_nan():
    close = random_walk(700)["Close"].copy()
    close.iloc[400] = np.nan                  # r5 is NaN at bars 400 and 405
    z = context.trailing_z(close)
    assert z.iloc[300:400].notna().all()      # W ends at 399: clean
    assert z.iloc[401:658].isna().all()       # W holds r5(400) or r5(405)
    assert z.iloc[658:].notna().all()         # W = r5[406..657]: clean again


def test_a_nan_r_at_t_gives_nan():
    close = random_walk(400)["Close"].copy()
    close.iloc[350] = np.nan
    z = context.trailing_z(close)
    assert np.isnan(z.iloc[350])              # r5(350) is NaN
    assert np.isnan(z.iloc[355])              # r5(355) reads close(350)


def test_a_flat_window_gives_nan_even_on_a_jump():
    values = np.full(300, 100.0)
    values[280:] = 150.0                      # r5(280) = 0.5, W before it is all 0
    z = context.trailing_z(_closes(values))
    assert np.isnan(z.iloc[280])
    assert z.iloc[257:281].isna().all()       # std(W) == 0 on the flat stretch


# --- z_gate -----------------------------------------------------------------

def test_z_gate_reads_the_sign_of_the_threshold():
    z = pd.Series([2.5, 2.0, 1.9, np.nan, -2.0, -2.1])
    assert context.z_gate(z, 2.0).tolist() == [True, True, False, False, False, False]
    assert context.z_gate(z, -2.0).tolist() == [False, False, False, False, True, True]


def test_z_gate_is_bool_and_nan_is_false():
    gate = context.z_gate(pd.Series([np.nan, np.nan]), 2.0)
    assert gate.dtype == bool and not gate.any()


# --- context_on -------------------------------------------------------------

def test_context_on_matches_exact_dates():
    days = pd.to_datetime(["2012-03-05", "2012-03-06", "2012-03-07"])
    series = pd.Series([True, False, True], index=days)
    out = context.context_on(days, series)
    assert out.tolist() == [True, False, True]
    assert out.dtype == bool and out.index.equals(days)


def test_a_stock_date_missing_from_the_context_is_false_never_forward_filled():
    series = pd.Series([True], index=pd.to_datetime(["2012-03-05"]))
    stock = pd.to_datetime(["2012-03-05", "2012-03-06"])
    assert context.context_on(stock, series).tolist() == [True, False]


def test_a_context_only_date_is_ignored():
    series = pd.Series([True, True], index=pd.to_datetime(["2012-03-05", "2012-03-06"]))
    stock = pd.to_datetime(["2012-03-06"])
    out = context.context_on(stock, series)
    assert out.index.equals(stock) and out.tolist() == [True]


def test_context_on_matches_dates_exactly_not_by_day():
    series = pd.Series([True], index=pd.to_datetime(["2012-03-05 16:00"]))
    assert context.context_on(pd.to_datetime(["2012-03-05"]), series).tolist() == [False]


# --- no lookahead -----------------------------------------------------------

def test_trailing_z_and_its_gate_are_prefix_stable():
    df = random_walk(700, seed=3)
    checkpoints = [257, 300, 451, 699]
    assert_prefix_stable(lambda d: context.trailing_z(d["Close"]), df, checkpoints)
    assert_prefix_stable(lambda d: context.z_gate(context.trailing_z(d["Close"]), 1.0),
                         df, checkpoints)


def test_changing_a_context_bar_after_t_never_changes_the_event_at_t():
    ctx = random_walk(800, seed=5, start="2009-06-01")
    stock = ctx.index[::2]                    # a stock calendar inside the context calendar

    def event(frame):
        return context.context_on(stock, context.z_gate(context.trailing_z(frame["Close"]), 1.0))

    before = event(ctx)
    assert before.any()                       # the test has events to protect
    t = ctx.index[600]
    later = ctx.copy()
    later.loc[later.index > t, "Close"] *= 3.0
    after = event(later)
    pd.testing.assert_series_equal(before[before.index <= t], after[after.index <= t])
    assert not before[before.index > t].equals(after[after.index > t])


# --- near_mask --------------------------------------------------------------

def test_near_mask_marks_bars_closer_than_cap_to_a_shock():
    raw = np.zeros(10, dtype=bool)
    raw[4] = True
    assert np.flatnonzero(context.near_mask(raw, 3)).tolist() == [2, 3, 4, 5, 6]
    assert np.flatnonzero(context.near_mask(raw, 1)).tolist() == [4]


def test_near_mask_unions_shocks_and_clips_at_the_edges():
    raw = np.zeros(8, dtype=bool)
    raw[[0, 7]] = True
    assert np.flatnonzero(context.near_mask(raw, 2)).tolist() == [0, 1, 6, 7]


def test_near_mask_without_shocks_is_all_false():
    out = context.near_mask(np.zeros(5, dtype=bool), 10)
    assert out.dtype == bool and not out.any() and len(out) == 5


def test_near_mask_keeps_the_input_length_when_cap_exceeds_it():
    raw = np.zeros(5, dtype=bool)
    raw[2] = True
    out = context.near_mask(raw, 10)
    assert len(out) == 5 and out.all()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/dev/testrun.py file tests/backtesting/screen/test_context.py`
Expected: collection error, `ImportError: cannot import name 'context' from 'swingbot.core.backtesting.screen'`.

- [ ] **Step 4: Write the module**

Create `$WT/swingbot/core/backtesting/screen/context.py` with the Write tool:

```python
"""v174 context hook: other markets an idea may read, point in time.

An idea module that exports ``CONTEXT = ("TLT",)`` receives those frames as
``events(df, context)``. Everything here is pure: the trailing z of a
5-day return, the gate on it, and the exact-date alignment onto a stock's
own index. A value at t reads context bars dated <= t only, and a stock date
the context lacks is ``False``, never forward-filled (v174 spec § 1, § 3).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

#: First bar of backtest_cache_ext/SPY.csv: the context window starts here,
#: so 5 + 252 warm-up bars exist well before EVENT_START (2011-01-01).
CONTEXT_START = "2009-06-01"
LOOKBACK = 5
Z_WINDOW = 252
#: std(W) at or below this is the floating-point form of std(W) == 0.
STD_FLOOR = 1e-12


def r_lookback(close: pd.Series, lookback: int = LOOKBACK) -> pd.Series:
    """close(t) / close(t - lookback) - 1, by row offset (the contiguity
    check against SPY sessions makes the row offset a session offset)."""
    close = close.astype(float)
    return close / close.shift(lookback) - 1.0


def trailing_z(close: pd.Series, lookback: int = LOOKBACK,
               window: int = Z_WINDOW) -> pd.Series:
    """z(t) = (r(t) - mean(W)) / std(W, ddof=0), W = r[t-window .. t-1].

    W is trailing and excludes t. NaN when W is short, W or r(t) holds a
    NaN, or std(W) <= STD_FLOOR."""
    values = r_lookback(close, lookback).to_numpy(dtype=float)
    z = np.full(len(values), np.nan)
    if len(values) > window:
        win = sliding_window_view(values[:-1], window)   # win[i] = r[i .. i+window-1], t = i+window
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = win.mean(axis=1)                      # NaN when W holds a NaN
            std = win.std(axis=1)                        # population std (ddof=0)
            cur = values[window:]
            ok = np.isfinite(cur) & np.isfinite(mean) & (std > STD_FLOOR)
            z[window:] = np.where(ok, (cur - mean) / np.where(ok, std, 1.0), np.nan)
    return pd.Series(z, index=close.index, name="z", dtype=float)


def z_gate(z: pd.Series, threshold: float) -> pd.Series:
    """z >= threshold for a positive threshold, z <= threshold otherwise.
    An undefined z is no event."""
    hit = z >= threshold if threshold > 0 else z <= threshold
    return hit.fillna(False).astype(bool)


def context_on(df_index: pd.DatetimeIndex, series: pd.Series) -> pd.Series:
    """A context series on a stock's dates, by exact date. A stock date the
    context lacks is False, never forward-filled; a context-only date is
    dropped."""
    return series.astype(bool).reindex(df_index, fill_value=False).astype(bool)


def near_mask(raw: np.ndarray, cap: int) -> np.ndarray:
    """True at i when some True position p in ``raw`` has |i - p| < cap
    (the restricted-null diagnostic drops these bars from the null pool)."""
    raw = np.asarray(raw, dtype=bool)
    n = len(raw)
    pos = np.flatnonzero(raw)
    marks = np.zeros(n + 1, dtype=int)            # +1 opens a run, -1 closes it
    np.add.at(marks, np.maximum(pos - cap + 1, 0), 1)
    np.add.at(marks, np.minimum(pos + cap, n), -1)
    return np.cumsum(marks[:n]) > 0
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/dev/testrun.py file tests/backtesting/screen/test_context.py`
Expected: all tests pass, `0 failed`.

Then the import guard and complexity:

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/swingbot/core/backtesting/screen/context.py | head
```

Expected: the guard passes; radon prints nothing (every function below C).

- [ ] **Step 6: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens add swingbot/core/backtesting/screen/context.py tests/backtesting/screen/test_context.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens commit -m "feat(v174): point-in-time context math -- trailing z, gate, exact-date alignment" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: one commit on the branch; the main tree shows no new change from this task.

### Task V174-2: Context load checks and file record

**Model:** sonnet — file and index checks in one module, behaviour fixed by the spec

**Files:**
- Modify: `swingbot/core/backtesting/screen/context.py` (created by V174-1; append below `near_mask`)
- Modify: `tests/backtesting/screen/test_context.py` (created by V174-1; append at the end)

**Interfaces:**
- Consumes: V174-1's module (`trailing_z`, imports).
- Produces (in `swingbot/core/backtesting/screen/context.py`):
  - `MIN_Z_COVERAGE = 0.95`
  - `class ContextError(ValueError)` — every load check raises it; the runner turns `str(exc)` into `refused: <reason>`.
  - `check_raw_index(index: pd.Index, name: str) -> None` — refuses a non-date index, a tz-aware index, an index that is not monotonic increasing, a duplicated date, or a time other than midnight. Called on the **raw** `pd.read_csv(path, parse_dates=["Date"], index_col="Date").index`, before `load_frame` repairs anything.
  - `check_contiguous(index: pd.DatetimeIndex, sessions: pd.DatetimeIndex, name: str) -> None` — refuses when any of `sessions` is absent from `index`.
  - `check_z_coverage(z: pd.Series, sessions: pd.DatetimeIndex, name: str, *, event_start: str, minimum: float = MIN_Z_COVERAGE) -> None` — refuses when the share of `sessions >= event_start` with a defined `z` is below `minimum`.
  - `file_record(path) -> dict` — keys `ticker` (file stem), `rows` (data rows), `first`, `last` (ISO dates, `YYYY-MM-DD`), `fetched` (file mtime as an ISO date), `sha256` (hex digest of the file bytes); raises `ContextError` naming the path when the file is missing.
  - `@dataclass(frozen=True) class ContextData` with fields `frames: Mapping[str, pd.DataFrame]`, `calendar: pd.DataFrame` (the loaded SPY frame), `records: Mapping[str, dict]` (one `file_record` per frame).
- V174-4 composes these into `screen_idea.load_context`; V174-7/V174-8 (part 2) read `ContextData.calendar`, `.frames`, `.records`.

- [ ] **Step 1: Write the failing tests**

Append to `$WT/tests/backtesting/screen/test_context.py` (Write the whole file back with these lines added at the end; add `import dataclasses`, `import hashlib`, `import os` and `from datetime import date` to the import block at the top):

```python
# --- V174-2: load checks ----------------------------------------------------

def test_min_z_coverage_is_95_percent():
    assert context.MIN_Z_COVERAGE == 0.95
    assert issubclass(context.ContextError, ValueError)


def test_a_clean_raw_index_passes():
    context.check_raw_index(pd.bdate_range("2009-06-01", periods=30), "TLT")


@pytest.mark.parametrize("index, words", [
    (pd.bdate_range("2009-06-01", periods=5, tz="UTC"), "tz-aware"),
    (pd.DatetimeIndex(["2009-06-02", "2009-06-01", "2009-06-03"]), "not sorted"),
    (pd.DatetimeIndex(["2009-06-01", "2009-06-01", "2009-06-02"]), "not unique"),
    (pd.DatetimeIndex(["2009-06-01 16:00", "2009-06-02 16:00"]), "not normalised"),
    (pd.Index(["2009-06-01", "junk"]), "not a date index"),
])
def test_a_bad_raw_index_is_refused(index, words):
    with pytest.raises(context.ContextError, match=words):
        context.check_raw_index(index, "TLT")


def test_a_tz_aware_csv_read_raw_is_refused(tmp_path):
    df = random_walk(20, start="2009-06-01")
    df.index = df.index.tz_localize("UTC")
    df.rename_axis("Date").to_csv(tmp_path / "TLT.csv")
    raw = pd.read_csv(tmp_path / "TLT.csv", parse_dates=["Date"], index_col="Date")
    with pytest.raises(context.ContextError, match="TLT: .*tz-aware"):
        context.check_raw_index(raw.index, "TLT")


def test_contiguity_passes_when_every_session_is_present():
    sessions = pd.bdate_range("2009-06-01", periods=40)
    context.check_contiguous(sessions.union(pd.DatetimeIndex(["2009-06-06"])), sessions, "TLT")


def test_a_missing_spy_session_is_refused_and_named():
    sessions = pd.bdate_range("2009-06-01", periods=40)
    with pytest.raises(context.ContextError, match=r"UUP: 1 SPY session.*2009-06-10"):
        context.check_contiguous(sessions.delete(7), sessions, "UUP")


def test_z_coverage_counts_only_sessions_from_the_event_start():
    sessions = pd.bdate_range("2010-11-01", periods=300)
    z = pd.Series(1.0, index=sessions)
    z[z.index < pd.Timestamp("2011-01-01")] = np.nan      # warm-up NaNs do not count
    context.check_z_coverage(z, sessions, "TLT", event_start="2011-01-01")


def test_z_coverage_below_95_percent_is_refused():
    sessions = pd.bdate_range("2011-01-03", periods=100)
    z = pd.Series(1.0, index=sessions)
    z.iloc[:6] = np.nan                                   # 94% defined
    with pytest.raises(context.ContextError, match="TLT: defined z covers 94.0%"):
        context.check_z_coverage(z, sessions, "TLT", event_start="2011-01-01")
    z.iloc[:5] = 1.0                                      # 99% defined
    context.check_z_coverage(z, sessions, "TLT", event_start="2011-01-01")


def test_a_session_absent_from_z_counts_as_undefined():
    sessions = pd.bdate_range("2011-01-03", periods=100)
    z = pd.Series(1.0, index=sessions[10:])               # z never saw 10 sessions
    with pytest.raises(context.ContextError, match="90.0%"):
        context.check_z_coverage(z, sessions, "UUP", event_start="2011-01-01")


def test_no_session_in_the_event_window_is_refused():
    sessions = pd.bdate_range("2009-06-01", periods=10)
    with pytest.raises(context.ContextError, match="no SPY session"):
        context.check_z_coverage(pd.Series(1.0, index=sessions), sessions, "TLT",
                                 event_start="2011-01-01")


# --- V174-2: file record ----------------------------------------------------

def test_file_record_reads_rows_dates_mtime_and_sha256(tmp_path):
    path = tmp_path / "TLT.csv"
    random_walk(30, start="2009-06-01").rename_axis("Date").to_csv(path)
    stamp = pd.Timestamp("2026-10-18 09:30").timestamp()
    os.utime(path, (stamp, stamp))
    record = context.file_record(path)
    assert record == {
        "ticker": "TLT", "rows": 30, "first": "2009-06-01", "last": "2009-07-10",
        "fetched": date.fromtimestamp(stamp).isoformat(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_file_record_changes_with_one_byte(tmp_path):
    path = tmp_path / "UUP.csv"
    random_walk(30, start="2009-06-01").rename_axis("Date").to_csv(path)
    before = context.file_record(path)["sha256"]
    path.write_bytes(path.read_bytes().replace(b"Volume", b"volume"))
    assert context.file_record(path)["sha256"] != before


def test_file_record_of_a_missing_file_is_refused(tmp_path):
    with pytest.raises(context.ContextError, match="TLT: context file .*TLT.csv is missing"):
        context.file_record(tmp_path / "TLT.csv")


def test_context_data_is_frozen():
    data = context.ContextData(frames={}, calendar=pd.DataFrame(), records={})
    with pytest.raises(dataclasses.FrozenInstanceError):
        data.frames = {"TLT": pd.DataFrame()}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/dev/testrun.py file tests/backtesting/screen/test_context.py`
Expected: the V174-1 tests pass; every new test fails with `AttributeError: module 'swingbot.core.backtesting.screen.context' has no attribute 'MIN_Z_COVERAGE'` (or `ContextError`, `check_raw_index`, `file_record`, `ContextData`).

- [ ] **Step 3: Write the implementation**

In `$WT/swingbot/core/backtesting/screen/context.py`, extend the import block to:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
```

add, under `STD_FLOOR = 1e-12`:

```python
#: Defined z must cover this share of SPY sessions in the event window, or
#: the file would spend a shot on an idea that can hardly fire (v174 § 1).
MIN_Z_COVERAGE = 0.95
```

and append at the end of the module:

```python
class ContextError(ValueError):
    """A context file the screen must not run on; the runner refuses with it."""


def check_raw_index(index: pd.Index, name: str) -> None:
    """The CSV index as written, before load_frame repairs it: one date
    index, tz-naive, sorted, unique, every stamp at midnight."""
    if not isinstance(index, pd.DatetimeIndex):
        raise ContextError(f"{name}: the Date column is not a date index")
    if index.tz is not None:
        raise ContextError(f"{name}: the raw index is tz-aware ({index.tz}); "
                           f"the cache is tz-naive")
    if not index.is_monotonic_increasing:
        raise ContextError(f"{name}: the raw index is not sorted")
    if index.has_duplicates:
        raise ContextError(f"{name}: the raw index is not unique "
                           f"({int(index.duplicated().sum())} repeated dates)")
    if (index != index.normalize()).any():
        raise ContextError(f"{name}: the raw index is not normalised "
                           f"(a stamp other than midnight)")


def check_contiguous(index: pd.DatetimeIndex, sessions: pd.DatetimeIndex,
                     name: str) -> None:
    """Every SPY session is a bar of the context frame, so the 5-row
    offset of r5 is a 5-session offset."""
    missing = sessions.difference(index)
    if len(missing):
        raise ContextError(
            f"{name}: {len(missing)} SPY session(s) missing between "
            f"{sessions[0]:%Y-%m-%d} and {sessions[-1]:%Y-%m-%d}, "
            f"first {missing[0]:%Y-%m-%d}")


def check_z_coverage(z: pd.Series, sessions: pd.DatetimeIndex, name: str, *,
                     event_start: str, minimum: float = MIN_Z_COVERAGE) -> None:
    """Defined z on at least ``minimum`` of the SPY sessions from
    ``event_start``; a session z never saw counts as undefined."""
    window = sessions[sessions >= pd.Timestamp(event_start)]
    if not len(window):
        raise ContextError(f"{name}: no SPY session from {event_start}")
    share = float(z.reindex(window).notna().mean())
    if share < minimum:
        raise ContextError(
            f"{name}: defined z covers {share:.1%} of {len(window)} SPY sessions "
            f"from {event_start}; the floor is {minimum:.0%}")


def file_record(path) -> dict:
    """What the results doc prints and the hash file pins for one CSV."""
    path = Path(path)
    if not path.is_file():
        raise ContextError(f"{path.stem}: context file {path} is missing")
    dates = pd.read_csv(path, usecols=["Date"])["Date"].astype(str)
    return {"ticker": path.stem, "rows": int(len(dates)),
            "first": dates.min()[:10], "last": dates.max()[:10],
            "fetched": date.fromtimestamp(path.stat().st_mtime).isoformat(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


@dataclass(frozen=True)
class ContextData:
    """The context frames an idea reads, the SPY calendar they were checked
    against, and one file record per frame."""
    frames: Mapping[str, pd.DataFrame]
    calendar: pd.DataFrame
    records: Mapping[str, dict]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/dev/testrun.py file tests/backtesting/screen/test_context.py`
Expected: every test passes, `0 failed`.

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/swingbot/core/backtesting/screen/context.py | head
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens add swingbot/core/backtesting/screen/context.py tests/backtesting/screen/test_context.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens commit -m "feat(v174): context load checks, file record and ContextData" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: one commit on the branch; the main tree shows no new change from this task.

### Task V174-3: `Idea.context`; table-driven `events` dispatch; `screen_ticker`/`screen_universe` `context=`; real-call-path parity

**Model:** opus — the call seam every past and future screen runs through, pinned byte for byte

**Files:**
- Modify: `swingbot/core/backtesting/screen/ideas/__init__.py`
- Modify: `scripts/backtest/screen_idea.py`
- Modify: `tests/backtesting/screen/test_ideas_registry.py`
- Create: `tests/backtest_scripts/test_screen_context_runner.py`

**Interfaces:**
- Consumes: nothing from V174-1/V174-2 (this task runs beside V174-1 in Wave A). Existing: `screen_idea.screen_ticker`, `screen_universe`, `load_universe`, `TickerScreen` (`scripts/backtest/screen_idea.py:92-195`); `IDEAS`, `Idea`, `_load` (`ideas/__init__.py:31-64`); `tests.backtesting.screen.helpers.random_walk`.
- Produces:
  - `Idea.context: tuple[str, ...] = ()` — the last field, after `race_shape`; `__post_init__` stores it as a tuple; `_load` reads `tuple(getattr(module, "CONTEXT", ()))`. `Idea.events` is typed `Callable[..., pd.Series]`.
  - `screen_idea._EVENT_CALLS: dict[bool, Callable]` — `False` calls `idea.events(df)` (one argument), `True` calls `idea.events(df, {name: context[name] for name in idea.context})` and raises `ValueError` when `context is None`.
  - `screen_idea.raw_events(idea: Idea, df: pd.DataFrame, context: Mapping | None) -> pd.Series` — the dispatched series reindexed to `df.index` with `fill_value=False`.
  - `screen_ticker(idea, ticker, df, spans, *, slippage_bps=None, commission=None, context: Mapping | None = None) -> TickerScreen`
  - `screen_universe(idea, universe, cache_dir, *, start=WINDOW_START, end=WINDOW_END, tickers=None, out=print, context: Mapping | None = None)` — passes `context=context` to every `screen_ticker` call (V174-4 adds loading when `idea.context` and `context is None`).
  - In `tests/backtest_scripts/test_screen_context_runner.py`: `_digest(screen) -> str` (SHA-256 over the eight v140/v163 `TickerScreen` fields only, so a later defaulted field such as V174-8's `restricted` never moves it), `_ctx_cache(tmp_path, *, tickers=("AAA", "BBB"), context=("TLT", "UUP")) -> Path` (returns `tmp_path / "cache"` holding the stock CSVs from 2010-01-04, plus `SPY.csv` and one CSV per context name on one business-day calendar from 2009-06-01; also writes `tmp_path / "membership.csv"` listing `tickers`), `_write_csv(path, df)`, `ALWAYS`, `OLD_IDEAS`, autouse `fast_bootstrap`. V174-4 and V174-8 append tests to this file and reuse these helpers.

- [ ] **Step 1: Write the runner test file, digests still empty**

Create `$WT/tests/backtest_scripts/test_screen_context_runner.py` with the Write tool:

```python
"""v174 context hook in the runner: the events seam, parity of the six v140
ideas on the real call path, context loading and refusals."""
import dataclasses
import functools
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402

from swingbot.core.backtesting.screen import verdict  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS, Idea  # noqa: E402
from tests.backtesting.screen.helpers import random_walk  # noqa: E402

ALWAYS = [("2000-01-01", "9999-12-31")]
OLD_IDEAS = ("high52w", "uptrend_pullback", "gap_volume", "turn_of_month",
             "turtle_soup", "quiet_pullback")
CONTEXT_FROM = "2009-06-01"
#: TickerScreen digests captured on the code BEFORE v174 (V174-3 Step 2).
PARITY_DIGESTS: dict[str, str] = {}


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    """500 week resamples instead of 10,000: same code path, test-speed."""
    monkeypatch.setattr(screen_idea.verdict, "decide",
                        functools.partial(verdict.decide, n_resamples=500))


def _write_csv(path, df):
    df.rename_axis("Date").to_csv(path)


def _ctx_cache(tmp_path, *, tickers=("AAA", "BBB"), context=("TLT", "UUP")) -> Path:
    """tmp_path/cache: stock CSVs from 2010-01-04 (as test_screen_idea), and
    SPY plus every context series on one business-day calendar from
    2009-06-01. Also writes tmp_path/membership.csv listing ``tickers``."""
    cache = tmp_path / "cache"
    cache.mkdir()
    for seed, ticker in enumerate(tickers, start=1):
        _write_csv(cache / f"{ticker}.csv", random_walk(2700, seed=seed))
    for seed, ticker in enumerate(("SPY",) + tuple(context), start=50):
        _write_csv(cache / f"{ticker}.csv", random_walk(2800, seed=seed, start=CONTEXT_FROM))
    (tmp_path / "membership.csv").write_text(
        "ticker,start_date,end_date\n" + "".join(f"{t},2000-01-01,\n" for t in tickers),
        encoding="utf-8")
    return cache


def _plain(value):
    if isinstance(value, pd.DataFrame):
        return value.to_csv(float_format="%.17g")
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return repr(value)


def _digest(screen) -> str:
    """SHA-256 of the eight fields a TickerScreen had before v174. JSON
    writes floats with repr, so any change in any R moves the digest."""
    payload = {"ticker": screen.ticker,
               "counters": sorted(screen.counters.items()),
               "events": screen.events,
               "null_outcomes": sorted(screen.null_outcomes.items()),
               "excess": {str(h): v for h, v in screen.excess.items()},
               "rank": screen.rank,
               "null_timeout_r": screen.null_timeout_r,
               "stressed": screen.stressed}
    text = json.dumps(payload, sort_keys=True, default=_plain)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parity_screens() -> dict:
    """The six v140 ideas plus a trail variant (covers the v163 stressed
    path), screened on one frame through the real screen_ticker."""
    df = random_walk(2600, seed=11)
    ideas = {name: IDEAS[name] for name in OLD_IDEAS}
    ideas["high52w_trail"] = dataclasses.replace(IDEAS["high52w"], name="high52w_trail",
                                                 race_shape="trail")
    return {name: screen_idea.screen_ticker(idea, "AAA", df, ALWAYS)
            for name, idea in ideas.items()}


def _fake_ctx_idea(record=None):
    """A context idea that needs nothing from v174's context module."""
    def events(df, context):
        if record is not None:
            record.append((df, context))
        tlt = context["TLT"]["Close"]
        return (tlt.pct_change(5) > 0.03).reindex(df.index, fill_value=False).rename("fake_ctx")
    return Idea(name="fake_ctx", events=events, time_cap_bars=10,
                summary="TLT up 3% over 5 days", source="test", context=("TLT",))


def _quiet(*_args, **_kwargs):
    return None


# --- parity: the six v140 ideas, real call path -----------------------------

def test_old_ideas_screen_byte_identical_on_the_real_call_path():
    digests = {name: _digest(screen) for name, screen in _parity_screens().items()}
    assert set(PARITY_DIGESTS) == set(OLD_IDEAS) | {"high52w_trail"}
    assert digests == PARITY_DIGESTS


def test_an_old_idea_is_called_with_exactly_one_argument():
    original = IDEAS["turn_of_month"]
    calls = []

    def spy(*args, **kwargs):
        calls.append((len(args), kwargs))
        return original.events(*args, **kwargs)

    idea = dataclasses.replace(original, events=spy)
    frames = {"TLT": random_walk(700, start=CONTEXT_FROM)}
    screen_idea.screen_ticker(idea, "AAA", random_walk(700), ALWAYS, context=frames)
    assert calls and all(call == (1, {}) for call in calls)


# --- the dispatch table -----------------------------------------------------

def test_the_dispatch_table_has_one_entry_per_kind():
    assert set(screen_idea._EVENT_CALLS) == {False, True}


def test_a_context_idea_receives_only_its_own_series():
    record = []
    df = random_walk(700)
    tlt, uup = random_walk(800, seed=2, start=CONTEXT_FROM), random_walk(800, seed=3, start=CONTEXT_FROM)
    screen_idea.screen_ticker(_fake_ctx_idea(record), "AAA", df, ALWAYS,
                              context={"TLT": tlt, "UUP": uup})
    seen_df, seen_ctx = record[0]
    assert seen_df is df
    assert list(seen_ctx) == ["TLT"] and seen_ctx["TLT"] is tlt


def test_a_context_idea_without_context_is_an_error():
    with pytest.raises(ValueError, match="reads context"):
        screen_idea.raw_events(_fake_ctx_idea(), random_walk(50), None)


def test_raw_events_lands_on_the_stock_index_with_false_fill():
    df = random_walk(300)
    idea = Idea(name="sparse", events=lambda d: pd.Series(True, index=d.index[::3]),
                time_cap_bars=5)
    out = screen_idea.raw_events(idea, df, None)
    assert out.index.equals(df.index)
    assert out.tolist() == [i % 3 == 0 for i in range(len(df))]


# --- screen_universe passes context through ---------------------------------

def test_screen_universe_hands_the_same_context_to_every_ticker(tmp_path, monkeypatch):
    cache = _ctx_cache(tmp_path)
    universe = screen_idea.load_universe(cache, tmp_path / "membership.csv")
    seen = []
    monkeypatch.setattr(screen_idea, "screen_ticker",
                        lambda idea, ticker, df, spans, **kw: seen.append((ticker, kw)))
    frames = {"TLT": random_walk(800, start=CONTEXT_FROM)}
    screen_idea.screen_universe(IDEAS["turn_of_month"], universe, cache,
                                out=_quiet, context=frames)
    assert [ticker for ticker, _ in seen] == ["AAA", "BBB"]
    assert all(kw["context"] is frames for _, kw in seen)


def test_screen_universe_passes_none_for_an_old_idea_by_default(tmp_path, monkeypatch):
    cache = _ctx_cache(tmp_path)
    universe = screen_idea.load_universe(cache, tmp_path / "membership.csv")
    seen = []
    monkeypatch.setattr(screen_idea, "screen_ticker",
                        lambda idea, ticker, df, spans, **kw: seen.append(kw))
    screen_idea.screen_universe(IDEAS["turn_of_month"], universe, cache, out=_quiet)
    assert seen and all(kw["context"] is None for kw in seen)
```

- [ ] **Step 2: Capture the parity digests on the unmodified code**

`scripts/backtest/screen_idea.py` and `ideas/__init__.py` must still be untouched (`git -C $WT diff --stat` shows nothing but the new test file as untracked). Create `$WT/v174_capture.py` with the Write tool (it is never committed):

```python
"""One-off: print the pre-v174 TickerScreen digests for PARITY_DIGESTS."""
import json
import sys
from pathlib import Path

WT = Path(__file__).resolve().parent
sys.path.insert(0, str(WT))

from tests.backtest_scripts.test_screen_context_runner import _digest, _parity_screens  # noqa: E402

print(json.dumps({name: _digest(screen) for name, screen in _parity_screens().items()},
                 indent=4, sort_keys=True))
```

Run:

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/v174_capture.py
```

Expected: a JSON object with seven keys (`gap_volume`, `high52w`, `high52w_trail`, `quiet_pullback`, `turn_of_month`, `turtle_soup`, `uptrend_pullback`), each a 64-hex digest. Run it a second time: the output must be identical (the screen is seeded); if it is not, stop and report, because parity cannot be pinned.

- [ ] **Step 3: Pin the digests and delete the capture script**

In the test file, replace `PARITY_DIGESTS: dict[str, str] = {}` with the printed object verbatim (JSON with double-quoted strings is a valid Python dict literal), for example the shape:

```python
PARITY_DIGESTS: dict[str, str] = {
    "gap_volume": "<64 hex chars from Step 2>",
    "high52w": "<64 hex chars from Step 2>",
    "high52w_trail": "<64 hex chars from Step 2>",
    "quiet_pullback": "<64 hex chars from Step 2>",
    "turn_of_month": "<64 hex chars from Step 2>",
    "turtle_soup": "<64 hex chars from Step 2>",
    "uptrend_pullback": "<64 hex chars from Step 2>",
}
```

(the angle-bracket text stands for the captured values; the committed file holds only real digests). Cross-check: when this plan was written, the same capture on `main` at 3ec61302 printed `gap_volume` 754ec86a..., `high52w` ed4fba6e..., `high52w_trail` eebc95fe..., `quiet_pullback` f8d99b46..., `turn_of_month` 5730a720..., `turtle_soup` 33e7d4b7..., `uptrend_pullback` 1ee25dda.... Pin what YOUR Step 2 printed; a differing prefix only means a different numpy/pandas build, as long as Step 2 ran on unmodified code. Then:

```bash
rm E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/v174_capture.py
python -m pytest "E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/tests/backtest_scripts/test_screen_context_runner.py::test_old_ideas_screen_byte_identical_on_the_real_call_path" -q
```

Expected: `1 passed` — the pin holds on the unmodified code.

- [ ] **Step 4: Run the whole new file to see the rest fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py`
Expected: the parity test passes; the others fail with `TypeError: screen_ticker() got an unexpected keyword argument 'context'`, `AttributeError: module 'screen_idea' has no attribute '_EVENT_CALLS'` / `'raw_events'`, or `TypeError: Idea.__init__() got an unexpected keyword argument 'context'`.

- [ ] **Step 5: Add the registry tests**

Append to `$WT/tests/backtesting/screen/test_ideas_registry.py` (Write the file back with these lines at the end; `_fake_module` already exists at line 99):

```python
def test_the_six_v140_ideas_read_no_context():
    for name in ("high52w", "uptrend_pullback", "gap_volume", "turn_of_month",
                 "turtle_soup", "quiet_pullback"):
        assert IDEAS[name].context == ()


def test_load_reads_the_context_constant_and_defaults_to_empty(monkeypatch):
    plain = _fake_module(monkeypatch, "fake_no_context", CAP=10)
    reads = _fake_module(monkeypatch, "fake_context", CAP=10, CONTEXT=["TLT"])
    assert ideas._load(plain).context == ()
    assert ideas._load(reads).context == ("TLT",)


def test_context_is_stored_as_a_tuple():
    idea = Idea(name="x", events=lambda df, context: df["Close"] > 0,
                time_cap_bars=5, context=["TLT", "UUP"])
    assert idea.context == ("TLT", "UUP")
```

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: the three new tests fail (`AttributeError: 'Idea' object has no attribute 'context'`, `TypeError ... unexpected keyword argument 'context'`).

- [ ] **Step 6: Add the field to the registry**

In `$WT/swingbot/core/backtesting/screen/ideas/__init__.py`:

Replace the module docstring with:

```python
"""The v140 idea registry: one frozen trigger per published effect.

A trigger module exports CAP, PARAMS, SUMMARY, SOURCE and events(df), and
optionally RACE: "fixed" (the default: entry next open, 1.5/3 ATR stop and
target) or "trail" (v163: chandelier 3 ATR trail, no target, CAP >= 60). A
changed parameter or a changed race shape is a new idea with a new name (and
a new ledger row), never an edit here: each idea is screened once, under one
shape.

v174: a module may also export CONTEXT, a tuple of cached tickers (e.g.
("TLT",)). It then defines events(df, context), where context maps each of
those names to its frame (screen/context.py: point in time, exact-date
alignment). A module without CONTEXT keeps events(df) and is called with
exactly one argument.
"""
```

Replace the `Idea` field block and the start of `__post_init__`:

```python
@dataclass(frozen=True)
class Idea:
    name: str
    events: Callable[..., pd.Series]
    time_cap_bars: int
    direction: str = "long"
    params: Mapping = field(default_factory=dict)
    summary: str = ""
    source: str = ""
    race_shape: str = "fixed"
    context: tuple[str, ...] = ()
```

and, as the last line of `__post_init__` (after the `params` line):

```python
        object.__setattr__(self, "context", tuple(self.context))
```

Replace `_load` with:

```python
def _load(name: str) -> Idea:
    module = importlib.import_module(f"{__name__}.{name}")
    return Idea(name=name, events=module.events, time_cap_bars=module.CAP,
                params=module.PARAMS, summary=module.SUMMARY,
                source=module.SOURCE,
                race_shape=getattr(module, "RACE", "fixed"),
                context=tuple(getattr(module, "CONTEXT", ())))
```

- [ ] **Step 7: Add the seam to the runner**

In `$WT/scripts/backtest/screen_idea.py`:

Add to the standard-library imports (after `from pathlib import Path`):

```python
from typing import Callable, Mapping
```

Insert directly above `def screen_ticker(`:

```python
def _events_plain(idea: Idea, df: pd.DataFrame, context) -> pd.Series:
    """An idea without CONTEXT: one argument, exactly as since v140."""
    return idea.events(df)


def _events_with_context(idea: Idea, df: pd.DataFrame, context) -> pd.Series:
    """A v174 context idea: its own named frames, nothing else."""
    if context is None:
        raise ValueError(f"{idea.name} reads context {idea.context}; none was loaded")
    return idea.events(df, {name: context[name] for name in idea.context})


#: Keyed on bool(idea.context), so screen_ticker grows no branch (v174 § 1).
_EVENT_CALLS: dict[bool, Callable] = {False: _events_plain, True: _events_with_context}


def raw_events(idea: Idea, df: pd.DataFrame, context: Mapping | None) -> pd.Series:
    """The idea's raw event flags on the ticker's own index."""
    return _EVENT_CALLS[bool(idea.context)](idea, df, context).reindex(df.index, fill_value=False)
```

Replace the `screen_ticker` signature and its `ctx` line:

```python
def screen_ticker(idea: Idea, ticker: str, df: pd.DataFrame, spans, *,
                  slippage_bps=None, commission=None,
                  context: Mapping | None = None) -> TickerScreen:
    costs = {"slippage_bps": slippage_bps, "commission": commission}
    atr = indicators.atr(df)
    sma200 = indicators.sma(df["Close"], 200)
    member = null.member_mask(df.index, spans)
    warm = race.warm_mask(atr, sma200) & (df.index >= pd.Timestamp(EVENT_START))
    ctx = {"raw": np.asarray(raw_events(idea, df, context), dtype=bool),
           "member": member, "warm": warm, "atr": atr,
           "trend": null.trend_state(df, sma200)}
```

(the rest of `screen_ticker` is unchanged). Replace `screen_universe` with:

```python
def screen_universe(idea: Idea, universe: Universe, cache_dir, *,
                    start: str = WINDOW_START, end: str = WINDOW_END,
                    tickers=None, out=print, context: Mapping | None = None):
    """Every cached member, one at a time, with flushed percent progress.
    ``context`` (v174) is handed unchanged to every screen_ticker call."""
    names = universe.cached if tickers is None else [t for t in tickers if t in universe.cached]
    screens, skipped = [], Counter()
    for i, ticker in enumerate(names, start=1):
        df = load_frame(Path(cache_dir) / f"{ticker}.csv", start, end)
        if df is None:
            skipped["empty_frame"] += 1
        else:
            screens.append(screen_ticker(idea, ticker, df,
                                         universe.intervals.get(ticker, []),
                                         context=context))
        if i % PROGRESS_EVERY == 0 or i == len(names):
            out(f"[{idea.name}] {i}/{len(names)} tickers ({100.0 * i / len(names):.0f}%)",
                flush=True)
    return screens, skipped
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
```

Expected: all three files `0 failed`. The parity test passes against the digests captured before the change; `test_screen_idea.py` (including the `FIXED_DOC` and `FIXED_HYPOTHESIS` pins at lines 411 and 417) is untouched and green. If the parity test fails, the seam changed an old idea: fix the seam, never the digests.

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/backtest/screen_idea.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/swingbot/core/backtesting/screen/ideas/__init__.py | head
```

Expected: no output (`screen_ticker` stays A, `screen_universe` B(8), `__post_init__` below C).

- [ ] **Step 9: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens status --short
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens add swingbot/core/backtesting/screen/ideas/__init__.py scripts/backtest/screen_idea.py tests/backtesting/screen/test_ideas_registry.py tests/backtest_scripts/test_screen_context_runner.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens commit -m "feat(v174): Idea.context and a table-driven events seam, pinned by real-call-path parity" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the first status shows exactly the four files (no `v174_capture.py`); one commit on the branch; the main tree shows no new change from this task.

### Task V174-4: Context loading once per universe; load and hash refusals in `main`

**Model:** sonnet — runner CLI and refusals inside one script, behaviour fixed by the spec

**Files:**
- Modify: `scripts/backtest/screen_idea.py`
- Modify: `tests/backtest_scripts/test_screen_context_runner.py` (created by V174-3)

**Interfaces:**
- Consumes: V174-2 `context.ContextError`, `check_raw_index`, `check_contiguous`, `check_z_coverage`, `file_record`, `ContextData`; V174-1 `CONTEXT_START`, `trailing_z`; V174-3 `screen_universe(..., context=)`, `Idea.context`, test helpers `_ctx_cache`, `_write_csv`, `_fake_ctx_idea`, `_quiet`.
- Produces (in `scripts/backtest/screen_idea.py`; the module is imported as `screen_context` there, because `context` is already a parameter name in `screen_ticker`/`screen_universe`):
  - `CONTEXT_START` (re-export of `context.CONTEXT_START`); `CONTEXT_HASHES = RESULTS_DIR / "2026-10-18-v174-context-hashes.json"`; CLI `--context-hashes` (`type=Path`, default `CONTEXT_HASHES`).
  - `context_tickers() -> tuple[str, ...]` — sorted union of `idea.context` over `IDEAS`.
  - `load_context(cache_dir, tickers: tuple[str, ...], *, end: str = WINDOW_END) -> ContextData` — SPY calendar from `load_frame(cache_dir / "SPY.csv", CONTEXT_START, end)`; per ticker: `file_record` (missing), raw-index check, `load_frame(path, CONTEXT_START, end)`, contiguity, z coverage from `EVENT_START`; raises `ContextError`.
  - `hash_refusal(records: Mapping[str, dict], path) -> str | None`; `write_hashes(records: Mapping[str, dict], path) -> bool` (writes `{ticker: sha256}`, indent 2, sorted keys, trailing newline, only when absent).
  - `_context_step(args, idea) -> tuple[ContextData | None, str | None]` — `(None, None)` for an idea without context; loads `idea.context` and checks the hash file over `context_tickers()` for any run, dry or real.
  - `screen_universe` loads once through `_universe_context(idea, cache_dir, end, context)` when `idea.context` and `context is None`.
  - `publish` calls `_pin_context_hashes(args, idea)` between the results-doc write and `stats.append_ledger_row`.
  - `main` refuses (exit 2, `refused: <reason>`) on any `ContextError` or hash mismatch, before `screen_universe` and before any write; it passes `data.frames` to `screen_universe`. V174-8 (part 2) threads `data` further into the summary and the results doc.

- [ ] **Step 1: Write the failing tests**

In `$WT/tests/backtest_scripts/test_screen_context_runner.py`, add `import re` after `import json`, and add to the import block (after the `verdict` import):

```python
from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.backtesting.screen import context as ctx_math  # noqa: E402
```

and append at the end of the file:

```python
# --- V174-4: loading and refusals -------------------------------------------

def _ctx_argv(tmp_path, cache, *extra, idea="fake_ctx"):
    return ["--idea", idea, "--cache-dir", str(cache),
            "--membership", str(tmp_path / "membership.csv"),
            "--ledger", str(tmp_path / "ledger.jsonl"),
            "--results-dir", str(tmp_path / "results"), "--date", "2026-10-18",
            "--context-hashes", str(tmp_path / "hashes.json"), *extra]


@pytest.fixture
def fake_registered(monkeypatch):
    idea = _fake_ctx_idea()
    monkeypatch.setitem(screen_idea.IDEAS, idea.name, idea)
    return idea


def _forbid_screening(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("screen_universe ran after a refusal")
    monkeypatch.setattr(screen_idea, "screen_universe", boom)


def _rewrite_tlt(cache, change):
    path = cache / "TLT.csv"
    _write_csv(path, change(pd.read_csv(path, parse_dates=["Date"], index_col="Date")))


def _tz_aware(df):
    df.index = df.index.tz_localize("UTC")
    return df


def _flat_2011_2014(df):
    inside = (df.index >= "2011-01-01") & (df.index <= "2014-12-31")
    df.loc[inside, ["Open", "High", "Low", "Close"]] = 100.0
    return df


def _sha(records):
    return {t: r["sha256"] for t, r in records.items()}


def test_context_start_and_hash_path_are_exposed():
    assert screen_idea.CONTEXT_START == "2009-06-01"
    assert screen_idea.CONTEXT_HASHES.name == "2026-10-18-v174-context-hashes.json"
    assert screen_idea.build_parser().parse_args(
        ["--idea", "high52w"]).context_hashes == screen_idea.CONTEXT_HASHES


def test_load_context_returns_frames_calendar_and_records(tmp_path):
    cache = _ctx_cache(tmp_path)
    data = screen_idea.load_context(cache, ("TLT", "UUP"))
    assert list(data.frames) == ["TLT", "UUP"]
    tlt = data.frames["TLT"]
    assert tlt.index[0] == pd.Timestamp("2009-06-01")
    assert tlt.index[-1] <= pd.Timestamp("2019-12-31")
    assert data.calendar.index.equals(tlt.index)
    assert data.records["UUP"] == ctx_math.file_record(cache / "UUP.csv")


@pytest.mark.parametrize("mutate, words", [
    (lambda c: (c / "TLT.csv").unlink(), r"TLT: context file .*TLT\.csv is missing"),
    (lambda c: (c / "SPY.csv").unlink(), "SPY calendar .* is missing"),
    (lambda c: _rewrite_tlt(c, _tz_aware), "TLT: the raw index is tz-aware"),
    (lambda c: _rewrite_tlt(c, lambda df: df.iloc[::-1]), "TLT: the raw index is not sorted"),
    (lambda c: _rewrite_tlt(c, lambda df: df.drop(pd.Timestamp("2012-03-05"))),
     r"TLT: 1 SPY session\(s\) missing .* first 2012-03-05"),
    (lambda c: _rewrite_tlt(c, _flat_2011_2014), "TLT: defined z covers"),
])
def test_a_bad_context_file_refuses_before_any_ticker_or_write(
        tmp_path, monkeypatch, capsys, fake_registered, mutate, words):
    cache = _ctx_cache(tmp_path)
    mutate(cache)
    _forbid_screening(monkeypatch)
    assert screen_idea.main(_ctx_argv(tmp_path, cache)) == 2
    err = capsys.readouterr().err
    assert err.startswith("refused: ")
    assert re.search(words, err)
    for written in ("ledger.jsonl", "results", "hashes.json"):
        assert not (tmp_path / written).exists()


def test_a_changed_context_file_refuses_even_a_dry_run(tmp_path, monkeypatch, capsys,
                                                       fake_registered):
    cache = _ctx_cache(tmp_path)
    hashes = tmp_path / "hashes.json"
    pinned = _sha({t: ctx_math.file_record(cache / f"{t}.csv")
                   for t in screen_idea.context_tickers()})
    pinned["TLT"] = "0" * 64
    hashes.write_text(json.dumps(pinned), encoding="utf-8")
    before = hashes.read_bytes()
    _forbid_screening(monkeypatch)
    assert screen_idea.main(_ctx_argv(tmp_path, cache, "--dry-run")) == 2
    assert "TLT.csv SHA-256" in capsys.readouterr().err
    assert hashes.read_bytes() == before


def test_a_ticker_missing_from_the_hash_file_refuses(tmp_path, monkeypatch, capsys,
                                                     fake_registered):
    cache = _ctx_cache(tmp_path)
    (tmp_path / "hashes.json").write_text("{}", encoding="utf-8")
    _forbid_screening(monkeypatch)
    assert screen_idea.main(_ctx_argv(tmp_path, cache, "--dry-run")) == 2
    assert "TLT has no SHA-256" in capsys.readouterr().err


def test_matching_hashes_let_a_dry_run_through(tmp_path, capsys, fake_registered):
    cache = _ctx_cache(tmp_path)
    records = {t: ctx_math.file_record(cache / f"{t}.csv") for t in screen_idea.context_tickers()}
    assert screen_idea.write_hashes(records, tmp_path / "hashes.json")
    assert screen_idea.main(_ctx_argv(tmp_path, cache, "--dry-run")) == 0
    assert "# v140 screen: `fake_ctx`" in capsys.readouterr().out
    assert not (tmp_path / "ledger.jsonl").exists()


def test_a_real_run_pins_hashes_after_the_doc_and_before_the_ledger(tmp_path, monkeypatch,
                                                                    fake_registered):
    cache = _ctx_cache(tmp_path)
    hashes = tmp_path / "hashes.json"
    doc = tmp_path / "results" / "2026-10-18-screen-fake_ctx.md"
    seen, append = [], stats.append_ledger_row

    def spy(row, path):
        seen.append((doc.exists(), hashes.exists()))
        return append(row, path=path)

    monkeypatch.setattr(screen_idea.stats, "append_ledger_row", spy)
    assert screen_idea.main(_ctx_argv(tmp_path, cache)) == 0
    assert seen == [(True, True)]
    expected = _sha({t: ctx_math.file_record(cache / f"{t}.csv")
                     for t in screen_idea.context_tickers()})
    assert hashes.read_text(encoding="utf-8") == json.dumps(expected, indent=2, sort_keys=True) + "\n"


def test_write_hashes_never_overwrites(tmp_path):
    path = tmp_path / "hashes.json"
    assert screen_idea.write_hashes({"TLT": {"sha256": "a" * 64}}, path)
    assert not screen_idea.write_hashes({"TLT": {"sha256": "b" * 64}}, path)
    assert json.loads(path.read_text(encoding="utf-8")) == {"TLT": "a" * 64}


def test_context_tickers_is_the_sorted_union(monkeypatch):
    monkeypatch.setitem(screen_idea.IDEAS, "fake_a", dataclasses.replace(
        _fake_ctx_idea(), name="fake_a", context=("UUP",)))
    monkeypatch.setitem(screen_idea.IDEAS, "fake_b", dataclasses.replace(
        _fake_ctx_idea(), name="fake_b", context=("TLT", "UUP")))
    tickers = screen_idea.context_tickers()
    assert isinstance(tickers, tuple) and tickers == tuple(sorted(set(tickers)))
    assert {"TLT", "UUP"} <= set(tickers)


def test_context_frames_load_once_per_universe(tmp_path, monkeypatch):
    cache = _ctx_cache(tmp_path)
    universe = screen_idea.load_universe(cache, tmp_path / "membership.csv")
    loads, seen, real = [], [], screen_idea.load_context

    def counting(*args, **kwargs):
        loads.append(args[1])
        return real(*args, **kwargs)

    monkeypatch.setattr(screen_idea, "load_context", counting)
    monkeypatch.setattr(screen_idea, "screen_ticker",
                        lambda idea, ticker, df, spans, **kw: seen.append(kw["context"]))
    screen_idea.screen_universe(_fake_ctx_idea(), universe, cache, out=_quiet)
    assert loads == [("TLT",)]
    assert len(seen) == 2 and seen[0] is seen[1] and list(seen[0]) == ["TLT"]


def test_an_old_idea_never_loads_context(tmp_path, monkeypatch):
    cache = _ctx_cache(tmp_path)
    universe = screen_idea.load_universe(cache, tmp_path / "membership.csv")
    monkeypatch.setattr(screen_idea, "load_context",
                        lambda *a, **k: pytest.fail("an old idea loaded context"))
    monkeypatch.setattr(screen_idea, "screen_ticker", lambda *a, **k: None)
    screen_idea.screen_universe(IDEAS["turn_of_month"], universe, cache, out=_quiet)
    args = screen_idea.build_parser().parse_args(["--idea", "turn_of_month"])
    assert screen_idea._context_step(args, IDEAS["turn_of_month"]) == (None, None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py`
Expected: the V174-3 tests pass; the new ones fail with `AttributeError: module 'screen_idea' has no attribute 'CONTEXT_START'` / `'load_context'` / `'write_hashes'` / `'context_tickers'`, or `error: unrecognized arguments: --context-hashes`.

- [ ] **Step 3: Write the implementation**

In `$WT/scripts/backtest/screen_idea.py`:

Add `import json` to the standard-library imports (after `import argparse`), and below the `ideas` import line:

```python
from swingbot.core.backtesting.screen import context as screen_context  # noqa: E402
from swingbot.core.backtesting.screen.context import CONTEXT_START  # noqa: E402,F401
```

Insert directly above `def screen_universe(`:

```python
def _spy_calendar(cache_dir, end: str) -> pd.DataFrame:
    """SPY sessions in [CONTEXT_START, end]: the calendar every context file
    must cover (v174 load check 3)."""
    path = Path(cache_dir) / "SPY.csv"
    if not path.is_file():
        raise screen_context.ContextError(f"SPY calendar {path} is missing")
    calendar = load_frame(path, CONTEXT_START, end)
    if calendar is None:
        raise screen_context.ContextError(f"SPY calendar has no bar in {CONTEXT_START}..{end}")
    return calendar


def _context_frame(cache_dir, ticker: str, sessions: pd.DatetimeIndex, end: str):
    """One context CSV through the v174 load checks, the raw index first
    (load_frame silently repairs tz, order and duplicates)."""
    path = Path(cache_dir) / f"{ticker}.csv"
    record = screen_context.file_record(path)
    raw = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    screen_context.check_raw_index(raw.index, ticker)
    frame = load_frame(path, CONTEXT_START, end)
    if frame is None:
        raise screen_context.ContextError(f"{ticker}: no bar in {CONTEXT_START}..{end}")
    screen_context.check_contiguous(frame.index, sessions, ticker)
    screen_context.check_z_coverage(screen_context.trailing_z(frame["Close"]), sessions,
                                    ticker, event_start=EVENT_START)
    return frame, record


def load_context(cache_dir, tickers, *, end: str = WINDOW_END) -> screen_context.ContextData:
    """Every context frame an idea names, checked, from CONTEXT_START to end."""
    calendar = _spy_calendar(cache_dir, end)
    frames, records = {}, {}
    for ticker in tickers:
        frames[ticker], records[ticker] = _context_frame(cache_dir, ticker, calendar.index, end)
    return screen_context.ContextData(frames=frames, calendar=calendar, records=records)


def _universe_context(idea: Idea, cache_dir, end: str, context):
    """A context idea run without frames loads them here, once per universe."""
    if idea.context and context is None:
        return load_context(cache_dir, idea.context, end=end).frames
    return context
```

In `screen_universe`, make the first body line (after the docstring):

```python
    context = _universe_context(idea, cache_dir, end, context)
```

Directly below `INSTRUMENT = "screen-v1"`, add:

```python
#: {ticker: sha256} of every registered context CSV, written by the first
#: real run of a context idea; backtest_cache_ext is gitignored (v174 § 2).
CONTEXT_HASHES = RESULTS_DIR / "2026-10-18-v174-context-hashes.json"


def context_tickers() -> tuple[str, ...]:
    return tuple(sorted({name for idea in IDEAS.values() for name in idea.context}))


def _hash_records(cache_dir) -> dict:
    return {t: screen_context.file_record(Path(cache_dir) / f"{t}.csv")
            for t in context_tickers()}


def hash_refusal(records: Mapping[str, dict], path) -> str | None:
    """Why the context bytes differ from the pinned ones, or None (no pin yet,
    or every ticker matches)."""
    path = Path(path)
    if not path.is_file():
        return None
    pinned = json.loads(path.read_text(encoding="utf-8"))
    for ticker, record in sorted(records.items()):
        if ticker not in pinned:
            return f"{ticker} has no SHA-256 in {path}; the pinned context set changed"
        if pinned[ticker] != record["sha256"]:
            return (f"{ticker}.csv SHA-256 {record['sha256'][:12]} differs from "
                    f"{pinned[ticker][:12]} pinned in {path}; the context data changed "
                    f"after the first shot (never refetch)")
    return None


def write_hashes(records: Mapping[str, dict], path) -> bool:
    """Pin the context bytes once; never overwrite a pin."""
    path = Path(path)
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({t: r["sha256"] for t, r in records.items()}, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")
    return True


def _context_step(args, idea: Idea):
    """(ContextData, None), or (None, reason) to refuse; (None, None) for an
    idea without context. Runs for dry and real runs alike."""
    if not idea.context:
        return None, None
    try:
        data = load_context(args.cache_dir, idea.context, end=args.end)
        reason = hash_refusal(_hash_records(args.cache_dir), args.context_hashes)
    except screen_context.ContextError as exc:
        return None, str(exc)
    return (None, reason) if reason else (data, None)


def _pin_context_hashes(args, idea: Idea) -> None:
    if idea.context and write_hashes(_hash_records(args.cache_dir), args.context_hashes):
        print(f"pinned context SHA-256 -> {args.context_hashes}")
```

In `build_parser`, after the `--results-dir` line:

```python
    p.add_argument("--context-hashes", type=Path, default=CONTEXT_HASHES,
                   help="v174 pinned SHA-256 of the context CSVs")
```

In `publish`, between `path.write_text(text, encoding="utf-8", newline="\n")` and `stats.append_ledger_row(row, path=args.ledger)`, insert:

```python
    _pin_context_hashes(args, idea)
```

Replace `main` with:

```python
def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    _utf8_stdout()
    rows = stats.load_ledger(args.ledger)
    reason = refusal(args, rows)
    if reason is None:
        try:
            universe = load_universe(args.cache_dir, args.membership, args.start, args.end)
        except ValueError as exc:
            reason = str(exc)
    data = None
    if reason is None:
        data, reason = _context_step(args, IDEAS[args.idea])
    if reason:
        print(f"refused: {reason}", file=sys.stderr)
        return 2
    idea = IDEAS[args.idea]
    tickers = args.tickers.split(",") if args.tickers else None
    screens, skipped = screen_universe(idea, universe, args.cache_dir, start=args.start,
                                       end=args.end, tickers=tickers,
                                       context=None if data is None else data.frames)
    return publish(args, idea, universe, summarise(screens, skipped), rows)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens/scripts/backtest/screen_idea.py | head
```

Expected: both files `0 failed` (parity, `FIXED_DOC` and `FIXED_HYPOTHESIS` still green: an old idea never reaches the new code); radon prints nothing (`main` is B(7)).

- [ ] **Step 5: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens add scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_context_runner.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v174-intermarket-shock-screens commit -m "feat(v174): load context once per universe; refuse bad context files and changed bytes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: one commit on the branch; the main tree shows no new change from this task.

### Task V174-5: Fetch TLT and UUP adjusted bars into `backtest_cache_ext`

**Model:** haiku — one fixed command and a read-back check, no code

**Files:** none in git. Writes the gitignored `data/backtest_cache_ext/TLT.csv` and `UUP.csv` in the **main tree** (never the worktree). Runs any time before V174-11; needs no code from this plan.

- [ ] **Step 1: Fetch once.** If both files already exist, skip to Step 2: never refetch and never pass `--force` (adjusted history is restated at fetch time; the shots must read the bytes fetched here).

```bash
ls E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext/TLT.csv E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext/UUP.csv
BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python E:/Documents/Private/Projects/Discord-Bot/scripts/data/fetch_backtest_data.py --tickers TLT,UUP --start 2009-06-01 --end 2020-01-01
```

Expected: the `ls` reports both missing; the fetch prints `+ TLT: <n> bars (2009-06-01 -> 2019-12-31)`, the same for UUP, and `Done: 2 fetched, 0 already cached, 0 failed`. Closes are adjusted (`auto_adjust=True` at `fetch_backtest_data.py:99`). A failed ticker: stop and report; do not retry with other dates.

- [ ] **Step 2: Read back**

```bash
for t in TLT UUP; do f=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext/$t.csv; head -2 $f; tail -1 $f; grep -c "" $f; sha256sum $f; done
git -C E:/Documents/Private/Projects/Discord-Bot status --short data/
```

Expected per file: header `Date,Open,High,Low,Close,Volume`; first bar `2009-06-01`; last bar `2019-12-31`; about 2660 lines; a SHA-256. `git status` prints nothing (gitignored). Report the two digests to the controller: V174-11 pins the same values in `docs/superpowers/results/2026-10-18-v174-context-hashes.json`. Nothing to commit.

