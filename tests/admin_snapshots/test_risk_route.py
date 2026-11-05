"""v204: GET /risk serves its snapshot when the refresher is on, today's code when off."""
from datetime import datetime

import pytest

import swingbot.admin.app  # noqa: F401  (app first: api_v1 modules import under it)
from swingbot import config
from swingbot.admin.api_v1 import risk
from swingbot.core.analytics import admin_snapshots, risk_payload
from swingbot.core.edge import portfolio_state, throttle
from swingbot.core.marketdata import fx
from swingbot.core.marketdata.shared.admin_refresh import PRIORITY_MISSING, QUEUE_KIND_SNAPSHOT
from swingbot.core.planning import account as account_module
from tests.admin_market.conftest import (  # noqa: F401
    _clear_login_limiter, admin_app, auth, client, market, on_client, session_is)
from tests.admin_market.test_page_loads_never_fetch import network_forbidden  # noqa: F401
from tests.admin_snapshots.golden_book import (  # noqa: F401
    BAR_SYMBOLS, GOLDEN_NOW, assert_matches_golden, golden_book)
from tests.admin_snapshots.test_snapshot_door import snapshot_row, snapshot_store  # noqa: F401

NEW_KEYS = {"market_meta", "computed_at", "bars_meta", "fx_meta", "lower_bound", "account"}
POSITIONS = [{"trade_id": 7, "ticker": "AAPL"}, {"trade_id": 9, "ticker": "SAP.DE"},
             {"trade_id": 11, "ticker": "XAUUSD"}]


def inputs(*, fx_missing=(), bars_missing=None, per_symbol=None):
    per = per_symbol or {"AAPL": "2026-10-29", "SPY": "2026-10-28"}
    return {"computed_at": "2026-10-30T14:55:00+00:00", "oldest_quote_as_of": None, "quotes": {},
            "fx": {"EUR": {"rate": 1.08, "as_of": "2026-10-29"}}, "oldest_fx_as_of": "2026-10-29",
            "bars_as_of": {"per_symbol": per, "oldest": min(per.values()), "newest": max(per.values())},
            "missing": {"quotes": [], "fx": list(fx_missing),
                        "bars": bars_missing if bars_missing is not None else {"XAUUSD": "spot_metal"}}}


def doc(**extra):
    return {**risk_payload.empty_body(), "positions": POSITIONS, **extra}


@pytest.fixture
def heavy_forbidden(monkeypatch):
    called = []
    for module, name in ((portfolio_state, "collect_portfolio_state"), (admin_snapshots, "build_risk"),
                         (risk, "_risk_bars"), (risk, "_risk_metrics"), (risk, "_cached")):
        def boom(*a, _n=f"{module.__name__}.{name}", **k):
            called.append(_n)
            raise AssertionError(f"{_n} on the snapshot path")
        monkeypatch.setattr(module, name, boom)
    return called


def test_risk_on_serves_the_snapshot_with_a_live_killswitch(on_client, market, snapshot_store,
                                                            heavy_forbidden, network_forbidden,
                                                            monkeypatch):
    row = snapshot_row("risk", doc(heat={"open_pct": 1.2, "cap_pct": 6.0}), age_s=120, stale=True,
                       inputs=inputs())
    snapshot_store.rows["risk"] = row
    monkeypatch.setattr(throttle, "kill_state", lambda: {"on": True, "reason": "dd", "at": None})
    body = on_client.get("/api/v1/risk").get_json()
    assert body["heat"] == {"open_pct": 1.2, "cap_pct": 6.0} and body["killswitch"]["on"] is True
    assert body["availability"]["killswitch"]["state"] == "ok"
    assert body["bars_meta"] == {"per_symbol": {"AAPL": "2026-10-29", "SPY": "2026-10-28"},
                                 "oldest": "2026-10-28", "newest": "2026-10-29", "stale_inputs": True,
                                 "missing": [{"symbol": "XAUUSD", "reason": "spot_metal"}]}
    assert body["fx_meta"] == {"as_of": "2026-10-29", "missing": []}
    meta = body["market_meta"]
    assert (meta["source"], meta["stale_inputs"], meta["missing_count"]) == ("snapshot", True, 1)
    assert body["computed_at"] == row["computed_at"].isoformat()
    assert heavy_forbidden == [] and network_forbidden == []


def test_risk_on_with_no_row_returns_empty_body_refreshing(on_client, market, snapshot_store,
                                                          heavy_forbidden, network_forbidden):
    body = on_client.get("/api/v1/risk").get_json()
    assert set(risk_payload.empty_body()) | NEW_KEYS | {"killswitch", "scan_health"} == set(body)
    assert body["positions"] is None and body["computed_at"] is None and body["lower_bound"] == []
    assert body["market_meta"]["refreshing"] is True and body["bars_meta"]["per_symbol"] == {}
    assert market.queue.pending == {(QUEUE_KIND_SNAPSHOT, "risk"): PRIORITY_MISSING}
    assert heavy_forbidden == [] and network_forbidden == []


def test_risk_lower_bound_names_figures_missing_inputs(on_client, market, snapshot_store):
    metrics = {**risk_payload.empty_body()["metrics"],
               "max_drawdown_amount": {"value": -120.0, "n": 5, "fx_missing_count": 2,
                                       "invalid_date_count": 0}}
    snapshot_store.rows["risk"] = snapshot_row("risk", doc(metrics=metrics), age_s=60,
                                               inputs=inputs(fx_missing=["SAP.DE"]))
    body = on_client.get("/api/v1/risk").get_json()
    assert body["lower_bound"] == ["metrics.closed", "metrics.distribution", "correlation", "clusters"]
    assert body["market_meta"]["missing_count"] == 2 and body["market_meta"]["incomplete"] is True


@pytest.mark.parametrize("missing, expected", [
    ({"fx": ["SAP.DE"], "bars": {}}, ["metrics.distribution"]),
    ({"fx": [], "bars": {"XAUUSD": "spot_metal"}}, ["metrics.distribution", "correlation", "clusters"]),
    ({"fx": [], "bars": {"SPY": "short:9/21"}}, []),          # benchmark only: not a held position
    ({"fx": ["NVDA"], "bars": {}}, []),                        # not held
    ({"fx": [], "bars": {}}, []),
])
def test_lower_bound_counts_only_held_positions(missing, expected):
    assert risk._lower_bound(doc(), missing) == expected


def test_lower_bound_with_no_positions_is_empty():
    assert risk._lower_bound(risk_payload.empty_body(), {"fx": ["AAPL"], "bars": {"AAPL": "no_file"}}) == []


def test_risk_account_carries_balance_and_currency(on_client, market, snapshot_store, monkeypatch):
    monkeypatch.setattr(account_module, "load_account_config", lambda: {"balance": 12_500.0})
    monkeypatch.setattr(fx, "account_currency_code", lambda: "USD")
    assert on_client.get("/api/v1/risk").get_json()["account"] == {"balance": 12_500.0, "currency": "USD"}


@pytest.mark.parametrize("cfg", [{"base_balance": 9000.0}, {"balance": 0, "base_balance": 9000.0}])
def test_risk_account_balance_falls_back_to_base_balance(on_client, market, snapshot_store,
                                                         monkeypatch, cfg):
    monkeypatch.setattr(account_module, "load_account_config", lambda: cfg)
    assert on_client.get("/api/v1/risk").get_json()["account"]["balance"] == 9000.0


def test_risk_on_all_account_currency_book_dates_market_meta_by_its_bars(on_client, market,
                                                                         snapshot_store):
    usd_only = {**inputs(bars_missing={}), "fx": {}, "oldest_fx_as_of": None}
    snapshot_store.rows["risk"] = snapshot_row("risk", doc(), age_s=60, inputs=usd_only)
    body = on_client.get("/api/v1/risk").get_json()
    assert body["market_meta"]["as_of"] == "2026-10-28" == body["bars_meta"]["oldest"]
    assert body["market_meta"]["as_of"] != body["computed_at"]


def test_risk_on_with_no_inputs_has_no_market_date(on_client, market, snapshot_store):
    assert on_client.get("/api/v1/risk").get_json()["market_meta"]["as_of"] is None


def test_risk_off_all_account_currency_book_dates_market_meta_by_its_bars(golden_book, monkeypatch):
    monkeypatch.setattr(admin_snapshots, "_fx_inputs", lambda tickers, *, on: ({}, []))
    body = golden_book.client.get("/api/v1/risk").get_json()
    assert body["bars_meta"]["oldest"] and body["bars_meta"]["oldest"] < body["computed_at"][:10]
    assert body["market_meta"]["as_of"] == body["bars_meta"]["oldest"]


def test_risk_off_fx_inputs_failure_is_swallowed(golden_book, monkeypatch):
    def boom(tickers, *, on):
        raise RuntimeError("fx store down")
    monkeypatch.setattr(admin_snapshots, "_fx_inputs", boom)
    res = golden_book.client.get("/api/v1/risk")
    assert res.status_code == 200
    assert res.get_json()["fx_meta"] == {"as_of": None, "missing": []}


@pytest.mark.parametrize("cfg", [{"balance": float("nan")}, {"balance": 0}, None])
def test_risk_account_balance_unknown_is_null_never_zero(on_client, market, snapshot_store,
                                                         monkeypatch, cfg):
    def load():
        if cfg is None:
            raise RuntimeError("db down")
        return cfg
    monkeypatch.setattr(account_module, "load_account_config", load)
    assert on_client.get("/api/v1/risk").get_json()["account"]["balance"] is None


def test_risk_off_runs_todays_code_and_adds_the_meta_keys(golden_book, monkeypatch):
    calls = []
    real = portfolio_state.collect_portfolio_state
    monkeypatch.setattr(portfolio_state, "collect_portfolio_state",
                        lambda **kw: calls.append(1) or real(**kw))
    body = golden_book.client.get("/api/v1/risk").get_json()
    assert calls == [1]                                          # the kill-switch fallback computes
    assert_matches_golden("risk", body)
    assert NEW_KEYS <= set(body) and body["market_meta"]["source"] == "request"
    assert body["computed_at"] is not None and body["market_meta"]["refreshing"] is False
    assert body["bars_meta"]["per_symbol"] and set(body["bars_meta"]["per_symbol"]) <= set(BAR_SYMBOLS)
    assert golden_book.network_calls == []


def test_snapshot_body_matches_the_off_body_and_the_golden(golden_book, market, snapshot_store,
                                                           session_is, monkeypatch):
    class AtGoldenNow(datetime):           # both paths on one clock, so stale_inputs is comparable
        @classmethod
        def now(cls, tz=None):
            return GOLDEN_NOW

    monkeypatch.setattr(risk, "datetime", AtGoldenNow)
    off = golden_book.client.get("/api/v1/risk").get_json()
    monkeypatch.setattr(risk_payload, "_now", lambda: GOLDEN_NOW)
    monkeypatch.setattr(admin_snapshots, "_now", lambda: GOLDEN_NOW)
    res = admin_snapshots.build_risk()
    snapshot_store.rows["risk"] = {"key": "risk", "doc": res.doc, "inputs": res.inputs,
                                   "computed_at": datetime.fromisoformat(res.inputs["computed_at"]),
                                   "stale_inputs": res.stale_inputs, "updated_at": GOLDEN_NOW}
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    on = golden_book.client.get("/api/v1/risk").get_json()
    assert set(on) == set(off)
    for key in ("bars_meta", "fx_meta", "lower_bound"):
        assert on[key] == off[key], key
    assert_matches_golden("risk", on)
    assert on["market_meta"]["source"] == "snapshot" and golden_book.network_calls == []
