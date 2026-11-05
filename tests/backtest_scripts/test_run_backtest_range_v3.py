"""v190 V190-7: run_backtest_range --instrument v3 on a fixture PIT store.

Pins (spec §3, §4): v3 reads the PIT store with one frame trim (MON) and one
signal-span cut (AAA) applied; no ticker, context or intraday bar on or after
2026-01-01 is reachable; a v3 run refuses the holdout, yfinance, a missing
context ETF and a missing integrity report before any backtest; v1 and v2 are
byte-identical with a PIT store on disk."""
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
for _sub in ("scripts/backtest", "scripts/data"):
    if str(ROOT / _sub) not in sys.path:
        sys.path.insert(0, str(ROOT / _sub))

import run_backtest_range as rbr  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting import asof_context, backtest  # noqa: E402
from swingbot.core.backtesting.backtest import BacktestTrade  # noqa: E402
from swingbot.core.backtesting.instrument.cli import HOLDOUT_SEALED  # noqa: E402
from swingbot.core.backtesting.instrument.contract import resolve  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402
from swingbot.core.marketdata.data_store import safe_symbol  # noqa: E402
from swingbot.core.marketdata.pit_membership import OPEN_END, membership_map  # noqa: E402
from swingbot.core.marketdata.universe import sector_map  # noqa: E402

V3 = resolve("v3")
RESEARCH_END = pd.Timestamp("2025-12-31")
HOLDOUT = pd.Timestamp("2026-01-01")
MEMBERS = ("AAA", "BBB", "MON")
CONTEXT = tuple(sorted({config.MARKET_REGIME_TICKER, *sector_map("etfs")}))
MEMBERSHIP = ("ticker,start_date,end_date\n"
              "AAA,2010-01-04,\n"
              "BBB,2010-01-04,\n"
              "MON,2010-01-04,2018-06-08\n")
CUT = ("2019-03-01", "2019-04-01")   # AAA: a missing run, cut from the signal mask
TRIM_BEFORE = "2018-06-08"           # MON: a reused symbol's bars from here on
DAYS = pd.bdate_range("2016-01-04", "2026-03-31")
#: entry days the stubbed engine returns per ticker. Kept under v3: AAA 02-15
#: and 05-15 (03-15 is inside CUT), BBB 03-15 (the cut is AAA's alone), MON
#: 2017-06-01 (2019-01-15 is after MON left the index) -> n_eval 4.
TRADES = {"AAA": ("2019-02-15", "2019-03-15", "2019-05-15"),
          "BBB": ("2019-03-15",),
          "MON": ("2017-06-01", "2019-01-15")}
V2_KNOBS = ("--exit-model", "v2", "--tp2", "none")
V3_FLAGS = ("--instrument", "v3", *V2_KNOBS)


def _trade(entry):
    return BacktestTrade(entry_date=entry, exit_date=entry, direction="bullish", entry=50.0,
                         stop_loss=48.0, take_profit=54.0, outcome="win", exit_price=54.0,
                         return_pct=8.0, r_multiple=1.0, holding_days=3)


def _intraday(stamps):
    return pd.DatetimeIndex([day + pd.Timedelta(hours=h, minutes=m)
                             for day in DAYS[-300:] for h, m in stamps], name="Datetime")


INDEXES = {"daily": lambda: pd.DatetimeIndex(DAYS, name="Date"),
           "hourly": lambda: _intraday(((10, 0), (14, 0))),
           "15min": lambda: _intraday(((9, 30), (15, 45)))}


def _write_timeframe(root: Path, timeframe: str, tickers, close: float) -> str:
    """One timeframe's CSVs and manifest; returns the manifest file's sha256
    (the value `_integrity.json` freezes and V190-4's staleness check compares)."""
    folder = root / timeframe
    folder.mkdir(parents=True)
    index = INDEXES[timeframe]()
    frame = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                          "Volume": 1_000_000.0}, index=index)
    for ticker in tickers:
        frame.to_csv(folder / f"{safe_symbol(ticker)}.csv")
    manifest = folder / "_manifest.json"
    manifest.write_text(json.dumps({
        "timeframe": timeframe, "feed": "sip", "adjustment": "all", "hash": f"h-{timeframe}",
        "tickers": {t: {"status": "ok", "sha256": "x"} for t in tickers}}), encoding="utf-8")
    return hashlib.sha256(manifest.read_bytes()).hexdigest()


def _entry(**over) -> dict:
    entry = {"admitted": True, "reason": None, "identity": "ok", "identity_manifest": "ok",
             "reference": {"source": "backtest_cache_ext", "sha256": "r"}, "dropped_before": 0,
             "first_bar": "2016-01-04", "last_bar": "2026-03-31", "coverage": [],
             "signal_cuts": [], "trim": {"keep_from": None, "keep_before": None, "reason": None},
             "breaks": []}
    entry.update(over)
    return entry


def build_pit_store(data_dir: Path, *, close: float = 50.0, context=CONTEXT) -> Path:
    """A fixture PIT store under <data_dir>/market_data_pit: members plus context
    symbols, all three timeframes, and an `_integrity.json` carrying one frame
    trim (MON) and one signal-date cut (AAA)."""
    root = data_dir / "market_data_pit"
    tickers = (*MEMBERS, *context)
    shas = {tf: _write_timeframe(root, tf, tickers, close) for tf in ("daily", "hourly", "15min")}
    entries = {t: _entry() for t in tickers}
    entries["AAA"] = _entry(signal_cuts=[[*CUT, "missing run of 6 sessions"]])
    entries["MON"] = _entry(
        trim={"keep_from": None, "keep_before": TRIM_BEFORE,
              "reason": "reused symbol: break after the last membership end"},
        breaks=[{"date": TRIM_BEFORE, "kind": "close+volume", "resolution": "trim_after"}])
    doc = {"schema": 1, "generated_at": "2026-10-25T00:00:00+00:00",
           "store_start": "2016-01-04", "store_end": "2025-12-31",
           "thresholds": {"max_missing_run": 5, "trailing_sessions": 60,
                          "min_trailing_share": 0.95, "break_move": 0.5, "break_ratio": 10.0,
                          "revert_sessions": 20, "gap_sessions": 20, "edge_sessions": 20},
           "detector_sha": {}, "manifest_sha256": shas, "no_bars": [], "tickers": entries}
    (root / "_integrity.json").write_text(json.dumps(doc), encoding="utf-8")
    return root


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """config.DATA_DIR -> tmp (membership CSV, PIT root); HISTORY_STORE_DIR -> a
    watchlist store holding AAA, BBB and the regime ticker, which v3 must never read."""
    for name in backtest._LIVE_STATE_FLAGS:
        monkeypatch.setattr(config, name, False, raising=False)
    data = tmp_path / "data"
    (data / "universe").mkdir(parents=True)
    (data / "universe" / "sp500_membership.csv").write_text(MEMBERSHIP, encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    watchlist = tmp_path / "watchlist_store"
    _write_timeframe(watchlist, "daily", ("AAA", "BBB", config.MARKET_REGIME_TICKER), 40.0)
    monkeypatch.setenv("HISTORY_STORE_DIR", str(watchlist))
    monkeypatch.chdir(tmp_path)          # main writes backtest_range_summary.txt to cwd
    rbr._SPY_CACHE.clear()
    training_data.reset()
    yield data
    rbr._SPY_CACHE.clear()
    training_data.reset()


@pytest.fixture
def harness(data_dir, monkeypatch, tmp_path, capsys):
    calls = []

    def fake_run_backtest(ticker, df, strat, hk, **kwargs):
        calls.append({"ticker": ticker, "first": df.index.min(), "last": df.index.max(),
                      "rows": len(df), "digest": int(pd.util.hash_pandas_object(df).sum()),
                      "instrument": kwargs.get("instrument")})
        return SimpleNamespace(trades=[_trade(day) for day in TRADES.get(ticker, ())])

    monkeypatch.setattr(rbr, "run_backtest", fake_run_backtest)
    monkeypatch.setattr(rbr, "_tickers_for_run",
                        lambda universe, tickers_file=None: list(MEMBERS) if universe else ["AAA", "BBB"])
    monkeypatch.setattr(rbr, "_exclusion_reason", lambda df, ticker, pit: None)
    monkeypatch.setattr(rbr, "load_watchlist", lambda: ["AAA", "BBB"])
    monkeypatch.setattr(rbr, "LEGACY_HORIZONS", ("3m",))

    def run(*argv, context="off"):
        calls.clear()
        rbr._SPY_CACHE.clear()
        training_data.reset()
        capsys.readouterr()
        out = tmp_path / "out.json"
        monkeypatch.setattr(sys, "argv", ["run_backtest_range.py", "--strategy", "RSI",
                                          "--context", context, "--json", str(out), *argv])
        rbr.main()
        return SimpleNamespace(
            payload=json.loads(out.read_text(encoding="utf-8")),
            report=(tmp_path / "backtest_range_summary.txt").read_text(encoding="utf-8"),
            provenance=json.loads(training_data.provenance_path(out).read_text(encoding="utf-8")),
            stdout=capsys.readouterr().out, calls=list(calls))

    return SimpleNamespace(run=run, calls=calls)


# --- v3 end to end ------------------------------------------------------------------

def _assert_v3_frame_selection(calls):
    """The v3 engine receives the PIT members with the integrity frame trim."""
    by_ticker = {call["ticker"]: call for call in calls}
    assert set(by_ticker) == set(MEMBERS)
    assert all(call["instrument"] == V3 for call in calls)
    assert by_ticker["MON"]["last"] < pd.Timestamp(TRIM_BEFORE)    # the frame trim
    assert by_ticker["AAA"]["last"] <= RESEARCH_END
    assert by_ticker["AAA"]["first"] == pd.Timestamp("2016-01-04")


def test_v3_runs_on_the_pit_store_with_one_trim_and_one_cut(harness, data_dir):
    build_pit_store(data_dir)
    result = harness.run("--train", *V3_FLAGS)
    _assert_v3_frame_selection(result.calls)
    assert result.payload["RSI"]["n_eval"] == 4                     # the span cut drops AAA 03-15
    assert "== TRAIN 2017-01-01 .. 2025-12-31" in result.report
    assert "instrument v3: universe sp500_pit" in result.report
    assert ("signal-date cuts ON from the PIT integrity report: 1 cut range(s) on 1 ticker(s)"
            in result.stdout)


def test_v3_provenance_names_the_store_and_the_integrity_sha(harness, data_dir):
    root = build_pit_store(data_dir)
    result = harness.run("--train", *V3_FLAGS)
    assert result.provenance["data_source"] == "alpaca"
    assert result.provenance["store"] == "pit"
    assert result.provenance["integrity_sha256"] == \
        hashlib.sha256((root / "_integrity.json").read_bytes()).hexdigest()


def test_v3_context_frames_stop_at_research_end(harness, data_dir, monkeypatch):
    build_pit_store(data_dir)
    seen = {}

    def capture(frames, spy_df, *, sector_of_ticker, sector_etf_frames, sector_of_etf, **kwargs):
        seen.update(frames=frames, spy=spy_df, etfs=sector_etf_frames)
        return {}

    monkeypatch.setattr(asof_context, "build_asof", capture)
    harness.run("--train", *V3_FLAGS, context="on")
    assert seen["spy"].index.max() <= RESEARCH_END
    assert set(seen["etfs"]) == set(sector_map("etfs"))
    assert all(frame.index.max() <= RESEARCH_END for frame in seen["etfs"].values())
    assert all(frame.index.max() <= RESEARCH_END for frame in seen["frames"].values())
    assert rbr._market_frame().index.max() <= RESEARCH_END


def test_v3_leaves_no_intraday_bar_on_or_after_the_holdout(harness, data_dir):
    build_pit_store(data_dir)
    harness.run("--train", *V3_FLAGS)
    assert training_data.active_store() == "pit"
    for ticker in ("AAA", config.MARKET_REGIME_TICKER):
        for timeframe in ("hourly", "15min"):
            frame = training_data.load_intraday(ticker, timeframe)
            assert frame is not None and frame.index.max() < HOLDOUT
    # MON's stored intraday bars all lie after its trim: trimmed to nothing is None
    assert training_data.load_intraday("MON", "hourly") is None
    assert training_data.load_daily("AAA").index.max() <= RESEARCH_END


# --- v3 refusals: before any backtest ------------------------------------------------

def test_v3_validation_is_the_sealed_holdout(harness, data_dir):
    build_pit_store(data_dir)
    with pytest.raises(SystemExit) as exc:
        harness.run("--validation", *V3_FLAGS)
    assert HOLDOUT_SEALED in str(exc.value)
    assert harness.calls == []


def test_v3_refuses_a_window_reaching_into_2026(harness, data_dir):
    build_pit_store(data_dir)
    with pytest.raises(SystemExit, match="research span"):
        harness.run("--from", "2025-06-01", "--to", "2026-02-27", *V3_FLAGS)
    assert harness.calls == []


def test_v3_refuses_yfinance(harness, data_dir):
    build_pit_store(data_dir)
    with pytest.raises(SystemExit):
        harness.run("--train", *V3_FLAGS, "--data-source", "yfinance")
    assert harness.calls == []


def test_v3_refuses_a_store_missing_a_context_symbol(harness, data_dir):
    build_pit_store(data_dir, context=CONTEXT[:-1])
    with pytest.raises(SystemExit) as exc:
        harness.run("--train", *V3_FLAGS)
    assert CONTEXT[-1] in str(exc.value)
    assert harness.calls == []


def test_v3_refuses_a_store_without_an_integrity_report(harness, data_dir):
    root = build_pit_store(data_dir)
    (root / "_integrity.json").unlink()
    with pytest.raises(SystemExit):
        harness.run("--train", *V3_FLAGS)
    assert harness.calls == []


# --- _membership_for_run ------------------------------------------------------------

def test_membership_for_run_subtracts_the_integrity_cuts_under_the_pit_store(data_dir, capsys):
    build_pit_store(data_dir)
    training_data.select("alpaca", "pit", V3.research_end)
    membership = rbr._membership_for_run("sp500_pit", list(MEMBERS))
    assert membership["AAA"] == [("2010-01-04", CUT[0]), (CUT[1], OPEN_END)]
    assert membership["BBB"] == [("2010-01-04", OPEN_END)]
    assert membership["MON"] == [("2010-01-04", "2018-06-08")]
    assert "1 cut range(s) on 1 ticker(s)" in capsys.readouterr().out


@pytest.mark.parametrize("source", ["alpaca", "yfinance"])
def test_membership_for_run_is_unchanged_off_the_pit_store(data_dir, capsys, source):
    build_pit_store(data_dir)                 # on disk, never selected
    training_data.select(source)
    assert training_data.signal_cuts() is None
    assert rbr._membership_for_run("sp500_pit", list(MEMBERS)) == \
        membership_map("sp500_pit", list(MEMBERS))
    assert rbr._membership_for_run(None, ["AAA"]) is None
    assert "signal-date cuts" not in capsys.readouterr().out


# --- v1 and v2: byte-identical with a PIT store on disk (spec §3 regression pins) -----

def test_the_default_selection_ignores_a_pit_store_on_disk(data_dir):
    training_data.select()
    before = (training_data.active_store(), training_data.available_tickers(),
              training_data.provenance())
    build_pit_store(data_dir, close=99.0)
    training_data.reset()
    training_data.select()
    after = (training_data.active_store(), training_data.available_tickers(),
             training_data.provenance())
    assert after == before
    assert before[0] == "watchlist"
    assert before[1] == sorted(["AAA", "BBB", config.MARKET_REGIME_TICKER])


@pytest.mark.parametrize("flags", [("--train",), ("--train", "--instrument", "v1"),
                                   ("--train", "--instrument", "v2", *V2_KNOBS)],
                         ids=["default", "v1", "v2"])
def test_v1_and_v2_are_byte_identical_with_a_pit_store_on_disk(harness, data_dir, flags):
    before = harness.run(*flags)
    build_pit_store(data_dir, close=99.0)     # different prices: any leak changes the digest
    after = harness.run(*flags)
    assert after.calls == before.calls
    assert after.payload == before.payload
    assert after.report == before.report
    assert after.provenance == before.provenance
    assert after.stdout == before.stdout
    assert after.provenance["store"] == "watchlist"
    assert "signal-date cuts" not in after.stdout
