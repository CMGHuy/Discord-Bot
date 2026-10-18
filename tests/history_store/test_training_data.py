"""v162 AH10: the training-data switch -- source selection, the hard error on
a missing store, exclusions with reasons, provenance, and the load_cached
seam every backtest script reads through."""
from __future__ import annotations

import argparse
import json

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import backtest_cache, history_store, training_data

import fetch_backtest_data as fbd


@pytest.fixture(autouse=True)
def _fresh_switch(monkeypatch):
    """No selection leaks between tests; config and env start at the defaults."""
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    training_data.reset()
    yield
    training_data.reset()


def _daily(close: float = 10.0) -> pd.DataFrame:
    idx = pd.DatetimeIndex(pd.to_datetime(["2016-01-04", "2016-01-05"]), name="Date")
    return pd.DataFrame({"Open": [close, close], "High": [close + 1] * 2, "Low": [close - 1] * 2,
                         "Close": [close, close + 0.5], "Volume": [1000.0, 1100.0]}, index=idx)


def _store(root, entries: dict[str, str], files: tuple[str, ...], *, hash_="h-1") -> None:
    """Hand-built daily manifest ({ticker: status}) plus CSVs for `files`."""
    folder = root / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    for ticker in files:
        _daily().to_csv(folder / f"{ticker}.csv", index_label="Date")
    tickers = {t: {"status": s, "sha256": None if s != "ok" else "x"} for t, s in entries.items()}
    (folder / "_manifest.json").write_text(json.dumps(
        {"timeframe": "daily", "feed": "sip", "adjustment": "all", "hash": hash_, "tickers": tickers}))


ENTRIES = {"AAPL": "ok", "MSFT": "ok", "SNDK": "flagged: short-overlap",
           "GLD": "skipped: not Alpaca-eligible"}


# --- selection ------------------------------------------------------------------

def test_sources():
    assert training_data.DATA_SOURCES == ("alpaca", "yfinance")


def test_none_resolves_to_the_config_value(monkeypatch):
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")
    assert training_data.select() == "yfinance"
    assert training_data.active() == "yfinance"


def test_an_explicit_name_wins_over_config(store_root):
    _store(store_root, {"AAPL": "ok"}, ("AAPL",))
    assert training_data.select("ALPACA") == "alpaca"
    assert training_data.select("yfinance") == "yfinance"     # each call replaces the last


def test_unknown_source_is_rejected():
    with pytest.raises(ValueError, match="polygon"):
        training_data.select("polygon")


def test_backtest_cache_dir_means_yfinance_unless_named(store_root, monkeypatch):
    _store(store_root, {"AAPL": "ok"}, ("AAPL",))
    monkeypatch.setenv("BACKTEST_CACHE_DIR", "data/backtest_cache_ext")
    assert training_data.select() == "yfinance"
    assert training_data.select("alpaca") == "alpaca"


# --- the hard error ---------------------------------------------------------------

def test_alpaca_without_a_manifest_raises_naming_the_path(store_root):
    with pytest.raises(history_store.MissingStoreError) as info:
        training_data.select("alpaca")
    assert str(store_root / "daily" / "_manifest.json") in str(info.value)


def test_first_use_raises_and_nothing_stays_selected(store_root):
    with pytest.raises(history_store.MissingStoreError):
        training_data.load_daily("AAPL")
    with pytest.raises(history_store.MissingStoreError):   # never a silent zero-ticker run
        training_data.active()
    with pytest.raises(history_store.MissingStoreError):
        fbd.load_cached("AAPL")


# --- alpaca reads and exclusions ----------------------------------------------------

def test_alpaca_loads_the_store_frame(store_root):
    _store(store_root, ENTRIES, ("AAPL", "MSFT"))
    out = training_data.load_daily("aapl")
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert out.index.name == "Date"
    assert list(out["Close"]) == [10.0, 10.5]
    assert training_data.active() == "alpaca"


def test_non_ok_entries_and_missing_files_are_excluded_with_reasons(store_root):
    _store(store_root, ENTRIES, ("AAPL",))                      # MSFT is ok but has no file
    training_data.select("alpaca")
    assert training_data.excluded() == {"GLD": "skipped: not Alpaca-eligible", "MSFT": "no file",
                                        "SNDK": "flagged: short-overlap"}
    for ticker in ("GLD", "MSFT", "SNDK"):
        assert training_data.load_daily(ticker) is None


def test_a_ticker_absent_from_the_manifest_is_excluded_when_asked_for(store_root):
    _store(store_root, ENTRIES, ("AAPL", "MSFT"))
    assert training_data.load_daily("ZZZ") is None
    assert training_data.excluded()["ZZZ"] == "not in store"


def test_an_ok_entry_with_an_empty_file_is_excluded(store_root):
    _store(store_root, {"AAPL": "ok"}, ())
    (store_root / "daily" / "AAPL.csv").write_text("Date,Open,High,Low,Close,Volume\n")
    training_data.select("alpaca")
    assert training_data.load_daily("AAPL") is None
    assert training_data.excluded() == {"AAPL": "empty file"}


def test_exclusion_lines_and_available_tickers(store_root):
    _store(store_root, ENTRIES, ("AAPL", "MSFT"))
    training_data.select("alpaca")
    assert training_data.available_tickers() == ["AAPL", "MSFT"]
    assert training_data.exclusion_lines() == ["excluded GLD: skipped: not Alpaca-eligible",
                                               "excluded SNDK: flagged: short-overlap"]


# --- yfinance is the pre-v162 loader ----------------------------------------------------

def test_yfinance_reads_the_backtest_cache_exactly_as_before(tmp_path, monkeypatch):
    monkeypatch.setattr(backtest_cache, "CACHE_DIR", tmp_path)
    _daily(20.0).to_csv(tmp_path / "AAPL.csv")
    (tmp_path / "EMPTY.csv").write_text("Date,Open,High,Low,Close,Volume\n")
    training_data.select("yfinance")
    expected = pd.read_csv(tmp_path / "AAPL.csv", index_col="Date", parse_dates=True)
    pd.testing.assert_frame_equal(training_data.load_daily("AAPL"), expected)
    assert training_data.load_daily("EMPTY") is None
    assert training_data.load_daily("NOPE") is None
    assert training_data.excluded() == {}
    assert training_data.available_tickers() == ["AAPL", "EMPTY"]


# --- provenance -------------------------------------------------------------------------

def test_alpaca_provenance(store_root):
    _store(store_root, ENTRIES, ("AAPL", "MSFT"), hash_="abc123")
    training_data.select("alpaca")
    assert training_data.provenance() == {
        "data_source": "alpaca", "feed": "sip", "adjustment": "all", "manifest_hash": "abc123",
        "store_dir": str(store_root),
        "excluded": {"GLD": "skipped: not Alpaca-eligible", "SNDK": "flagged: short-overlap"}}


def test_yfinance_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(backtest_cache, "CACHE_DIR", tmp_path)
    training_data.select("yfinance")
    assert training_data.provenance() == {
        "data_source": "yfinance", "feed": "yfinance", "adjustment": "auto_adjust",
        "manifest_hash": None, "store_dir": str(tmp_path), "excluded": {}}


def test_write_provenance_writes_the_sidecar_next_to_the_output(store_root, tmp_path):
    _store(store_root, {"AAPL": "ok"}, ("AAPL",))
    training_data.select("alpaca")
    out = tmp_path / "res.json"
    path = training_data.write_provenance(out)
    assert path == tmp_path / "res.json.provenance.json" == training_data.provenance_path(str(out))
    assert json.loads(path.read_text(encoding="utf-8")) == training_data.provenance()


# --- the load_cached seam and the CLI helpers ----------------------------------------------

def test_load_cached_delegates_to_the_switch(monkeypatch):
    seen = []
    monkeypatch.setattr(training_data, "load_daily", lambda t: seen.append(t) or "frame")
    assert fbd.load_cached("AAPL") == "frame"
    assert seen == ["AAPL"]


def test_data_source_arg_defaults_to_none_and_rejects_unknown():
    ap = argparse.ArgumentParser()
    fbd.add_data_source_arg(ap)
    assert ap.parse_args([]).data_source is None
    assert ap.parse_args(["--data-source", "yfinance"]).data_source == "yfinance"
    with pytest.raises(SystemExit):
        ap.parse_args(["--data-source", "polygon"])


def test_apply_data_source_selects_and_prints(store_root, capsys):
    _store(store_root, ENTRIES, ("AAPL", "MSFT"))
    assert fbd.apply_data_source(argparse.Namespace(data_source=None)) == "alpaca"
    assert "training data: alpaca (2 excluded)" in capsys.readouterr().out
    assert fbd.apply_data_source(argparse.Namespace(data_source="yfinance")) == "yfinance"
    assert "training data: yfinance (0 excluded)" in capsys.readouterr().out
