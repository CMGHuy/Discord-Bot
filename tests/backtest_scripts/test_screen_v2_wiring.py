"""v230 A2/A4: screen_idea runs the v2 null -- the screen-v2 instrument, the null
version and scope in the head, a starved pool refused with exit 2, the adapter."""
import functools
import json
from collections import Counter
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import screen_idea  # on sys.path via conftest.py

from swingbot.core.backtesting.screen import screen_v2, verdict
from swingbot.core.backtesting.screen.errors import IdeaError
from swingbot.core.backtesting.screen.ideas import IDEAS, Idea
from tests.backtesting.screen.helpers import random_walk

IDEA = IDEAS["turn_of_month"]       # market scope: three tickers are a whole pool


def _quiet(*_args, **_kwargs):
    return None


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    monkeypatch.setattr(screen_idea.verdict, "decide",
                        functools.partial(verdict.decide, n_resamples=500))


def _universe(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    for seed, ticker in enumerate(("AAA", "BBB", "DDD"), start=1):
        random_walk(2700, seed=seed).rename_axis("Date").to_csv(cache / f"{ticker}.csv")
    membership = tmp_path / "membership.csv"
    membership.write_text("ticker,start_date,end_date\n" + "".join(
        f"{t},2000-01-01,\n" for t in ("AAA", "BBB", "DDD")), encoding="utf-8")
    return cache, screen_idea.load_universe(cache, membership)


def _argv(tmp_path, cache, idea, *extra):
    return ["--idea", idea, "--cache-dir", str(cache),
            "--membership", str(tmp_path / "membership.csv"),
            "--ledger", str(tmp_path / "ledger.jsonl"),
            "--results-dir", str(tmp_path / "results"), "--date", "2026-11-20",
            "--dry-run", *extra]


def test_the_entry_offsets_match_the_v2_orchestration():
    assert screen_v2._ENTRY_OFFSET == screen_idea._ENTRY_OFFSET


def test_v2_is_the_default_and_names_its_instrument(monkeypatch):
    assert screen_idea.NULL_VERSION == "v2" and screen_idea.instrument() == "screen-v2"
    row = screen_idea.ledger_row(IDEA, verdict.decide([]), "r.md", "2026-11-20")
    assert row["instrument"] == "screen-v2"
    monkeypatch.setattr(screen_idea, "NULL_VERSION", "v1")
    assert screen_idea.instrument() == screen_idea.INSTRUMENT == "screen-v1"


def test_screen_universe_v2_adapts_every_event_ticker(tmp_path):
    cache, universe = _universe(tmp_path)
    screens, skipped = screen_idea.screen_universe_v2(IDEA, universe, cache, out=_quiet)
    assert [s.ticker for s in screens] == ["AAA", "BBB", "DDD"] and not skipped
    s = screens[0]
    assert isinstance(s, screen_idea.TickerScreen) and len(s.rank) and s.events
    assert {"cost_event", "cost_null"} <= set(s.events[0])
    assert (s.restricted, s.stressed, s.repriced, s.control, s.shock, s.avoid) == (None,) * 6
    summary = screen_idea.summarise(screens, skipped)
    assert summary["verdict"].n == sum(len(x.events) for x in screens)


def test_tickers_restrict_the_event_book_only(tmp_path):
    cache, universe = _universe(tmp_path)
    screens, _ = screen_idea.screen_universe_v2(IDEA, universe, cache, tickers=["BBB", "ZZZ"],
                                                out=_quiet, checkpoint_dir=tmp_path / "ck")
    assert [s.ticker for s in screens] == ["BBB"]
    saved = json.loads((tmp_path / "ck" / "panel" / "manifest.json").read_text(encoding="utf-8"))
    assert (saved["null_version"], saved["scope"]) == ("v2", "market")


def test_a_dry_run_prints_the_null_version_scope_and_the_v2_blocks(tmp_path, monkeypatch,
                                                                    capsys):
    cache, _ = _universe(tmp_path)
    sectors = tmp_path / "pit.json"
    sectors.write_text(json.dumps([{"symbol": "AAA", "sector": "Tech"}]), encoding="utf-8")
    monkeypatch.setattr(screen_idea, "SECTOR_MAP", sectors)
    assert screen_idea.main(_argv(tmp_path, cache, "turn_of_month")) == 0
    text = capsys.readouterr().out
    for needle in ("(instrument `screen-v2`)", "**Null:** v2, scope `market`",
                   "## Null v2 (v230)", "same ticker in the same trend state", "| Tech |",
                   "- `shock`:"):
        assert needle in text, needle
    assert text.index("## Forward drift") < text.index("## Null v2")


def test_the_v1_fixture_keeps_the_v1_head(tmp_path, capsys, screen_null_v1):
    cache, _ = _universe(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, "turn_of_month")) == 0
    text = capsys.readouterr().out
    assert "(instrument `screen-v1`)" in text and "**Null:**" not in text
    assert "## Null v2" not in text


def test_a_starved_ticker_scope_pool_is_refused_with_exit_2(tmp_path, capsys):
    cache, _ = _universe(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, "uptrend_pullback")) == 2
    assert "refused: SCOPE_MISMATCH:" in capsys.readouterr().err


def _v2_ticker(**kw):
    base = dict(ticker="AAA", counters=Counter({"dropped_no_match": 1, "control_below_floor": 2}),
                events=[{"ticker": "AAA", "entry_date": "2012-03-02"},
                        {"ticker": "AAA", "entry_date": "2012-04-02"}],
                null_outcomes=Counter({"stop": 3}), excess={5: [0.1]},
                extras={"rank": pd.DataFrame(), "overlap": None,
                        "avoid": {"excluded": 7, "population": 70,
                                  "overnight_dates": ["2012-03-02", "2013-01-02"]}},
                null_timeout_r=[], null_slots=40, null_unfilled=0, depths=None,
                avoid_control=[{"ticker": "AAA"}])
    return screen_v2.V2Ticker(**{**base, **kw})


def test_the_adapter_carries_the_avoid_counts_and_the_overlap():
    s = screen_idea._v2_screen(_v2_ticker())
    assert s.avoid == {"control": [{"ticker": "AAA"}], "below_floor": 2, "kept": 2,
                       "excluded": 7, "population": 70, "overnight": 1}
    assert s.null_slots == 40 and s.counters["dropped_no_match"] == 1
    overlap = {"own": 1, "other": 2, "both": 0}
    plain = screen_idea._v2_screen(_v2_ticker(extras={"rank": pd.DataFrame(), "overlap": overlap},
                                              avoid_control=None))
    assert plain.avoid is None and plain.overlap == overlap


def test_collect_counts_empty_frames_and_idea_errors():
    found = [_v2_ticker(), _v2_ticker(ticker="BBB", extras={"idea_error": "bad bar"})]
    screens, skipped = screen_idea._v2_collect(found, 3)
    assert [s.ticker for s in screens] == ["AAA"]
    assert skipped == Counter({"empty_frame": 1, "idea_error": 1, "idea_error:BBB": 1})


def test_avoid_extras_read_the_pre_draw_book():
    df = random_walk(300, seed=4)
    n = len(df)
    bottom = np.full(n, -np.inf)
    bottom[20] = np.inf                               # bar 10 reaches its bottom, bar 20 never
    ctx = {"member": np.ones(n, bool), "warm": np.ones(n, bool),
           "condition": np.arange(n) < 5, "bottom": bottom,
           "book": SimpleNamespace(event_pos=np.array([10, 20]))}
    assert screen_idea._avoid_extras(df, ctx) == {
        "excluded": 5, "population": n, "overnight_dates": [df.index[11].strftime("%Y-%m-%d")]}


def _broken_states(df):
    raise IdeaError("bad bar")


def test_an_avoid_idea_error_leaves_the_ticker_out_of_both_arms(tmp_path):
    _, universe = _universe(tmp_path)
    idea = Idea(name="av", events=lambda df: df["Close"] > 0, time_cap_bars=10, mode="avoid",
                states=_broken_states)
    df = random_walk(300, seed=1)
    ctx = screen_idea._v2_context(idea, universe, None, screen_idea.EVENT_START, _quiet)("AAA", df)
    assert "bad bar" in ctx["idea_error"]
    assert not ctx["member"].any() and not ctx["raw"].any()
    extras = screen_idea._v2_extras(idea)("AAA", df, {**ctx, "book": None})
    assert extras == {"idea_error": ctx["idea_error"]}
