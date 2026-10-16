"""v162 AH11: run_backtest_range reads one training-data source, stops when the
store is absent, writes a provenance sidecar next to every result file, and
keys registry rows by data_source so yfinance and Alpaca rows sit side by side."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import training_data

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "rbr_v162", ROOT / "scripts" / "backtest" / "run_backtest_range.py")
rbr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rbr)


@pytest.fixture(autouse=True)
def _fresh_switch(monkeypatch):
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    training_data.reset()
    yield
    training_data.reset()


def _frame(n=600, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    open_ = np.r_[close[0], close[:-1]]
    idx = pd.DatetimeIndex(pd.bdate_range("2018-01-02", periods=n), name="Date")
    return pd.DataFrame({"Open": open_, "High": np.maximum(open_, close) + 0.5,
                         "Low": np.minimum(open_, close) - 0.5, "Close": close,
                         "Volume": np.full(n, 2_000_000.0)}, index=idx)


def _write_store(root, frames, statuses=None):
    """Hand-built daily store in the index's manifest shape."""
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


def _row(source="strategy", strategy="RSI", horizon=None, **extra):
    row = {"source": source, "strategy": strategy, "horizon": horizon, "status": "WEAK",
           "n": 40, "win_rate": 55.0, "expectancy_r": 0.1, "window": "w", "run_date": "d"}
    row.update(extra)
    return row


# --- registry key ------------------------------------------------------------------

def test_registry_key_treats_a_missing_or_null_source_as_yfinance():
    assert rbr.registry_key(_row()) == ("strategy", "RSI", None, "yfinance")
    assert rbr.registry_key(_row(data_source=None))[3] == "yfinance"
    assert rbr.registry_key(_row(data_source="alpaca"))[3] == "alpaca"


def test_build_registry_records_stamps_the_data_source():
    summaries = [{"strategy": "RSI", "n": 100, "win_rate": 60.0, "expectancy_r": 0.2}]
    default = rbr.build_registry_records(summaries, source="strategy", window="w", run_date="d")
    alpaca = rbr.build_registry_records(summaries, source="strategy", window="w", run_date="d",
                                        data_source="alpaca")
    assert default[0]["data_source"] == "yfinance"
    assert alpaca[0]["data_source"] == "alpaca"


def test_merge_keeps_both_populations_and_never_rewrites_an_old_row(tmp_path):
    path = tmp_path / "reg.json"
    old = _row(window="old")
    path.write_text(json.dumps([old]), encoding="utf-8")
    merged = rbr.merge_registry(path, [_row(window="alpaca", data_source="alpaca")])
    assert [r["window"] for r in merged] == ["old", "alpaca"]
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk[0] == old and "data_source" not in on_disk[0]


def test_merge_replaces_only_the_same_source(tmp_path):
    path = tmp_path / "reg.json"
    path.write_text(json.dumps([_row(window="old"), _row(window="a1", data_source="alpaca")]),
                    encoding="utf-8")
    merged = rbr.merge_registry(path, [_row(window="y2", data_source="yfinance")])
    assert sorted(r["window"] for r in merged) == ["a1", "y2"]


# --- provenance sidecar ------------------------------------------------------------

def test_replay_source_reads_the_sidecar_and_defaults_to_yfinance(tmp_path):
    out = tmp_path / "res.json"
    out.write_text("{}", encoding="utf-8")
    assert rbr._replay_data_source(str(out)) == "yfinance"
    training_data.provenance_path(out).write_text(json.dumps({"data_source": "alpaca"}),
                                                  encoding="utf-8")
    assert rbr._replay_data_source(str(out)) == "alpaca"


def test_write_provenance_is_a_noop_without_a_path_and_writes_the_sidecar(store_root, tmp_path):
    _write_store(store_root, {"AAA": _frame(30)})
    training_data.select("alpaca")
    rbr._write_provenance(None)
    assert not list(tmp_path.glob("*.provenance.json"))
    out = tmp_path / "res.json"
    rbr._write_provenance(str(out))
    side = json.loads(training_data.provenance_path(out).read_text(encoding="utf-8"))
    assert (side["data_source"], side["manifest_hash"]) == ("alpaca", "f" * 64)


def test_report_exclusions_prints_every_left_out_ticker(store_root, capsys):
    _write_store(store_root, {"AAA": _frame(30), "BBB": _frame(30)},
                 {"BBB": "flagged: price-mismatch"})
    training_data.select("alpaca")
    rbr._report_exclusions()
    assert "excluded BBB: flagged: price-mismatch" in capsys.readouterr().out


def test_sector_etfs_missing_from_the_store_are_never_loaded(store_root, monkeypatch):
    from swingbot.core.backtesting import asof_context
    from swingbot.core.marketdata import universe
    _write_store(store_root, {"SPY": _frame(30), "XLK": _frame(30), "AAA": _frame(30)})
    training_data.select("alpaca")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(rbr, "_SPY_CACHE", {})
    monkeypatch.setattr(universe, "sector_map",
                        lambda name: {"XLK": "Technology", "XLE": "Energy"} if name == "etfs" else {})
    seen = {}
    monkeypatch.setattr(asof_context, "build_asof",
                        lambda frames, spy, **kw: seen.update(kw["sector_etf_frames"]) or {})
    rbr._build_asof_map(["AAA"], {"AAA": _frame(30)}, None)
    assert sorted(seen) == ["XLK"]                       # XLE is not in the store: skipped
    assert training_data.excluded() == {}                # no context-only noise


# --- source resolution -------------------------------------------------------------

def _ns(**over):
    base = {"from_json": None, "data_source": "alpaca", "validation": False}
    base.update(over)
    return argparse.Namespace(**base)


def test_alpaca_without_a_store_stops_naming_the_manifest(store_root):
    with pytest.raises(SystemExit) as exc:
        rbr._resolve_data_source(_ns())
    assert str(exc.value).startswith("error: ") and "_manifest.json" in str(exc.value)


def test_validation_prints_the_budget_notice(store_root, capsys):
    _write_store(store_root, {"AAA": _frame(30)})
    assert rbr._resolve_data_source(_ns(validation=True)) == "alpaca"
    assert rbr.VALIDATION_SOURCE_NOTICE in capsys.readouterr().out


def test_from_json_replays_the_sidecar_and_reads_no_store(tmp_path):
    out = tmp_path / "res.json"
    out.write_text("{}", encoding="utf-8")
    training_data.provenance_path(out).write_text(json.dumps({"data_source": "alpaca"}),
                                                  encoding="utf-8")
    assert rbr._resolve_data_source(_ns(from_json=str(out), data_source=None)) == "alpaca"
    with pytest.raises(SystemExit, match="cannot relabel"):
        rbr._resolve_data_source(_ns(from_json=str(out), data_source="yfinance"))


# --- main ----------------------------------------------------------------------------

def test_main_without_a_store_errors_before_any_backtest(store_root, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["rbr", "--train", "--data-source", "alpaca"])
    monkeypatch.setattr(rbr, "run_backtest", lambda *a, **k: pytest.fail("ran a backtest"))
    with pytest.raises(SystemExit) as exc:
        rbr.main()
    assert "_manifest.json" in str(exc.value)


def test_from_json_main_emits_rows_stamped_with_the_replayed_source(tmp_path, monkeypatch):
    out = tmp_path / "res.json"
    out.write_text(json.dumps({"RSI": {"n_eval": 40, "win_rate": 55.0, "expectancy_r": 0.2}}),
                   encoding="utf-8")
    training_data.provenance_path(out).write_text(json.dumps({"data_source": "alpaca"}),
                                                  encoding="utf-8")
    reg = tmp_path / "reg.json"
    monkeypatch.setattr(sys, "argv", ["rbr", "--train", "--from-json", str(out),
                                      "--emit-registry", str(reg), "--run-date", "2026-10-15"])
    rbr.main()
    rows = json.loads(reg.read_text(encoding="utf-8"))
    assert [(r["strategy"], r["data_source"]) for r in rows] == [("RSI", "alpaca")]


def test_train_run_writes_sidecars_naming_source_and_exclusions(store_root, tmp_path,
                                                                monkeypatch, capsys):
    _write_store(store_root, {"AAA": _frame(), "BBB": _frame(seed=8)},
                 {"BBB": "flagged: price-mismatch"})
    monkeypatch.chdir(tmp_path)                      # backtest_range_summary.txt lands here
    monkeypatch.setattr(rbr, "load_watchlist", lambda: ["AAA", "BBB"])
    out, trades = tmp_path / "res.json", tmp_path / "trades.jsonl"
    monkeypatch.setattr(sys, "argv", ["rbr", "--from", "2019-01-01", "--to", "2020-03-31",
                                      "--strategy", "RSI", "--context", "off",
                                      "--data-source", "alpaca", "--json", str(out),
                                      "--trades-jsonl", str(trades)])
    rbr.main()
    assert set(json.loads(out.read_text(encoding="utf-8"))) == {"RSI"}   # flat shape kept
    for path in (out, trades):
        side = json.loads(training_data.provenance_path(path).read_text(encoding="utf-8"))
        assert side["data_source"] == "alpaca"
        assert side["excluded"]["BBB"] == "flagged: price-mismatch"
    assert "excluded BBB: flagged: price-mismatch" in capsys.readouterr().out


# --- the spent VALIDATION shot: no second source buys a second look -------------------

_VAL = "2024-01-01..2025-12-31"


def _val_registry(tmp_path, existing):
    path = tmp_path / "reg.json"
    path.write_text(json.dumps(existing), encoding="utf-8")
    return path


def test_merge_refuses_an_alpaca_validation_row_when_the_yfinance_shot_is_spent(tmp_path):
    path = _val_registry(tmp_path, [_row(window=_VAL)])
    before = path.read_text(encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        rbr.merge_registry(path, [_row(window=_VAL, data_source="alpaca")])
    assert "error:" in str(exc.value) and "RSI" in str(exc.value)
    assert path.read_text(encoding="utf-8") == before            # nothing written


def test_merge_allows_an_alpaca_validation_row_when_no_yfinance_shot_is_spent(tmp_path):
    path = _val_registry(tmp_path, [_row(window="2020-01-01..2023-12-31")])
    merged = rbr.merge_registry(path, [_row(window=_VAL, data_source="alpaca")])
    assert len(merged) == 2
    path = _val_registry(tmp_path, [])
    assert len(rbr.merge_registry(path, [_row(window=_VAL, data_source="alpaca")])) == 1


def test_merge_allows_an_alpaca_train_row_beside_a_spent_yfinance_row(tmp_path):
    path = _val_registry(tmp_path, [_row(window=_VAL)])
    merged = rbr.merge_registry(path, [_row(window="2020-01-01..2023-12-31", data_source="alpaca")])
    assert len(merged) == 2


def test_merge_still_lets_yfinance_re_emit_its_own_validation_row(tmp_path):
    path = _val_registry(tmp_path, [_row(window=_VAL, n=1)])
    merged = rbr.merge_registry(path, [_row(window=_VAL, n=2)])
    assert [r["n"] for r in merged] == [2]
