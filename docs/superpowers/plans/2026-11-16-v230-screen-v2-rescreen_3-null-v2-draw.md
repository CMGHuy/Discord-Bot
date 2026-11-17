# v230 Plan 1, Part 3 — the v2 null: panel, cross-section and the draws

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V230-7" -A 400 <this file>`).

**Spec:** [2026-11-16-v230-screen-v2-ladder-additive-gate-design.md](../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md) (A2 stages 1–2, market scope, refusals, checkpoint manifest; Constraints: no-lookahead truncation test, golden draws)
**Index:** [2026-11-16-v230-screen-v2-rescreen_0-index.md](2026-11-16-v230-screen-v2-rescreen_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there; every task below obeys them.
**Tasks:** V230-6..V230-8

What this part builds: the new module `swingbot/core/backtesting/screen/null_v2.py`
up to its draw pass. V230-6 adds stage 1 (one `TickerPanel` per ticker), the
dates × tickers `CrossSection` with per-date ATR% terciles, and the stage
checkpoints that refuse a v1 checkpoint. V230-7 adds the ticker-scope draw
(pool = other tickers on the same date, same trend state, same ATR% tercile),
the `SCOPE_MISMATCH` / `NULL_STARVED` refusal, and the golden test pinning one
v1 draw and one v2 draw. V230-8 adds the market-scope draw (same ticker,
trailing 252 sessions, embargo of `CAP` bars around raw events).

**Runs only if V230-5 recorded `BIAS`** (index `## Handoff`). Every test here
uses synthetic panels or `helpers.random_walk` frames; nothing reads the real
cache (Global Constraints: no real idea under v2 before V230-13).

Shared private helpers created in V230-7 and reused by V230-8 and V230-9 (same
file): `_v2_name(idea) -> str`, `_records(event_ticker, event_pos, day,
null_tickers, null_pos, fills=None) -> list[tuple]`, `_table(records) ->
pd.DataFrame`, `_events_by_row(xs, booked) -> dict[int, list[tuple[int, int]]]`
and the accumulator `class _Tally` (`records`, `dropped`, `add(rows)`,
`mark_date(day, starved: bool)` (dates kept as sets, so a date seen on several
tickers counts once), `count_slots(m)`, `count_unfilled(m)`, `result() -> DrawResult`).

# Phase 3 — the v2 null, stages 1 and 2

### Task V230-6: v2 panel, cross-section and stage checkpoints

**Model:** opus — the no-lookahead boundary of the whole v2 null (only race completeness may read the frame's end) and the checkpoint layout every later stage resumes from.

**Files:**
- Create: `swingbot/core/backtesting/screen/null_v2.py`
- Test: `tests/backtesting/screen/test_null_v2_panel.py` (create)

**Interfaces:**
- Consumes: existing `null.eligible_mask`, `null.trend_state`. `ctx` is `screen_idea.ticker_context`'s dict (`raw`, `member`, `warm`, `atr`, `trend`, optional `condition`); the module never imports the script.
- Produces: `NULL_VERSION = "v2"`; `STAGES = ("panel", "draw", "race")`; `STAGE_MANIFEST = "manifest.json"`; `@dataclass(frozen=True, eq=False) TickerPanel(ticker, dates: np.ndarray, eligible, trend, atr_pct, event, control: np.ndarray | None = None, level_bars: np.ndarray | None = None)` (`level_bars` shape (n, 4): Open, High, Low, ATR14[t-1], NaN ATR on row 0); `ticker_panel(ticker, df, ctx, *, cap, control=None, keep_bars=False) -> TickerPanel` (V230-11 passes `control=ctx.get("control_condition")` in avoid mode, `keep_bars=True` for level entries); `@dataclass(frozen=True, eq=False) CrossSection(dates: pd.DatetimeIndex, tickers: tuple[str, ...], eligible, trend, tercile, event, control, pos)` (arrays shape (dates, tickers); `tercile` int8, -1 where ATR% is not finite or the date has no eligible ticker; `pos` int32 own-frame position, -1 absent; `control` None when no panel carries one); `atr_terciles(atr_pct_row, eligible_row) -> np.ndarray`; `cross_section(panels: Mapping[str, TickerPanel]) -> CrossSection`; `class StageCheckpoint(directory)` (`load(key)`, `save(key, obj)`, `done() -> set[str]`; no-op when `directory` is None); `open_stage(root, stage, manifest, out=print) -> StageCheckpoint`; `resumable_map(keys, fn, *, checkpoint, out=print, label="") -> dict`.

**Tercile rule (builder call):** cut points are the 1/3 and 2/3 quantiles of
the date's **eligible** ATR%; every finite ATR% gets `(v > q1) + (v > q2)`.
The event ticker is never eligible at its own event bar, yet needs a tercile.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/screen/test_null_v2_panel.py`:

```python
"""v230 A2 stage 1: the v2 panel, the dates x tickers cross-section and the
stage checkpoints. Every panel value at bar t reads bars <= t, except race
completeness (pos + cap <= n - 1), exactly as v1."""
import json

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators, null, null_v2
from swingbot.core.backtesting.screen import race as race_mod
from tests.backtesting.screen.helpers import assert_prefix_stable, random_walk

CAP = 10
QUIET = {"out": lambda *a, **k: None}


def _ctx(df, condition=None):
    atr = indicators.atr(df)
    sma200 = indicators.sma(df["Close"], 200)
    prior_high = df["High"].shift(1).rolling(20).max()
    ctx = {"raw": (df["Close"] > prior_high).to_numpy(dtype=bool),
           "member": np.ones(len(df), dtype=bool),
           "warm": race_mod.warm_mask(atr, sma200), "atr": atr,
           "trend": null.trend_state(df, sma200)}
    if condition is not None:
        ctx["condition"] = condition
    return ctx


def _panel(df, **kw):
    return null_v2.ticker_panel("AAA", df, _ctx(df), cap=CAP, **kw)


def test_panel_copies_v1_eligibility_trend_events_and_atr_pct():
    df = random_walk(600, seed=3)
    ctx = _ctx(df)
    p = null_v2.ticker_panel("AAA", df, ctx, cap=CAP)
    assert p.ticker == "AAA"
    assert (p.dates == df.index.to_numpy()).all()
    assert (p.event == ctx["raw"]).all()
    assert (p.trend == ctx["trend"]).all()
    expected = null.eligible_mask(ctx["raw"], ctx["member"], ctx["warm"], CAP)
    assert (p.eligible == expected).all()
    assert not p.eligible[p.event].any()
    assert p.atr_pct[400] == pytest.approx(ctx["atr"].iloc[400] / df["Close"].iloc[400])
    assert p.control is None and p.level_bars is None


def test_avoid_condition_leaves_the_pool_and_control_is_stored():
    df = random_walk(600, seed=3)
    base = _panel(df)
    bar = int(np.flatnonzero(base.eligible)[0])
    condition = np.zeros(len(df), dtype=bool)
    condition[bar] = True
    control = np.arange(len(df)) % 2 == 0
    p = null_v2.ticker_panel("AAA", df, _ctx(df, condition), cap=CAP, control=control)
    assert not p.eligible[bar]
    assert (p.eligible == (base.eligible & ~condition)).all()
    assert (p.control == control).all()


def test_level_bars_hold_open_high_low_and_the_previous_atr():
    df = random_walk(600, seed=3)
    atr = indicators.atr(df).to_numpy()
    bars = _panel(df, keep_bars=True).level_bars
    assert bars.shape == (len(df), 4)
    assert np.isnan(bars[0, 3])
    assert bars[300].tolist() == pytest.approx(
        [df["Open"].iloc[300], df["High"].iloc[300], df["Low"].iloc[300], atr[299]])


@pytest.mark.parametrize("field", ["trend", "atr_pct", "event"])
def test_panel_values_read_no_later_bar(field):
    df = random_walk(600, seed=5)
    assert_prefix_stable(lambda d: getattr(_panel(d), field).astype(float), df, [250, 333, 480, 599])


def test_eligibility_changes_under_truncation_only_through_completeness():
    df = random_walk(600, seed=5)
    full = _panel(df).eligible
    for t in (250, 333, 480):
        part = _panel(df.iloc[: t + 1]).eligible
        complete = np.arange(t + 1) + CAP <= t
        assert (part == (full[: t + 1] & complete)).all()


def test_terciles_cut_on_eligible_values_and_place_every_finite_ticker():
    values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 2.5, np.nan]) / 100
    eligible = np.array([True] * 9 + [False, False])
    assert null_v2.atr_terciles(values, eligible).tolist() == [
        0, 0, 0, 1, 1, 1, 2, 2, 2, 0, -1]


def test_terciles_without_an_eligible_ticker_are_all_off():
    out = null_v2.atr_terciles(np.array([0.01, 0.02]), np.array([False, False]))
    assert out.dtype == np.int8 and out.tolist() == [-1, -1]


def _bare(ticker, dates, atr, control=None):
    n = len(dates)
    return null_v2.TickerPanel(ticker, pd.DatetimeIndex(dates).to_numpy(),
                               np.ones(n, dtype=bool), np.ones(n, dtype=bool),
                               np.full(n, atr), np.zeros(n, dtype=bool), control)


def test_cross_section_unions_dates_sorts_tickers_and_marks_absent_bars():
    days = pd.bdate_range("2015-01-05", periods=4)
    panels = {"BBB": _bare("BBB", days[1:], 0.02), "AAA": _bare("AAA", days, 0.01),
              "CCC": _bare("CCC", days[:3], 0.03)}
    xs = null_v2.cross_section(panels)
    assert xs.tickers == ("AAA", "BBB", "CCC")
    assert list(xs.dates) == list(days)
    assert xs.pos[:, 1].tolist() == [-1, 0, 1, 2]
    assert xs.pos[:, 2].tolist() == [0, 1, 2, -1]
    assert not xs.eligible[0, 1] and not xs.eligible[3, 2]
    assert xs.tercile[1].tolist() == [0, 1, 2]
    assert xs.tercile[0, 1] == -1
    assert xs.control is None


def test_cross_section_control_defaults_false_for_panels_without_one():
    days = pd.bdate_range("2015-01-05", periods=3)
    panels = {"AAA": _bare("AAA", days, 0.01, control=np.array([True, False, True])),
              "BBB": _bare("BBB", days, 0.02)}
    xs = null_v2.cross_section(panels)
    assert xs.control[:, 0].tolist() == [True, False, True]
    assert not xs.control[:, 1].any()


def test_cross_section_of_nothing_is_empty():
    xs = null_v2.cross_section({})
    assert xs.tickers == () and len(xs.dates) == 0 and xs.pos.shape == (0, 0)


def test_stage_checkpoint_round_trips_atomically_and_lists_done_keys(tmp_path):
    cp = null_v2.StageCheckpoint(tmp_path)
    assert cp.load("BRK.B") is None and cp.done() == set()
    cp.save("BRK.B", {"x": 1})
    assert cp.load("BRK.B") == {"x": 1}
    assert cp.done() == {"BRK.B"}
    assert not list(tmp_path.glob("*.tmp"))


def test_stage_checkpoint_without_a_directory_is_a_no_op():
    cp = null_v2.StageCheckpoint(None)
    cp.save("AAA", 1)
    assert cp.load("AAA") is None and cp.done() == set()


def test_open_stage_writes_its_manifest_and_refuses_another_run(tmp_path):
    manifest = {"idea": "x", "scope": "ticker", "tickers": ("AAA", "BBB")}
    null_v2.open_stage(tmp_path, "panel", manifest, **QUIET)
    saved = json.loads((tmp_path / "panel" / "manifest.json").read_text(encoding="utf-8"))
    assert saved == {"idea": "x", "scope": "ticker", "tickers": ["AAA", "BBB"],
                     "null_version": "v2", "stage": "panel"}
    null_v2.open_stage(tmp_path, "panel", manifest, **QUIET)        # same run resumes
    with pytest.raises(ValueError, match="another run"):
        null_v2.open_stage(tmp_path, "panel", {**manifest, "scope": "market"}, **QUIET)


def test_open_stage_refuses_an_unknown_stage_and_a_v1_checkpoint(tmp_path):
    with pytest.raises(ValueError, match="unknown stage"):
        null_v2.open_stage(tmp_path, "rank", {"idea": "x"}, **QUIET)
    (tmp_path / "manifest.json").write_text(json.dumps({"idea": "x"}), encoding="utf-8")
    with pytest.raises(ValueError, match="v1"):
        null_v2.open_stage(tmp_path, "panel", {"idea": "x"}, **QUIET)
    other = tmp_path / "other"
    other.mkdir()
    (other / "AAA.pkl").write_bytes(b"")
    with pytest.raises(ValueError, match="v1"):
        null_v2.open_stage(other, "panel", {"idea": "x"}, **QUIET)
    assert null_v2.open_stage(None, "draw", {"idea": "x"}, **QUIET).done() == set()


def test_resumable_map_skips_finished_keys_and_never_saves_none(tmp_path):
    calls = []

    def fn(key):
        calls.append(key)
        return None if key == "CCC" else key.lower()

    cp = null_v2.StageCheckpoint(tmp_path)
    first = null_v2.resumable_map(["AAA", "BBB", "CCC"], fn, checkpoint=cp, **QUIET)
    assert first == {"AAA": "aaa", "BBB": "bbb"}
    calls.clear()
    again = null_v2.resumable_map(["AAA", "BBB", "CCC"], fn, checkpoint=cp, **QUIET)
    assert again == first and calls == ["CCC"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_v2_panel.py`
Expected: FAIL — `ImportError: cannot import name 'null_v2'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/backtesting/screen/null_v2.py`:

```python
"""v230 A2: the v2 matched null -- a cross-sectional pool in three stages.

Stage 1 (panel, per ticker): on the ticker's own bars, v1's eligible flag
(member, warm, race completes inside the frame, not a raw event), the trend
state (close > SMA200), ATR14 as a fraction of close, the raw event flag and,
in avoid mode, the control flag. Every value at bar t reads bars <= t, except
race completeness, which reads the frame's end exactly as v1 does.

Stage 2 (draw, per date): for an event on ticker i at date t the pool is
every other ticker j eligible at t, in the same trend state, in the same ATR%
tercile of t's eligible cross-section, with no raw event at t. Market-scope
ideas draw from the same ticker's trailing sessions instead.

Stage 3 (race, per null ticker): null bars raced on their own frame with
their own ATR14 and scattered back to their events.

v1's null.py is not edited; v2 imports its constants and masks.
"""
from __future__ import annotations

import json
import os
import pickle
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import null

NULL_VERSION = "v2"
STAGES = ("panel", "draw", "race")
STAGE_MANIFEST = "manifest.json"
_PROGRESS_EVERY = 50


def _bool(values) -> np.ndarray:
    return np.asarray(values, dtype=bool)


@dataclass(frozen=True, eq=False)
class TickerPanel:
    """Stage 1 for one ticker: one value per bar of its own frame."""
    ticker: str
    dates: np.ndarray
    eligible: np.ndarray
    trend: np.ndarray
    atr_pct: np.ndarray
    event: np.ndarray
    control: np.ndarray | None = None
    level_bars: np.ndarray | None = None


def _level_bars(df: pd.DataFrame, atr: np.ndarray) -> np.ndarray:
    """(n, 4): Open, High, Low and ATR14 of the previous bar (NaN on row 0),
    what a level fill at bar p reads (v1 ``null._null_fills``)."""
    prev_atr = np.r_[np.nan, atr[:-1]]
    return np.column_stack([df["Open"].to_numpy(dtype=float),
                            df["High"].to_numpy(dtype=float),
                            df["Low"].to_numpy(dtype=float), prev_atr])


def ticker_panel(ticker: str, df: pd.DataFrame, ctx: Mapping, *, cap: int,
                 control=None, keep_bars: bool = False) -> TickerPanel:
    """Stage 1 from one ticker's ``ticker_context``. In avoid mode
    ``ctx["condition"]`` leaves the pool and ``control`` is the control flag."""
    raw = _bool(ctx["raw"])
    eligible = null.eligible_mask(raw, ctx["member"], ctx["warm"], cap)
    if ctx.get("condition") is not None:
        eligible = eligible & ~_bool(ctx["condition"])
    atr = np.asarray(ctx["atr"], dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        atr_pct = atr / df["Close"].to_numpy(dtype=float)
    return TickerPanel(ticker, df.index.to_numpy(), eligible, _bool(ctx["trend"]), atr_pct,
                       raw, None if control is None else _bool(control),
                       _level_bars(df, atr) if keep_bars else None)


@dataclass(frozen=True, eq=False)
class CrossSection:
    """Every panel on the union calendar, shape (dates, tickers), tickers sorted."""
    dates: pd.DatetimeIndex
    tickers: tuple
    eligible: np.ndarray
    trend: np.ndarray
    tercile: np.ndarray
    event: np.ndarray
    control: np.ndarray | None
    pos: np.ndarray


def atr_terciles(atr_pct_row, eligible_row) -> np.ndarray:
    """0/1/2 by the date's eligible ATR% terciles for every finite value; -1 off."""
    values = np.asarray(atr_pct_row, dtype=float)
    out = np.full(values.shape, -1, dtype=np.int8)
    finite = np.isfinite(values)
    pool = values[_bool(eligible_row) & finite]
    if pool.size == 0:
        return out
    low, high = np.quantile(pool, [1 / 3, 2 / 3])
    out[finite] = (values[finite] > low).astype(np.int8) + (values[finite] > high)
    return out


def _union_dates(panels: Mapping[str, TickerPanel], tickers) -> pd.DatetimeIndex:
    if not tickers:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(np.unique(np.concatenate([panels[t].dates for t in tickers])))


def cross_section(panels: Mapping[str, TickerPanel]) -> CrossSection:
    tickers = tuple(sorted(panels))
    dates = _union_dates(panels, tickers)
    shape = (len(dates), len(tickers))
    eligible, trend, event = (np.zeros(shape, dtype=bool) for _ in range(3))
    atr_pct = np.full(shape, np.nan)
    pos = np.full(shape, -1, dtype=np.int32)
    with_control = any(panels[t].control is not None for t in tickers)
    control = np.zeros(shape, dtype=bool) if with_control else None
    for col, ticker in enumerate(tickers):
        p = panels[ticker]
        rows = dates.get_indexer(pd.DatetimeIndex(p.dates))
        eligible[rows, col], trend[rows, col], event[rows, col] = p.eligible, p.trend, p.event
        atr_pct[rows, col] = p.atr_pct
        pos[rows, col] = np.arange(len(rows), dtype=np.int32)
        if control is not None and p.control is not None:
            control[rows, col] = p.control
    tercile = np.zeros(shape, dtype=np.int8)
    for row in range(len(dates)):
        tercile[row] = atr_terciles(atr_pct[row], eligible[row])
    return CrossSection(dates, tickers, eligible, trend, tercile, event, control, pos)


class StageCheckpoint:
    """One pickle per finished key under a stage directory; a no-op without one."""

    def __init__(self, directory: Path | None):
        self.directory = None if directory is None else Path(directory)

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.pkl"

    def load(self, key: str):
        if self.directory is None:
            return None
        path = self._path(key)
        # pickle is safe here: local scratch files this same run wrote, never shared input
        return pickle.loads(path.read_bytes()) if path.exists() else None

    def save(self, key: str, obj) -> None:
        if self.directory is None:
            return
        final = self._path(key)
        tmp = final.with_name(final.name + ".tmp")
        tmp.write_bytes(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
        os.replace(tmp, final)

    def done(self) -> set[str]:
        if self.directory is None:
            return set()
        return {p.name[: -len(".pkl")] for p in self.directory.glob("*.pkl")}


def _normalised(manifest: Mapping) -> dict:
    return json.loads(json.dumps(dict(manifest), sort_keys=True, default=str))


def _refuse_v1_root(root: Path) -> None:
    """A v1 screen checkpoint keeps manifest.json and <ticker>.pkl in its root."""
    path = root / STAGE_MANIFEST
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if any(root.glob("*.pkl")) or (saved is not None
                                   and saved.get("null_version") != NULL_VERSION):
        raise ValueError(f"checkpoint {root} is a v1 screen checkpoint; "
                         "a v1 checkpoint never resumes under v2")


def open_stage(root, stage: str, manifest: Mapping, out=print) -> StageCheckpoint:
    """``<root>/<stage>/`` with a manifest adding ``null_version`` and ``stage``."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {STAGES}")
    if root is None:
        return StageCheckpoint(None)
    root = Path(root)
    if root.exists():
        _refuse_v1_root(root)
    directory = root / stage
    directory.mkdir(parents=True, exist_ok=True)
    full = _normalised({**manifest, "null_version": NULL_VERSION, "stage": stage})
    path = directory / STAGE_MANIFEST
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved != full:
            raise ValueError(f"checkpoint {directory} belongs to another run: "
                             f"{saved} != {full}")
    else:
        path.write_text(json.dumps(full, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
    checkpoint = StageCheckpoint(directory)
    out(f"[{manifest.get('idea', '?')}] {stage} checkpoint {directory}: "
        f"{len(checkpoint.done())} unit(s) already done", flush=True)
    return checkpoint


def resumable_map(keys: Iterable[str], fn: Callable[[str], object], *,
                  checkpoint: StageCheckpoint, out=print, label: str = "") -> dict:
    """``{key: fn(key)}``, resuming finished keys; a None result is never saved."""
    keys = list(keys)
    done = checkpoint.done()
    out(f"{label}: {len(done & set(keys))} of {len(keys)} already done", flush=True)
    results = {}
    for i, key in enumerate(keys, 1):
        obj = checkpoint.load(key) if key in done else None
        if obj is None:
            obj = fn(key)
            if obj is not None:
                checkpoint.save(key, obj)
        if obj is not None:
            results[key] = obj
        if i % _PROGRESS_EVERY == 0 or i == len(keys):
            out(f"{label}: {i}/{len(keys)} ({100 * i // len(keys)}%)", flush=True)
    return results
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_v2_panel.py`
Expected: PASS, 0 failed.

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py`
Expected: PASS (the new module sits under `swingbot/core/backtesting/screen/`).

Complexity: `python scripts/dev/complexity_gate.py` — `cross_section` and `resumable_map` are the largest, both under 10.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/null_v2.py tests/backtesting/screen/test_null_v2_panel.py
git commit -m "feat(v230): v2 null stage 1 -- ticker panels, cross-section, stage checkpoints"
```

### Task V230-7: v2 ticker-scope draw, refusals and the golden draws

**Model:** opus — the pool definition that replaces v1's same-month draw, its seed and consumption order, and the golden pins every later null change is judged against.

**Files:**
- Modify: `swingbot/core/backtesting/screen/null_v2.py` (imports; append the draw section)
- Test: `tests/backtesting/screen/test_null_v2_draw.py` (create)
- Test: `tests/backtesting/screen/test_null_golden.py` (create)
- Create: `tests/backtesting/screen/golden/null_draws.json` (written once by the golden module's `--write`)

**Interfaces:**
- Consumes: V230-6 `TickerPanel`, `CrossSection`, `cross_section`, `ticker_panel`; existing `null.K`, `null.MIN_CANDIDATES`, `null.null_seed`, `null.draw_groups`.
- Produces: `DRAW_COLUMNS = ("event_ticker", "event_pos", "event_date", "null_ticker", "null_pos", "fill")` (`event_pos` / `null_pos` are positions in each ticker's own frame; `fill` NaN on next-open draws); `date_seed(idea, day) -> list`; `ticker_pool(xs, row, col, *, require_control=False) -> np.ndarray` (column indices; `ValueError` when control is required and `xs.control` is None); `@dataclass(frozen=True) DrawResult(table, dropped: Counter, event_dates, starved_dates, slots, unfilled)` (`dropped` counts dropped events **per event ticker**, so V230-11 sets each `V2Ticker.counters["dropped_no_match"]` from it); `draw_ticker_scope(xs, booked, *, idea: str, k=null.K) -> DrawResult` (`booked`: event ticker → its kept event positions; an unknown ticker is a `ValueError`); `SCOPE_MISMATCH`, `NULL_STARVED`, `STARVED_SHARE = 0.5`; `class NullRefusal(ValueError)` (`.code`; `str(exc)` is `"<code>: <detail>"`, which V230-12 prints after `refused: `); `check_starvation(result, scope) -> None`. Private, reused by V230-8/9: `_v2_name`, `_records`, `_table`, `_events_by_row`, `_Tally` (see the part header).

An event whose pool is under the floor consumes nothing from the date's
generator (as v1); a date is starved when any of its events was dropped;
refusal fires when starved dates **exceed** half the event dates.

- [ ] **Step 1: Write the failing draw tests**

Create `tests/backtesting/screen/test_null_v2_draw.py`:

```python
"""v230 A2 stage 2, ticker scope: other tickers on the event's date, same
trend state, same ATR% tercile, no event of the idea that day; K = 20, floor
5; one generator per date consumed in sorted-ticker order."""
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators, null, null_v2
from swingbot.core.backtesting.screen import race as race_mod
from tests.backtesting.screen.helpers import random_walk

IDEA = "x"
DAYS = pd.bdate_range("2015-01-05", periods=5)
CAP = 10


def _panel(ticker, *, eligible=True, trend=True, atr=0.02, event=(), control=None):
    n = len(DAYS)
    ev = np.zeros(n, dtype=bool)
    ev[list(event)] = True
    return null_v2.TickerPanel(ticker, DAYS.to_numpy(), np.full(n, eligible) & ~ev,
                               np.full(n, trend), np.full(n, atr, dtype=float), ev,
                               None if control is None else np.asarray(control, dtype=bool))


def _xs(n=30, **special):
    names = [f"T{i:02d}" for i in range(n)]
    return null_v2.cross_section({t: _panel(t, **special.get(t, {})) for t in names})


def _names(xs, cols):
    return [xs.tickers[j] for j in cols]


def test_date_seed_is_the_v1_seed_on_the_idea_v2_name_and_the_day():
    assert null_v2.date_seed(IDEA, DAYS[0]) == null.null_seed("x:v2", "2015-01-05")
    assert null_v2.date_seed(IDEA, DAYS[0]) != null_v2.date_seed(IDEA, DAYS[1])


def test_pool_drops_the_event_ticker_event_tickers_and_ineligible_ones():
    xs = _xs(T00={"event": (2,)}, T01={"event": (2,)}, T02={"eligible": False})
    assert _names(xs, null_v2.ticker_pool(xs, 2, 0)) == [f"T{i:02d}" for i in range(3, 30)]


def test_pool_matches_trend_state_and_atr_tercile():
    xs = _xs(T03={"trend": False}, T04={"atr": 0.05}, T05={"atr": 0.05}, T06={"atr": 0.05})
    pool = _names(xs, null_v2.ticker_pool(xs, 1, 0))
    assert not {"T03", "T04", "T05", "T06"} & set(pool) and len(pool) == 25
    assert _names(xs, null_v2.ticker_pool(xs, 1, 4)) == ["T05", "T06"]


def test_pool_can_require_the_control_flag():
    xs = _xs(**{f"T{i:02d}": {"control": [i % 2 == 0] * 5} for i in range(30)})
    pool = null_v2.ticker_pool(xs, 1, 0, require_control=True)
    assert _names(xs, pool) == [f"T{i:02d}" for i in range(2, 30, 2)]
    with pytest.raises(ValueError, match="control"):
        null_v2.ticker_pool(_xs(), 1, 0, require_control=True)


def test_draw_takes_k_sorted_pool_bars_and_their_own_positions():
    xs = _xs(T00={"event": (1,)}, T03={"event": (1, 3)})
    result = null_v2.draw_ticker_scope(xs, {"T00": [1], "T03": [1, 3]}, idea=IDEA)
    table = result.table
    assert tuple(table.columns) == null_v2.DRAW_COLUMNS
    first = table[(table.event_ticker == "T00")]
    assert len(first) == null.K and first.null_ticker.is_unique
    assert list(first.null_ticker) == sorted(first.null_ticker)
    assert not {"T00", "T03"} & set(first.null_ticker)
    assert (first.event_date == DAYS[1]).all() and (first.null_pos == 1).all()
    assert table.fill.isna().all()
    assert (result.slots, result.unfilled, result.event_dates, result.starved_dates) == (
        3 * null.K, 0, 2, 0)


def test_draw_replays_the_date_generator_in_sorted_ticker_order():
    xs = _xs(T00={"event": (1,)}, T05={"event": (1,)})
    table = null_v2.draw_ticker_scope(xs, {"T05": [1], "T00": [1]}, idea=IDEA).table
    rng = np.random.default_rng(null_v2.date_seed(IDEA, DAYS[1]))
    for col in (0, 5):
        pool = null_v2.ticker_pool(xs, 1, col)
        expected = _names(xs, np.sort(rng.choice(pool, size=null.K, replace=False)))
        assert list(table[table.event_ticker == xs.tickers[col]].null_ticker) == expected


def test_draw_is_deterministic_and_another_date_leaves_a_date_alone():
    xs = _xs(T00={"event": (1,)}, T07={"event": (4,)})
    once = null_v2.draw_ticker_scope(xs, {"T00": [1]}, idea=IDEA).table
    pd.testing.assert_frame_equal(once, null_v2.draw_ticker_scope(xs, {"T00": [1]}, idea=IDEA).table)
    both = null_v2.draw_ticker_scope(xs, {"T00": [1], "T07": [4]}, idea=IDEA).table
    pd.testing.assert_frame_equal(both[both.event_ticker == "T00"].reset_index(drop=True), once)


def test_the_floor_is_inclusive_and_a_short_pool_drops_and_starves():
    kept = null_v2.draw_ticker_scope(_xs(6, T00={"event": (1,)}), {"T00": [1]}, idea=IDEA)
    assert len(kept.table) == null.MIN_CANDIDATES and kept.starved_dates == 0
    short = null_v2.draw_ticker_scope(_xs(6, T00={"event": (1,)}, T05={"trend": False}),
                                      {"T00": [1]}, idea=IDEA)
    assert short.table.empty and tuple(short.table.columns) == null_v2.DRAW_COLUMNS
    assert short.dropped == Counter({"T00": 1})
    assert (short.event_dates, short.starved_dates, short.slots) == (1, 1, 0)


def test_an_unknown_booked_ticker_is_refused():
    with pytest.raises(ValueError, match="ZZZ"):
        null_v2.draw_ticker_scope(_xs(), {"ZZZ": [1]}, idea=IDEA)


def _result(dates, starved):
    return null_v2.DrawResult(null_v2._table([]), Counter(), dates, starved, 0, 0)


@pytest.mark.parametrize("scope, code", [("ticker", "SCOPE_MISMATCH"),
                                         ("market", "NULL_STARVED")])
def test_refusal_fires_only_above_half_the_event_dates(scope, code):
    null_v2.check_starvation(_result(4, 2), scope)          # exactly half: no refusal
    null_v2.check_starvation(_result(0, 0), scope)
    with pytest.raises(null_v2.NullRefusal) as caught:
        null_v2.check_starvation(_result(4, 3), scope)
    assert caught.value.code == code and str(caught.value).startswith(f"{code}: 3 of 4")
    assert isinstance(caught.value, ValueError)


def test_refusal_rejects_an_unknown_scope():
    with pytest.raises(ValueError, match="scope"):
        null_v2.check_starvation(_result(1, 0), "sector")


def _ctx(df):
    atr = indicators.atr(df)
    sma200 = indicators.sma(df["Close"], 200)
    prior_high = df["High"].shift(1).rolling(20).max()
    return {"raw": (df["Close"] > prior_high).to_numpy(dtype=bool),
            "member": np.ones(len(df), dtype=bool), "atr": atr,
            "warm": race_mod.warm_mask(atr, sma200), "trend": null.trend_state(df, sma200)}


def _frames_xs(frames):
    return null_v2.cross_section({t: null_v2.ticker_panel(t, df, _ctx(df), cap=CAP)
                                  for t, df in frames.items()})


def test_pools_change_under_truncation_only_through_completeness():
    """Spec Constraints: cut every ticker's tail; the pool at t changes only
    through the race-completeness flag."""
    frames = {f"T{i:02d}": random_walk(600, seed=i + 1) for i in range(12)}
    cut = 450
    full = _frames_xs(frames)
    part = _frames_xs({t: df.iloc[: cut + 1] for t, df in frames.items()})
    for row in range(200, cut - CAP + 1):
        for col in range(12):
            assert (null_v2.ticker_pool(part, row, col)
                    == null_v2.ticker_pool(full, row, col)).all(), (row, col)
    assert not part.eligible[cut - CAP + 1:].any()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_v2_draw.py`
Expected: FAIL — `AttributeError: module ... null_v2 has no attribute 'date_seed'`.

- [ ] **Step 3: Write the draw section**

In `swingbot/core/backtesting/screen/null_v2.py` add `from collections import Counter`
to the imports, then append:

```python
DRAW_COLUMNS = ("event_ticker", "event_pos", "event_date", "null_ticker", "null_pos", "fill")
SCOPE_MISMATCH = "SCOPE_MISMATCH"
NULL_STARVED = "NULL_STARVED"
STARVED_SHARE = 0.5
_REFUSAL_CODES = {"ticker": SCOPE_MISMATCH, "market": NULL_STARVED}
_TABLE_TYPES = {"event_ticker": object, "event_pos": "int64", "event_date": "datetime64[ns]",
                "null_ticker": object, "null_pos": "int64", "fill": "float64"}


class NullRefusal(ValueError):
    """A v2 pool too thin to judge: raised after the draw, before any race."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code


def _v2_name(idea: str) -> str:
    return f"{idea}:v2"


def date_seed(idea: str, day) -> list:
    """Ticker scope: one generator per date, ``null_seed(idea + ":v2", ISO day)``."""
    return null.null_seed(_v2_name(idea), pd.Timestamp(day).strftime("%Y-%m-%d"))


def ticker_pool(xs: CrossSection, row: int, col: int, *,
                require_control: bool = False) -> np.ndarray:
    """Columns j != col eligible at row, same trend state and ATR% tercile, no event."""
    mask = (xs.eligible[row] & ~xs.event[row]
            & (xs.trend[row] == xs.trend[row, col])
            & (xs.tercile[row] == xs.tercile[row, col]))
    if require_control:
        if xs.control is None:
            raise ValueError("the cross-section carries no control flag")
        mask &= xs.control[row]
    mask[col] = False
    return np.flatnonzero(mask)


@dataclass(frozen=True)
class DrawResult:
    """Stage 2's artefact: the draw table and the counts the refusal reads."""
    table: pd.DataFrame
    dropped: Counter
    event_dates: int
    starved_dates: int
    slots: int
    unfilled: int


def _records(event_ticker, event_pos, day, null_tickers, null_pos, fills=None) -> list[tuple]:
    fills = np.full(len(null_pos), np.nan) if fills is None else np.asarray(fills, dtype=float)
    return [(event_ticker, int(event_pos), pd.Timestamp(day), str(t), int(p), float(f))
            for t, p, f in zip(null_tickers, null_pos, fills)]


def _table(records) -> pd.DataFrame:
    return pd.DataFrame.from_records(records, columns=list(DRAW_COLUMNS)).astype(_TABLE_TYPES)


class _Tally:
    """The draw passes' accumulator; event dates are sets, so a date seen on
    several tickers (market scope) counts once."""

    def __init__(self):
        self.records: list[tuple] = []
        self.dropped: Counter = Counter()
        self.days: set = set()
        self.starved_days: set = set()
        self.slots = 0
        self.unfilled = 0

    def add(self, rows) -> None:
        self.records.extend(rows)

    def count_slots(self, m) -> None:
        self.slots += int(m)

    def count_unfilled(self, m) -> None:
        self.unfilled += int(m)

    def mark_date(self, day, starved: bool) -> None:
        self.days.add(pd.Timestamp(day))
        if starved:
            self.starved_days.add(pd.Timestamp(day))

    def result(self) -> DrawResult:
        return DrawResult(_table(self.records), self.dropped, len(self.days),
                          len(self.starved_days), self.slots, self.unfilled)


def _events_by_row(xs: CrossSection, booked: Mapping) -> dict[int, list[tuple[int, int]]]:
    """{row: [(col, own position), ...]} with columns ascending (sorted tickers)."""
    unknown = sorted(set(booked) - set(xs.tickers))
    if unknown:
        raise ValueError(f"booked tickers missing from the cross-section: {unknown[:5]}")
    by_row: dict[int, list[tuple[int, int]]] = {}
    for col, ticker in enumerate(xs.tickers):
        positions = np.sort(np.asarray(booked.get(ticker, ()), dtype=int))
        rows = np.flatnonzero(xs.pos[:, col] >= 0)[positions]
        for row, pos in zip(rows.tolist(), positions.tolist()):
            by_row.setdefault(row, []).append((col, pos))
    return by_row


def draw_ticker_scope(xs: CrossSection, booked: Mapping, *, idea: str,
                      k: int = null.K) -> DrawResult:
    """Stage 2, ticker scope: up to k null bars per event from its date's pool."""
    tally = _Tally()
    for row, events in sorted(_events_by_row(xs, booked).items()):
        day = xs.dates[row]
        rng = np.random.default_rng(date_seed(idea, day))
        starved = False
        for col, pos in events:
            pool = ticker_pool(xs, row, col)
            if pool.size < null.MIN_CANDIDATES:
                tally.dropped[xs.tickers[col]] += 1
                starved = True
                continue
            pick = np.sort(rng.choice(pool, size=min(k, pool.size), replace=False))
            tally.count_slots(pick.size)
            tally.add(_records(xs.tickers[col], pos, day, [xs.tickers[j] for j in pick],
                               xs.pos[row, pick]))
        tally.mark_date(day, starved)
    return tally.result()


def check_starvation(result: DrawResult, scope: str) -> None:
    """SCOPE_MISMATCH / NULL_STARVED when starved dates exceed half the event dates."""
    if scope not in _REFUSAL_CODES:
        raise ValueError(f"unknown scope {scope!r}")
    if result.starved_dates > STARVED_SHARE * result.event_dates:
        raise NullRefusal(_REFUSAL_CODES[scope],
                          f"{result.starved_dates} of {result.event_dates} event dates "
                          f"left an event under {null.MIN_CANDIDATES} candidates")
```

- [ ] **Step 4: Run the draw tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_v2_draw.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Write the golden module**

Create `tests/backtesting/screen/test_null_golden.py`:

```python
"""v230: golden draws -- one v1 draw (null.draw_groups, next-open) and one
v2 draw (null_v2.draw_ticker_scope), captured once at V230-7 and compared
exactly. Never regenerate the file to make this pass: a changed draw is a
changed null, and v1 is frozen.

    python tests/backtesting/screen/test_null_golden.py --write   # V230-7 only

Inputs are integer draws and exact divisions, the same bits on every OS.
k = 3 / 4 keeps every pool larger than the draw, so the generator is pinned."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.screen import null, null_v2  # noqa: E402

GOLDEN_PATH = Path(__file__).with_name("golden") / "null_draws.json"
IDEA = "golden"
V1_K, V2_K = 3, 4
V2_TICKERS, V2_DATES, EVENT_TICKERS = 60, 24, 6


def v1_draw() -> dict:
    rng = np.random.default_rng(230)
    idx = pd.bdate_range("2019-01-01", "2019-03-29")
    df = pd.DataFrame({"Close": np.full(len(idx), 100.0)}, index=idx)
    event_pos = np.array([5, 20, 33, 47])
    eligible = rng.integers(0, 4, len(idx)) > 0
    eligible[event_pos] = False
    trend = rng.integers(0, 2, len(idx)) == 1
    g = null.draw_groups(df, event_pos, eligible, V1_K, null.null_seed(IDEA, "AAA"),
                         atr=None, trend=trend)
    return {"event_pos": g.event_pos.tolist(), "groups": [x.tolist() for x in g.groups]}


def v2_panels() -> dict:
    rng = np.random.default_rng(231)
    dates = pd.bdate_range("2016-01-04", periods=V2_DATES).to_numpy()
    panels = {}
    for i in range(V2_TICKERS):
        ticker = f"T{i:02d}"
        event = rng.integers(0, 6, V2_DATES) == 0
        eligible = (rng.integers(0, 5, V2_DATES) > 0) & ~event
        trend = rng.integers(0, 2, V2_DATES) == 1
        atr_pct = rng.integers(10, 60, V2_DATES) / 1000.0
        panels[ticker] = null_v2.TickerPanel(ticker, dates, eligible, trend, atr_pct, event)
    return panels


def v2_draw() -> list:
    panels = v2_panels()
    booked = {t: np.flatnonzero(panels[t].event) for t in sorted(panels)[:EVENT_TICKERS]}
    table = null_v2.draw_ticker_scope(null_v2.cross_section(panels), booked,
                                      idea=IDEA, k=V2_K).table
    return [[r.event_ticker, int(r.event_pos), r.event_date.strftime("%Y-%m-%d"),
             r.null_ticker, int(r.null_pos)] for r in table.itertuples(index=False)]


def capture() -> dict:
    return {"v1": v1_draw(), "v2": v2_draw()}


def _golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_the_v1_draw_is_unchanged():
    assert v1_draw() == _golden()["v1"]


def test_the_v2_draw_is_unchanged():
    assert v2_draw() == _golden()["v2"]


def test_the_golden_draws_exercise_the_generators():
    golden = _golden()
    assert len(golden["v1"]["groups"]) >= 3
    assert all(len(g) == V1_K for g in golden["v1"]["groups"])
    assert len(golden["v2"]) >= 10 * V2_K


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    if not parser.parse_args(argv).write:
        parser.error("pass --write to capture the golden draws (V230-7 only)")
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(capture(), indent=1) + "\n",
                           encoding="utf-8", newline="\n")
    print(f"wrote {GOLDEN_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Capture the golden file once and run the golden tests**

Run: `python tests/backtesting/screen/test_null_golden.py --write`
Expected: `wrote ...golden/null_draws.json`. Open it: `v1.groups` holds 3-element lists, `v2` at least 40 rows. If `test_the_golden_draws_exercise_the_generators` fails, adjust the fixture constants (never the null code) and capture again — this is the only capture.

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_golden.py`
Expected: PASS, 3 passed.

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null.py`
Expected: PASS (v1 untouched). Complexity: `python scripts/dev/complexity_gate.py` — `draw_ticker_scope` and `_events_by_row` stay under 10.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/backtesting/screen/null_v2.py tests/backtesting/screen/test_null_v2_draw.py tests/backtesting/screen/test_null_golden.py tests/backtesting/screen/golden/null_draws.json
git commit -m "feat(v230): v2 ticker-scope draw, starvation refusals, golden v1/v2 draws"
```

### Task V230-8: v2 market-scope draw

**Model:** opus — the trailing pool and its embargo decide whether a market-wide trigger's null can see the future; the edge is subtle (events after *t*).

**Files:**
- Modify: `swingbot/core/backtesting/screen/null_v2.py` (append the market-scope section)
- Test: `tests/backtesting/screen/test_null_v2_market.py` (create)

**Interfaces:**
- Consumes: V230-6 `TickerPanel`; V230-7 `DrawResult`, `check_starvation`, `NullRefusal`, `NULL_STARVED`, `_v2_name`, `_records`, `_Tally` (`mark_date`, `count_slots`, `add`, `dropped`, `result()`); existing `null.K`, `null.MIN_CANDIDATES`, `null.null_seed`.
- Produces: `TRAILING_DAYS = 252`; `market_pool(panel, pos, *, cap) -> np.ndarray` (own-frame positions); `draw_market_scope(panels: Mapping[str, TickerPanel], booked: Mapping[str, array], *, idea: str, cap: int, k=null.K) -> DrawResult` (`null_ticker == event_ticker`; `fill` NaN; `event_dates` / `starved_dates` count distinct dates across tickers; `dropped` per event ticker). V230-9's `draw` dispatches `idea.scope == "market"` here and then calls `check_starvation(result, "market")`.

**Pool (spec A2, index Global Constraints):** for an event at own position
`pos`, the positions `p` in `[pos - 252, pos)` that are eligible, share the
trend state of `pos`, and lie more than `cap` bars from every raw event of the
ticker. The embargo reads `panel.event[: pos + 1]` only: because `pos` is itself
a raw event, any `p` within `cap` bars of a later event is already within `cap`
of `pos`, so cutting the event flag at `pos` changes nothing and makes the
pool causal by construction. Every null race therefore ends before the event's
signal bar (`p + cap < pos`). One generator per ticker,
`null_seed(f"{idea}:v2", ticker)`, consumed over that ticker's events ascending;
an event under the floor consumes nothing.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/screen/test_null_v2_market.py`:

```python
"""v230 A2 stage 2, market scope: the same ticker's trailing 252 sessions,
same trend state, embargo of CAP bars around every raw event, floor 5, one
generator per ticker. No null bar postdates its event."""
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import null, null_v2

IDEA = "x"
CAP = 10
N = 600


def _panel(ticker="AAA", events=(), trend=None, eligible=None):
    dates = pd.bdate_range("2012-01-02", periods=N).to_numpy()
    ev = np.zeros(N, dtype=bool)
    ev[list(events)] = True
    elig = (np.ones(N, dtype=bool) if eligible is None else eligible) & ~ev
    tr = np.ones(N, dtype=bool) if trend is None else trend
    return null_v2.TickerPanel(ticker, dates, elig, tr, np.full(N, 0.02), ev)


def _pool(panel, pos):
    return null_v2.market_pool(panel, pos, cap=CAP).tolist()


def test_pool_is_the_trailing_window_short_of_the_event_embargo():
    assert null_v2.TRAILING_DAYS == 252
    assert _pool(_panel(events=(400,)), 400) == list(range(400 - 252, 400 - CAP))


def test_pool_starts_at_the_first_bar_when_history_is_short():
    assert _pool(_panel(events=(100,)), 100) == list(range(0, 100 - CAP))


def test_pool_skips_bars_within_cap_of_an_earlier_event():
    pool = _pool(_panel(events=(300, 400)), 400)
    assert pool == [p for p in range(148, 390) if abs(p - 300) > CAP]


def test_pool_matches_the_event_bar_trend_state_and_eligibility():
    trend = np.arange(N) % 2 == 1                            # bar 400 is down-trend
    eligible = np.ones(N, dtype=bool)
    eligible[200:250] = False
    pool = _pool(_panel(events=(400,), trend=trend, eligible=eligible), 400)
    assert pool and all(p % 2 == 0 for p in pool)
    assert not set(range(200, 250)) & set(pool)


def test_later_events_never_change_the_pool():
    alone = _pool(_panel(events=(400,)), 400)
    assert _pool(_panel(events=(400, 405, 420, 500)), 400) == alone
    assert max(alone) < 400 - CAP


def test_draw_takes_k_bars_from_the_same_ticker_on_its_own_seed():
    panel = _panel(events=(400,))
    result = null_v2.draw_market_scope({"AAA": panel}, {"AAA": [400]}, idea=IDEA, cap=CAP)
    table = result.table
    assert tuple(table.columns) == null_v2.DRAW_COLUMNS
    assert (table.null_ticker == "AAA").all() and (table.event_ticker == "AAA").all()
    assert (table.event_date == pd.Timestamp(panel.dates[400])).all()
    assert table.fill.isna().all()
    rng = np.random.default_rng(null.null_seed("x:v2", "AAA"))
    expected = np.sort(rng.choice(null_v2.market_pool(panel, 400, cap=CAP),
                                  size=null.K, replace=False))
    assert table.null_pos.tolist() == expected.tolist()
    assert (result.slots, result.unfilled, result.event_dates, result.starved_dates) == (
        null.K, 0, 1, 0)


def test_events_are_consumed_ascending_and_other_tickers_leave_a_ticker_alone():
    aaa = _panel(events=(300, 400))
    one = null_v2.draw_market_scope({"AAA": aaa}, {"AAA": [400, 300]}, idea=IDEA, cap=CAP)
    assert one.table.event_pos.tolist() == [300] * null.K + [400] * null.K
    panels = {"AAA": aaa, "BBB": _panel("BBB", events=(350,))}
    two = null_v2.draw_market_scope(panels, {"BBB": [350], "AAA": [300, 400]},
                                    idea=IDEA, cap=CAP)
    mine = two.table[two.table.event_ticker == "AAA"].reset_index(drop=True)
    pd.testing.assert_frame_equal(mine, one.table)


def test_a_short_pool_drops_the_event_and_starves_its_date_once():
    panels = {"AAA": _panel(events=(3, 400)), "BBB": _panel("BBB", events=(3,))}
    result = null_v2.draw_market_scope(panels, {"AAA": [3, 400], "BBB": [3]},
                                       idea=IDEA, cap=CAP)
    assert result.dropped == Counter({"AAA": 1, "BBB": 1})
    assert (result.event_dates, result.starved_dates) == (2, 1)
    null_v2.check_starvation(result, "market")                # 1 of 2: not above half


def test_null_starved_fires_before_any_race():
    panels = {"AAA": _panel(events=(3,)), "BBB": _panel("BBB", events=(3,))}
    result = null_v2.draw_market_scope(panels, {"AAA": [3], "BBB": [3]}, idea=IDEA, cap=CAP)
    assert result.table.empty
    with pytest.raises(null_v2.NullRefusal) as caught:
        null_v2.check_starvation(result, "market")
    assert caught.value.code == null_v2.NULL_STARVED


def test_an_unknown_booked_ticker_is_refused():
    with pytest.raises(ValueError, match="ZZZ"):
        null_v2.draw_market_scope({"AAA": _panel()}, {"ZZZ": [400]}, idea=IDEA, cap=CAP)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_v2_market.py`
Expected: FAIL — `AttributeError: module ... null_v2 has no attribute 'TRAILING_DAYS'`.

- [ ] **Step 3: Write the market-scope section**

Append to `swingbot/core/backtesting/screen/null_v2.py`:

```python
TRAILING_DAYS = 252


def _embargoed(event: np.ndarray, lo: int, hi: int, cap: int) -> np.ndarray:
    """True for positions lo..hi-1 within ``cap`` bars of any raw event in ``event``."""
    hits = np.flatnonzero(event)
    window = np.arange(lo, hi)
    if hits.size == 0:
        return np.zeros(window.size, dtype=bool)
    nxt = np.searchsorted(hits, window)                       # first event at or after p
    after = hits[np.minimum(nxt, hits.size - 1)] - window
    before = window - hits[np.maximum(nxt - 1, 0)]
    return ((nxt < hits.size) & (after <= cap)) | ((nxt > 0) & (before <= cap))


def market_pool(panel: TickerPanel, pos: int, *, cap: int) -> np.ndarray:
    """Market scope: own positions in the TRAILING_DAYS sessions before ``pos``,
    eligible, same trend state, more than ``cap`` bars from every raw event.
    Reads the event flag up to ``pos`` only; ``pos`` is itself a raw event, so
    a later event could only embargo bars ``pos`` already embargoes."""
    lo = max(0, pos - TRAILING_DAYS)
    near = _embargoed(panel.event[: pos + 1], lo, pos, cap)
    keep = (panel.eligible[lo:pos] & (panel.trend[lo:pos] == panel.trend[pos]) & ~near)
    return np.arange(lo, pos)[keep]


def _draw_market_ticker(tally: _Tally, panel: TickerPanel, positions, *,
                        idea: str, cap: int, k: int) -> None:
    rng = np.random.default_rng(null.null_seed(_v2_name(idea), panel.ticker))
    for pos in np.sort(np.asarray(positions, dtype=int)).tolist():
        day = panel.dates[pos]
        pool = market_pool(panel, pos, cap=cap)
        starved = pool.size < null.MIN_CANDIDATES
        tally.mark_date(day, starved)
        if starved:
            tally.dropped[panel.ticker] += 1
            continue
        pick = np.sort(rng.choice(pool, size=min(k, pool.size), replace=False))
        tally.count_slots(pick.size)
        tally.add(_records(panel.ticker, pos, day, [panel.ticker] * pick.size, pick))


def draw_market_scope(panels: Mapping[str, TickerPanel], booked: Mapping, *, idea: str,
                      cap: int, k: int = null.K) -> DrawResult:
    """Stage 2, market scope: one generator per ticker, its events ascending."""
    unknown = sorted(set(booked) - set(panels))
    if unknown:
        raise ValueError(f"booked tickers without a panel: {unknown[:5]}")
    tally = _Tally()
    for ticker in sorted(booked):
        _draw_market_ticker(tally, panels[ticker], booked[ticker], idea=idea, cap=cap, k=k)
    return tally.result()
```

Also extend the module docstring's stage-2 paragraph with one sentence:
`Market scope: the same ticker's TRAILING_DAYS sessions before t, embargoed
CAP bars around every raw event, so no null bar postdates its event.`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_v2_market.py`
Expected: PASS, 0 failed.

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_v2_draw.py`
Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_null_golden.py`
Expected: PASS (the shared `_Tally` and the ticker-scope draw are unchanged).

Complexity: `python scripts/dev/complexity_gate.py` — `_draw_market_ticker` is the largest, under 6.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/null_v2.py tests/backtesting/screen/test_null_v2_market.py
git commit -m "feat(v230): v2 market-scope draw -- trailing 252 sessions with event embargo"
```

