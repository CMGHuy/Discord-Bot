"""v187 D3: one PENDING_CANCEL_EVENTS set drives the placeholder discard and
the notice queue, so no pending-cancel event can be added half-wired.

Production incident, 2026-09-11: _on_event discarded the scan's placeholder
trade only for a hand-listed set of cancel events; a cancel event missing
from that list left the placeholder "open" forever. Every member of the set
must discard it."""
import logging

import pytest

from swingbot import config
from swingbot.core.planning.plan_manager import (NOTICE_EVENTS, PENDING_CANCEL_EVENTS,
                                                 PlanEvent, PlanManager, _TRANSITION_LOG,
                                                 log_plan_event)
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store


@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    })
    return TradeLog()


def _placeholder(tlog):
    return tlog.log_trade(
        ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
        direction="bullish", confidence_level=4, confidence_label="High",
        entry=100.0, stop_loss=98.5, take_profit=102.0, plan_id="p1")


def _trades_for(tlog, plan_id):
    return [t for t in tlog.get_trades(status=None, limit=None) if t.get("plan_id") == plan_id]


def test_the_set_holds_exactly_the_six_pending_cancel_events():
    assert PENDING_CANCEL_EVENTS == frozenset({
        "cancelled_expired", "cancelled_invalidated", "cancelled_risk_cap",
        "cancelled_limit", "cancelled_gap_through_stop",
        "cancelled_trade_deleted",      # v189 A7
    })


def test_notice_events_derive_from_the_cancel_set():
    assert NOTICE_EVENTS == frozenset({"filled", "closed"}) | PENDING_CANCEL_EVENTS


@pytest.mark.parametrize("transition", sorted(PENDING_CANCEL_EVENTS))
def test_every_pending_cancel_discards_the_placeholder(tlog, transition):
    _placeholder(tlog)
    assert len(_trades_for(tlog, "p1")) == 1

    mgr = PlanManager(PlanStore(), lambda ticker: 100.0, trade_log=tlog)
    mgr._on_event(_plan(), PlanEvent("p1", transition, {}))

    assert _trades_for(tlog, "p1") == []


@pytest.mark.parametrize("transition", sorted(PENDING_CANCEL_EVENTS))
def test_every_pending_cancel_writes_a_transition_line(transition):
    assert transition in _TRANSITION_LOG


@pytest.mark.parametrize("transition, label", [
    ("cancelled_limit", "limit cancelled"),
    ("cancelled_gap_through_stop", "gap through stop"),
])
def test_the_new_cancels_log_their_label_and_the_live_price(caplog, transition, label):
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.plan_manager"):
        log_plan_event(_plan(), PlanEvent("p1", transition, {"live_price": 101.2}))
    assert f"Plan {label}: AAPL" in caplog.text
    assert "price=101.20" in caplog.text
