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


@pytest.mark.parametrize("flag,value", [("--start", "2013-01-01"), ("--end", "2015-12-31")])
def test_a_non_registered_window_is_refused_on_a_real_run(tmp_path, capsys, flag, value):
    cache, membership = _universe_fixture(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, membership, flag, value)) == 2
    assert "pre-registered window" in capsys.readouterr().err
    assert not (tmp_path / "ledger.jsonl").exists()
    assert not (tmp_path / "results").exists()


@pytest.mark.parametrize("flag,value", [("--start", "2013-01-01"), ("--end", "2015-12-31")])
def test_a_non_registered_window_is_allowed_with_dry_run(tmp_path, flag, value):
    cache, membership = _universe_fixture(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, membership, "--dry-run", "--tickers",
                                  "AAA", flag, value)) == 0
    assert not (tmp_path / "ledger.jsonl").exists()


def test_results_doc_states_the_event_start_and_year_rule(tmp_path, capsys):
    cache, membership = _universe_fixture(tmp_path)
    screen_idea.main(_argv(tmp_path, cache, membership, "--dry-run", "--tickers", "AAA"))
    out = capsys.readouterr().out
    assert (f"events count from {screen_idea.EVENT_START}" in out
            and f"{verdict.MIN_POSITIVE_YEARS} of {len(verdict.YEARS)} calendar years" in out)
