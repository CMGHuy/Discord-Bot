import pytest

from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan


def _active(**kw):
    p = _plan(entry_type="market", direction="bullish", trigger_price=100.0,
              entry_price=100.0, stop_loss=95.0, tp1=110.0, **kw)
    record_transition(p, PlanStatus.ACTIVE, reason="market_entry", at="t0")
    return p


def _env(tmp_path, prices, plan=None):
    feed = FakePriceFeed()
    feed.set_series("AAPL", prices)
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(plan or _active())
    return store, PlanManager(store, feed.get_price)


def test_be_move_at_half_way_to_tp1(tmp_path):
    # BE trigger = 100 + 0.5*(110-100) = 105
    store, mgr = _env(tmp_path, [105.0, 105.0])
    events = mgr.poll()
    assert [e.transition for e in events] == ["be_moved"]
    assert store.get("p1").working_stop == 100.0
    assert mgr.poll() == []               # idempotent at the same price


def test_below_trigger_no_move(tmp_path):
    store, mgr = _env(tmp_path, [104.9])
    assert mgr.poll() == []
    assert store.get("p1").working_stop is None


def test_stop_hit_pre_be_is_loss(tmp_path):
    store, mgr = _env(tmp_path, [94.5])
    events = mgr.poll()
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "loss"
    assert events[0].detail["exit_price"] == 94.5   # gap-aware: real price, not 95
    assert store.get("p1").status == PlanStatus.CLOSED


def test_stop_hit_post_be_is_scratch(tmp_path):
    import datetime as dt
    from swingbot.core.market.session import US_MARKET_TZ

    day1 = dt.datetime(2026, 8, 27, 12, 0, tzinfo=US_MARKET_TZ)
    day2 = dt.datetime(2026, 8, 28, 12, 0, tzinfo=US_MARKET_TZ)
    store, mgr = _env(tmp_path, [105.0, 99.9])
    assert [event.transition for event in mgr.poll(now=day1)] == ["be_moved"]
    events = mgr.poll(now=day2)
    assert events[0].detail["reason"] == "scratch"
    assert store.get("p1").status == PlanStatus.CLOSED

def test_tp1_touch_banks_partial_and_moves_to_partial(tmp_path):
    store, mgr = _env(tmp_path, [110.5])
    events = mgr.poll()
    assert [e.transition for e in events] == ["tp1_partial"]
    d = events[0].detail
    assert d["fraction"] == 0.5
    assert d["exit_price"] == 110.5                  # gap-aware fill
    assert d["r"] == (110.5 - 100.0) / 5.0
    p = store.get("p1")
    assert p.status == PlanStatus.PARTIAL
    assert p.working_stop == pytest.approx(106.66666666666667)   # v39 runner floor:
                                                                 # 100 + (2/3)*(110-100)
    assert p.legs_realized == [{"fraction": 0.5, "exit_price": 110.5,
                                "r": d["r"], "reason": "tp1"}]

@pytest.fixture(autouse=True)
def _rth_gate_off(monkeypatch):
    """Arithmetic tests stay independent of the wall clock."""
    from swingbot import config
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)