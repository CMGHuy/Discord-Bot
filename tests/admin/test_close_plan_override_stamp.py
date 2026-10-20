"""v173 §1: a manual close stamps its exit price, the price's source, the
quote time and the bar-cache date; a bulk clear says `manual_bulk`.

Everything is faked -- the plan store, the trade log, the live quote and the
daily cache -- so no test here opens a database or the network."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from flask import Flask

import swingbot.admin.app  # noqa: F401  (loads the api_v1 package in order; avoids a circular import)
from swingbot.admin.api_v1 import trade_commands as tc
from swingbot.core.analytics import runner_path as rp
from swingbot.core.marketdata import data as md
from swingbot.core.marketdata.data import PriceQuote
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from tests.planning.test_plan_engine_model import _plan

PLAN_ID = "55555555-5555-4555-8555-555555555555"
TRADE_ID = "bbbbbbbbbbbbbbbb"
FILL_AT = "2026-10-14T14:00:00+00:00"


def _bars(last_close=101.5):
    index = pd.DatetimeIndex(["2026-10-15", "2026-10-16"])
    return pd.DataFrame({"Open": [100.0, 100.5], "High": [101.0, 102.0], "Low": [99.0, 100.0],
                         "Close": [100.2, last_close], "Volume": [1e6, 1e6]}, index=index)


def _active(plan_id=PLAN_ID, ticker="AAPL"):
    plan = _plan(plan_id=plan_id, ticker=ticker, entry_price=101.0)
    record_transition(plan, PlanStatus.ACTIVE, reason="filled", at=FILL_AT)
    return plan


def _partial():
    plan = _active()
    record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial", at="2026-10-15T15:00:00+00:00")
    return plan


class FakeStore:
    def __init__(self, plans=()):
        self.plans = {plan.plan_id: plan for plan in plans}
        self.updated = []

    def all(self):
        return list(self.plans.values())

    def get(self, plan_id):
        return self.plans.get(plan_id)

    def update(self, plan):
        self.updated.append(plan.plan_id)


class FakeTradeLog:
    trades: list[dict] = []
    closes: list[dict] = []

    def get_trades(self, status=None, limit=None):
        return list(FakeTradeLog.trades)

    def close_trade_manual(self, trade_id, reason="manual", *, exit_price=None):
        FakeTradeLog.closes.append({"id": trade_id, "reason": reason, "exit_price": exit_price})
        return True


@pytest.fixture
def env(monkeypatch):
    """Offline seams. `env["quote"]` / `env["bars"]` are read at call time, so a
    test sets them before closing. An Exception value is raised instead."""
    state = {"quote": PriceQuote(123.45, False), "bars": _bars(), "quote_calls": [],
             "notified": [], "runner_stamps": []}

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

    FakeTradeLog.trades = [{"id": TRADE_ID, "plan_id": PLAN_ID, "status": "open"}]
    FakeTradeLog.closes = []
    monkeypatch.setattr(md, "get_current_price_detail", quote)
    monkeypatch.setattr(rp, "cached_daily_bars", bars)
    monkeypatch.setattr(rp, "stamp_runner_path",
                        lambda plan, fn, *, source="live": state["runner_stamps"].append(plan.plan_id))
    monkeypatch.setattr(tc, "TradeLog", FakeTradeLog)
    monkeypatch.setattr(tc, "_queue_notify", state["notified"].append)
    return state


def _closed_entry(plan):
    entry = plan.status_history[-1]
    assert entry["status"] == "CLOSED"
    return entry


# --- the stamp ----------------------------------------------------------------

def test_a_single_close_stamps_manual_with_the_four_override_fields(env):
    plan = _active()
    store = FakeStore([plan])
    tc._close_plan(store, plan)

    entry = _closed_entry(plan)
    assert entry["reason"] == "manual"
    stamp = entry["override"]
    assert set(stamp) == {"exit_price", "price_source", "quote_ts", "bars_asof"}
    assert stamp["exit_price"] == pytest.approx(123.45)
    assert stamp["price_source"] == "quote"
    assert stamp["bars_asof"] == "2026-10-16"
    assert datetime.fromisoformat(stamp["quote_ts"]).utcoffset() is not None
    assert plan.status == PlanStatus.CLOSED
    assert store.updated == [PLAN_ID]


def test_the_quote_is_fetched_once_and_never_stale(env):
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    assert env["quote_calls"] == [("AAPL", False)]


def test_the_linked_trade_settles_at_the_stamped_quote(env):
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    assert FakeTradeLog.closes == [{"id": TRADE_ID, "reason": "manual (plan close, admin UI)",
                                    "exit_price": pytest.approx(123.45)}]
    assert _closed_entry(plan)["override"]["exit_price"] == FakeTradeLog.closes[0]["exit_price"]


def test_a_bulk_close_stamps_manual_bulk(env):
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan, "manual_bulk")
    entry = _closed_entry(plan)
    assert entry["reason"] == "manual_bulk"
    assert entry["override"]["price_source"] == "quote"
    assert FakeTradeLog.closes[0]["reason"] == "manual (plan close, admin UI)"


def test_no_quote_falls_back_to_the_cached_daily_close(env):
    env["quote"] = None
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    assert _closed_entry(plan)["override"] == {
        "exit_price": pytest.approx(101.5), "price_source": "bar_close",
        "quote_ts": None, "bars_asof": "2026-10-16"}
    # A daily close is never written to the trade as a live fill.
    assert FakeTradeLog.closes[0]["exit_price"] is None


def test_a_quote_that_raises_is_treated_as_no_quote(env):
    env["quote"] = TimeoutError("yfinance down")
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    assert _closed_entry(plan)["override"]["price_source"] == "bar_close"


def test_no_quote_and_no_cache_records_source_none(env):
    env["quote"], env["bars"] = None, None
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    assert _closed_entry(plan)["override"] == {
        "exit_price": None, "price_source": "none", "quote_ts": None, "bars_asof": None}


def test_a_nan_last_close_is_no_price(env):
    env["quote"], env["bars"] = None, _bars(last_close=float("nan"))
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    stamp = _closed_entry(plan)["override"]
    assert (stamp["price_source"], stamp["exit_price"], stamp["bars_asof"]) == ("none", None, "2026-10-16")


def test_an_unreadable_cache_writes_a_null_stamp_and_still_closes(env):
    env["bars"] = OSError("bad csv")
    plan = _active()
    store = FakeStore([plan])
    tc._close_plan(store, plan)
    entry = _closed_entry(plan)
    assert "override" in entry and entry["override"] is None
    assert plan.status == PlanStatus.CLOSED
    assert store.updated == [PLAN_ID]
    assert env["notified"] and env["notified"][0]["status"] == PlanStatus.CLOSED


def test_a_stamp_builder_failure_still_closes(env, monkeypatch):
    def boom(ticker):
        raise RuntimeError("bug in the builder")

    monkeypatch.setattr(tc, "_build_override_stamp", boom)
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    assert _closed_entry(plan)["override"] is None
    assert FakeTradeLog.closes[0]["exit_price"] is None


def test_override_stamp_never_raises(env):
    env["bars"] = ValueError("malformed frame")
    assert tc._override_stamp("AAPL") is None


def test_a_partial_close_still_stamps_its_runner_path(env):
    plan = _partial()
    tc._close_plan(FakeStore([plan]), plan)
    assert env["runner_stamps"] == [PLAN_ID]
    assert _closed_entry(plan)["override"]["price_source"] == "quote"


def test_a_plan_with_no_linked_trade_is_still_stamped(env):
    FakeTradeLog.trades = []
    plan = _active()
    tc._close_plan(FakeStore([plan]), plan)
    assert FakeTradeLog.closes == []
    assert _closed_entry(plan)["override"]["exit_price"] == pytest.approx(123.45)


# --- the two callers ------------------------------------------------------------

@pytest.fixture
def request_ctx():
    return Flask("v173-close-tests").test_request_context


def test_close_open_passes_manual_bulk(env, monkeypatch, request_ctx):
    plans = [_active("11111111-1111-4111-8111-111111111111", "AAA"),
             _active("22222222-2222-4222-8222-222222222222", "BBB")]
    store = FakeStore(plans)
    seen = []
    monkeypatch.setattr(tc, "PlanStore", lambda: store)
    monkeypatch.setattr(tc, "_close_plan",
                        lambda store_, plan, reason="manual": seen.append((plan.ticker, reason)))
    with request_ctx("/api/v1/trades/close-open", method="POST"):
        body = tc.close_open.__wrapped__().get_json()
    assert body == {"closed": 2, "failed": 0, "tickers": ["AAA", "BBB"]}
    assert seen == [("AAA", "manual_bulk"), ("BBB", "manual_bulk")]


def test_close_trade_passes_the_default_manual(env, monkeypatch, request_ctx):
    store = FakeStore([_active()])
    seen = []
    monkeypatch.setattr(tc, "PlanStore", lambda: store)
    monkeypatch.setattr(tc, "_close_plan",
                        lambda store_, plan, reason="manual": seen.append(reason))
    monkeypatch.setattr(tc, "_plan_row", lambda plan_id: {"plan_id": plan_id})
    with request_ctx(f"/api/v1/trades/{PLAN_ID}/close", method="POST"):
        assert tc.close_trade.__wrapped__(PLAN_ID) == {"plan_id": PLAN_ID}
    assert seen == ["manual"]


def test_a_bulk_close_end_to_end_stamps_every_plan(env, monkeypatch, request_ctx):
    plans = [_active("11111111-1111-4111-8111-111111111111", "AAA"),
             _active("22222222-2222-4222-8222-222222222222", "BBB")]
    FakeTradeLog.trades = []
    monkeypatch.setattr(tc, "PlanStore", lambda: FakeStore(plans))
    with request_ctx("/api/v1/trades/close-open", method="POST"):
        tc.close_open.__wrapped__()
    for plan in plans:
        entry = _closed_entry(plan)
        assert entry["reason"] == "manual_bulk"
        assert entry["override"]["price_source"] == "quote"
