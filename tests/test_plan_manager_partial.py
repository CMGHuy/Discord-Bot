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
