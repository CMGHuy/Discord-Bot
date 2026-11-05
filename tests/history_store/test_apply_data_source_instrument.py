"""v190 section 3 / 4: the instrument, not a universe name or an environment
variable, picks the store. v1, v2 and scripts without --instrument select
exactly as before; v3 selects the PIT store cut at research_end and refuses
to run without its context frames (regime ticker, etfs.json)."""
from __future__ import annotations

import argparse
import hashlib
import json

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.marketdata import history_store, pit_integrity, training_data, universe

import fetch_backtest_data as fbd

ETFS = {"SPY": "Broad Market", "XLK": "Information Technology"}


def _bars(start, end):
    idx = pd.date_range(start, end, freq="B")
    n = len(idx)
    return pd.DataFrame({"Open": [10.0] * n, "High": [11.0] * n, "Low": [9.0] * n,
                         "Close": [10.0] * n, "Volume": [1000.0] * n}, index=idx)


def _store(root, files, statuses=None):
    """A daily store: CSVs plus a manifest; returns the manifest bytes."""
    folder = root / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    for ticker in files:
        _bars("2016-01-04", "2026-03-31").to_csv(folder / f"{ticker}.csv", index_label="Date")
    statuses = statuses or {t: "ok" for t in files}
    path = folder / "_manifest.json"
    path.write_text(json.dumps({"timeframe": "daily", "feed": "sip", "adjustment": "all",
                                "hash": "h", "tickers": {t: {"status": s}
                                                         for t, s in statuses.items()}}))
    return path.read_bytes()


def _report(root, manifest_bytes, tickers):
    (root / pit_integrity.INTEGRITY_NAME).write_text(json.dumps({
        "schema": 1, "generated_at": "2026-10-25T10:00:00Z", "store_start": "2016-01-04",
        "store_end": "2025-12-31", "thresholds": {}, "detector_sha": {},
        "manifest_sha256": {"daily": hashlib.sha256(manifest_bytes).hexdigest()},
        "no_bars": [],
        "tickers": {t: {"admitted": ok, "reason": None if ok else "unresolved break 2019-05-02",
                        "signal_cuts": [], "trim": None} for t, ok in tickers.items()}}))


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(universe, "sector_map", lambda name: dict(ETFS) if name == "etfs" else {})
    watch = tmp_path / "market_data"
    monkeypatch.setenv("HISTORY_STORE_DIR", str(watch))
    _store(watch, ("AAPL", "SPY"))
    training_data.reset()
    yield
    training_data.reset()


@pytest.fixture
def pit(tmp_path):
    root = tmp_path / "data" / "market_data_pit"
    _report(root, _store(root, ("AAA", "SPY", "XLK")), {"AAA": True, "SPY": True, "XLK": True})
    return root


def _args(**over):
    base = {"data_source": None, "instrument": "v1"}
    base.update(over)
    return argparse.Namespace(**base)


# --- v1, v2 and scripts without --instrument: unchanged ---------------------------------

@pytest.mark.parametrize("args", [argparse.Namespace(data_source=None), _args(),
                                  _args(instrument="v2"), _args(instrument=None)])
def test_without_a_store_instrument_the_selection_is_todays(pit, capsys, args):
    assert fbd.instrument_store_spec(args) is None
    assert fbd.apply_data_source(args) == "alpaca"
    assert capsys.readouterr().out.strip() == "training data: alpaca (0 excluded)"
    assert training_data.active_store() == "watchlist"
    assert training_data.available_tickers() == ["AAPL", "SPY"]


def test_v2_with_yfinance_is_todays_yfinance(pit):
    assert fbd.apply_data_source(_args(instrument="v2", data_source="yfinance")) == "yfinance"
    assert training_data.selection_args() == ("yfinance",)


# --- v3 ---------------------------------------------------------------------------------

def test_v3_selects_the_pit_store_cut_at_research_end(pit, capsys):
    assert fbd.instrument_store_spec(_args(instrument="v3")) is resolve("v3")
    assert fbd.apply_data_source(_args(instrument="v3")) == "alpaca"
    assert training_data.selection_args() == ("alpaca", "pit", "2025-12-31")
    assert training_data.available_tickers() == ["AAA", "SPY", "XLK"]
    out = capsys.readouterr().out
    assert "training data: alpaca, PIT store cut at 2025-12-31 (0 excluded)" in out


def test_v3_context_frames_stop_at_research_end(pit):
    """SPY and the sector ETFs load through training_data, so the same cut
    holds for the as-of build and the regime gate (spec section 4)."""
    fbd.apply_data_source(_args(instrument="v3"))
    for symbol in ("SPY", "XLK"):
        assert fbd.load_cached(symbol).index.max() == pd.Timestamp("2025-12-31"), symbol


@pytest.mark.parametrize("source", [None, "alpaca"])
def test_v3_accepts_alpaca_or_no_data_source(pit, source):
    assert fbd.apply_data_source(_args(instrument="v3", data_source=source)) == "alpaca"


def test_v3_refuses_yfinance(pit):
    with pytest.raises(SystemExit, match="--data-source yfinance"):
        fbd.apply_data_source(_args(instrument="v3", data_source="yfinance"))


def test_v3_refuses_a_missing_context_frame_naming_it(tmp_path):
    root = tmp_path / "data" / "market_data_pit"
    _report(root, _store(root, ("AAA", "SPY")), {"AAA": True, "SPY": True})
    with pytest.raises(SystemExit) as exc:
        fbd.apply_data_source(_args(instrument="v3"))
    message = str(exc.value)
    assert "XLK" in message and "SPY" not in message.split(":", 1)[1]


def test_v3_refuses_a_context_frame_the_integrity_report_excluded(tmp_path):
    root = tmp_path / "data" / "market_data_pit"
    _report(root, _store(root, ("AAA", "SPY", "XLK")), {"AAA": True, "SPY": False, "XLK": True})
    with pytest.raises(SystemExit) as exc:
        fbd.apply_data_source(_args(instrument="v3"))
    assert "SPY (integrity: unresolved break 2019-05-02)" in str(exc.value)


def test_v3_without_a_pit_store_raises_the_store_error(tmp_path):
    """Callers already turn MissingStoreError into SystemExit; it is not swallowed here."""
    with pytest.raises(history_store.MissingStoreError, match="market_data_pit"):
        fbd.apply_data_source(_args(instrument="v3"))


def test_a_universe_name_never_selects_the_pit_store(pit):
    args = _args(instrument="v2")
    args.universe = "sp500_pit"
    fbd.apply_data_source(args)
    assert training_data.active_store() == "watchlist"


def test_v3_reports_all_missing_context_frames_once(tmp_path):
    root = tmp_path / "data" / "market_data_pit"
    _report(root, _store(root, ("AAA",)), {"AAA": True})
    with pytest.raises(SystemExit) as exc:
        fbd.apply_data_source(_args(instrument="v3"))
    message = str(exc.value)
    assert message.count("SPY (not in store)") == 1
    assert "XLK (not in store)" in message


def test_v3_propagates_stale_integrity_error(pit):
    manifest = pit / "daily" / "_manifest.json"
    manifest.write_text(manifest.read_text() + " ")
    with pytest.raises(training_data.StaleIntegrityError, match="manifest changed"):
        fbd.apply_data_source(_args(instrument="v3"))


@pytest.mark.parametrize("trim, reason", [
    ({"keep_from": "2027-01-01"}, "empty after integrity trim"),
    ({"keep_from": "2026-01-01"}, "no bars on or before the cut"),
])
def test_v3_refuses_context_frames_empty_after_trim_or_cut(pit, trim, reason):
    report = pit / pit_integrity.INTEGRITY_NAME
    payload = json.loads(report.read_text())
    payload["tickers"]["XLK"]["trim"] = trim
    report.write_text(json.dumps(payload))
    with pytest.raises(SystemExit) as exc:
        fbd.apply_data_source(_args(instrument="v3"))
    assert f"XLK ({reason})" in str(exc.value)
