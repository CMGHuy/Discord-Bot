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


def test_events_before_2011_count_as_warmup_not_events():
    df = random_walk(2600)
    out = screen_idea.screen_ticker(IDEAS["turn_of_month"], "AAA", df, ALWAYS)
    assert min(row["entry_date"] for row in out.events) >= screen_idea.EVENT_START


def test_a_ticker_that_was_never_a_member_keeps_no_event():
    df = random_walk(2600)
    idea = IDEAS["turn_of_month"]
    out = screen_idea.screen_ticker(idea, "AAA", df, [])
    assert out.events == []
    assert out.counters["dropped_nonmember"] == int(idea.events(df).sum())


def test_rank_frame_holds_only_member_and_warm_bars():
    df = random_walk(2600)
    idea = IDEAS["turn_of_month"]
    spans = [("2014-01-01", "2016-01-01")]
    rank = screen_idea.screen_ticker(idea, "AAA", df, spans).rank
    assert len(rank) and set(rank["year"]) <= {2014, 2015}
    assert {"year", "event"} | {f"fwd_{h}" for h in forward.HORIZONS} <= set(rank.columns)


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
