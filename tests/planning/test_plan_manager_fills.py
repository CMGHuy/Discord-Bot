import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_manager import PlanManager, poll_stop_fill
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_active import _active
from tests.planning.test_plan_engine_model import _plan

DAY1_OPEN = dt.datetime(2026, 8, 27, 9, 35, tzinfo=US_MARKET_TZ)
DAY1_NOON = dt.datetime(2026, 8, 27, 12, 0, tzinfo=US_MARKET_TZ)
DAY2_OPEN = dt.datetime(2026, 8, 28, 9, 35, tzinfo=US_MARKET_TZ)


@pytest.fixture(autouse=True)
def _rth_on(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)


def _env(tmp_path, prices):
    feed = FakePriceFeed()
    feed.set_series("AAPL", prices)
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())
    return store, PlanManager(store, feed.get_price)


def test_poll_stop_fill_clamps_when_continuous():
    assert poll_stop_fill(94.2, 95.0, continuous=True) == 95.0
    assert poll_stop_fill(94.2, 95.0, continuous=False) == 94.2


def test_continuous_breach_fills_at_the_stop_not_the_sampled_price(tmp_path):
    store, mgr = _env(tmp_path, [99.0, 94.2])
    assert mgr.poll(now=DAY1_OPEN) == []
    events = mgr.poll(now=DAY1_NOON)
    assert events[0].detail["exit_price"] == 95.0


def test_first_poll_of_a_session_keeps_the_gap(tmp_path):
    store, mgr = _env(tmp_path, [91.0])
    events = mgr.poll(now=DAY1_OPEN)
    assert events[0].detail["exit_price"] == 91.0


def test_yesterdays_observation_does_not_make_today_continuous(tmp_path):
    store, mgr = _env(tmp_path, [99.0, 91.0])
    assert mgr.poll(now=DAY1_NOON) == []
    events = mgr.poll(now=DAY2_OPEN)
    assert events[0].detail["exit_price"] == 91.0


def test_continuity_works_the_same_way_for_a_short(tmp_path):
    feed = FakePriceFeed()
    feed.set_series("AAPL", [101.0, 106.0])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    plan = _plan(entry_type="market", direction="bearish", trigger_price=100.0,
                 entry_price=100.0, stop_loss=105.0, tp1=90.0)
    record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at="t0")
    store.add(plan)
    mgr = PlanManager(store, feed.get_price)
    assert mgr.poll(now=DAY1_OPEN) == []
    events = mgr.poll(now=DAY1_NOON)
    assert events[0].detail["exit_price"] == 105.0
