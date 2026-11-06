"""v204: the risk chain lives in core; GET /risk and the snapshot call the same functions."""
import pandas as pd
import pytest

import swingbot.admin.app  # noqa: F401 -- initialise the API package first, as admin fixtures do
from swingbot import config
from swingbot.admin.api_v1 import risk
from swingbot.core.analytics import risk_payload
from swingbot.core.marketdata import fx
from swingbot.core.marketdata.daily_readonly import DailyCacheUnavailable, ReadOnlyBars
from tests.admin_snapshots.golden_book import (  # noqa: F401
    GOLDEN_NOW, _clear_login_limiter, admin_app, assert_matches_golden, client, golden_book)


def frame(days=60, flat=False):
    close = [100.0] * days if flat else [100.0 + i * (1 + (i % 3)) for i in range(days)]
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                         "Volume": [1000.0] * days},
                        index=pd.bdate_range("2026-07-01", periods=days))


def trade(ticker, tid, direction="bullish"):
    return {"id": tid, "ticker": ticker, "direction": direction, "entry": 100.0,
            "stop_loss": 95.0, "shares": 10.0, "status": "open", "strategy": "RSI"}


@pytest.fixture
def seams(monkeypatch):
    monkeypatch.setattr(fx, "account_currency_code", lambda: "USD")
    monkeypatch.setattr(fx, "quote_currency_code", lambda t, **k: "USD")
    monkeypatch.setattr(fx, "fx_rate", lambda *a, **k: 1.0)
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(risk_payload, "_now", lambda: GOLDEN_NOW)
    monkeypatch.setattr(risk_payload, "_closed_history", lambda: [])
    monkeypatch.setattr(risk_payload, "_open_trades",
                        lambda: [trade("AAPL", 1), trade("MSFT", 2)])


def test_off_path_risk_matches_the_golden_payload(golden_book, monkeypatch):
    monkeypatch.setattr(risk_payload, "_now", lambda: GOLDEN_NOW)
    risk._invalidate_cache()
    assert_matches_golden("risk", golden_book.client.get("/api/v1/risk").get_json())
    assert golden_book.network_calls == []


def test_metrics_record_bars_as_of_and_missing_symbols(seams):
    result = risk_payload.metrics_and_correlation(lambda syms: {"AAPL": frame(), "SPY": frame()})
    assert result.bars_as_of == {"AAPL": "2026-09-22", "SPY": "2026-09-22"}
    assert result.missing_bars == {"MSFT": "no_bars"}
    assert result.availability["distribution_metrics"]["reason"] == "incomplete_bars"
    assert result.metrics["benchmark_symbol"] == "SPY"


def test_missing_reasons_come_from_a_recording_reader(seams):
    class Reader:
        seen = ReadOnlyBars(frames={}, missing={"MSFT": "short:12/21"}, fingerprints={})

        def __call__(self, syms):
            return {"AAPL": frame(), "SPY": frame()}
    assert risk_payload.metrics_and_correlation(Reader()).missing_bars == {"MSFT": "short:12/21"}


def test_complete_bars_give_values_and_a_full_matrix(seams):
    result = risk_payload.metrics_and_correlation(lambda syms: {s: frame() for s in syms})
    assert result.missing_bars == {}
    assert result.metrics["annualised_vol"]["value"] is not None
    assert result.correlation["labels"] == ["AAPL", "MSFT"]
    assert result.correlation["values"][0][1] is not None


def test_no_overlapping_bars_gives_null_correlation_with_a_reason(seams):
    short = frame(days=5)
    result = risk_payload.metrics_and_correlation(
        lambda syms: {"AAPL": short, "MSFT": short, "SPY": frame()})
    assert result.correlation == {"labels": ["AAPL", "MSFT"], "values": None,
                                  "reason": "insufficient_overlap"}


def test_flat_benchmark_gives_null_beta_with_a_reason(seams):
    result = risk_payload.metrics_and_correlation(
        lambda syms: {**{s: frame() for s in syms}, "SPY": frame(flat=True)})
    assert result.metrics["beta_spy"]["value"] is None
    assert result.availability["beta_spy"] == "zero_variance"


def test_unavailable_bar_cache_is_raised_strict_or_not(seams):
    def reader(syms):
        raise DailyCacheUnavailable("daily bar cache /x is not mounted")
    for strict in (False, True):
        with pytest.raises(DailyCacheUnavailable):
            risk_payload.metrics_and_correlation(reader, strict=strict)


def test_other_reader_errors_degrade_as_today_and_raise_when_strict(seams):
    def reader(syms):
        raise RuntimeError("provider down")
    result = risk_payload.metrics_and_correlation(reader)
    assert result.availability["distribution_metrics"]["reason"] == "market_data_unavailable"
    with pytest.raises(RuntimeError, match="provider down"):
        risk_payload.metrics_and_correlation(reader, strict=True)


def test_correlation_errors_raise_only_when_strict(seams, monkeypatch):
    from swingbot.core.analytics import risk_metrics as rm

    def broken(symbols, bars):
        raise ValueError("bad matrix")
    monkeypatch.setattr(rm, "correlation_matrix", broken)
    bars = lambda syms: {s: frame() for s in syms}  # noqa: E731
    assert risk_payload.metrics_and_correlation(bars).correlation["values"] == []
    with pytest.raises(ValueError, match="bad matrix"):
        risk_payload.metrics_and_correlation(bars, strict=True)


STATE = {"open_trades": [trade("AAPL", 1)], "balance": 10_000.0, "open_heat": 0.5,
         "heat_cap": 6.0, "sector_heat": {"Tech": 0.5}, "unmapped_count": 0,
         "clusters": [], "throttle_mult": 1.0, "paused": False, "availability": {}}
BODY_KEYS = {"heat", "availability", "positions", "sector_heat", "unmapped_count",
             "clusters", "throttle", "metrics", "correlation"}


def test_market_body_carries_no_live_control_fields(seams):
    result = risk_payload.metrics_and_correlation(lambda syms: {s: frame() for s in syms})
    body = risk_payload.market_body(STATE, result)
    assert set(body) == BODY_KEYS and "killswitch" not in body["availability"]
    assert body["heat"]["utilisation_pct"] == round(0.5 / 6.0 * 100.0, 1)


def test_empty_body_has_every_key_and_no_figures():
    body = risk_payload.empty_body()
    assert set(body) == BODY_KEYS and body["positions"] is None
    assert body["correlation"] == {"labels": [], "values": []}
    assert body["metrics"]["var_95"] == {"value": None, "n": 0}


def test_compat_names_still_answer_from_risk_py():
    assert risk._closed_metrics is risk_payload._closed_metrics
    assert risk._DISTRIBUTION_KEYS == risk_payload._DISTRIBUTION_KEYS
    assert callable(risk._risk_metrics) and callable(risk._risk_metrics_and_correlation)


def test_core_risk_modules_never_import_admin():
    import inspect
    from swingbot.core.analytics import risk_read_model
    for module in (risk_payload, risk_read_model):
        assert "swingbot.admin" not in inspect.getsource(module)
