import pytest

from swingbot.core.plan_store import PlanStore
from swingbot.core.plan_manager import PlanManager
from tests.fake_feed import FakePriceFeed
from tests.test_plan_manager_active import _active


def _env(tmp_path):
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())          # entry 100, stop 95, tp1 110
    return store, PlanManager(store, FakePriceFeed([("AAPL", 100.0)]).get_price)


def test_overnight_gap_through_stop_fills_at_open(tmp_path):
    store, mgr = _env(tmp_path)
    events = mgr.check_bar("p1", bar_open=91.0, bar_high=93.0, bar_low=90.0)
    assert events[0].detail["reason"] == "loss"
    assert events[0].detail["exit_price"] == 91.0     # gapped open, not 95
    assert store.get("p1").legs_realized[0]["r"] == pytest.approx((91 - 100) / 5)


def test_gap_up_through_tp1_fills_at_open(tmp_path):
    store, mgr = _env(tmp_path)
    events = mgr.check_bar("p1", bar_open=113.0, bar_high=114.0, bar_low=112.0)
    assert events[0].transition == "tp1_partial"
    assert events[0].detail["exit_price"] == 113.0    # better-than-tp1 real fill
    assert events[0].detail["r"] == pytest.approx((113 - 100) / 5)


def test_intrabar_touch_fills_at_level(tmp_path):
    store, mgr = _env(tmp_path)
    events = mgr.check_bar("p1", bar_open=96.0, bar_high=97.0, bar_low=94.5)
    assert events[0].detail["exit_price"] == 95.0     # traded down TO the stop
