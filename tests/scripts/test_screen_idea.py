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


# --- v163: a fixed idea's results doc and ledger row stay byte-identical ---

from swingbot.core.backtesting.screen import race  # noqa: E402


def _fixed_doc_inputs():
    """A hand-built fixed-idea summary: every section of the doc renders and
    nothing depends on a bootstrap or a cache."""
    idea = IDEAS["gap_volume"]
    per_year = {year: (40 + year - 2011, 0.01 * (year - 2015)) for year in verdict.YEARS}
    v = verdict.Verdict("SCREEN-FAIL", 412, 0.031234567, -0.01, 0.07, 0.2345678, 4,
                        per_year, {"exp_r": False, "ci": False, "years": False, "n": True})
    summary = {
        "verdict": v,
        "counters": Counter(dropped_nonmember=7, dropped_warmup=11, dropped_window=2,
                            skipped_overlap=5, dropped_no_match=1),
        "skipped": Counter(empty_frame=1),
        "event_outcomes": Counter(gap_stop=12, stop=200, target=150, timeout=50),
        "null_outcomes": Counter(gap_stop=200, gap_target=40, stop=4000, target=2900,
                                 timeout=1100),
        "mean_r_event": 0.1234567, "mean_r_null": 0.0921,
        "drift": {5: (412, 0.05), 10: (412, -0.02), 20: (410, None), 60: (0, None)},
        "rank": {5: {2011: 0.01, 2012: -0.03}, 10: {2011: None, 2012: 0.02}},
    }
    universe = screen_idea.Universe(intervals={}, members=["AAA", "BBB", "ZZZ"],
                                    cached=["AAA", "BBB"], missing=["ZZZ"])
    run = {"ledger_id": "screen-gap_volume", "q": 0.1234, "date": "2026-10-09",
           "start": "2010-01-01", "end": "2019-12-31", "slippage_bps": 5.0,
           "commission": 0.02}
    return idea, summary, universe, run


# Rendered on main @ 7fcccfed (screen code == 316c57e9), before v163. Never edit.
FIXED_DOC = (
    '# v140 screen: `gap_volume` -> SCREEN-FAIL\n'
    '\n'
    '**Ledger id:** `screen-gap_volume` (instrument `screen-v1`); BH q = 0.1234 across the ledger (reported, never gating).\n'
    '\n'
    '**Run:** 2026-10-09; window 2010-01-01..2019-12-31; events count from 2011-01-01 (earlier bars only prime the indicators); the year rule is 7 of 9 calendar years (2011-2019); `python scripts/backtest/screen_idea.py --idea gap_volume`; null K = 20, seed 42 per (idea, ticker); bootstrap 10,000 week resamples, seed 42.\n'
    '\n'
    '**Trigger:** open >= prior close + 1.0 x prior ATR14, volume >= 2 x the 50-bar mean volume ending the prior bar, close >= open (earnings/news gap drift; volume as the news proxy); params gap_atr=1.0, atr_n=14, volume_mult=2.0, volume_window=50; time cap 20 bars; long only.\n'
    '\n'
    '**Trade:** entry next open; stop 1.5 x ATR14; target 3.0 x ATR14; a gap through either level fills at the open; stop first on a bar touching both; costs 5.0 bps a side + 0.0200R commission.\n'
    '\n'
    '**Spec:** `docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md`\n'
    '\n'
    '## Universe and counters\n'
    '\n'
    '| | count |\n'
    '|---|---|\n'
    '| point-in-time S&P 500 members in the window | 3 |\n'
    '| cached and screened | 2 |\n'
    '| missing from the cache (survivorship that remains) | 1 |\n'
    '| cached but empty inside the window | 1 |\n'
    '| raw events | 438 |\n'
    '| `dropped_nonmember` | 7 |\n'
    '| `dropped_warmup` | 11 |\n'
    '| `dropped_window` | 2 |\n'
    '| `skipped_overlap` | 5 |\n'
    '| `dropped_no_match` | 1 |\n'
    '| **kept events (N)** | **412** |\n'
    '\n'
    'PIT members missing from the cache: ZZZ.\n'
    '\n'
    '## Verdict: SCREEN-FAIL\n'
    '\n'
    '| Clause | Measured | Rule | Holds |\n'
    '|---|---|---|---|\n'
    '| ΔExpR = mean(R_event − mean R_null) | +0.0312R | ≥ +0.10R | **no** |\n'
    '| lower 95% bound, week-clustered bootstrap | -0.0100R (upper +0.0700R) | > 0 | **no** |\n'
    '| years with mean(d) > 0 | 4 of 9 | ≥ 7 | **no** |\n'
    '| kept events N | 412 | ≥ 300 | yes |\n'
    '\n'
    'One-sided bootstrap p (share of resamples ≤ 0): 0.2346. N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say.\n'
    '\n'
    '## Both arms\n'
    '\n'
    "Mean R_event +0.1235R; mean R_null (each event's null mean, averaged) +0.0921R. Both after costs.\n"
    '\n'
    '| Exit | event arm | null arm |\n'
    '|---|---|---|\n'
    '| gap_stop | 12 (2.9%) | 200 (2.4%) |\n'
    '| gap_target | 0 (0.0%) | 40 (0.5%) |\n'
    '| stop | 200 (48.5%) | 4000 (48.5%) |\n'
    '| target | 150 (36.4%) | 2900 (35.2%) |\n'
    '| timeout | 50 (12.1%) | 1100 (13.3%) |\n'
    '\n'
    '## Per year\n'
    '\n'
    '| Year | N | mean(d) |\n'
    '|---|---|---|\n'
    '| 2011 | 40 | -0.0400R |\n'
    '| 2012 | 41 | -0.0300R |\n'
    '| 2013 | 42 | -0.0200R |\n'
    '| 2014 | 43 | -0.0100R |\n'
    '| 2015 | 44 | +0.0000R |\n'
    '| 2016 | 45 | +0.0100R |\n'
    '| 2017 | 46 | +0.0200R |\n'
    '| 2018 | 47 | +0.0300R |\n'
    '| 2019 | 48 | +0.0400R |\n'
    '\n'
    '## Forward drift (reported, never gating)\n'
    '\n'
    'Mean excess forward return in ATR14 units from the signal close, event minus its matched null.\n'
    '\n'
    '| h (bars) | events | mean excess (ATR) |\n'
    '|---|---|---|\n'
    '| 5 | 412 | +0.0500 |\n'
    '| 10 | 412 | -0.0200 |\n'
    '| 20 | 410 | n/a |\n'
    '| 60 | 0 | n/a |\n'
    '\n'
    'Spearman rank correlation, raw event indicator vs h-bar forward return, member and warm bars pooled across tickers per year:\n'
    '\n'
    '| Year | h=5 | h=10 |\n'
    '|---|---|---|\n'
    '| 2011 | +0.0100 | n/a |\n'
    '| 2012 | -0.0300 | +0.0200 |\n'
)

FIXED_HYPOTHESIS = (
    'gap_volume: open >= prior close + 1.0 x prior ATR14, volume >= 2 x the 50-bar mean volume ending the prior bar'
    ', close >= open; fixed 1.5/3.0 ATR race vs K=20 matched null, cap 20, PIT S&P 500 2010-2019, after costs (v140 screen)')


def test_a_fixed_idea_renders_its_results_doc_byte_identical_to_v140():
    idea, summary, universe, run = _fixed_doc_inputs()
    assert idea.race_shape == "fixed"
    assert screen_idea.render_results(idea, summary, universe, run) == FIXED_DOC


def test_a_fixed_idea_ledger_row_is_unchanged():
    idea, summary, _, _ = _fixed_doc_inputs()
    row = screen_idea.ledger_row(idea, summary["verdict"], "docs/x.md", "2026-10-09")
    stats.validate_ledger_row(row)
    assert row == {"id": "screen-gap_volume", "date": "2026-10-09",
                   "hypothesis": FIXED_HYPOTHESIS, "instrument": "screen-v1",
                   "n": 412, "exp_r": 0.0312, "p": 0.2346,
                   "verdict": "SCREEN-FAIL", "record": "docs/x.md",
                   "data_source": "yfinance"}


def test_mix_lists_one_cell_per_outcome_of_the_shape():
    fixed = screen_idea._mix(Counter(stop=3, target=1), race.SHAPE_OUTCOMES["fixed"])
    assert fixed == ["0 (0.0%)", "0 (0.0%)", "3 (75.0%)", "1 (25.0%)", "0 (0.0%)"]
    assert screen_idea._mix(Counter(), race.SHAPE_OUTCOMES["trail"]) == ["0"] * 5


def test_render_arms_lists_only_the_shape_outcomes():
    summary = {"mean_r_event": 0.5, "mean_r_null": 0.1,
               "event_outcomes": Counter(trail=2, gap_trail=1, stop=1),
               "null_outcomes": Counter(timeout=4)}
    rows = [line for line in screen_idea._render_arms(summary, race.SHAPE_OUTCOMES["trail"])
            if line.startswith("| ") and not line.startswith("| Exit")]
    assert [row.split(" | ")[0][2:] for row in rows] == [
        "gap_stop", "stop", "gap_trail", "trail", "timeout"]
    fixed = screen_idea._render_arms(summary, race.SHAPE_OUTCOMES["fixed"])
    assert not any("trail" in line for line in fixed)


# --- v163: the idea's shape reaches the race; trail-only timeout and stress data

from swingbot.core.backtesting.screen import race as race_mod  # noqa: E402
from swingbot.core.backtesting.screen.ideas import Idea  # noqa: E402


def _trail_probe(cap=60):
    """turn_of_month's trigger raced under the trail shape; never registered."""
    return Idea(name="trail_probe", events=IDEAS["turn_of_month"].events,
                time_cap_bars=cap, race_shape="trail", summary="probe", source="test")


def test_base_slippage_reads_config_only_when_none(monkeypatch):
    monkeypatch.setattr(screen_idea.config, "SLIPPAGE_BPS", 7.0, raising=False)
    assert screen_idea.base_slippage(None) == 7.0
    assert screen_idea.base_slippage(3.0) == 3.0
    assert screen_idea.base_slippage(0.0) == 0.0
    assert screen_idea.STRESS_SLIPPAGE_FACTOR == 2


def test_screen_ticker_passes_the_idea_shape_to_book_and_null(monkeypatch):
    shapes = {"book": [], "null": []}
    real_book, real_null = race_mod.run_book, null.matched_null

    def book_spy(*args, **kwargs):
        shapes["book"].append(kwargs.get("shape"))
        return real_book(*args, **kwargs)

    def null_spy(*args, **kwargs):
        shapes["null"].append(kwargs.get("shape"))
        return real_null(*args, **kwargs)

    monkeypatch.setattr(race_mod, "run_book", book_spy)
    monkeypatch.setattr(null, "matched_null", null_spy)
    df = random_walk(2600)
    screen_idea.screen_ticker(IDEAS["turn_of_month"], "AAA", df, ALWAYS)
    assert shapes == {"book": ["fixed"], "null": ["fixed"]}
    shapes["book"].clear()
    shapes["null"].clear()
    screen_idea.screen_ticker(_trail_probe(), "AAA", df, ALWAYS)
    # the base book, then the 2 x slippage re-race
    assert shapes == {"book": ["trail", "trail"], "null": ["trail", "trail"]}


def test_a_fixed_idea_carries_no_trail_only_data():
    out = screen_idea.screen_ticker(IDEAS["turn_of_month"], "AAA", random_walk(2600), ALWAYS)
    assert out.null_timeout_r == [] and out.stressed is None


def test_a_trail_idea_races_only_trail_outcomes():
    out = screen_idea.screen_ticker(_trail_probe(), "AAA", random_walk(2600), ALWAYS)
    allowed = set(race_mod.SHAPE_OUTCOMES["trail"])
    assert out.events
    assert {row["outcome"] for row in out.events} <= allowed
    assert set(out.null_outcomes) <= allowed
    assert "target" not in out.null_outcomes and "gap_target" not in out.null_outcomes


def test_trail_null_timeout_r_is_every_null_timeout():
    out = screen_idea.screen_ticker(_trail_probe(), "AAA", random_walk(2600), ALWAYS)
    assert out.null_outcomes["timeout"] > 0
    assert len(out.null_timeout_r) == out.null_outcomes["timeout"]
    assert all(np.isfinite(out.null_timeout_r))


def test_stressed_rows_equal_a_rerun_at_twice_the_slippage():
    df = random_walk(2600)
    idea = _trail_probe()
    base = screen_idea.screen_ticker(idea, "AAA", df, ALWAYS, slippage_bps=5.0, commission=0.0)
    double = screen_idea.screen_ticker(idea, "AAA", df, ALWAYS, slippage_bps=10.0, commission=0.0)
    assert base.stressed == [{"entry_date": r["entry_date"], "r_event": r["r_event"],
                              "r_null": r["r_null"]} for r in double.events]
    assert [r["entry_date"] for r in base.stressed] == [r["entry_date"] for r in base.events]
    assert all(s["r_event"] < r["r_event"] for s, r in zip(base.stressed, base.events))


def _screen(events, null_outcomes, *, null_timeout_r=(), stressed=None):
    empty_rank = pd.DataFrame(columns=["year", "event"]
                              + [f"fwd_{h}" for h in forward.HORIZONS])
    return screen_idea.TickerScreen(
        ticker="AAA", counters=Counter(), events=events,
        null_outcomes=Counter(null_outcomes),
        excess={h: [] for h in forward.HORIZONS}, rank=empty_rank,
        null_timeout_r=list(null_timeout_r), stressed=stressed)


def _row(day, r_event, r_null, outcome):
    return {"ticker": "AAA", "entry_date": day, "exit_date": day,
            "r_event": r_event, "r_null": r_null, "outcome": outcome}


def test_summarise_reports_timeouts_per_book():
    rows = [_row("2012-03-01", 2.0, 0.5, "timeout"), _row("2012-04-02", -1.0, 0.0, "stop"),
            _row("2013-05-01", 4.0, 0.5, "timeout"), _row("2013-06-03", 1.5, 0.5, "trail")]
    screen = _screen(rows, {"timeout": 2, "trail": 5, "stop": 3}, null_timeout_r=[0.5, 1.5])
    out = screen_idea.summarise([screen])
    assert out["timeouts"]["event"] == (2, 0.5, pytest.approx(3.0))
    assert out["timeouts"]["null"] == (2, 0.2, pytest.approx(1.0))


def test_summarise_timeouts_and_stress_are_empty_for_an_empty_book():
    out = screen_idea.summarise([_screen([], {})])
    assert out["timeouts"] == {"event": (0, None, None), "null": (0, None, None)}
    assert out["stress"] is None


def test_summarise_stress_verdict_pools_only_stressed_rows():
    rows = [_row("2012-03-01", 2.0, 0.5, "timeout"), _row("2013-04-02", -1.0, 0.0, "stop")]
    stressed = [{"entry_date": "2012-03-01", "r_event": 1.9, "r_null": 0.45},
                {"entry_date": "2013-04-02", "r_event": -1.1, "r_null": -0.05}]
    trail = _screen(rows, {"timeout": 1}, null_timeout_r=[0.3], stressed=stressed)
    fixed = _screen([_row("2014-01-02", 1.0, 0.0, "target")], {"target": 1})
    out = screen_idea.summarise([trail, fixed])
    assert out["stress"].n == 2
    assert out["stress"].delta_exp_r == pytest.approx(((1.9 - 0.45) + (-1.1 + 0.05)) / 2)
    assert screen_idea.summarise([fixed])["stress"] is None
