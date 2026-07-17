import pytest

from swingbot.core.plan_engine import PlanStatus
from swingbot.core.plan_manager import PlanManager
from swingbot.core.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.test_plan_manager_active import _active


def _partial_env(tmp_path, prices, tp2=None, atr_fn=None):
    """Walk a fresh ACTIVE plan through the TP1 partial first (price 110.5),
    then feed `prices` to the runner."""
    feed = FakePriceFeed()
    feed.set_series("AAPL", [110.5] + list(prices))
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active(tp2=tp2))
    mgr = PlanManager(store, feed.get_price, atr_fn=atr_fn)
    assert [e.transition for e in mgr.poll()] == ["tp1_partial"]
    return store, mgr


def test_runner_closes_at_breakeven(tmp_path):
    store, mgr = _partial_env(tmp_path, [99.9])
    events = mgr.poll()
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_be"
    p = store.get("p1")
    assert p.status == PlanStatus.CLOSED
    assert len(p.legs_realized) == 2
    leg2 = p.legs_realized[1]
    assert leg2["r"] <= 0.0 or leg2["r"] == pytest.approx(0.0, abs=0.05)
    # total realized: leg1 banked ~+2.1R on 50% -- the win survives
    total = sum(l["fraction"] * l["r"] for l in p.legs_realized)
    assert total >= 0.5 * 2.0 * 0.9


def test_runner_closes_at_tp2(tmp_path):
    store, mgr = _partial_env(tmp_path, [118.5], tp2=118.0)
    events = mgr.poll()
    assert events[0].detail["reason"] == "tp1_runner_tp2"
    assert store.get("p1").legs_realized[1]["r"] == pytest.approx((118.5 - 100) / 5)


def test_tp2_none_runner_ignores_high_prices(tmp_path):
    store, mgr = _partial_env(tmp_path, [140.0], tp2=None)
    assert mgr.poll() == []          # no trail (no atr_fn), no tp2 -> still open


def test_trail_ratchets_and_closes(tmp_path):
    # ATR faked at 2.0, trail_atr_mult=2.5 -> trail = extreme - 5.0.
    store, mgr = _partial_env(tmp_path, [120.0, 118.0, 114.9],
                              atr_fn=lambda t: 2.0)
    assert mgr.poll() == []                      # 120: trail -> max(100, 115)
    assert store.get("p1").working_stop == 115.0
    assert mgr.poll() == []                      # 118: above trail; no ratchet down
    assert store.get("p1").working_stop == 115.0
    events = mgr.poll()                          # 114.9 <= 115 -> trail close
    assert events[0].detail["reason"] == "tp1_runner_trail"
    assert store.get("p1").legs_realized[1]["r"] == pytest.approx((114.9 - 100) / 5)
