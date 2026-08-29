import datetime as dt

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_active import _active

RTH = dt.datetime(2026, 8, 27, 12, 0, tzinfo=US_MARKET_TZ)
AFTER_HOURS = dt.datetime(2026, 8, 27, 19, 30, tzinfo=US_MARKET_TZ)


def _env(tmp_path, prices):
    feed = FakePriceFeed()
    feed.set_series("AAPL", prices)
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())
    return store, PlanManager(store, feed.get_price)


def test_after_hours_poll_is_a_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    store, mgr = _env(tmp_path, [94.0])
    assert mgr.poll(now=AFTER_HOURS) == []
    assert store.get("p1").status == "ACTIVE"


def test_regular_hours_poll_still_acts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    store, mgr = _env(tmp_path, [94.0])
    events = mgr.poll(now=RTH)
    assert [event.transition for event in events] == ["closed"]


def test_flag_off_restores_round_the_clock_behaviour(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    store, mgr = _env(tmp_path, [94.0])
    events = mgr.poll(now=AFTER_HOURS)
    assert [event.transition for event in events] == ["closed"]