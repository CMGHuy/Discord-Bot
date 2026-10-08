# v140 Idea screen: Implementation Plan, part 4 — the screen script

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Header, Global Constraints, Review Focus, Frozen readings and Parallelisation live in [`_0-index`](2026-10-08-v140-idea-screen_0-index.md); every task here implicitly includes them. Work only in the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen`.

**Spec:** [`docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md`](../specs/2026-10-08-v140-idea-screen-design.md)

# Phase 4 (continued) — `scripts/backtest/screen_idea.py`

V140-13 and V140-14 edit the same two files and are strictly sequential. Both need every Group A task and V140-12 merged on the branch; V140-14 also needs V140-10 (it writes `screen-v1` / `SCREEN-*` ledger rows).

### Task V140-13: Universe loading and the per-ticker pipeline

**Files:**
- Create: `scripts/backtest/screen_idea.py`
- Test: `tests/scripts/test_screen_idea.py`

**Interfaces:**
- Consumes: `indicators.atr`, `indicators.sma` (V140-1); `IDEAS`, `Idea` (V140-2); `race.run_book`, `race.warm_mask` (V140-3); `null.K`, `null.member_mask`, `null.eligible_mask`, `null.trend_state`, `null.null_seed`, `null.matched_null` (V140-4); `forward.HORIZONS`, `forward.forward_atr`, `forward.excess_drift` (V140-5); the four triggers (V140-6..9); `pit_membership.load_intervals`, `pit_membership.members_between` (existing); `config.DATA_DIR` (existing).
- Produces (in `screen_idea`):
  - Constants `WINDOW_START = "2010-01-01"`, `EVENT_START = "2011-01-01"` (F14), `WINDOW_END = "2019-12-31"`, `OHLCV`, `DEFAULT_CACHE`, `DEFAULT_MEMBERSHIP`, `PROGRESS_EVERY = 25`, `COUNTER_ORDER = ("dropped_nonmember", "dropped_warmup", "dropped_window", "skipped_overlap", "dropped_no_match")`.
  - `load_frame(path, start=WINDOW_START, end=WINDOW_END) -> pd.DataFrame | None` — rows after `end` never leave it.
  - `Universe(intervals: dict, members: list[str], cached: list[str], missing: list[str])` — frozen.
  - `load_universe(cache_dir, membership_path, start=WINDOW_START, end=WINDOW_END) -> Universe` — `ValueError` when the membership file yields no rows.
  - `TickerScreen(ticker, counters: Counter, events: list[dict], null_outcomes: Counter, excess: dict[int, list[float]], rank: pd.DataFrame)`; each event dict has `ticker`, `entry_date`, `exit_date` (ISO strings), `r_event`, `r_null` (floats, net of costs), `outcome`.
  - `screen_ticker(idea, ticker, df, spans, *, slippage_bps=None, commission=None) -> TickerScreen`.
  - `screen_universe(idea, universe, cache_dir, *, start=WINDOW_START, end=WINDOW_END, tickers=None, out=print) -> tuple[list[TickerScreen], Counter]` — the Counter holds `empty_frame`.

- [ ] **Step 1: Invoke `no-lookahead`, then write the failing tests**

`tests/scripts/test_screen_idea.py`:

```python
"""v140 screen_idea.py: universe, per-ticker pipeline, CLI, one shot per idea."""
import functools
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402

from swingbot.core.backtesting.screen import forward, null, verdict  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS  # noqa: E402
from tests.backtesting.screen.helpers import random_walk  # noqa: E402

ALWAYS = [("2000-01-01", "9999-12-31")]


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    """500 week resamples instead of 10,000: same code path, test-speed."""
    monkeypatch.setattr(screen_idea.verdict, "decide",
                        functools.partial(verdict.decide, n_resamples=500))


def _write_csv(path, df):
    df.rename_axis("Date").to_csv(path)


def test_load_frame_never_returns_a_bar_after_the_window(tmp_path):
    df = random_walk(2700)                      # 2010-01-04 .. mid 2020
    messy = pd.concat([df, df.iloc[[5]]])       # a duplicated date
    messy.iloc[10, messy.columns.get_loc("Close")] = np.nan
    _write_csv(tmp_path / "AAA.csv", messy)
    out = screen_idea.load_frame(tmp_path / "AAA.csv")
    assert out.index.max() <= pd.Timestamp("2019-12-31")
    assert out.index.is_monotonic_increasing and not out.index.duplicated().any()
    assert not out.isna().any().any()
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_load_frame_is_none_when_nothing_falls_in_the_window(tmp_path):
    _write_csv(tmp_path / "LATE.csv", random_walk(30, start="2021-01-04"))
    assert screen_idea.load_frame(tmp_path / "LATE.csv") is None


def test_load_universe_splits_cached_from_missing(tmp_path):
    membership = tmp_path / "membership.csv"
    membership.write_text(
        "ticker,start_date,end_date\nAAA,2000-01-01,\nBBB,2012-01-01,2015-01-01\n"
        "CCC,2021-01-01,\nBRK.B,2005-01-01,\n", encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    for ticker in ("AAA", "BRK-B", "CCC"):
        _write_csv(cache / f"{ticker}.csv", random_walk(10))
    uni = screen_idea.load_universe(cache, membership)
    assert uni.members == ["AAA", "BBB", "BRK-B"]       # CCC joined after 2019
    assert uni.cached == ["AAA", "BRK-B"]
    assert uni.missing == ["BBB"]


def test_load_universe_refuses_an_absent_membership_file(tmp_path):
    with pytest.raises(ValueError):
        screen_idea.load_universe(tmp_path, tmp_path / "absent.csv")


def test_screen_ticker_accounts_for_every_raw_event():
    df = random_walk(2600)
    idea = IDEAS["turn_of_month"]
    raw = int(idea.events(df).sum())
    out = screen_idea.screen_ticker(idea, "AAA", df, ALWAYS)
    assert set(out.counters) == set(screen_idea.COUNTER_ORDER)
    assert sum(out.counters.values()) + len(out.events) == raw
    assert out.counters["dropped_warmup"] > 0         # no SMA200 for ~10 months
    assert out.events and set(out.excess) == set(forward.HORIZONS)
    assert all(row["exit_date"] >= row["entry_date"] for row in out.events)


def test_a_ticker_that_was_never_a_member_keeps_no_event():
    df = random_walk(2600)
    idea = IDEAS["turn_of_month"]
    out = screen_idea.screen_ticker(idea, "AAA", df, [])
    assert out.events == []
    assert out.counters["dropped_nonmember"] == int(idea.events(df).sum())


def test_screen_ticker_passes_raw_events_to_the_null(monkeypatch):
    seen = {}
    real = null.matched_null

    def spy(df, event_pos, eligible, *args, **kwargs):
        seen["eligible"] = eligible
        return real(df, event_pos, eligible, *args, **kwargs)

    monkeypatch.setattr(null, "matched_null", spy)
    df = random_walk(2600)
    idea = IDEAS["turn_of_month"]
    raw = idea.events(df).to_numpy()
    screen_idea.screen_ticker(idea, "AAA", df, ALWAYS)
    assert raw.any() and not seen["eligible"][raw].any()


def test_screen_ticker_is_deterministic():
    df = random_walk(2600)
    idea = IDEAS["turn_of_month"]
    a = screen_idea.screen_ticker(idea, "AAA", df, ALWAYS)
    b = screen_idea.screen_ticker(idea, "AAA", df, ALWAYS)
    assert a.events == b.events


def test_screen_reads_no_2020_bar_end_to_end(tmp_path):
    _write_csv(tmp_path / "AAA.csv", random_walk(2700))        # runs into 2020
    uni = screen_idea.Universe(intervals={"AAA": ALWAYS}, members=["AAA"],
                               cached=["AAA"], missing=[])
    screens, skipped = screen_idea.screen_universe(
        IDEAS["turn_of_month"], uni, tmp_path, out=lambda *a, **k: None)
    rows = screens[0].events
    assert rows and max(row["exit_date"] for row in rows) <= "2019-12-31"
    assert screens[0].rank["year"].max() <= 2019
    assert skipped == Counter()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_screen_idea.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'screen_idea'`.

- [ ] **Step 3: Write the script's loading and pipeline half**

`scripts/backtest/screen_idea.py`:

```python
#!/usr/bin/env python3
"""v140 idea screen: one idea, one shot, PIT S&P 500 daily bars 2010-2019.

    python scripts/backtest/screen_idea.py --idea high52w \\
        --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext

Every event races a fixed trade (entry next open, stop 1.5 x ATR14, target
3 x ATR14, idea-specific time cap, costs) against K = 20 matched random bars
(same ticker, month and trend state). verdict.decide applies the four-clause
pass rule; the script writes docs/superpowers/results/<date>-screen-<idea>.md
and appends ledger row screen-<idea>. It refuses an idea already in the
ledger (one shot per idea) and a window end after 2019-12-31. --dry-run
prints the results doc and writes nothing; --tickers needs --dry-run.
"""
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot import config  # noqa: E402
from swingbot.core.backtesting.screen import forward, indicators, null, race, verdict  # noqa: E402
from swingbot.core.backtesting.screen.ideas import Idea  # noqa: E402
from swingbot.core.marketdata import pit_membership  # noqa: E402

WINDOW_START = "2010-01-01"
EVENT_START = "2011-01-01"  # 2010 primes ATR14/SMA200/252-bar max only (v140 F14)
WINDOW_END = "2019-12-31"
OHLCV = ["Open", "High", "Low", "Close", "Volume"]
DEFAULT_CACHE = Path(config.DATA_DIR) / "backtest_cache_ext"
DEFAULT_MEMBERSHIP = Path(config.DATA_DIR) / "universe" / "sp500_membership.csv"
PROGRESS_EVERY = 25
COUNTER_ORDER = ("dropped_nonmember", "dropped_warmup", "dropped_window",
                 "skipped_overlap", "dropped_no_match")


def load_frame(path, start: str = WINDOW_START, end: str = WINDOW_END):
    """One cached CSV cut to [start, end]. A bar after ``end`` never leaves
    this function, so nothing downstream can read 2020+."""
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    inside = (df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))
    df = df.loc[inside, OHLCV].dropna()
    return df if len(df) else None


@dataclass(frozen=True)
class Universe:
    intervals: dict
    members: list
    cached: list
    missing: list


def load_universe(cache_dir, membership_path, start: str = WINDOW_START,
                  end: str = WINDOW_END) -> Universe:
    intervals = pit_membership.load_intervals(str(membership_path))
    if not intervals:
        raise ValueError(f"no membership rows in {membership_path}")
    members = pit_membership.members_between(intervals, start, end)
    cached = [s for s in members if (Path(cache_dir) / f"{s}.csv").is_file()]
    have = set(cached)
    return Universe(intervals, members, cached, [s for s in members if s not in have])


@dataclass
class TickerScreen:
    ticker: str
    counters: Counter
    events: list
    null_outcomes: Counter
    excess: dict
    rank: pd.DataFrame


def _event_rows(ticker, index, kept, null_mean_r) -> list:
    return [{"ticker": ticker,
             "entry_date": index[pos + 1].strftime("%Y-%m-%d"),
             "exit_date": index[out].strftime("%Y-%m-%d"),
             "r_event": float(r), "r_null": float(m), "outcome": str(o)}
            for pos, out, r, m, o in zip(kept.event_pos, kept.exit_pos, kept.r,
                                         null_mean_r, kept.outcome)]


def _rank_frame(index, raw, population, fwd) -> pd.DataFrame:
    """Member and warm bars, raw event indicator, forward returns (F10)."""
    columns = {"year": np.asarray(index.year)[population],
               "event": raw[population].astype(int)}
    columns.update({f"fwd_{h}": values[population] for h, values in fwd.items()})
    return pd.DataFrame(columns)


def screen_ticker(idea: Idea, ticker: str, df: pd.DataFrame, spans, *,
                  slippage_bps=None, commission=None) -> TickerScreen:
    costs = {"slippage_bps": slippage_bps, "commission": commission}
    cap = idea.time_cap_bars
    atr = indicators.atr(df)
    sma200 = indicators.sma(df["Close"], 200)
    raw = np.asarray(idea.events(df).reindex(df.index, fill_value=False), dtype=bool)
    member = null.member_mask(df.index, spans)
    warm = race.warm_mask(atr, sma200) & (df.index >= pd.Timestamp(EVENT_START))
    booked, counts = race.run_book(df, raw, cap, member=member, warm=warm,
                                   atr=atr, **costs)
    draw = null.matched_null(df, booked.event_pos,
                             null.eligible_mask(raw, member, warm, cap), null.K,
                             null.null_seed(idea.name, ticker), cap=cap, atr=atr,
                             trend=null.trend_state(df, sma200), **costs)
    counts["dropped_no_match"] = draw.dropped_no_match
    kept = booked.take(np.isin(booked.event_pos, draw.event_pos))
    fwd = {h: forward.forward_atr(df, atr, h) for h in forward.HORIZONS}
    return TickerScreen(
        ticker=ticker, counters=Counter(counts),
        events=_event_rows(ticker, df.index, kept, draw.null_mean_r),
        null_outcomes=Counter(draw.null_race.outcome.tolist()),
        excess={h: forward.excess_drift(fwd[h], draw.event_pos, draw.groups)
                for h in forward.HORIZONS},
        rank=_rank_frame(df.index, raw, member & warm, fwd))


def screen_universe(idea: Idea, universe: Universe, cache_dir, *,
                    start: str = WINDOW_START, end: str = WINDOW_END,
                    tickers=None, out=print):
    """Every cached member, one at a time, with flushed percent progress."""
    names = universe.cached if tickers is None else [t for t in tickers if t in universe.cached]
    screens, skipped = [], Counter()
    for i, ticker in enumerate(names, start=1):
        df = load_frame(Path(cache_dir) / f"{ticker}.csv", start, end)
        if df is None:
            skipped["empty_frame"] += 1
        else:
            screens.append(screen_ticker(idea, ticker, df,
                                         universe.intervals.get(ticker, [])))
        if i % PROGRESS_EVERY == 0 or i == len(names):
            out(f"[{idea.name}] {i}/{len(names)} tickers ({100.0 * i / len(names):.0f}%)",
                flush=True)
    return screens, skipped
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_screen_idea.py`
Expected: PASS (9 tests). (`verdict` is imported now, unused until V140-14, because the test module's autouse `fast_bootstrap` fixture patches `screen_idea.verdict.decide`.)

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C scripts/backtest/screen_idea.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest/screen_idea.py tests/scripts/test_screen_idea.py
git commit -m "feat(screen): universe loading and per-ticker screen pipeline (V140-13)"
```

### Task V140-14: CLI, results doc, ledger row, refusals

**Files:**
- Modify: `scripts/backtest/screen_idea.py` (append the CLI half)
- Test: `tests/scripts/test_screen_idea.py` (append)

**Interfaces:**
- Consumes: everything V140-13 produces; `verdict.decide`, `verdict.PairedEvent`, `verdict.Verdict`, `verdict.YEARS` (V140-12); `stats.load_ledger`, `stats.validate_ledger_row`, `stats.append_ledger_row`, `stats.ledger_qvalues`, `stats.LEDGER_PATH`, `stats.WEEK_BOOTSTRAP_RESAMPLES`, `stats.WEEK_BOOTSTRAP_SEED` and the `screen-v1` / `SCREEN-*` vocabulary (V140-10); `race.OUTCOMES`, `race.STOP_ATR`, `race.REWARD_RISK`; `commission_r` (existing).
- Produces (in `screen_idea`): `INSTRUMENT = "screen-v1"`, `RESULTS_DIR`, `ledger_id(name) -> str`, `build_parser()`, `refusal(args, rows) -> str | None`, `summarise(screens, skipped=None) -> dict` (keys `verdict`, `events`, `counters`, `skipped`, `event_outcomes`, `null_outcomes`, `mean_r_event`, `mean_r_null`, `drift`, `rank`), `render_results(idea, summary, universe, run) -> str`, `record_path(path) -> str`, `ledger_row(idea, v, record, day) -> dict`, `publish(args, idea, universe, summary, rows) -> int`, `main(argv=None) -> int` (0 done, 2 refused).

- [ ] **Step 1: Append the failing tests**

Append to `tests/scripts/test_screen_idea.py`:

```python
from swingbot.core.backtesting.instrument import stats  # noqa: E402


def _universe_fixture(tmp_path, tickers=("AAA", "BBB")):
    cache = tmp_path / "cache"
    cache.mkdir()
    for seed, ticker in enumerate(tickers, start=1):
        _write_csv(cache / f"{ticker}.csv", random_walk(2700, seed=seed))
    membership = tmp_path / "membership.csv"
    membership.write_text("ticker,start_date,end_date\n"
                          + "".join(f"{t},2000-01-01,\n" for t in tickers)
                          + "ZZZ,2005-01-01,2016-01-01\n", encoding="utf-8")
    return cache, membership


def _argv(tmp_path, cache, membership, *extra, idea="turn_of_month"):
    return ["--idea", idea, "--cache-dir", str(cache), "--membership", str(membership),
            "--ledger", str(tmp_path / "ledger.jsonl"),
            "--results-dir", str(tmp_path / "results"), "--date", "2026-10-09", *extra]


def test_a_run_writes_the_results_doc_and_one_ledger_row(tmp_path):
    cache, membership = _universe_fixture(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, membership)) == 0
    doc = tmp_path / "results" / "2026-10-09-screen-turn_of_month.md"
    text = doc.read_text(encoding="utf-8")
    rows = stats.load_ledger(tmp_path / "ledger.jsonl")
    assert [row["id"] for row in rows] == ["screen-turn_of_month"]
    assert rows[0]["instrument"] == "screen-v1"
    assert rows[0]["verdict"] == "SCREEN-UNDERPOWERED"   # two tickers cannot reach N = 300
    assert rows[0]["record"].endswith("2026-10-09-screen-turn_of_month.md")
    for needle in ("SCREEN-UNDERPOWERED", "dropped_nonmember", "dropped_warmup",
                   "dropped_window", "skipped_overlap", "dropped_no_match",
                   "missing from the cache", "ZZZ", "Mean R_event", "mean R_null",
                   "## Per year", "## Forward drift", "Spearman", "gap_stop",
                   "timeout", "BH q"):
        assert needle in text, needle


def test_second_run_of_a_ledgered_idea_is_refused_and_changes_nothing(tmp_path, capsys):
    cache, membership = _universe_fixture(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, membership)) == 0
    ledger = tmp_path / "ledger.jsonl"
    doc = tmp_path / "results" / "2026-10-09-screen-turn_of_month.md"
    before = (ledger.read_bytes(), doc.read_bytes())
    capsys.readouterr()
    assert screen_idea.main(_argv(tmp_path, cache, membership, "--date", "2026-10-10")) == 2
    assert "one shot per idea" in capsys.readouterr().err
    assert (ledger.read_bytes(), doc.read_bytes()) == before
    assert not (tmp_path / "results" / "2026-10-10-screen-turn_of_month.md").exists()


def test_dry_run_of_a_ledgered_idea_is_refused(tmp_path):
    stats.append_ledger_row(
        {"id": "screen-turn_of_month", "date": "2026-10-09", "hypothesis": "x",
         "instrument": "screen-v1", "n": 1, "exp_r": 0.0, "p": 0.5,
         "verdict": "SCREEN-FAIL", "record": "docs/x.md"},
        path=tmp_path / "ledger.jsonl")
    cache, membership = _universe_fixture(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, membership, "--dry-run")) == 2


def test_refuses_a_window_end_after_2019(tmp_path, capsys):
    cache, membership = _universe_fixture(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, membership, "--end", "2020-01-02")) == 2
    assert "never reads 2020+" in capsys.readouterr().err
    assert not (tmp_path / "ledger.jsonl").exists()


def test_tickers_without_dry_run_is_refused(tmp_path):
    cache, membership = _universe_fixture(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, membership, "--tickers", "AAA")) == 2
    assert not (tmp_path / "ledger.jsonl").exists()


def test_dry_run_prints_the_doc_and_writes_nothing(tmp_path, capsys):
    cache, membership = _universe_fixture(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, membership, "--dry-run",
                                  "--tickers", "AAA")) == 0
    assert "# v140 screen: `turn_of_month`" in capsys.readouterr().out
    assert not (tmp_path / "ledger.jsonl").exists()
    assert not (tmp_path / "results").exists()


def test_an_unknown_idea_is_an_argparse_error():
    with pytest.raises(SystemExit):
        screen_idea.main(["--idea", "nope"])


def test_ledger_row_validates_and_rounds():
    v = verdict.Verdict("SCREEN-FAIL", 412, 0.031234567, -0.01, 0.07, 0.2345678,
                        6, {}, {})
    row = screen_idea.ledger_row(IDEAS["gap_volume"], v,
                                 "docs/superpowers/results/x.md", "2026-10-09")
    stats.validate_ledger_row(row)
    assert row["id"] == "screen-gap_volume" and row["instrument"] == "screen-v1"
    assert row["exp_r"] == 0.0312 and row["p"] == 0.2346 and row["n"] == 412


def test_summarise_pairs_each_event_with_its_null_mean():
    empty_rank = pd.DataFrame(columns=["year", "event"]
                              + [f"fwd_{h}" for h in forward.HORIZONS])
    screen = screen_idea.TickerScreen(
        ticker="AAA", counters=Counter(dropped_window=2),
        events=[{"ticker": "AAA", "entry_date": "2012-03-01", "exit_date": "2012-03-05",
                 "r_event": 1.0, "r_null": 0.25, "outcome": "target"},
                {"ticker": "AAA", "entry_date": "2013-04-01", "exit_date": "2013-04-02",
                 "r_event": -1.0, "r_null": -0.5, "outcome": "stop"}],
        null_outcomes=Counter(timeout=30),
        excess={h: [0.5] for h in forward.HORIZONS}, rank=empty_rank)
    out = screen_idea.summarise([screen], Counter(empty_frame=1))
    assert out["verdict"].n == 2
    assert out["verdict"].delta_exp_r == pytest.approx((0.75 - 0.5) / 2)
    assert out["mean_r_event"] == 0.0 and out["mean_r_null"] == pytest.approx(-0.125)
    assert out["counters"]["dropped_window"] == 2 and out["skipped"]["empty_frame"] == 1
    assert out["event_outcomes"] == Counter(target=1, stop=1)
    assert out["drift"][5] == (1, 0.5) and out["rank"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_screen_idea.py`
Expected: FAIL — `AttributeError: module 'screen_idea' has no attribute 'main'` (and siblings).

- [ ] **Step 3: Append the CLI half**

Add `import argparse` and `from datetime import date` to the stdlib imports, and these two imports beside the others:

```python
from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.edge.frictions import commission_r  # noqa: E402
```

Change `from swingbot.core.backtesting.screen.ideas import Idea  # noqa: E402` to `from swingbot.core.backtesting.screen.ideas import IDEAS, Idea  # noqa: E402`. Then append:

```python
RESULTS_DIR = ROOT / "docs" / "superpowers" / "results"
INSTRUMENT = "screen-v1"


def ledger_id(name: str) -> str:
    return f"screen-{name}"


def _iso_day(text: str) -> str:
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an ISO date: {text!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--idea", required=True, choices=list(IDEAS))
    p.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--membership", type=Path, default=DEFAULT_MEMBERSHIP)
    p.add_argument("--start", type=_iso_day, default=WINDOW_START)
    p.add_argument("--end", type=_iso_day, default=WINDOW_END)
    p.add_argument("--date", type=_iso_day, default=date.today().isoformat(),
                   help="results-doc and ledger date; default today")
    p.add_argument("--ledger", type=Path, default=stats.LEDGER_PATH)
    p.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--tickers", default=None, help="comma list; smoke test, needs --dry-run")
    p.add_argument("--dry-run", action="store_true", help="print the doc, write nothing")
    return p


def refusal(args, rows) -> str | None:
    """Why this run must not happen, or None. Checked before any data is read."""
    if args.end > WINDOW_END:
        return f"window end {args.end} is after {WINDOW_END}; the screen never reads 2020+"
    if args.start > args.end:
        return f"window start {args.start} is after its end {args.end}"
    if args.tickers and not args.dry_run:
        return "--tickers is a smoke test and needs --dry-run, so it cannot spend the one shot"
    if any(row["id"] == ledger_id(args.idea) for row in rows):
        return (f"{ledger_id(args.idea)} is already in the ledger: one shot per idea; "
                "a changed parameter is a new idea with a new name")
    return None


def _mean(values) -> float | None:
    return float(np.mean(values)) if len(values) else None


def _sum_counters(counters) -> Counter:
    total = Counter()
    for counter in counters:
        total.update(counter)
    return total


def _drift(screens) -> dict:
    out = {}
    for h in forward.HORIZONS:
        values = [v for screen in screens for v in screen.excess[h]]
        out[h] = (len(values), _mean(values))
    return out


def _rank(screens) -> dict:
    frames = [screen.rank for screen in screens if len(screen.rank)]
    if not frames:
        return {}
    pooled = pd.concat(frames, ignore_index=True)
    return {h: forward.yearly_rank_corr(pooled["year"], pooled["event"], pooled[f"fwd_{h}"])
            for h in forward.HORIZONS}


def summarise(screens, skipped=None) -> dict:
    events = [row for screen in screens for row in screen.events]
    paired = [verdict.PairedEvent(row["entry_date"], row["r_event"] - row["r_null"])
              for row in events]
    return {"verdict": verdict.decide(paired), "events": events,
            "counters": _sum_counters(screen.counters for screen in screens),
            "skipped": Counter(skipped or {}),
            "event_outcomes": Counter(row["outcome"] for row in events),
            "null_outcomes": _sum_counters(screen.null_outcomes for screen in screens),
            "mean_r_event": _mean([row["r_event"] for row in events]),
            "mean_r_null": _mean([row["r_null"] for row in events]),
            "drift": _drift(screens), "rank": _rank(screens)}


def _fmt(value, spec: str = "+.4f") -> str:
    return "n/a" if value is None else format(value, spec)


def _yes(ok: bool) -> str:
    return "yes" if ok else "**no**"


def _render_head(idea, v, run) -> list:
    params = ", ".join(f"{key}={value}" for key, value in idea.params.items())
    return [
        f"# v140 screen: `{idea.name}` -> {v.verdict}", "",
        f"**Ledger id:** `{run['ledger_id']}` (instrument `{INSTRUMENT}`); BH q = "
        f"{_fmt(run['q'], '.4f')} across the ledger (reported, never gating).", "",
        f"**Run:** {run['date']}; window {run['start']}..{run['end']}; "
        f"`python scripts/backtest/screen_idea.py --idea {idea.name}`; null K = {null.K}, "
        f"seed 42 per (idea, ticker); bootstrap {stats.WEEK_BOOTSTRAP_RESAMPLES:,} "
        f"week resamples, seed {stats.WEEK_BOOTSTRAP_SEED}.", "",
        f"**Trigger:** {idea.summary} ({idea.source}); params {params}; time cap "
        f"{idea.time_cap_bars} bars; {idea.direction} only.", "",
        f"**Trade:** entry next open; stop {race.STOP_ATR} x ATR14; target "
        f"{race.STOP_ATR * race.REWARD_RISK} x ATR14; a gap through either level "
        f"fills at the open; stop first on a bar touching both; costs "
        f"{run['slippage_bps']} bps a side + {run['commission']:.4f}R commission.", "",
        "**Spec:** `docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md`",
    ]


def _render_universe(universe, summary) -> list:
    counters, v = summary["counters"], summary["verdict"]
    raw = sum(counters[name] for name in COUNTER_ORDER) + v.n
    lines = ["## Universe and counters", "", "| | count |", "|---|---|",
             f"| point-in-time S&P 500 members in the window | {len(universe.members)} |",
             f"| cached and screened | {len(universe.cached)} |",
             f"| missing from the cache (survivorship that remains) | {len(universe.missing)} |",
             f"| cached but empty inside the window | {summary['skipped'].get('empty_frame', 0)} |",
             f"| raw events | {raw} |"]
    lines += [f"| `{name}` | {counters[name]} |" for name in COUNTER_ORDER]
    lines += [f"| **kept events (N)** | **{v.n}** |", "",
              "PIT members missing from the cache: "
              + (", ".join(universe.missing) or "none") + "."]
    return lines


def _render_verdict(v) -> list:
    return [f"## Verdict: {v.verdict}", "",
            "| Clause | Measured | Rule | Holds |", "|---|---|---|---|",
            f"| ΔExpR = mean(R_event − mean R_null) | {_fmt(v.delta_exp_r)}R | ≥ +0.10R | {_yes(v.clauses['exp_r'])} |",
            f"| lower 95% bound, week-clustered bootstrap | {_fmt(v.ci_low)}R (upper {_fmt(v.ci_high)}R) | > 0 | {_yes(v.clauses['ci'])} |",
            f"| years with mean(d) > 0 | {v.years_positive} of {len(verdict.YEARS)} | ≥ 7 | {_yes(v.clauses['years'])} |",
            f"| kept events N | {v.n} | ≥ 300 | {_yes(v.clauses['n'])} |", "",
            f"One-sided bootstrap p (share of resamples ≤ 0): {_fmt(v.p, '.4f')}. "
            "N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say."]


def _mix(outcomes: Counter) -> list:
    total = sum(outcomes.values())
    return [f"{outcomes.get(name, 0)} ({100.0 * outcomes.get(name, 0) / total:.1f}%)"
            if total else "0" for name in race.OUTCOMES]


def _render_arms(summary) -> list:
    lines = ["## Both arms", "",
             f"Mean R_event {_fmt(summary['mean_r_event'])}R; mean R_null (each event's "
             f"null mean, averaged) {_fmt(summary['mean_r_null'])}R. Both after costs.", "",
             "| Exit | event arm | null arm |", "|---|---|---|"]
    lines += [f"| {name} | {e} | {n} |" for name, e, n in
              zip(race.OUTCOMES, _mix(summary["event_outcomes"]), _mix(summary["null_outcomes"]))]
    return lines


def _render_years(v) -> list:
    lines = ["## Per year", "", "| Year | N | mean(d) |", "|---|---|---|"]
    lines += [f"| {year} | {n} | {_fmt(mean)}R |" for year, (n, mean) in v.per_year.items()]
    return lines


def _render_rank(rank) -> list:
    if not rank:
        return ["(no eligible bars)"]
    years = sorted({year for table in rank.values() for year in table})
    lines = ["| Year | " + " | ".join(f"h={h}" for h in rank) + " |",
             "|---|" + "---|" * len(rank)]
    lines += [f"| {year} | " + " | ".join(_fmt(rank[h].get(year)) for h in rank) + " |"
              for year in years]
    return lines


def _render_drift(summary) -> list:
    lines = ["## Forward drift (reported, never gating)", "",
             "Mean excess forward return in ATR14 units from the signal close, "
             "event minus its matched null.", "",
             "| h (bars) | events | mean excess (ATR) |", "|---|---|---|"]
    lines += [f"| {h} | {n} | {_fmt(mean)} |" for h, (n, mean) in summary["drift"].items()]
    lines += ["", "Spearman rank correlation, raw event indicator vs h-bar forward "
              "return, member and warm bars pooled across tickers per year:", ""]
    return lines + _render_rank(summary["rank"])


def render_results(idea, summary, universe, run) -> str:
    v = summary["verdict"]
    sections = [_render_head(idea, v, run), _render_universe(universe, summary),
                _render_verdict(v), _render_arms(summary), _render_years(v),
                _render_drift(summary)]
    return "\n\n".join("\n".join(lines) for lines in sections) + "\n"


def record_path(path) -> str:
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def ledger_row(idea, v, record: str, day: str) -> dict:
    return {"id": ledger_id(idea.name), "date": day,
            "hypothesis": (f"{idea.name}: {idea.summary}; fixed 1.5/3 ATR race vs K=20 "
                           f"matched null, cap {idea.time_cap_bars}, PIT S&P 500 "
                           "2010-2019, after costs (v140 screen)"),
            "instrument": INSTRUMENT, "n": v.n,
            "exp_r": None if v.delta_exp_r is None else round(v.delta_exp_r, 4),
            "p": None if v.p is None else round(v.p, 4),
            "verdict": v.verdict, "record": record}


def _run_info(args, q) -> dict:
    return {"ledger_id": ledger_id(args.idea), "q": q, "date": args.date,
            "start": args.start, "end": args.end,
            "slippage_bps": getattr(config, "SLIPPAGE_BPS", 5.0),
            "commission": commission_r()}


def publish(args, idea, universe, summary, rows) -> int:
    """Write the results doc, then append the ledger row (so the ledger never
    points at a missing doc). --dry-run prints and writes nothing."""
    v = summary["verdict"]
    path = Path(args.results_dir) / f"{args.date}-screen-{idea.name}.md"
    row = ledger_row(idea, v, record_path(path), args.date)
    stats.validate_ledger_row(row)
    q = stats.ledger_qvalues(rows + [row])[row["id"]]
    text = render_results(idea, summary, universe, _run_info(args, q))
    if args.dry_run:
        print(text)
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    stats.append_ledger_row(row, path=args.ledger)
    print(f"{row['id']}: {v.verdict}, N={v.n}, dExpR={_fmt(v.delta_exp_r)}R, "
          f"lower95={_fmt(v.ci_low)}R, {v.years_positive}/10 years -> {row['record']}")
    return 0


def _utf8_stdout() -> None:
    """The results doc carries Δ and ≥; a redirected Windows stdout is cp1252."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass    # a capture stream that cannot be reconfigured is already safe


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
    if reason:
        print(f"refused: {reason}", file=sys.stderr)
        return 2
    idea = IDEAS[args.idea]
    tickers = args.tickers.split(",") if args.tickers else None
    screens, skipped = screen_universe(idea, universe, args.cache_dir, start=args.start,
                                       end=args.end, tickers=tickers)
    return publish(args, idea, universe, summarise(screens, skipped), rows)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_screen_idea.py`
Expected: PASS (18 tests).

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C scripts/backtest/screen_idea.py`
Expected: no output.

- [ ] **Step 6: Smoke test on real data (spends nothing)**

`--dry-run` with `--tickers` cannot write a doc or a ledger row (`refusal`). Its printed result is discarded unread: only the exit code and the wall time matter, and nothing it shows may change any parameter (they are frozen in V140-2).

```bash
cd E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-08-v140-idea-screen
time python scripts/backtest/screen_idea.py --idea high52w --dry-run --tickers AAPL,MSFT,XOM \
  --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext > /dev/null; echo "exit=$?"
```

Expected: `exit=0`. Record the wall time per ticker in the task report (the controller sizes the V140-15..18 polling interval from it: ~506 cached members × that time). A crash here is a bug in this task: fix it with a test first.

- [ ] **Step 7: Commit**

```bash
git add scripts/backtest/screen_idea.py tests/scripts/test_screen_idea.py
git commit -m "feat(screen): screen_idea CLI, results doc, ledger row, one-shot refusal (V140-14)"
```
