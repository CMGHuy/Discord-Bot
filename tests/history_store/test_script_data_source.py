"""v162 AH12: tune_strategy and every load_cached/glob script read through the
training-data switch. They take --data-source, refuse to start without the
Alpaca store, list tickers from the selected source, hand pool workers the
selection, and stamp provenance on what they write."""
import concurrent.futures
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import backtest_cache, training_data
from swingbot.core.marketdata.history_store import MissingStoreError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))   # sibling imports (measure_arms, ...)


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tune = _load("scripts/backtest/tune_strategy.py", "tune_v162")
rcv = _load("scripts/backtest/run_confluence_validation.py", "rcv_v162")
parity = _load("scripts/reports/parity_exits.py", "parity_v162")
ma = _load("scripts/backtest/measure_arms.py", "ma_v162")
density = _load("scripts/backtest/measure_alert_density.py", "density_v162")
mae = _load("scripts/backtest/measure_acceptance_exits.py", "mae_v162")
lift = _load("scripts/backtest/measure_factor_lift.py", "lift_v162")
fvg = _load("scripts/backtest/measure_fvg_bullish_diagnostic.py", "fvg_v162")
quarterly = _load("scripts/backtest/quarterly_revalidation.py", "quarterly_v162")
gates = _load("scripts/backtest/tune_confluence_gates.py", "gates_v162")
exits = _load("scripts/backtest/tune_exit_v2.py", "exits_v162")
regime = _load("scripts/data/fill_regime_allow.py", "regime_v162")


@pytest.fixture(autouse=True)
def _fresh_switch(monkeypatch):
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    training_data.reset()
    yield
    training_data.reset()


def _frame(n=40, seed=7):
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
def yf_cache(tmp_path, monkeypatch):
    folder = tmp_path / "backtest_cache"
    folder.mkdir()
    for ticker, seed in (("AAA", 1), ("BBB", 2), ("SPY", 3)):
        _frame(seed=seed).to_csv(folder / f"{ticker}.csv", index_label="Date")
    monkeypatch.setattr(backtest_cache, "CACHE_DIR", folder)
    return folder


# --- every wired script refuses to start without the store ----------------------------

def _first(values):
    return str(sorted(values)[0])


REFUSALS = [
    (tune, lambda: ["--strategy", "RSI"]),
    (parity, lambda: []),
    (ma, lambda: ["--knob", "x=1", "--stage", "pilot", "--out", "o.json"]),
    (density, lambda: ["--train"]),
    (mae, lambda: ["--arm", _first(mae.CELLS), "--stage", _first(mae._STAGES)]),
    (lift, lambda: ["--train"]),
    (fvg, lambda: []),
    (gates, lambda: []),
    (exits, lambda: []),
    (regime, lambda: []),
]


@pytest.mark.parametrize("module, argv", REFUSALS, ids=lambda v: getattr(v, "__name__", ""))
def test_alpaca_without_a_store_stops_before_any_work(module, argv, store_root):
    with pytest.raises((SystemExit, MissingStoreError)) as exc:
        module.main([*argv(), "--data-source", "alpaca"])
    assert "_manifest.json" in str(exc.value)


def test_tune_strategy_error_is_a_clean_exit_message(store_root):
    with pytest.raises(SystemExit) as exc:
        tune.main(["--strategy", "RSI", "--data-source", "alpaca"])
    assert str(exc.value).startswith("error: ")


# --- tune_strategy payload ------------------------------------------------------------

def test_tune_payload_and_sidecar_name_the_source(alpaca_store, tmp_path, monkeypatch):
    stats = {"n_eval": 31, "win_rate": 55.0, "expectancy_r": 0.1, "excluded_share": 0.1}
    monkeypatch.setattr(tune, "run_config", lambda *a, **k: dict(stats))
    monkeypatch.setattr(tune, "load_watchlist", lambda: ["AAA", "BBB"])
    out = tmp_path / "grid.json"
    tune.main(["--strategy", "RSI", "--grid", "rsi_dip=45", "--data-source", "alpaca",
               "--json", str(out)])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["data_source"] == "alpaca"
    assert payload["provenance"]["excluded"]["BBB"] == "flagged: price-mismatch"
    assert set(payload) == {"strategy", "gate", "grid", "best", "data_source", "provenance"}
    side = json.loads(training_data.provenance_path(out).read_text(encoding="utf-8"))
    assert side["data_source"] == "alpaca"


# --- ticker listings come from the selected source -------------------------------------

def test_measure_arms_listing_follows_the_source(alpaca_store, yf_cache, monkeypatch):
    training_data.select("yfinance")
    assert ma.cache_listing() == ["AAA", "BBB", "SPY"]
    training_data.select("alpaca")
    assert ma.cache_listing() == ["AAA", "SPY"]                 # BBB is flagged
    monkeypatch.setenv(ma.UNIVERSE_ENV, "cache")
    assert ma.cached_universe() == ["AAA", "SPY"]


def test_measure_arms_watchlist_universe_drops_excluded_tickers(alpaca_store, yf_cache, monkeypatch):
    """The review note: the default (watchlist) universe and population_symbols
    must also honour store exclusions, not just the 'cache' listing."""
    import run_backtest_range
    monkeypatch.delenv(ma.UNIVERSE_ENV, raising=False)
    monkeypatch.setattr(run_backtest_range, "_tickers_for_run", lambda _t: ["AAA", "BBB", "SPY"])
    training_data.select("alpaca")
    assert ma.cached_universe() == ["AAA", "SPY"]


def test_acceptance_exits_universe_follows_the_source(alpaca_store):
    training_data.select("alpaca")
    assert mae.cache_universe() == ["AAA", "SPY"]


def test_factor_lift_and_grid_frames_follow_the_source(alpaca_store, yf_cache):
    training_data.select("alpaca")
    assert sorted(lift._training_frames()) == ["AAA", "SPY"]
    assert sorted(exits._frames()) == ["AAA", "SPY"]
    training_data.select("yfinance")
    frames, total = gates._sampled_frames()
    assert (sorted(frames), total) == (["AAA"], 3)             # every 3rd of AAA, BBB, SPY


def test_quarterly_sweep_visits_only_trainable_tickers(alpaca_store, monkeypatch):
    from swingbot.core.marketdata import universe
    seen = []
    monkeypatch.setattr(universe, "data_quality_issues",
                        lambda df, ticker: seen.append(ticker) or (["gap"] if ticker == "AAA" else []))
    training_data.select("alpaca")
    assert quarterly.data_quality_sweep() == {"AAA": ["gap"]}
    assert seen == ["AAA", "SPY"]


def test_fvg_calendar_comes_from_the_training_spy(alpaca_store):
    training_data.select("alpaca")
    assert len(fvg._session_calendar()) == 40


# --- pool workers inherit the selection ----------------------------------------------

class _FakePool:
    seen: dict = {}

    def __init__(self, max_workers=None, initializer=None, initargs=()):
        _FakePool.seen = {"initializer": initializer, "initargs": initargs}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args):
        future = concurrent.futures.Future()
        future.set_result(fn(*args))
        return future


def test_measure_arms_pool_gets_the_selection(yf_cache, monkeypatch):
    training_data.select("yfinance")
    monkeypatch.setattr(ma, "ProcessPoolExecutor", _FakePool)
    monkeypatch.setattr(ma, "_worker", lambda task: (task[0], []))
    ma._run_arm_all("x", ["AAA", "BBB"], [], [], None, {}, 2, None, [0], 2)
    assert _FakePool.seen == {"initializer": training_data.select, "initargs": ("yfinance",)}


def test_acceptance_exits_pool_gets_the_selection(yf_cache, tmp_path, monkeypatch):
    training_data.select("yfinance")
    monkeypatch.setattr(mae, "ProcessPoolExecutor", _FakePool)
    monkeypatch.setattr(mae, "_worker", lambda task: (task[1], []))
    monkeypatch.setattr(mae, "_resolve_replay_workers", lambda workers: 2)
    monkeypatch.setattr(mae, "LOG_DIR", tmp_path)
    mae.build_rows(_first(mae.CELLS), ("2020-01-01", "2023-12-31"), [], workers=2)
    assert _FakePool.seen == {"initializer": training_data.select, "initargs": ("yfinance",)}


# --- the VALIDATION-only replay is pinned to yfinance --------------------------------

def test_confluence_validation_is_pinned_to_yfinance(store_root, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["rcv"])
    monkeypatch.setattr(rcv, "load_watchlist", lambda: [])
    monkeypatch.setattr(rcv, "CHUNK_DIR", tmp_path / "chunks")
    monkeypatch.setattr(rcv, "RESULTS_PATH", tmp_path / "rcv.json")
    rcv.main()                                   # no store, config says alpaca: still runs
    assert training_data.active() == "yfinance"
    side = json.loads(training_data.provenance_path(tmp_path / "rcv.json").read_text(encoding="utf-8"))
    assert side["data_source"] == "yfinance"


def test_acceptance_exits_write_leaves_a_provenance_sidecar(yf_cache, tmp_path):
    target = tmp_path / "out.json"
    training_data.select("yfinance")
    mae._write(target, {"ok": 1})
    assert training_data.provenance_path(target).exists()
