"""v173 §1: a manual close stamps its exit price, the price's source, the
quote time and the bar-cache date; a bulk clear says `manual_bulk`.

V197-4b: the close is the atomic lifecycle service, so these run against the
test database; only the live quote and the daily cache are faked."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

import swingbot.admin.app  # noqa: F401  (loads the api_v1 package in order; avoids a circular import)
from swingbot import config
from swingbot.admin.api_v1 import trade_commands as tc
from swingbot.core.analytics import runner_path as rp
from swingbot.core.db.repositories.account import AccountRepository
from swingbot.core.db.repositories.notify_queue import notify_queue_repo
from swingbot.core.marketdata import data as md
from swingbot.core.marketdata.data import PriceQuote
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import performance as perf
from swingbot.core.tracking.performance import TradeLog
from tests.admin.test_api_v1_trades import _plan, _trade
from tests.store_seed import seed_store

PLAN_ID = "55555555-5555-4555-8555-555555555555"
TRADE_ID = "bbbbbbbbbbbbbbbb"
ID_A = "11111111-1111-4111-8111-111111111111"
ID_B = "22222222-2222-4222-8222-222222222222"
_LOGIN = {"username": "admin", "password": "admin"}


def _bars(last_close=101.5):
    index = pd.DatetimeIndex(["2026-10-15", "2026-10-16"])
    return pd.DataFrame({"Open": [100.0, 100.5], "High": [101.0, 102.0], "Low": [99.0, 100.0],
                         "Close": [100.2, last_close], "Volume": [1e6, 1e6]}, index=index)


def _seed(plans=None, trades=None):
    seed_store("plans", plans if plans is not None else [_plan(PLAN_ID, status="ACTIVE")])
    seed_store("trades", trades if trades is not None else [_trade(TRADE_ID, plan_id=PLAN_ID)])


@pytest.fixture
def env(store_db, monkeypatch):
    """Offline seams. `env["quote"]` / `env["bars"]` are read at call time, so a
    test sets them before closing. An Exception value is raised instead."""
    state = {"quote": PriceQuote(123.45, False), "bars": _bars(), "quote_calls": []}

    def quote(ticker, *args, **kwargs):
        state["quote_calls"].append((ticker, kwargs.get("allow_stale")))
        value = state["quote"]
        if isinstance(value, Exception):
            raise value
        return value

    def bars(ticker):
        value = state["bars"]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "5")
    monkeypatch.setattr(md, "get_current_price_detail", quote)
    monkeypatch.setattr(md, "get_current_price", lambda *a, **k: None)
    monkeypatch.setattr(rp, "cached_daily_bars", bars)
    monkeypatch.setattr(perf, "_after_close", lambda trade: None)
    AccountRepository().save(dict(base_balance=1000, balance=1000))
    return state


def _close(plan_id=PLAN_ID, reason="manual"):
    tc._close_plan(PlanStore(), PlanStore().get(plan_id), reason)
    plan = PlanStore().get(plan_id)
    entry = plan.status_history[-1]
    assert entry["status"] == "CLOSED"
    return plan, entry


# --- the stamp ----------------------------------------------------------------

def test_a_single_close_stamps_manual_with_the_four_override_fields(env):
    _seed()
    plan, entry = _close()
    assert entry["reason"] == "manual"
    stamp = entry["override"]
    assert set(stamp) == {"exit_price", "price_source", "quote_ts", "bars_asof"}
    assert stamp["exit_price"] == pytest.approx(123.45)
    assert stamp["price_source"] == "quote"
    assert stamp["bars_asof"] == "2026-10-16"
    assert datetime.fromisoformat(stamp["quote_ts"]).utcoffset() is not None
    assert plan.status == "CLOSED"


def test_the_quote_is_fetched_once_and_never_stale(env):
    _seed()
    _close()
    assert env["quote_calls"] == [("AAPL", False)]


def test_the_linked_trade_settles_at_the_stamped_quote(env):
    _seed()
    _, entry = _close()
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert trade["status"] != "open"
    assert trade["exit_price"] == pytest.approx(123.45)
    assert entry["override"]["exit_price"] == pytest.approx(123.45)


def test_a_bulk_close_stamps_manual_bulk(env):
    _seed()
    _, entry = _close(reason="manual_bulk")
    assert entry["reason"] == "manual_bulk"
    assert entry["override"]["price_source"] == "quote"
    trade = TradeLog().get_trade_by_id(TRADE_ID)
    assert trade["close_reason"] == "manual (plan close, admin UI)"


def test_no_quote_falls_back_to_the_cached_daily_close(env):
    env["quote"] = None
    _seed()
    _, entry = _close()
    assert entry["override"] == {
        "exit_price": pytest.approx(101.5), "price_source": "bar_close",
        "quote_ts": None, "bars_asof": "2026-10-16"}
    # A daily close is never written to the trade as a live fill.
    assert TradeLog().get_trade_by_id(TRADE_ID)["exit_price"] is None


def test_a_quote_that_raises_is_treated_as_no_quote(env):
    env["quote"] = TimeoutError("yfinance down")
    _seed()
    _, entry = _close()
    assert entry["override"]["price_source"] == "bar_close"


def test_no_quote_and_no_cache_records_source_none(env):
    env["quote"], env["bars"] = None, None
    _seed()
    _, entry = _close()
    assert entry["override"] == {
        "exit_price": None, "price_source": "none", "quote_ts": None, "bars_asof": None}


def test_a_nan_last_close_is_no_price(env):
    env["quote"], env["bars"] = None, _bars(last_close=float("nan"))
    _seed()
    _, entry = _close()
    stamp = entry["override"]
    assert (stamp["price_source"], stamp["exit_price"], stamp["bars_asof"]) == ("none", None, "2026-10-16")


def test_an_unreadable_cache_writes_a_null_stamp_and_still_closes(env):
    env["bars"] = OSError("bad csv")
    _seed()
    plan, entry = _close()
    assert "override" in entry and entry["override"] is None
    assert plan.status == "CLOSED"
    events = notify_queue_repo().list_all()
    assert [e["payload"]["new_status"] for e in events] == ["CLOSED"]


def test_a_stamp_builder_failure_still_closes(env, monkeypatch):
    def boom(ticker):
        raise RuntimeError("bug in the builder")

    monkeypatch.setattr(tc, "_build_override_stamp", boom)
    _seed()
    _, entry = _close()
    assert entry["override"] is None
    assert TradeLog().get_trade_by_id(TRADE_ID)["exit_price"] is None


def test_override_stamp_never_raises(env):
    env["bars"] = ValueError("malformed frame")
    assert tc._override_stamp("AAPL") is None


def test_a_partial_close_still_stamps_its_runner_path(env, monkeypatch):
    stamped = []
    real = rp.stamp_runner_path

    def spy(plan, fn, *, source="live"):
        stamped.append(plan.plan_id)
        return real(plan, fn, source=source)

    monkeypatch.setattr(rp, "stamp_runner_path", spy)
    _seed(plans=[_plan(PLAN_ID, status="PARTIAL")])
    _, entry = _close()
    assert stamped == [PLAN_ID]
    assert entry["override"]["price_source"] == "quote"


def test_a_plan_with_no_linked_trade_is_still_stamped(env):
    _seed(trades=[])
    _, entry = _close()
    assert entry["override"]["exit_price"] == pytest.approx(123.45)


# --- the callers ------------------------------------------------------------

def test_close_open_passes_manual_bulk(env, monkeypatch, client):
    client.post("/api/v1/session", json=_LOGIN)
    _seed(plans=[_plan(ID_A, ticker="AAA", status="ACTIVE"),
                 _plan(ID_B, ticker="BBB", status="ACTIVE")], trades=[])
    seen = []
    monkeypatch.setattr(tc, "_close_plan",
                        lambda store_, plan, reason="manual": seen.append((plan.ticker, reason)))
    body = client.post("/api/v1/trades/close-open").get_json()
    assert body == {"closed": 2, "failed": 0, "tickers": ["AAA", "BBB"]}
    assert sorted(seen) == [("AAA", "manual_bulk"), ("BBB", "manual_bulk")]


def test_close_trade_passes_the_default_manual(env, client):
    client.post("/api/v1/session", json=_LOGIN)
    _seed(trades=[])
    assert client.post(f"/api/v1/trades/{PLAN_ID}/close").status_code == 200
    assert PlanStore().get(PLAN_ID).status_history[-1]["reason"] == "manual"


def test_a_bulk_close_end_to_end_stamps_every_plan(env, client):
    client.post("/api/v1/session", json=_LOGIN)
    _seed(plans=[_plan(ID_A, ticker="AAA", status="ACTIVE"),
                 _plan(ID_B, ticker="BBB", status="ACTIVE")], trades=[])
    assert client.post("/api/v1/trades/close-open").get_json()["closed"] == 2
    for plan_id in (ID_A, ID_B):
        entry = PlanStore().get(plan_id).status_history[-1]
        assert entry["status"] == "CLOSED" and entry["reason"] == "manual_bulk"
