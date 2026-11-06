# v211 — Shock-conditioned short screens, Part 4: read-outs

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [v209 — Market-shock detector (shadow) and shock-conditioned short screens](../specs/2026-11-05-v209-market-shock-detector-design.md) § Track 2 → "Printed alongside each verdict (never gating)", "The two ideas form one FAMILY … `ledger_qvalues` across every short idea".
**Index:** [`2026-11-06-v211-shock-short-screens_0-index.md`](2026-11-06-v211-shock-short-screens_0-index.md) — Global Constraints, Review Focus, Parallelisation and the task ledger are the contract; every task here implicitly includes them.
**Worktree:** `.claude/worktrees/2026-11-06-v211-shock-short-screens` (all paths below are relative to it).

Tasks: V211-10, V211-11, V211-11b (split from V211-11), V211-12. Order: 10 → 11 → 11b → 12 (11/11b/12 all edit `scripts/backtest/screen_idea.py`).

Contracts consumed from other parts (ledger, final):
- V211-4: `Idea.context_kind`, `load_context(..., kind=)`, `_mode_runner(args)` (dispatches `--count-only`; `main` grows no branch).
- V211-5: `ticker_context(...)["context"]` (the ticker's context mapping or `None`); `render_results` appends `_render_context` only for `idea.context and idea.context_kind == "z"`; `_context_run` untouched there.
- V211-6: `_run_screens(args, idea, universe, data, spy) -> dict` (screen, `with_diagnostics`, `with_short_blocks`); test helpers in `tests/backtest_scripts/test_screen_level_context.py`: `_level_cache`, `_fake_level_idea`, `LEVEL`, `SHOCK_PARAMS`, `_level_argv`.
- V211-7: `ideas/_shock_breakdown.py` — `BREADTH`, `VIX`, `shock_state(breadth: pd.Series, vix: pd.Series) -> pd.DataFrame` (context calendar; `shock: bool`, `episode: int`), `ticker_state(df, context) -> pd.DataFrame` (same columns on `df.index`, absent dates NORMAL/0).
- V211-8/9: the two registered level ideas (`CONTEXT_KIND = "level"`, `control_events`).

# Phase D — Read-outs

### Task V211-10: `shock_readouts.py`: gap buckets, day of episode, shock-day null, preflight counts

**Model:** opus — the shock-day null is a second sampling design beside the matched null, and the day-of-episode tag must read no bar after the signal date (no lookahead).

**Files:**
- Create: `swingbot/core/backtesting/screen/shock_readouts.py`
- Create: `tests/backtesting/screen/test_shock_readouts.py` (suite `backtesting-arms`, existing directory)

**Interfaces:**
- Consumes: `null.MIN_CANDIDATES` (5), `null.null_seed`, `race.race_for(shape)`, `verdict.YEARS` (all existing). Needs nothing from V211-7 at import time: the state frame is an argument (V211-7 produces its shape: `shock: bool`, `episode: int`, 0 when NORMAL).
- Produces (index ledger, final):
  - `SHOCK_STRESS_SLIPPAGE_FACTOR = 3`
  - `GAP_BUCKETS = ("<= -1%", "-1% .. +1%", ">= +1%")`; `EPISODE_DAYS = ("peak", "later")`
  - `gap_bucket(gap_pct: float) -> str | None` — `gap_pct` in **percent** (`-1.0` = −1 %); `None` for NaN.
  - `event_tags(df, state: pd.DataFrame, breadth: pd.Series, signal_pos: np.ndarray) -> list[dict]` — one dict per signal position, in order: `{"signal_date": "YYYY-MM-DD", "gap_pct": float (NaN when no next bar), "gap_bucket": str | None, "episode_day": "peak" | "later" | None}`.
  - `@dataclass(frozen=True, eq=False) class ShockNull: event_pos: np.ndarray; null_mean_r: np.ndarray; dropped: int`
  - `shock_null(df, event_pos, pool: np.ndarray, k: int, seed, *, cap: int, atr, shape: str, direction: str, slippage_bps=None, commission=None) -> ShockNull`
  - `preflight_years(state: pd.DataFrame, event_dates: Iterable, years=verdict.YEARS) -> dict[int, dict]` → `{year: {"shock_days": int, "shock_weeks": int, "events": int}}`, every year of `years` present, in order.

**Why:** spec § Printed alongside each verdict freezes five read-outs before any TRAIN result is read. This task holds the pure parts, so the runner wiring (V211-11) only routes data. The definitions below are the index's OPEN decisions, written as tests:
- **Gap**: `100 × (Open[t+1] − Close[t]) / Close[t]`; `−1 %` is in `<= -1%`, `+1 %` in `>= +1%`; a signal on the frame's last bar has no next open (NaN, bucket `None`, counted as missing by the runner).
- **Day of the episode**: `peak` when the signal date's breadth equals the running maximum of breadth over the same episode's dates up to and including the signal date (ties count as `peak`). The entry is then the session after the breadth peak so far. Every other SHOCK date is `later`; a NORMAL date gets `None`. The running maximum restarts with each episode id and never reads a date after the signal (no lookahead).
- **Shock-day null**: K bars drawn without replacement from `pool` (the caller passes the eligible bars that are SHOCK on this ticker). There is no month or trend match, because inside a handful of shock days that match would drop nearly every event. The same `null.MIN_CANDIDATES` floor applies: a pool smaller than 5 drops every event. Raced with the idea's own shape and direction, at the given costs.
- **Preflight**: shock days and events per calendar year; shock weeks = distinct ISO `(year, week)` pairs among that calendar year's SHOCK dates (the bootstrap clusters on ISO weeks). An ISO week that straddles 31 December counts once in each calendar year. Event dates are entry dates, the year `verdict.per_year` books them in.

- [ ] **Step 1: Write the failing tests** — create `tests/backtesting/screen/test_shock_readouts.py`:

```python
"""v211 shock read-outs (spec § Printed alongside each verdict): gap
buckets, day of the episode, the shock-day null and the outcome-blind
preflight. Pure functions; printed by the runner, never gating."""
import types

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import null, verdict
from swingbot.core.backtesting.screen import shock_readouts as sr
from tests.backtesting.screen.helpers import frame, random_walk


def test_the_frozen_constants():
    assert sr.SHOCK_STRESS_SLIPPAGE_FACTOR == 3
    assert sr.GAP_BUCKETS == ("<= -1%", "-1% .. +1%", ">= +1%")
    assert sr.EPISODE_DAYS == ("peak", "later")


@pytest.mark.parametrize("gap, bucket", [
    (-5.0, "<= -1%"), (-1.0, "<= -1%"), (-0.999, "-1% .. +1%"), (0.0, "-1% .. +1%"),
    (0.999, "-1% .. +1%"), (1.0, ">= +1%"), (7.5, ">= +1%")])
def test_gap_bucket_edges_fall_on_the_outer_buckets(gap, bucket):
    assert sr.gap_bucket(gap) == bucket


def test_a_missing_gap_has_no_bucket():
    assert sr.gap_bucket(float("nan")) is None


# --- event tags ----------------------------------------------------------------

def _tag_inputs():
    """Eight bars at Close 100. Opens: bar 1 = 99 (-1 % gap after bar 0),
    bar 2 = 101 (+1 %), bar 3 = 100.5 (+0.5 %). Episode 1 on bars 1-3,
    episode 2 on bars 5-6 (its breadth stays below episode 1's peak)."""
    closes = np.full(8, 100.0)
    opens = closes.copy()
    opens[1], opens[2], opens[3] = 99.0, 101.0, 100.5
    df = frame(closes, opens=opens)
    shock = np.array([False, True, True, True, False, True, True, False])
    episode = np.array([0, 1, 1, 1, 0, 2, 2, 0])
    state = pd.DataFrame({"shock": shock, "episode": episode}, index=df.index)
    breadth = pd.Series([0.0, 0.45, 0.30, 0.50, 0.05, 0.42, 0.41, 0.0], index=df.index)
    return df, state, breadth


SIGNALS = np.array([0, 1, 2, 3, 5, 6, 7])


def test_event_tags_bucket_the_gap_and_the_day_of_the_episode():
    df, state, breadth = _tag_inputs()
    tags = sr.event_tags(df, state, breadth, SIGNALS)
    assert [t["signal_date"] for t in tags] == [d.strftime("%Y-%m-%d") for d in df.index[SIGNALS]]
    assert [t["gap_bucket"] for t in tags] == [
        "<= -1%", ">= +1%", "-1% .. +1%", "-1% .. +1%", "-1% .. +1%", "-1% .. +1%", None]
    assert [t["episode_day"] for t in tags] == [None, "peak", "later", "peak", "peak", "later", None]
    assert tags[0]["gap_pct"] == pytest.approx(-1.0)
    assert tags[2]["gap_pct"] == pytest.approx(0.5)
    assert np.isnan(tags[-1]["gap_pct"])


def test_event_tags_never_read_a_later_breadth():
    df, state, breadth = _tag_inputs()
    before = sr.event_tags(df, state, breadth, np.array([1, 2]))
    later = breadth.copy()
    later.iloc[3] = 0.99          # a higher peak after the signals
    assert sr.event_tags(df, state, later, np.array([1, 2])) == before


def test_event_tags_read_breadth_on_a_wider_context_calendar():
    df, state, breadth = _tag_inputs()
    wide = pd.concat([pd.Series([0.9], index=[pd.Timestamp("2009-12-31")]), breadth])
    assert _same(sr.event_tags(df, state, wide, SIGNALS), sr.event_tags(df, state, breadth, SIGNALS))


def _same(a, b):
    """Tag lists equal, NaN gaps equal to each other."""
    strip = lambda tags: [{k: v for k, v in t.items() if k != "gap_pct"} for t in tags]  # noqa: E731
    gaps = lambda tags: [t["gap_pct"] for t in tags]  # noqa: E731
    return strip(a) == strip(b) and np.allclose(gaps(a), gaps(b), equal_nan=True)


def test_event_tags_of_no_signal_are_empty():
    df, state, breadth = _tag_inputs()
    assert sr.event_tags(df, state, breadth, np.array([], dtype=int)) == []


# --- the shock-day null --------------------------------------------------------

@pytest.fixture
def raced(monkeypatch):
    """Replace the race with one whose R is the bar position, and record the call."""
    seen = {}

    def fake_race(df, positions, cap, *, atr=None, slippage_bps=None, commission=None, **extra):
        seen.update(positions=np.asarray(positions), cap=cap, extra=extra,
                    slippage_bps=slippage_bps, commission=commission)
        return types.SimpleNamespace(r=np.asarray(positions, dtype=float))

    def race_for(shape):
        seen["shape"] = shape
        return fake_race

    monkeypatch.setattr(sr.race, "race_for", race_for)
    return seen


POOL_BARS = [40, 50, 60, 70, 80, 90, 100]


def _pool(bars=POOL_BARS, n=300):
    pool = np.zeros(n, dtype=bool)
    pool[bars] = True
    return pool


def _null(pool, k=20, events=(10, 20), direction="short", **costs):
    return sr.shock_null(random_walk(300), np.array(events, dtype=int), pool, k,
                         null.null_seed("x", "AAA"), cap=10, atr=None, shape="fixed",
                         direction=direction, **costs)


def test_the_shock_null_draws_only_pool_bars_without_replacement(raced):
    out = _null(_pool(), slippage_bps=5.0, commission=0.01)
    assert out.event_pos.tolist() == [10, 20] and out.dropped == 0
    assert raced["shape"] == "fixed" and raced["cap"] == 10
    assert raced["extra"] == {"direction": "short"}
    assert (raced["slippage_bps"], raced["commission"]) == (5.0, 0.01)
    # k = 20 > 7 pool bars: each group is the whole pool, once each
    assert sorted(raced["positions"].tolist()) == sorted(POOL_BARS * 2)
    assert out.null_mean_r.tolist() == [70.0, 70.0]


def test_a_smaller_k_draws_k_distinct_pool_bars_per_event(raced):
    out = _null(_pool(), k=3)
    groups = raced["positions"].reshape(2, 3)
    for group in groups:
        assert len(set(group.tolist())) == 3 and set(group.tolist()) <= set(POOL_BARS)
    assert out.null_mean_r.tolist() == pytest.approx(groups.mean(axis=1).tolist())


def test_the_shock_null_is_deterministic(raced):
    first = _null(_pool(), k=3)
    second = _null(_pool(), k=3)
    assert first.null_mean_r.tolist() == second.null_mean_r.tolist()


def test_a_long_idea_passes_no_direction(raced):
    _null(_pool(), direction="long")
    assert raced["extra"] == {}


def test_a_pool_below_the_floor_drops_every_event_and_races_nothing(raced):
    out = _null(_pool(POOL_BARS[: null.MIN_CANDIDATES - 1]))
    assert out.event_pos.tolist() == [] and out.null_mean_r.tolist() == []
    assert out.dropped == 2 and raced == {}


def test_no_event_races_nothing(raced):
    out = _null(_pool(), events=())
    assert out.event_pos.tolist() == [] and out.dropped == 0 and raced == {}


# --- the outcome-blind preflight -----------------------------------------------

def _preflight_state():
    index = pd.bdate_range("2010-12-27", "2015-01-09")
    shock = pd.Series(False, index=index)
    for day in ("2010-12-28", "2011-03-01", "2011-03-02", "2011-03-08",
                "2014-12-31", "2015-01-02"):
        shock[pd.Timestamp(day)] = True
    return pd.DataFrame({"shock": shock, "episode": shock.astype(int)})


def test_preflight_counts_shock_days_iso_weeks_and_events_per_year():
    events = ["2011-03-02", "2011-03-03", "2014-12-31", "2010-12-29"]
    table = sr.preflight_years(_preflight_state(), events)
    assert list(table) == list(verdict.YEARS)
    assert table[2011] == {"shock_days": 3, "shock_weeks": 2, "events": 2}
    assert table[2012] == {"shock_days": 0, "shock_weeks": 0, "events": 0}
    # 2014-12-31 and 2015-01-02 share ISO week 2015-W01: once in each calendar year
    assert table[2014] == {"shock_days": 1, "shock_weeks": 1, "events": 1}
    assert table[2015] == {"shock_days": 1, "shock_weeks": 1, "events": 0}


def test_preflight_takes_timestamps_and_ignores_years_outside_the_rule():
    events = pd.to_datetime(["2010-12-29", "2011-03-02"])
    table = sr.preflight_years(_preflight_state(), events)
    assert 2010 not in table and table[2011]["events"] == 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_shock_readouts.py`
Expected: FAIL at collection — `ImportError: cannot import name 'shock_readouts'`.

- [ ] **Step 3: Implement `swingbot/core/backtesting/screen/shock_readouts.py`**

Module docstring: *"v211 (spec § Track 2, Printed alongside each verdict): the shock read-outs printed beside a level idea's verdict -- gap split, day of the episode, the shock-day null, the 3 x friction stress factor and the outcome-blind preflight. Pure; never gating; reads no bar after the signal date."* Imports: `dataclasses.dataclass`, `typing.Iterable`, `numpy`, `pandas`, `from swingbot.core.backtesting.screen import null, race, verdict`.

- Constants as in Interfaces, each with a `#:` comment citing the spec bullet.
- `gap_bucket(gap_pct)`: `None` if `not np.isfinite(gap_pct)`; `GAP_BUCKETS[0]` if `gap_pct <= -1.0`; `GAP_BUCKETS[2]` if `gap_pct >= 1.0`; else `GAP_BUCKETS[1]`.
- `_gaps(df, signal_pos) -> np.ndarray` — `100.0 * (Open[t+1] − Close[t]) / Close[t]` per position, NaN where `t + 1 >= len(df)`.
- `_episode_days(state, breadth, index, signal_pos) -> list` — `on = breadth.reindex(index)`; `episode = state["episode"].reindex(index, fill_value=0).to_numpy(dtype=int)`; `running = on.groupby(episode).cummax().to_numpy()` (`groupby(...).cummax()` keeps the row order and reads only earlier rows of the same episode); per `t`: `None` if `episode[t] == 0`, `"peak"` if `on.iloc[t] >= running[t]`, else `"later"`.
- `event_tags(...)`: zip the two helpers with `index[signal_pos].strftime("%Y-%m-%d")`; `gap_pct` as a Python `float`; `[]` for an empty `signal_pos`.
- `ShockNull` as in Interfaces.
- `shock_null(...)`:

```python
    event_pos = np.asarray(event_pos, dtype=int)
    bars = np.flatnonzero(np.asarray(pool, dtype=bool))
    if len(event_pos) == 0 or len(bars) < null.MIN_CANDIDATES:
        return ShockNull(np.array([], dtype=int), np.array([], dtype=float), len(event_pos))
    rng = np.random.default_rng(seed)
    size = min(k, len(bars))
    groups = [np.sort(rng.choice(bars, size=size, replace=False)) for _ in event_pos]
    extra = {} if direction == "long" else {"direction": direction}
    raced = race.race_for(shape)(df, np.concatenate(groups), cap, atr=atr,
                                 slippage_bps=slippage_bps, commission=commission, **extra)
    means = raced.r.reshape(len(groups), size).mean(axis=1)
    return ShockNull(event_pos, means, 0)
```

  (The `direction` handling mirrors `null.matched_null`, so a long call is byte-for-byte the race's default.)
- `preflight_years(...)`: `days = state.index[state["shock"].to_numpy(dtype=bool)]`; `iso = days.isocalendar()`; `events = pd.DatetimeIndex(pd.to_datetime(list(event_dates)))`; per year: `in_year = days.year == year`, `shock_weeks = len(set(zip(iso["year"][in_year], iso["week"][in_year])))`, `events = int((events.year == year).sum())`. Keep each function < 15 CC.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_shock_readouts.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Import guard and complexity**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py` then `python scripts/dev/complexity_gate.py`
Expected: `0 failed`; gate exit 0 (no new function ≥ 15).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/screen/shock_readouts.py tests/backtesting/screen/test_shock_readouts.py
git commit -m "feat(v211): shock read-outs -- gap buckets, episode day, shock-day null, preflight (V211-10)"
```

### Task V211-11: Runner wiring: `TickerScreen.shock` and the pooled shock block

**Model:** opus — it touches `screen_ticker`, the function the parity digests pin, and adds a second null and a re-priced book beside a one-shot verdict that must not move.

**Files:**
- Modify: `scripts/backtest/screen_idea.py` (imports; `TickerScreen.shock`; new `_SHOCK_NULL_TAG`, `_shock_rows`, `_shock_report`; `screen_ticker` (one keyword); new `_shock_split`, `with_shock_blocks`; `_run_screens` (V211-6) gains one line)
- Create: `tests/backtest_scripts/test_screen_shock_blocks.py`

**Interfaces:**
- Consumes: V211-10 `shock_readouts.{SHOCK_STRESS_SLIPPAGE_FACTOR, GAP_BUCKETS, EPISODE_DAYS, event_tags, shock_null, ShockNull}`; V211-7 `_shock_breakdown.{BREADTH, ticker_state}`; V211-5 `ctx["context"]`; V211-6 `_run_screens`; V211-4/5 test helpers `_level_cache`, `_fake_level_idea`, `_level_argv`, `LEVEL`.
- Produces (index ledger, final; V211-11b renders it):
  - `TickerScreen.shock: dict | None = None` — the **last** field; level ideas only: `{"null2": rows, "null2_dropped": int, "stress3": rows, "tags": list[dict]}`, where rows are `{"entry_date", "r_event", "r_null"}` and `tags[i]` belongs to `events[i]`.
  - `with_shock_blocks(summary: dict, screens, idea: Idea) -> dict` — the summary object itself for any idea whose `context_kind != "level"`; else `{**summary, "shock": block}` with `block = {"null2": Verdict, "null2_dropped": int, "stress3": Verdict, "gap": split, "episode_day": split, "skipped_overlap": int}`. A `split` is `{label: {"n": int, "exp_r_event": float | None, "delta_exp_r": float | None} for each label} | {"missing": int}` (labels `GAP_BUCKETS`, resp. `EPISODE_DAYS`; `missing` counts tags whose label is `None`).

**Why:** spec § Printed alongside each verdict. The standard null matches ticker, month and trend but not the shock state, so the shock-day null separates the stock trigger from the market's drift after a shock day. The 3× re-price exists because neither existing stress path runs for a fixed next-open short (brief § 5 "stress path"). The gap and day-of-episode splits show whether the result rests on V-reversal opens. Every piece is computed per ticker inside `screen_ticker` (one keyword, no branch: `_shock_report` returns `None` first for any non-level idea), so the parity digests, which read only the eight pre-v174 fields, stay equal, and `verdict.decide` on the standard pairs is untouched.

- [ ] **Step 1: Write the failing tests** — create `tests/backtest_scripts/test_screen_shock_blocks.py`:

```python
"""v211 runner wiring of the shock read-outs (spec § Printed alongside each
verdict): TickerScreen.shock for level ideas, the pooled "shock" summary
block, nothing new for any other idea. Printed only, never gating."""
import functools
import sys
import types
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402

from swingbot.core.backtesting.screen import null, shock_readouts, verdict  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS  # noqa: E402
from swingbot.core.backtesting.screen.ideas import _shock_breakdown as sb  # noqa: E402
from tests.backtest_scripts.test_screen_level_context import (  # noqa: E402
    LEVEL, _fake_level_idea, _level_argv, _level_cache)
from tests.backtesting.screen.helpers import random_walk  # noqa: E402

ALWAYS = [("2000-01-01", "9999-12-31")]


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    """500 week resamples instead of 10,000: same code path, test-speed."""
    monkeypatch.setattr(screen_idea.verdict, "decide",
                        functools.partial(verdict.decide, n_resamples=500))


def _fresh_low(df):
    """The fake idea's unconditional control: a close under the prior 20-day low."""
    return df["Close"] < df["Low"].shift(1).rolling(20).min()


@pytest.fixture
def level_idea(monkeypatch):
    idea = _fake_level_idea(control=_fresh_low)
    monkeypatch.setitem(screen_idea.IDEAS, idea.name, idea)
    return idea


def _level_inputs(tmp_path):
    cache = _level_cache(tmp_path)
    frames = screen_idea.load_context(cache, LEVEL, kind="level").frames
    return cache, frames, screen_idea.load_frame(cache / "AAA.csv")


def _capture_publish(monkeypatch) -> dict:
    seen = {}

    def publish(args, idea, universe, summary, rows, data=None):
        seen["summary"] = summary
        return 0

    monkeypatch.setattr(screen_idea, "publish", publish)
    return seen


# --- per ticker ----------------------------------------------------------------

def test_an_idea_without_level_context_carries_no_shock_report():
    df = random_walk(2700, seed=7)
    for name in ("high52w", "range_breakdown_close"):
        assert screen_idea.screen_ticker(IDEAS[name], "AAA", df, ALWAYS).shock is None


def test_a_level_screen_carries_tags_null2_and_stress3(tmp_path, level_idea):
    _cache, frames, df = _level_inputs(tmp_path)
    s = screen_idea.screen_ticker(level_idea, "AAA", df, ALWAYS, context=frames)
    assert set(s.shock) == {"null2", "null2_dropped", "stress3", "tags"}
    assert s.events and len(s.shock["tags"]) == len(s.events)
    for row, tag in zip(s.events, s.shock["tags"]):
        assert tag["signal_date"] < row["entry_date"]
        assert tag["episode_day"] in shock_readouts.EPISODE_DAYS   # events fire on SHOCK days
    stress = s.shock["stress3"]
    assert [r["entry_date"] for r in stress] == [r["entry_date"] for r in s.events]
    assert all(st["r_event"] <= row["r_event"] for st, row in zip(stress, s.events))
    assert any(st["r_event"] < row["r_event"] for st, row in zip(stress, s.events))
    own = {r["entry_date"]: r["r_event"] for r in s.events}
    assert s.shock["null2"]
    assert all(r["r_event"] == own[r["entry_date"]] for r in s.shock["null2"])
    assert len(s.shock["null2"]) + s.shock["null2_dropped"] == len(s.events)


def test_the_shock_null_pool_is_this_tickers_eligible_shock_days(tmp_path, level_idea,
                                                                monkeypatch):
    _cache, frames, df = _level_inputs(tmp_path)
    seen, real = {}, shock_readouts.shock_null

    def spy_null(df_, event_pos, pool, k, seed, **kw):
        seen.update(pool=pool, k=k, seed=seed, kw=kw)
        return real(df_, event_pos, pool, k, seed, **kw)

    monkeypatch.setattr(screen_idea.shock_readouts, "shock_null", spy_null)
    screen_idea.screen_ticker(level_idea, "AAA", df, ALWAYS, context=frames)
    shock = sb.ticker_state(df, frames)["shock"].to_numpy(dtype=bool)
    ctx = screen_idea.ticker_context(level_idea, df, ALWAYS, frames)
    assert seen["pool"].any()
    assert not (seen["pool"] & ~shock).any()
    assert not (seen["pool"] & ~screen_idea._null_pool(level_idea, ctx)).any()
    assert seen["k"] == null.K
    assert seen["seed"] == null.null_seed("fake_level#shock-null", "AAA")
    assert seen["seed"] != null.null_seed("fake_level", "AAA")
    assert (seen["kw"]["cap"], seen["kw"]["shape"], seen["kw"]["direction"]) == (10, "fixed", "short")


def test_the_standard_book_is_the_same_with_and_without_the_shock_report(tmp_path, level_idea,
                                                                        monkeypatch):
    _cache, frames, df = _level_inputs(tmp_path)
    with_report = screen_idea.screen_ticker(level_idea, "AAA", df, ALWAYS, context=frames)
    monkeypatch.setattr(screen_idea, "_shock_report", lambda *a, **k: None)
    without = screen_idea.screen_ticker(level_idea, "AAA", df, ALWAYS, context=frames)
    assert with_report.events == without.events
    assert with_report.counters == without.counters
    assert with_report.control == without.control


# --- pooled --------------------------------------------------------------------

def test_with_shock_blocks_leaves_every_other_idea_untouched():
    summary = {"counters": Counter()}
    for name in ("high52w", "range_breakdown_close", "dollar_drop"):
        assert screen_idea.with_shock_blocks(summary, [], IDEAS[name]) is summary


def _row(day, r_event, r_null):
    return {"entry_date": day, "r_event": r_event, "r_null": r_null}


def _tag(bucket, day):
    return {"signal_date": "x", "gap_pct": 0.0, "gap_bucket": bucket, "episode_day": day}


def test_with_shock_blocks_pools_the_tickers_and_splits_by_bucket(level_idea):
    a = types.SimpleNamespace(
        events=[_row("2011-03-02", 1.0, 0.2), _row("2011-03-10", -0.5, 0.1)],
        shock={"tags": [_tag("<= -1%", "peak"), _tag("<= -1%", "later")],
               "null2": [_row("2011-03-02", 1.0, -0.2)], "null2_dropped": 1,
               "stress3": [_row("2011-03-02", 0.9, 0.1), _row("2011-03-10", -0.6, 0.0)]})
    b = types.SimpleNamespace(
        events=[_row("2012-05-07", 2.0, 0.0)],
        shock={"tags": [_tag(None, "later")], "null2": [], "null2_dropped": 1,
               "stress3": [_row("2012-05-07", 1.9, 0.0)]})
    summary = {"counters": Counter(skipped_overlap=4)}
    out = screen_idea.with_shock_blocks(summary, [a, b], level_idea)
    assert out is not summary and "shock" not in summary
    block = out["shock"]
    assert block["null2"].n == 1 and block["null2"].delta_exp_r == pytest.approx(1.2)
    assert block["null2_dropped"] == 2
    assert block["stress3"].n == 3
    assert block["skipped_overlap"] == 4
    gap = block["gap"]
    assert gap["<= -1%"] == {"n": 2, "exp_r_event": pytest.approx(0.25),
                             "delta_exp_r": pytest.approx(0.1)}
    assert gap["-1% .. +1%"] == {"n": 0, "exp_r_event": None, "delta_exp_r": None}
    assert gap[">= +1%"]["n"] == 0 and gap["missing"] == 1
    day = block["episode_day"]
    assert (day["peak"]["n"], day["later"]["n"], day["missing"]) == (1, 2, 0)
    assert day["later"]["delta_exp_r"] == pytest.approx(0.7)


def test_with_shock_blocks_of_no_screen_has_empty_books(level_idea):
    block = screen_idea.with_shock_blocks({"counters": Counter()}, [], level_idea)["shock"]
    assert block["null2"].n == 0 and block["stress3"].n == 0
    assert block["skipped_overlap"] == 0 and block["gap"]["missing"] == 0


# --- through main --------------------------------------------------------------

def test_a_level_run_hands_publish_the_shock_block(tmp_path, monkeypatch, level_idea):
    cache = _level_cache(tmp_path)
    seen = _capture_publish(monkeypatch)
    assert screen_idea.main(_level_argv(tmp_path, cache, "--dry-run")) == 0
    assert set(seen["summary"]["shock"]) == {"null2", "null2_dropped", "stress3", "gap",
                                             "episode_day", "skipped_overlap"}
    assert "short" in seen["summary"]


def test_a_plain_run_has_no_shock_block(tmp_path, monkeypatch):
    cache = _level_cache(tmp_path)
    seen = _capture_publish(monkeypatch)
    argv = _level_argv(tmp_path, cache, "--dry-run")
    argv[1] = "turn_of_month"
    assert screen_idea.main(argv) == 0
    assert "shock" not in seen["summary"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_shock_blocks.py`
Expected: FAIL — `AttributeError: 'TickerScreen' object has no attribute 'shock'`, `module 'screen_idea' has no attribute 'shock_readouts'` / `'with_shock_blocks'`; `test_a_plain_run_has_no_shock_block` PASSES.

- [ ] **Step 3: Implement the per-ticker report** in `scripts/backtest/screen_idea.py`

- Imports beside the other screen imports: `from swingbot.core.backtesting.screen import shock_readouts  # noqa: E402` and `from swingbot.core.backtesting.screen.ideas import _shock_breakdown as sb  # noqa: E402`. Call `shock_readouts.shock_null` / `shock_readouts.event_tags` through the module attribute (the tests patch it there).
- `TickerScreen`: `shock: dict | None = None   # v211: level only, shock-day null, 3 x book, gap/episode tags` as the **last** field.
- `_SHOCK_NULL_TAG = "#shock-null"` with `#:` comment: *"v211: the shock-day null's seed is null_seed(idea + tag, ticker), a stream of its own, so the standard draw is untouched."*
- `def _shock_rows(ticker, index, kept, null_mean_r, entry: str) -> list` — `[{"entry_date", "r_event", "r_null"}]` from `_event_rows(ticker, index, kept, null_mean_r, entry_offset=_ENTRY_OFFSET[entry])` (the same projection `_stressed` uses; reuse it there only if `_stressed`'s output stays byte-identical, otherwise leave `_stressed` alone).
- `def _shock_report(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict, kept) -> dict | None`:
  - `if idea.context_kind != "level": return None` — first line, before any computation.
  - `context = ctx["context"]`; `state = sb.ticker_state(df, context)`; `pool = _null_pool(idea, ctx) & state["shock"].to_numpy(dtype=bool)`.
  - `draw2 = shock_readouts.shock_null(df, kept.event_pos, pool, null.K, null.null_seed(idea.name + _SHOCK_NULL_TAG, ticker), cap=idea.time_cap_bars, atr=ctx["atr"], shape=idea.race_shape, direction=idea.direction, **costs)`.
  - `null2 = _shock_rows(ticker, df.index, kept.take(np.isin(kept.event_pos, draw2.event_pos)), draw2.null_mean_r, idea.entry)`.
  - `stress = {"slippage_bps": shock_readouts.SHOCK_STRESS_SLIPPAGE_FACTOR * base_slippage(costs["slippage_bps"]), "commission": costs["commission"]}`; `kept3, _, draw3 = _books(idea, ticker, df, ctx, stress)`; `stress3 = _shock_rows(ticker, df.index, kept3, draw3.null_mean_r, idea.entry)` (slippage moves no exit bar and the draw is seeded, so the same events are kept, as `_stressed` documents).
  - `tags = shock_readouts.event_tags(df, state, context[sb.BREADTH]["Close"], kept.event_pos)`.
  - Return `{"null2": null2, "null2_dropped": draw2.dropped, "stress3": stress3, "tags": tags}`. Docstring: *"v211, level ideas only (spec § Printed alongside each verdict): the shock-day null, the 3 x slippage book and the per-event gap and episode-day tags. Printed, never gating; the standard book is not touched."*
- `screen_ticker`: add `shock=_shock_report(idea, ticker, df, ctx, costs, kept),` to the `TickerScreen(...)` call. Nothing else in `screen_ticker` changes.

- [ ] **Step 4: Implement the pooled block** in `scripts/backtest/screen_idea.py`

- `def _shock_split(pairs: list, key: str, labels: tuple) -> dict` — `pairs` is `[(event_row, tag)]`; per label: `rows = [row for row, tag in pairs if tag[key] == label]`, `{"n": len(rows), "exp_r_event": _mean([r["r_event"] for r in rows]), "delta_exp_r": _mean([r["r_event"] - r["r_null"] for r in rows])}`; plus `"missing": sum(tag[key] is None for _, tag in pairs)`.
- `def with_shock_blocks(summary: dict, screens, idea: Idea) -> dict` — `if idea.context_kind != "level": return summary`; `shocked = [s for s in screens if s.shock is not None]`; `pairs = [(row, tag) for s in shocked for row, tag in zip(s.events, s.shock["tags"])]`; the block of the Interfaces with `null2 = _decide([r for s in shocked for r in s.shock["null2"]])`, `stress3 = _decide([r for s in shocked for r in s.shock["stress3"]])` (a list, never `None`, so an empty book is a `Verdict` with `n == 0`), `null2_dropped = sum(...)`, `skipped_overlap = summary["counters"].get("skipped_overlap", 0)`. Docstring: *"v211: the summary plus ``"shock"`` for a level idea; the same dict, untouched, for any other. The verdict object is never rebuilt."*
- `_run_screens` (V211-6): after the `with_short_blocks(...)` line add `summary = with_shock_blocks(summary, screens, idea)`. `main` is not edited.

- [ ] **Step 5: Run the new tests**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_shock_blocks.py`
Expected: PASS, `0 failed`.

- [ ] **Step 6: Prove the existing paths are untouched (files unedited)**

Run each:
`python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py`
`python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py`
`python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_level_context.py`
`python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_checkpoint.py`
`python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py`
Expected: every file `0 failed`, `0 xfailed`; `PARITY_DIGESTS` and the hypothesis golden unchanged (`git diff --stat` lists none of these test files).

- [ ] **Step 7: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0; `screen_ticker` no higher than baseline (one keyword, no branch); `_shock_report`, `with_shock_blocks`, `_shock_split`, `_run_screens` each < 15.

- [ ] **Step 8: Commit**

```bash
git add scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_shock_blocks.py
git commit -m "feat(v211): per-ticker shock report and pooled shock block for level ideas (V211-11)"
```

### Task V211-11b: Results doc: shock blocks, level context section, short-family q-values

**Model:** sonnet — render-only text over the blocks V211-11 built, one BH helper over an existing function, and table-driven dispatch that leaves every other idea's doc byte-identical.

**Files:**
- Modify: `scripts/backtest/screen_idea.py` (new `SHORT_SCREEN_IDS`, `short_family_q`; `_context_run`; new `_render_shock_control`, `_CONTROL_TEXT`; `_render_short_blocks` (one line); new `_render_split`, `_render_shock_blocks`, `_render_level_context`, `_CONTEXT_SECTIONS`; `render_results`)
- Modify: `tests/backtest_scripts/test_screen_shock_blocks.py` (append)

**Interfaces:**
- Consumes: V211-11 `summary["shock"]` (shape in V211-11's Interfaces); V211-10 `shock_readouts.{SHOCK_STRESS_SLIPPAGE_FACTOR, GAP_BUCKETS, EPISODE_DAYS}`; V211-5 `diagnostics.scope_sentence(idea)` level branch, and `render_results` line `if idea.context and idea.context_kind == "z": sections.append(_render_context(...))` (replaced here by the table below); existing `_fmt`, `_minus`, `_mean`, `stats.ledger_qvalues`, `ContextData.records`.
- Produces (index ledger, final; V211-14/15 cite the q-values):
  - `SHORT_SCREEN_IDS = ("v104-b-short-mechanisms", "screen-range_breakdown_close", "screen-range_breakdown_stop", "screen-shock_support_break_short", "screen-shock_failed_bounce_short")`
  - `short_family_q(rows: list[dict], row: dict) -> dict[str, float | None]` — BH over the rows of `[*rows, row]` whose id is in `SHORT_SCREEN_IDS`, via `stats.ledger_qvalues`; keys in `SHORT_SCREEN_IDS` order, only the ids present; a row with `p = None` (v104 Part B) maps to `None` and does not count toward `m`.
  - `_context_run(run, idea, rows, row, data)` — a level idea's run dict gains `"context": data` and `"short_q": short_family_q(rows, row)` (no `"screen_q"`); z ideas and plain ideas unchanged.
  - Results doc for a level idea, in order after the short-side blocks: `## Shock read-outs (v211; descriptive, never gating)`, then `## Context series (v211 level)`.

**Why:** the spec (§ Track 2 opening, § Printed alongside each verdict) wants every read-out printed beside the verdict and the results doc to cite `ledger_qvalues` across every short idea screened so far. The control wording that v182 prints (trend-only control, "not credited to the range") is wrong for a shock idea, whose control is the same trigger with the shock state ignored. A dispatch table keyed on `context_kind` swaps the text without a branch, and z/plain ideas keep their exact text.

- [ ] **Step 1: Write the failing tests** — append to `tests/backtest_scripts/test_screen_shock_blocks.py`:

```python
# --- V211-11b: the results doc -------------------------------------------------

def test_short_screen_ids_are_every_short_idea_screened_so_far():
    assert screen_idea.SHORT_SCREEN_IDS == (
        "v104-b-short-mechanisms", "screen-range_breakdown_close",
        "screen-range_breakdown_stop", "screen-shock_support_break_short",
        "screen-shock_failed_bounce_short")


def _ledger(id_, p, instrument="screen-v1"):
    return {"id": id_, "p": p, "instrument": instrument}


def test_short_family_q_is_bh_over_the_short_ids_present():
    rows = [_ledger("screen-high52w", 0.001),
            _ledger("screen-range_breakdown_close", 0.9996),
            _ledger("v104-b-short-mechanisms", None, "v1")]
    q = screen_idea.short_family_q(rows, _ledger("screen-shock_support_break_short", 0.01))
    assert list(q) == ["v104-b-short-mechanisms", "screen-range_breakdown_close",
                       "screen-shock_support_break_short"]
    assert q["v104-b-short-mechanisms"] is None
    assert q["screen-shock_support_break_short"] == pytest.approx(0.02)   # 0.01 x 2 / 1
    assert q["screen-range_breakdown_close"] == pytest.approx(0.9996)


def test_short_family_q_of_a_non_short_row_is_empty():
    assert screen_idea.short_family_q([], _ledger("screen-fake_level", 0.5)) == {}


def test_the_run_dict_per_kind(level_idea):
    data, row = object(), _ledger("screen-x", 0.5)
    level = screen_idea._context_run({"q": 0.5}, level_idea, [], row, data)
    assert level["context"] is data and level["short_q"] == {} and "screen_q" not in level
    z = screen_idea._context_run({"q": 0.5}, IDEAS["dollar_drop"], [], row, data)
    assert "screen_q" in z and "short_q" not in z
    plain = {"q": 0.5}
    assert screen_idea._context_run(plain, IDEAS["high52w"], [], row, None) is plain


def test_a_level_dry_run_prints_the_shock_blocks_and_the_level_context(tmp_path, capsys,
                                                                      level_idea):
    cache = _level_cache(tmp_path)
    assert screen_idea.main(_level_argv(tmp_path, cache, "--dry-run")) == 0
    out = capsys.readouterr().out
    for needle in ("## Shock read-outs (v211; descriptive, never gating)",
                   "(`skipped_overlap`) = ", "**Shock-day null**",
                   "**Re-priced at 3 x slippage**", "**Gap split**",
                   "| <= -1% |", "| -1% .. +1% |", "| >= +1% |", "Events with no next open: ",
                   "**Day of the episode**", "| peak |", "| later |",
                   "**Unconditional control**",
                   "## Context series (v211 level)", "| BREADTH_ATR1 |", "| ^VIX |",
                   "**Short-family BH q**", "| (no short idea in the ledger yet) | n/a |",
                   screen_idea.diagnostics.scope_sentence(level_idea)):
        assert needle in out, needle
    assert "Trend-only control" not in out and "credited to the range" not in out
    assert (out.index("## Short-side blocks") < out.index("## Shock read-outs")
            < out.index("## Context series (v211 level)"))
    assert not (tmp_path / "results").exists()


def test_a_short_idea_without_context_keeps_the_v182_doc(tmp_path, capsys):
    cache = _level_cache(tmp_path)
    argv = _level_argv(tmp_path, cache, "--dry-run")
    argv[1] = "range_breakdown_close"
    assert screen_idea.main(argv) == 0
    out = capsys.readouterr().out
    assert "**Trend-only control**" in out and "credited to the range" in out
    for needle in ("Shock read-outs", "Unconditional control", "Context series (v211 level)",
                   "Short-family BH q"):
        assert needle not in out, needle


def test_render_split_prints_every_label_and_the_missing_count():
    split = {"peak": {"n": 2, "exp_r_event": 0.25, "delta_exp_r": 0.1},
             "later": {"n": 0, "exp_r_event": None, "delta_exp_r": None}, "missing": 3}
    lines = screen_idea._render_split("**Day of the episode**", "day", split,
                                      shock_readouts.EPISODE_DAYS, "Events on a NORMAL day")
    assert "| peak | 2 | +0.2500R | +0.1000R |" in lines
    assert "| later | 0 | n/aR | n/aR |" in lines
    assert lines[-1] == "Events on a NORMAL day: 3."
```

- [ ] **Step 2: Run to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_shock_blocks.py`
Expected: the V211-11 tests PASS; the new ones FAIL — `AttributeError: ... 'SHORT_SCREEN_IDS'`, `'short_family_q'`, `'_render_split'`; the dry-run test fails on `## Shock read-outs`; `test_a_short_idea_without_context_keeps_the_v182_doc` PASSES (it pins today's text).

- [ ] **Step 3: Implement the q-values and the run dict** in `scripts/backtest/screen_idea.py` (beside `_context_run`)

- `SHORT_SCREEN_IDS` as in Interfaces, `#:` comment: *"v211 (spec § Track 2): every short idea screened so far; the results doc prints BH q across them. range_breakdown_stop is unspent and simply absent from q until it runs."*
- `short_family_q(rows, row)`: `family = {r["id"]: r for r in [*rows, row] if r["id"] in SHORT_SCREEN_IDS}`; `q = stats.ledger_qvalues(list(family.values()))`; return `{i: q[i] for i in SHORT_SCREEN_IDS if i in q}`.
- `_context_run`: after `if not idea.context: return run`, add `if idea.context_kind == "level": return {**run, "context": data, "short_q": short_family_q(rows, row)}`; the z return is unchanged. Docstring gains: *"v211: a level idea carries the short-family q instead (§ Track 2)."*

- [ ] **Step 4: Implement the control text table**

- `def _render_shock_control(summary, block) -> list` — one line, exact copy with the `_render_control` numbers (`c = block["control"]`, margin `_minus(summary["verdict"].delta_exp_r, c.delta_exp_r)`):

```python
    return ["**Unconditional control** (`control_events`: the same trigger with the shock "
            "state ignored; same race, same matched null): "
            f"N = {c.n}, ΔExpR {_fmt(c.delta_exp_r)}R, 95% week-clustered interval "
            f"{_fmt(c.ci_low)}R to {_fmt(c.ci_high)}R. The idea's ΔExpR minus the control's: "
            f"{_fmt(margin)}R. A pass whose ΔExpR is not clearly above the control is not "
            "credited to the shock condition."]
```

- `_CONTROL_TEXT: dict[str, Callable] = {"z": _render_control, "level": _render_shock_control}` (after both).
- `_render_short_blocks`: `parts.append(_render_control(summary, block))` becomes `parts.append(_CONTROL_TEXT[idea.context_kind](summary, block))`. Nothing else changes; plain short ideas default to `"z"`, so their text is unchanged.

- [ ] **Step 5: Implement the shock blocks and the level context section**

- `def _render_split(title: str, column: str, split: dict, labels: tuple, missing_label: str) -> list` — `[title, "", f"| {column} | N | mean R_event | ΔExpR (standard null) |", "|---|---:|---:|---:|"]`, one row per label `f"| {label} | {cell['n']} | {_fmt(cell['exp_r_event'])}R | {_fmt(cell['delta_exp_r'])}R |"`, then `""` and `f"{missing_label}: {split['missing']}."`.
- `def _render_shock_blocks(idea, summary, run) -> list` — `b, v = summary["shock"], summary["verdict"]`; `n2, s3 = b["null2"], b["stress3"]`; `factor = shock_readouts.SHOCK_STRESS_SLIPPAGE_FACTOR`. Lines, blank line between parts:
  1. `"## Shock read-outs (v211; descriptive, never gating)"`
  2. `f"Kept events N = {v.n}; skipped as overlapping an open race (`skipped_overlap`) = {b['skipped_overlap']}."`
  3. `f"**Shock-day null** (K = {null.K} bars drawn only from this ticker's SHOCK days, no month or trend match; its own seeded stream): N = {n2.n}, ΔExpR {_fmt(n2.delta_exp_r)}R, 95% week-clustered interval {_fmt(n2.ci_low)}R to {_fmt(n2.ci_high)}R; events dropped for fewer than {null.MIN_CANDIDATES} SHOCK-day candidates: {b['null2_dropped']}. The standard ΔExpR minus this one: {_fmt(_minus(v.delta_exp_r, n2.delta_exp_r))}R. An edge that vanishes against this null is the market's drift after a shock day, not the stock trigger."`
  4. `f"**Re-priced at {factor} x slippage** ({factor * run['slippage_bps']} bps a side, both fills, events and standard null; shock-day spreads widen 2-5x): ΔExpR {_fmt(s3.delta_exp_r)}R, 95% week-clustered interval {_fmt(s3.ci_low)}R to {_fmt(s3.ci_high)}R; change vs the base book {_fmt(_minus(s3.delta_exp_r, v.delta_exp_r))}R. Printed, never gating."`
  5. `_render_split("**Gap split** (next open vs the signal close; the race fills the entry at that open, gap included, and a gap through the stop at the open):", "gap", b["gap"], shock_readouts.GAP_BUCKETS, "Events with no next open")`
  6. `_render_split("**Day of the episode** (`peak`: the signal close is the episode's highest BREADTH_ATR1 so far, so the entry is the session after the breadth peak; `later`: any other SHOCK day of the episode):", "day", b["episode_day"], shock_readouts.EPISODE_DAYS, "Events on a NORMAL day")`
- `def _render_level_context(idea, summary, run) -> list` — `["## Context series (v211 level)", "", diagnostics.scope_sentence(idea), "", "| series | rows | first | last | SHA-256 |", "|---|---:|---|---|---|"]`, one row per `record` in `sorted(run["context"].records.items())`: `f"| {r['ticker']} | {r['rows']} | {r['first']} | {r['last']} | `{r['sha256'][:12]}` |"`; then `""`, `"**Short-family BH q** (every short idea screened so far, `SHORT_SCREEN_IDS`, this run's row included; reported, never gating):"`, `""`, `"| ledger id | q |"`, `"|---|---:|"`, one row per `run["short_q"]` item `f"| `{i}` | {_fmt(q, '.4f')} |"`, or the single row `"| (no short idea in the ledger yet) | n/a |"` when it is empty.
- `_CONTEXT_SECTIONS: dict[str, Callable] = {"z": _render_context, "level": _render_level_context}` (after both).
- `render_results`: after the `"short"` section add `if "shock" in summary: sections.append(_render_shock_blocks(idea, summary, run))`; replace V211-5's `if idea.context and idea.context_kind == "z": ...` with `if idea.context: sections.append(_CONTEXT_SECTIONS[idea.context_kind](idea, summary, run))` (a z idea gets exactly `_render_context`, as before).

- [ ] **Step 6: Run the tests**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_shock_blocks.py`
Expected: PASS, `0 failed`.

- [ ] **Step 7: Prove the existing docs are untouched (files unedited)**

Run each:
`python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py`
`python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py`
`python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_level_context.py`
`python scripts/dev/testrun.py file tests/backtesting/screen/test_diagnostics.py`
Expected: every file `0 failed`, `0 xfailed`; none of them in `git diff --stat`.

- [ ] **Step 8: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0; `render_results`, `_render_short_blocks`, `_context_run` each < 15 and no higher than baseline +1 branch where one was added (`render_results`: one `if` added, one condition removed).

- [ ] **Step 9: Commit**

```bash
git add scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_shock_blocks.py
git commit -m "feat(v211): results doc shock blocks, level context section, short-family BH q (V211-11b)"
```

