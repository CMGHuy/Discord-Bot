"""v174 context hook in the runner: the events seam, parity of the six v140
ideas on the real call path, context loading and refusals."""
import dataclasses
import functools
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402

from swingbot.core.backtesting.screen import verdict  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.backtesting.screen import context as ctx_math  # noqa: E402
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
