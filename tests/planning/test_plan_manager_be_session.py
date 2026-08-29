import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_active import _active

DAY1_A = dt.datetime(2026, 8, 27, 10, 0, tzinfo=US_MARKET_TZ)
DAY1_B = dt.datetime(2026, 8, 27, 14, 0, tzinfo=US_MARKET_TZ)
DAY2_A = dt.datetime(2026, 8, 28, 10, 0, tzinfo=US_MARKET_TZ)
DAY2_B = dt.datetime(2026, 8, 28, 14, 0, tzinfo=US_MARKET_TZ)


@pytest.fixture(autouse=True)
def _rth_on(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)


def _env(tmp_path, prices):
    feed = FakePriceFeed(); feed.set_series("AAPL", prices)
    store = PlanStore(path=str(tmp_path / "plans.json")); store.add(_active())
    return store, PlanManager(store, feed.get_price)


def test_arming_stamps_the_session(tmp_path):
    store, mgr = _env(tmp_path, [105.0])
    assert [e.transition for e in mgr.poll(now=DAY1_A)] == ["be_moved"]
    assert store.get("p1").be_armed_session == "2026-08-27"


def test_be_stop_does_not_fire_the_session_it_armed(tmp_path):
    store, mgr = _env(tmp_path, [105.0, 99.9])
    mgr.poll(now=DAY1_A)
    assert mgr.poll(now=DAY1_B) == []
    assert store.get("p1").status == "ACTIVE"


def test_be_stop_fires_the_next_session(tmp_path):
    store, mgr = _env(tmp_path, [105.0, 101.0, 99.9])
    mgr.poll(now=DAY1_A); assert mgr.poll(now=DAY2_A) == []
    event = mgr.poll(now=DAY2_B)[0]
    assert event.detail == {"reason": "scratch", "exit_price": 100.0}
    assert store.get("p1").status == "CLOSED"


def test_original_stop_still_governs_the_arming_session(tmp_path):
    store, mgr = _env(tmp_path, [105.0, 94.0])
    mgr.poll(now=DAY1_A)
    event = mgr.poll(now=DAY1_B)[0]
    assert event.detail == {"reason": "loss", "exit_price": 95.0}


def test_unstamped_legacy_break_even_stop_governs_immediately(tmp_path):
    store, mgr = _env(tmp_path, [99.9])
    plan = store.get("p1"); plan.working_stop = 100.0; store.update(plan)
    assert mgr.poll(now=DAY1_A)[0].detail["reason"] == "scratch"