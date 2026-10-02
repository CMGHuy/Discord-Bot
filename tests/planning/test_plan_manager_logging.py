"""v111 §3: a paper trade's life reads from bot.log at INFO alone.
One line per lifecycle transition, with ticker, 8-char plan id, direction
and the relevant price."""
import logging

import pytest

from swingbot import config
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_manager import PlanEvent, PlanManager, log_plan_armed, log_plan_event
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_pending import _pending

CASES = [
    ("filled", {"entry_price": 106.0, "live_price": 106.0},
     "Plan filled: AAPL id=p1 bullish price=106.00"),
    ("be_moved", {"working_stop": 106.0, "live_price": 108.1},
     "Plan break-even moved: AAPL id=p1 bullish price=106.00"),
    ("tp1_partial", {"exit_price": 110.5, "reason": "tp1", "fraction": 0.5, "r": 2.0},
     "Plan TP1 hit: AAPL id=p1 bullish price=110.50 reason=tp1"),
    ("closed", {"exit_price": 104.0, "reason": "loss"},
     "Plan stopped: AAPL id=p1 bullish price=104.00 reason=loss"),
    ("closed", {"exit_price": 106.0, "reason": "scratch"},
     "Plan stopped: AAPL id=p1 bullish price=106.00 reason=scratch"),
    ("closed", {"exit_price": 118.0, "reason": "tp1_runner_trail"},
     "Plan stopped: AAPL id=p1 bullish price=118.00 reason=tp1_runner_trail"),
    ("closed", {"exit_price": 120.0, "reason": "tp1_runner_tp2"},
     "Plan closed: AAPL id=p1 bullish price=120.00 reason=tp1_runner_tp2"),
    ("closed", {"exit_price": 101.0, "reason": "stall_exit"},
     "Plan closed: AAPL id=p1 bullish price=101.00 reason=stall_exit"),
    ("cancelled_expired", {"bars_waited": 5},
     "Plan expired: AAPL id=p1 bullish price=n/a"),
    ("cancelled_invalidated", {"live_price": 99.0},
     "Plan invalidated: AAPL id=p1 bullish price=99.00"),
    ("cancelled_risk_cap", {"entry_price": 106.0, "stop_loss": 95.0,
                            "planned_loss_pct": 10.38, "max_planned_loss_pct": 2.0},
     "Plan risk cap hit: AAPL id=p1 bullish price=106.00"),
]


def _plan_lines(caplog):
    return [r for r in caplog.records if r.name == pm.log.name]


@pytest.mark.parametrize("transition,detail,expected", CASES)
def test_each_transition_logs_one_info_line(transition, detail, expected, caplog):
    with caplog.at_level(logging.INFO, logger=pm.log.name):
        log_plan_event(_plan(), PlanEvent("p1", transition, dict(detail)))
    [record] = _plan_lines(caplog)
    assert record.levelno == logging.INFO
    assert record.getMessage() == expected


def test_plan_id_is_cut_to_eight_characters(caplog):
    with caplog.at_level(logging.INFO, logger=pm.log.name):
        log_plan_event(_plan(plan_id="abcdef1234567890"),
                       PlanEvent("abcdef1234567890", "filled", {"entry_price": 1.0}))
    assert "id=abcdef12 " in _plan_lines(caplog)[0].getMessage()


@pytest.mark.parametrize("transition", ["stop_moved", "pyramid_add"])
def test_feed_only_events_are_not_transition_lines(transition, caplog):
    with caplog.at_level(logging.INFO, logger=pm.log.name):
        log_plan_event(_plan(), PlanEvent("p1", transition, {"new": 1.0}))
    assert _plan_lines(caplog) == []


def test_armed_line_uses_the_trigger_for_a_pending_plan(caplog):
    with caplog.at_level(logging.INFO, logger=pm.log.name):
        log_plan_armed(_pending())
    assert [r.getMessage() for r in _plan_lines(caplog)] == [
        "Plan armed: AAPL id=p1 bullish price=105.00 status=PENDING"]


def test_armed_line_uses_the_entry_once_there_is_one(caplog):
    with caplog.at_level(logging.INFO, logger=pm.log.name):
        log_plan_armed(_plan(entry_price=100.5, status="ACTIVE"))
    assert [r.getMessage() for r in _plan_lines(caplog)] == [
        "Plan armed: AAPL id=p1 bullish price=100.50 status=ACTIVE"]


def test_poll_logs_the_fill_it_performs(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    feed = FakePriceFeed([("AAPL", 106.0)])
    store = PlanStore()
    store.add(_pending(stop_loss=104.0))
    mgr = PlanManager(store, feed.get_price)
    with caplog.at_level(logging.INFO, logger=pm.log.name):
        mgr.poll()
    assert "Plan filled: AAPL id=p1 bullish price=106.00" in [r.getMessage() for r in _plan_lines(caplog)]


def test_a_malformed_event_detail_does_not_raise(caplog):
    with caplog.at_level(logging.DEBUG, logger=pm.log.name):
        log_plan_event(_plan(), PlanEvent("p1", "filled", None))
    assert any(r.levelno == logging.DEBUG and r.exc_info for r in _plan_lines(caplog))


def test_a_logging_failure_does_not_skip_the_event_handler(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    feed = FakePriceFeed([("AAPL", 106.0)])
    store = PlanStore()
    store.add(_pending(stop_loss=104.0))
    mgr = PlanManager(store, feed.get_price)
    handled = []
    monkeypatch.setattr(mgr, "_on_event", lambda plan, event: handled.append(event.transition))
    monkeypatch.setattr(pm, "_plan_line", lambda *a, **k: 1 / 0)
    mgr.poll()
    assert "filled" in handled
