import importlib.util
import json
import pathlib

import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location(
    "ppr", pathlib.Path("scripts/reports/provider_parity_report.py"))
ppr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ppr)

_DAYS = pd.DatetimeIndex(["2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"])


def _frame(closes, volumes=None, index=_DAYS):
    return pd.DataFrame({"Close": closes, "Volume": volumes or [100.0] * len(closes)},
                        index=index)


def test_identical_sources_are_zero_bps():
    f = _frame([100.0, 101.0, 102.0, 103.0])
    out = ppr.compare_daily({"AAPL": f}, {"AAPL": f.copy()})
    assert out["symbols"] == 1
    assert out["close_bps_median"] == 0 and out["close_bps_p95"] == 0
    assert out["close_bps_max"] == 0
    assert out["action_mismatches"] == []
    assert out["missing_alpaca"] == 0 and out["missing_yf"] == 0
    assert out["volume_ratio_median"] == pytest.approx(1.0)


def test_one_day_off_by_one_percent_is_an_action_mismatch():
    yf = _frame([100.0, 100.0, 100.0, 100.0])
    alp = _frame([100.0, 100.0, 101.0, 100.0])
    out = ppr.compare_daily({"AAPL": alp}, {"AAPL": yf})
    assert out["close_bps_max"] == pytest.approx(100)
    assert out["action_mismatches"] == [
        {"symbol": "AAPL", "date": "2026-09-24", "bps": pytest.approx(100)}]


def test_dates_in_only_one_source_are_counted_missing():
    yf = _frame([100.0] * 4)
    alp = _frame([100.0] * 3, index=_DAYS[:3])
    out = ppr.compare_daily({"AAPL": alp, "MSFT": _frame([1.0] * 4)}, {"AAPL": yf})
    assert out["missing_alpaca"] == 1          # AAPL 2026-09-25
    assert out["missing_yf"] == 4              # every MSFT date
    assert out["symbols"] == 2


def test_no_overlap_gives_null_stats():
    out = ppr.compare_daily({}, {})
    assert out["symbols"] == 0
    assert out["close_bps_median"] is None and out["volume_ratio_median"] is None


def test_main_runs_end_to_end_on_fakes(monkeypatch, tmp_path, capsys):
    from swingbot import config
    from swingbot.core.marketdata import data
    from swingbot.core.marketdata.providers import alpaca_provider

    class FakeProvider:
        def __init__(self, *a):
            pass

        def daily_bars(self, symbols, period):
            return {s: _frame([100.0, 100.0, 101.0, 100.0]) for s in symbols}

        def latest_prices(self, symbols, max_age):
            return {s: 101.0 for s in symbols}

    monkeypatch.setattr(config, "ALPACA_API_KEY_ID", "k")
    monkeypatch.setattr(config, "ALPACA_API_SECRET_KEY", "s")
    monkeypatch.setattr(alpaca_provider, "AlpacaProvider", FakeProvider)
    monkeypatch.setattr(data, "_yf_daily_batch",
                        lambda symbols, period: {s: _frame([100.0] * 4) for s in symbols})
    monkeypatch.setattr(data, "_yf_batch_prices", lambda symbols: {s: 100.0 for s in symbols})
    out = tmp_path / "parity.json"
    assert ppr.main(["--symbols", "AAPL,SAP.DE", "--json", str(out)]) == 0
    report = json.loads(out.read_text())
    assert report["daily"]["symbols"] == 1                 # SAP.DE is not eligible
    assert report["live_bps"] == {"AAPL": pytest.approx(100)}
    assert "fetched 1/1" in capsys.readouterr().out
