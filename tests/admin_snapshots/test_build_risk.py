"""v204: the risk snapshot records its inputs, flags stale bars and fails loudly."""
from datetime import datetime, timezone

import pytest

from swingbot.core.analytics import admin_snapshots as snaps
from swingbot.core.analytics import risk_metrics, risk_payload
from swingbot.core.edge import portfolio_state
from swingbot.core.marketdata import daily_readonly, fx
from swingbot.core.marketdata.daily_readonly import DailyCacheUnavailable, ReadOnlyBars
from tests.admin_snapshots.golden_book import (  # noqa: F401
    GOLDEN_NOW, _clear_login_limiter, admin_app, assert_matches_golden, client, golden_book)

NOW = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)
RESULT = risk_payload.RiskMetrics(
    metrics={"benchmark_symbol": "SPY"}, correlation={"labels": [], "values": []},
    availability={}, bars_as_of={}, missing_bars={})
STATE = {"open_trades": [
    {"id": 7, "ticker": "AAPL", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0, "shares": 10.0},
    {"id": 9, "ticker": "SAP.DE", "direction": "bullish", "entry": 50.0, "stop_loss": 45.0, "shares": 4.0},
    {"id": 11, "ticker": "XAUUSD", "direction": "bullish", "entry": 2400.0, "stop_loss": 2350.0, "shares": 1.0}],
    "balance": 10_000.0, "open_heat": 0.7, "heat_cap": 6.0, "sector_heat": {}, "unmapped_count": 3,
    "clusters": [], "throttle_mult": 1.0, "paused": False, "availability": {}}


def bars(per):
    fps = {s: {"path": f"/m/{s}.csv", "mtime": 1.0, "last_bar": d, "rows": 500} for s, d in per.items()}
    return ReadOnlyBars(frames={s: object() for s in per},
                        missing={"SAP.DE": "no_file", "XAUUSD": "spot_metal"}, fingerprints=fps)


@pytest.fixture
def world(monkeypatch):
    calls = {}

    def collect(*, bars_reader=None):
        calls["collect_reader"] = bars_reader
        bars_reader(["AAPL", "SAP.DE", "XAUUSD"])
        return dict(STATE)

    def metrics(reader, *, strict=False):
        calls["strict"] = strict
        reader(["AAPL", "SPY"])
        return RESULT
    monkeypatch.setattr(portfolio_state, "collect_portfolio_state", collect)
    monkeypatch.setattr(risk_payload, "metrics_and_correlation", metrics)
    monkeypatch.setattr(fx, "account_currency_code", lambda: "USD")
    monkeypatch.setattr(fx, "quote_currency_code",
                        lambda t, **k: {"AAPL": "USD", "XAUUSD": "USD"}.get(t))
    monkeypatch.setattr(snaps, "_now", lambda: NOW)
    monkeypatch.setattr(snaps, "_code_version", lambda: "2.16.0")
    return calls


def test_risk_builder_records_inputs_and_flags_stale_bars(world, monkeypatch):
    monkeypatch.setattr(daily_readonly, "read_cached_daily",
                        lambda syms, **k: bars({"AAPL": "2026-09-15", "SPY": "2026-09-14"}))
    res = snaps.build_risk()
    assert res.doc == risk_payload.market_body(STATE, RESULT)
    assert world["strict"] is True
    assert isinstance(world["collect_reader"], daily_readonly.RecordingReader)
    assert res.inputs["missing"] == {"quotes": [], "fx": ["SAP.DE"],
                                     "bars": {"SAP.DE": "no_file", "XAUUSD": "spot_metal"}}
    assert res.inputs["quotes"] == {} and res.inputs["oldest_quote_as_of"] is None
    assert res.inputs["trade_ids"] == [7, 9, 11] and res.inputs["ledger"] is None
    assert res.stale_inputs is True                         # SPY is a session behind


def test_current_bars_are_not_stale_and_spot_metal_is_only_missing(world, monkeypatch):
    monkeypatch.setattr(daily_readonly, "read_cached_daily",
                        lambda syms, **k: bars({"AAPL": "2026-09-15", "SPY": "2026-09-15"}))
    res = snaps.build_risk()
    assert res.stale_inputs is False and res.inputs["missing"]["bars"]["XAUUSD"] == "spot_metal"


def test_non_usd_position_records_its_rate_and_pair_date(world, monkeypatch):
    monkeypatch.setattr(fx, "quote_currency_code", lambda t, **k: "EUR" if t == "SAP.DE" else "USD")
    monkeypatch.setattr(fx, "fx_rate", lambda src, dst, on, **k: 1.08 if k == {"refresh": False} else None)
    pair = ReadOnlyBars({}, {}, {"EURUSD=X": {"path": "p", "mtime": 1.0, "last_bar": "2026-09-15", "rows": 9}})
    monkeypatch.setattr(daily_readonly, "read_cached_daily", lambda syms, **k: (
        pair if list(syms) == ["EURUSD=X"] else bars({"AAPL": "2026-09-15", "SPY": "2026-09-15"})))
    res = snaps.build_risk()
    assert res.inputs["fx"] == {"EUR": {"rate": 1.08, "as_of": "2026-09-15"}}
    assert res.inputs["missing"]["fx"] == []


def _pair_or_bars(pair_symbol):
    pair = ReadOnlyBars({}, {}, {pair_symbol: {"path": "p", "mtime": 1.0, "last_bar": "2026-09-15", "rows": 9}})
    return lambda syms, **k: (
        pair if list(syms) == [pair_symbol] else bars({"AAPL": "2026-09-15", "SPY": "2026-09-15"}))


def test_unknown_rate_is_recorded_and_its_ticker_is_missing(world, monkeypatch):
    monkeypatch.setattr(fx, "quote_currency_code", lambda t, **k: "EUR" if t == "SAP.DE" else "USD")
    monkeypatch.setattr(fx, "fx_rate", lambda src, dst, on, **k: None)
    monkeypatch.setattr(daily_readonly, "read_cached_daily", _pair_or_bars("EURUSD=X"))
    res = snaps.build_risk()
    assert res.inputs["fx"] == {"EUR": {"rate": None, "as_of": "2026-09-15"}}
    assert res.inputs["missing"]["fx"] == ["SAP.DE"]


def test_minor_unit_ticker_records_the_major_unit_rate(world, monkeypatch):
    asked = []

    def rate(src, dst, on, **k):
        asked.append(src)
        return {"GBP": 1.27, "GBp": 0.0127}[src]
    monkeypatch.setattr(fx, "quote_currency_code",
                        lambda t, **k: {"AAPL": "GBP", "SAP.DE": "GBp"}.get(t, "USD"))
    monkeypatch.setattr(fx, "fx_rate", rate)
    monkeypatch.setattr(daily_readonly, "read_cached_daily", _pair_or_bars("GBPUSD=X"))
    res = snaps.build_risk()
    assert res.inputs["fx"] == {"GBP": {"rate": 1.27, "as_of": "2026-09-15"}}
    assert res.inputs["missing"]["fx"] == [] and set(asked) == {"GBP"}


def test_missing_bar_cache_fails_the_risk_snapshot(world, monkeypatch):
    def unmounted(syms, **k):
        raise DailyCacheUnavailable("daily bar cache /app/market_data is not mounted")
    monkeypatch.setattr(daily_readonly, "read_cached_daily", unmounted)
    with pytest.raises(DailyCacheUnavailable, match="not mounted"):
        snaps.build_risk()


def test_min_rows_is_the_risk_metric_window():
    assert snaps.RISK_MIN_ROWS == risk_metrics._MIN_BARS + 1


def test_risk_snapshot_doc_matches_the_golden_payload(golden_book, monkeypatch):
    monkeypatch.setattr(risk_payload, "_now", lambda: GOLDEN_NOW)
    monkeypatch.setattr(snaps, "_now", lambda: GOLDEN_NOW)
    res = snaps.build_risk()
    assert set(res.doc) == set(risk_payload.empty_body())
    assert_matches_golden("risk", res.doc)       # normalise drops availability.killswitch
    assert golden_book.network_calls == []
    assert res.inputs["fx"] == {"EUR": {"rate": 1.1, "as_of": None}}   # no EURUSD=X file in the book
    assert res.stale_inputs is False                                   # bars end 2026-10-28
