"""v162 AH13: an explicit --cache-dir is a yfinance-shaped directory and pins
yfinance; without one the measure_* scripts and the fold harness read the
training-data switch. Pools hand the selection to their workers."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_wf
from swingbot.core.marketdata import training_data
from swingbot.core.marketdata.history_store import MissingStoreError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import cache_dir_source as cds  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_v162",
                                                  ROOT / "scripts" / "backtest" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _fresh_switch(monkeypatch):
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    training_data.reset()
    yield
    training_data.reset()


def _frame(n=30, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    idx = pd.DatetimeIndex(pd.bdate_range("2020-01-02", periods=n), name="Date")
    return pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1, "Close": close,
                         "Volume": np.full(n, 1_000_000.0)}, index=idx)


def _write_store(root, frames, statuses=None):
    statuses = statuses or {}
    folder = root / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    tickers = {}
    for ticker, frame in frames.items():
        frame.to_csv(folder / f"{ticker}.csv", index_label="Date", date_format="%Y-%m-%d")
        tickers[ticker] = {"status": statuses.get(ticker, "ok"), "start": "2016-01-01",
                           "first": str(frame.index[0].date()), "last": str(frame.index[-1].date()),
                           "rows": len(frame), "sha256": "0" * 64,
                           "fetched_at": "2026-10-18T06:12:40Z",
                           "identity": {"status": "ok", "median_ratio": 1.0,
                                        "overlap": len(frame), "dropped_before": None}}
    (folder / "_manifest.json").write_text(json.dumps(
        {"timeframe": "daily", "feed": "sip", "adjustment": "all",
         "updated_at": "2026-10-18T06:31:02Z", "hash": "f" * 64, "tickers": tickers}),
        encoding="utf-8")


@pytest.fixture
def alpaca_store(store_root):
    _write_store(store_root, {"AAA": _frame(), "BBB": _frame(seed=8), "SPY": _frame(seed=9)},
                 {"BBB": "flagged: price-mismatch"})
    return store_root


@pytest.fixture
def csv_dir(tmp_path):
    folder = tmp_path / "yf"
    folder.mkdir()
    for ticker, seed in (("AAA", 1), ("CCC", 2), ("SPY", 3)):
        _frame(seed=seed).to_csv(folder / f"{ticker}.csv", index_label="Date")
    return folder


def _ns(**kw):
    base = {"cache_dir": None, "data_source": None}
    base.update(kw)
    return argparse.Namespace(**base)


# --- the rule -------------------------------------------------------------------------

def test_an_explicit_cache_dir_pins_yfinance(csv_dir, store_root):
    assert cds.resolve(_ns(cache_dir=str(csv_dir))) == csv_dir
    assert training_data.active() == "yfinance"


def test_cache_dir_with_alpaca_is_an_error(csv_dir):
    with pytest.raises(SystemExit, match="yfinance-shaped"):
        cds.resolve(_ns(cache_dir=str(csv_dir), data_source="alpaca"))


def test_no_cache_dir_follows_the_switch(alpaca_store):
    assert cds.resolve(_ns()) is None
    assert training_data.active() == "alpaca"


def test_no_cache_dir_and_no_store_is_an_error(store_root):
    with pytest.raises(MissingStoreError):
        cds.resolve(_ns(data_source="alpaca"))


# --- readers --------------------------------------------------------------------------

def test_readers_on_a_directory_match_the_old_glob(csv_dir):
    assert cds.listing(csv_dir) == ["AAA", "CCC", "SPY"]
    assert sorted(cds.load_all(csv_dir, limit=2)) == ["AAA", "CCC"]
    assert cds.cache_files(csv_dir) == ["AAA.csv", "CCC.csv", "SPY.csv"]
    assert cds.load_frame(csv_dir, "AAA").index.name == "Date"
    assert cds.load_frame(csv_dir, "ZZZ") is None
    assert cds.describe(csv_dir) == str(csv_dir)


def test_readers_without_a_directory_use_the_training_data(alpaca_store):
    training_data.select("alpaca")
    assert cds.listing(None) == ["AAA", "SPY"]
    assert sorted(cds.load_all(None)) == ["AAA", "SPY"]
    assert cds.cache_files(None) == ["AAA.csv", "SPY.csv"]
    assert cds.load_frame(None, "BBB") is None
    assert len(cds.load_frame(None, "AAA")) == 30
    assert cds.describe(None) == "the alpaca training data"


def test_pool_kwargs_carry_the_selection(alpaca_store):
    training_data.select("alpaca")
    assert cds.pool_kwargs() == {"initializer": training_data.select, "initargs": ("alpaca",)}


# --- backtest_wf._frame_for ------------------------------------------------------------

def test_frame_for_reads_the_training_data(alpaca_store):
    training_data.select("alpaca")
    assert len(backtest_wf._frame_for("AAA")) == 30
    assert backtest_wf._frame_for("BBB") is None


def test_frame_for_without_a_store_raises(store_root):
    with pytest.raises(MissingStoreError):
        backtest_wf._frame_for("AAA")


# --- every script applies the rule before reading a bar --------------------------------

SCRIPTS = [
    ("measure_trend_signal_overlap", lambda: ["--train"]),
    ("measure_adjacent_gate_effect", lambda: ["--train"]),
    ("measure_dcb_veto", lambda: ["--train"]),
    ("measure_rs_gate_effect", lambda: ["--train"]),
    ("measure_armed_entries", lambda: ["replay", "--run", "run1", "--workers", "1"]),
    ("measure_structure_arm", lambda: ["replay", "--run", "run1", "--workers", "1"]),
    ("measure_earnings_blackout", lambda: ["replay", "--run", "run1", "--workers", "1"]),
]


@pytest.mark.parametrize("name, argv", SCRIPTS, ids=[s[0] for s in SCRIPTS])
def test_alpaca_without_a_store_stops_first(name, argv, store_root, tmp_path):
    module = _load(name)
    extra = ["--out-root", str(tmp_path / "out")] if argv()[0] == "replay" else []
    with pytest.raises(MissingStoreError):
        module.main([*argv(), *extra, "--data-source", "alpaca"])


@pytest.mark.parametrize("name, argv", SCRIPTS, ids=[s[0] for s in SCRIPTS])
def test_cache_dir_with_alpaca_is_refused(name, argv, csv_dir, tmp_path):
    module = _load(name)
    extra = ["--out-root", str(tmp_path / "out")] if argv()[0] == "replay" else []
    with pytest.raises(SystemExit, match="yfinance-shaped"):
        module.main([*argv(), *extra, "--cache-dir", str(csv_dir), "--data-source", "alpaca"])


def test_validate_component_and_wf_components_take_the_flag(store_root):
    for name, argv in (("validate_component", ["--stage", "selection", "--title", "t",
                                               "--window", "w"]),
                       ("wf_components", [])):
        with pytest.raises(MissingStoreError):
            _load(name).main([*argv, "--data-source", "alpaca"])


def test_earnings_calendar_comes_from_the_training_spy(alpaca_store):
    training_data.select("alpaca")
    blackout = _load("measure_earnings_blackout")
    assert len(blackout.load_calendar(None)) == 30


def test_armed_run_meta_lists_training_files(alpaca_store):
    training_data.select("alpaca")
    armed = _load("measure_armed_entries")
    meta = armed.run_meta(None, ("2020-01-01", "2023-12-31"), ["4w"])
    assert meta["cache_files"] == ["AAA.csv", "SPY.csv"]
