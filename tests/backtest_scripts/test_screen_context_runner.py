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
PARITY_DIGESTS: dict[str, str] = {
    "gap_volume": "754ec86aaf08c64a75322ca0163dd0634b80f18f780861eb582daa63ba251d92",
    "high52w": "ed4fba6e7739def94b33030b8a971c44bb8f9a735911983c3668fdc54eafd10a",
    "high52w_trail": "eebc95fe42e37adbc1268224bc6e6fa2b38939c4486c5b7f9db5aa5adc2cac75",
    "quiet_pullback": "f8d99b46c8d618ce3717372b0dfa1b2fb207665b48776500c05044522282b024",
    "turn_of_month": "5730a7201259ef26727457366e734d8d631d8d29cef807a9723937dd57cb22c0",
    "turtle_soup": "33e7d4b75ad305ef352b3658ca9ad926400c2e00fb98431622ecc2191fc99b04",
    "uptrend_pullback": "1ee25ddad46bb88201b1d6fe593561531daa773cfd4b9d9bae78390cf10ec935"
}


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


@pytest.mark.parametrize("name", OLD_IDEAS)
def test_an_old_idea_is_called_with_exactly_one_argument(name):
    original = IDEAS[name]
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
