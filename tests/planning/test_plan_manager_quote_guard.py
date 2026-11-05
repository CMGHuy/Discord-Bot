"""V189-9: poll ignores NaN/inf/non-positive quotes, steps stop-bearing plans
before PENDING ones, and skips (never stalls on) a plan another process has
locked."""
from __future__ import annotations

import datetime as dt
import logging
import math
import time
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.db.engine import transaction
from swingbot.core.marketdata.shared.kinds import QuoteDetail
from swingbot.core.planning import plan_manager
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager, _usable_price
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_active import _active
from tests.planning.test_plan_manager_pending import _pending

SATURDAY = dt.datetime(2026, 10, 17, 12, 0, tzinfo=ZoneInfo("America/New_York"))
MANAGER_LOG = "swingbot.core.planning.plan_manager"


@pytest.fixture(autouse=True)
def _full_step_every_tick(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)


def _quote(symbol, price):
    return QuoteDetail(symbol=symbol, price=price, trade_at=None, bid=None, ask=None,
                       quote_at=None, source="legacy")


@pytest.mark.parametrize("price, usable", [
    (100.0, True), (0.01, True), (7, True),
    (0.0, False), (-1.0, False), (None, False), ("n/a", False),
    (math.nan, False), (math.inf, False), (-math.inf, False),
])
def test_usable_price(price, usable):
    assert _usable_price(price) is usable


@pytest.mark.parametrize("bad", [math.nan, math.inf, 0.0, -3.0])
def test_poll_never_steps_a_plan_on_an_unusable_quote(monkeypatch, bad):
    store = PlanStore()
    store.add(_active())
    mgr = PlanManager(store, lambda ticker: bad)
    stepped: list = []
    monkeypatch.setattr(mgr, "_step", lambda plan, price, now=None: stepped.append(price) or [])

    assert mgr.poll(now=SATURDAY) == []
    assert stepped == []
    assert store.get("p1").first_seen_price is None


def test_the_shared_price_batch_drops_unusable_quotes(monkeypatch):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    details = {"GOOD": _quote("GOOD", 101.0), "NAN": _quote("NAN", math.nan),
               "ZERO": _quote("ZERO", 0.0), "NONE": _quote("NONE", None)}
    monkeypatch.setattr(plan_manager, "monitor_quotes", lambda tickers: details)

    prices = plan_manager._price_batch_fn(list(details))

    assert dict(prices) == {"GOOD": 101.0}


def test_the_quote_worker_drops_unusable_quotes(monkeypatch):
    from swingbot.core.marketdata import data
    quotes = {"GOOD": _quote("GOOD", 101.0), "NAN": _quote("NAN", math.nan),
              "INF": _quote("INF", math.inf)}
    monkeypatch.setattr(data, "get_quote_batch", lambda tickers, **kw: quotes)

    docs, _rows = plan_manager._monitor_quote_worker(list(quotes))

    assert set(docs) == {"GOOD"}


def test_ordered_puts_stop_bearing_plans_first_and_keeps_order():
    plans = [_plan(plan_id="a", status=PlanStatus.PENDING),
             _plan(plan_id="b", status=PlanStatus.ACTIVE),
             _plan(plan_id="c", status=PlanStatus.PENDING),
             _plan(plan_id="d", status=PlanStatus.PARTIAL)]
    ordered = PlanManager(PlanStore(), lambda ticker: 1.0)._ordered(plans)
    assert [p.plan_id for p in ordered] == ["b", "d", "a", "c"]


def test_poll_steps_the_active_plan_before_the_pending_one(monkeypatch):
    store = PlanStore()
    store.add(_pending(plan_id="pend", ticker="MSFT"))
    store.add(_active(plan_id="act"))
    mgr = PlanManager(store, lambda ticker: 100.0)
    order: list = []
    real_step = mgr._step

    def spy(plan, price, now=None):
        order.append(plan.plan_id)
        return real_step(plan, price, now)

    monkeypatch.setattr(mgr, "_step", spy)
    mgr.poll(now=SATURDAY)
    assert order == ["act", "pend"]


def test_a_step_that_raises_is_logged_and_skipped(monkeypatch, caplog):
    store = PlanStore()
    store.add(_active())
    mgr = PlanManager(store, lambda ticker: 100.0)

    def broken(plan, price, now=None):
        raise ValueError("bad plan geometry")

    monkeypatch.setattr(mgr, "_step", broken)
    caplog.set_level(logging.WARNING, logger=MANAGER_LOG)
    assert mgr.poll(now=SATURDAY) == []
    assert "poll: step failed for plan p1" in caplog.text


@pytest.mark.slow
def test_a_locked_plan_is_skipped_for_one_poll_and_the_rest_are_stepped(caplog):
    store = PlanStore()
    store.add(_active())                                   # p1 AAPL
    store.add(_active(plan_id="p2", ticker="MSFT"))
    mgr = PlanManager(store, lambda ticker: 105.0)         # arms break-even on both
    caplog.set_level(logging.INFO, logger=MANAGER_LOG)

    with transaction() as conn:
        PlanStore().lock_for_update("p1", conn=conn)       # an admin transaction holds p1
        started = time.monotonic()
        events = mgr.poll(now=SATURDAY)
        elapsed = time.monotonic() - started

    assert [(e.plan_id, e.transition) for e in events] == [("p2", "be_moved")]
    assert PlanStore().get("p1").working_stop is None
    assert PlanStore().get("p2").working_stop == 100.0
    assert "plan p1 is locked by another writer" in caplog.text
    assert elapsed < 4.0                                   # one 1s wait, not a stall
