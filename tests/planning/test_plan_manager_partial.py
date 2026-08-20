import pytest

from swingbot.core.planning.plan_engine import (PlanStatus, record_transition,
                                                runner_floor)
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_active import _active


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
    assert mgr.poll() == []                      # 120: trail -> max(floor, 115)
    assert store.get("p1").working_stop == 115.0
    assert store.get("p1").working_stop > FLOOR  # floor is a start, not a ceiling
    assert mgr.poll() == []                      # 118: above trail; no ratchet down
    assert store.get("p1").working_stop == 115.0
    events = mgr.poll()                          # 114.9 <= 115 -> trail close
    assert events[0].detail["reason"] == "tp1_runner_trail"
    assert store.get("p1").legs_realized[1]["r"] == pytest.approx((114.9 - 100) / 5)


# ---------------------------------------------------------------------------
# v39: the runner floor on the live poll path and the overnight bar-check
# path. FLOOR / BEAR_FLOOR are plan_engine.runner_floor's values for the two
# fixture plans, written out so a drift in the constant fails loudly here.
# ---------------------------------------------------------------------------

FLOOR = 106.66666666666667        # runner_floor(100.0, 110.0)
BEAR_FLOOR = 93.33333333333333    # runner_floor(100.0,  90.0)


def _bear_active(**kw):
    p = _plan(entry_type="market", direction="bearish", trigger_price=100.0,
              entry_price=100.0, stop_loss=105.0, tp1=90.0, tp2=None, **kw)
    record_transition(p, PlanStatus.ACTIVE, reason="market_entry", at="t0")
    return p


def _bear_partial_env(tmp_path, prices):
    feed = FakePriceFeed()
    feed.set_series("AAPL", [89.5] + list(prices))
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_bear_active())
    mgr = PlanManager(store, feed.get_price)
    assert [e.transition for e in mgr.poll()] == ["tp1_partial"]
    return store, mgr


def test_tp1_sets_the_working_stop_to_the_runner_floor(tmp_path):
    store, _ = _partial_env(tmp_path, [])
    assert store.get("p1").working_stop == pytest.approx(FLOOR)
    assert store.get("p1").working_stop == pytest.approx(runner_floor(100.0, 110.0))


def test_bearish_tp1_sets_the_working_stop_to_the_runner_floor(tmp_path):
    store, _ = _bear_partial_env(tmp_path, [])
    assert store.get("p1").working_stop == pytest.approx(BEAR_FLOOR)


def test_pullback_to_exactly_the_floor_closes_the_runner_as_be(tmp_path):
    store, mgr = _partial_env(tmp_path, [FLOOR])
    events = mgr.poll()
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_be"
    assert events[0].detail["exit_price"] == pytest.approx(FLOOR)
    assert store.get("p1").legs_realized[1]["r"] == pytest.approx(4.0 / 3.0)


def test_pullback_between_old_breakeven_and_the_floor_now_closes(tmp_path):
    # THE regression guard. 103.0 is above the pre-v39 breakeven floor
    # (entry 100) and below the v39 floor, so pre-v39 the runner stayed open
    # here. It must now close. The live path fills at the observed price
    # (103.0), not at the stop level -- that is the existing live-vs-backtest
    # fill convention (_close_runner takes `price`), unchanged by v39.
    store, mgr = _partial_env(tmp_path, [103.0])
    events = mgr.poll()
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_be"
    assert events[0].detail["exit_price"] == pytest.approx(103.0)
    assert store.get("p1").status == PlanStatus.CLOSED
    assert store.get("p1").legs_realized[1]["r"] == pytest.approx(0.6)


def test_price_just_above_the_floor_keeps_the_runner_open(tmp_path):
    # The other side of the same boundary: 107.0 clears the floor, so the
    # runner rides on with its stop untouched.
    store, mgr = _partial_env(tmp_path, [107.0])
    assert mgr.poll() == []
    assert store.get("p1").status == PlanStatus.PARTIAL
    assert store.get("p1").working_stop == pytest.approx(FLOOR)


def test_check_bar_tp1_sets_the_runner_floor_and_closes_at_it(tmp_path):
    # Overnight bar-check path (_check_bar_active / _check_bar_partial) must
    # mirror the poll path exactly.
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())
    mgr = PlanManager(store, lambda t: 100.0)
    events = mgr.check_bar("p1", bar_open=109.0, bar_high=111.0, bar_low=108.0)
    assert [e.transition for e in events] == ["tp1_partial"]
    assert store.get("p1").working_stop == pytest.approx(FLOOR)
    events = mgr.check_bar("p1", bar_open=107.0, bar_high=107.5, bar_low=100.0)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_be"
    # gap_stop_fill(107.0, 106.667, "bullish") == 106.667 -- the bar opened
    # above the floor, so the stop fills at the floor, not at the open.
    assert events[0].detail["exit_price"] == pytest.approx(FLOOR)
    assert store.get("p1").legs_realized[1]["r"] == pytest.approx(4.0 / 3.0)


def test_check_bar_bearish_tp1_sets_the_runner_floor_and_closes_at_it(tmp_path):
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_bear_active())
    mgr = PlanManager(store, lambda t: 100.0)
    events = mgr.check_bar("p1", bar_open=91.0, bar_high=92.0, bar_low=89.0)
    assert [e.transition for e in events] == ["tp1_partial"]
    assert store.get("p1").working_stop == pytest.approx(BEAR_FLOOR)
    events = mgr.check_bar("p1", bar_open=93.0, bar_high=100.0, bar_low=92.5)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_be"
    assert events[0].detail["exit_price"] == pytest.approx(BEAR_FLOOR)
    assert store.get("p1").legs_realized[1]["r"] == pytest.approx(4.0 / 3.0)


def test_legacy_partial_without_a_working_stop_falls_back_to_the_floor(tmp_path):
    # A PARTIAL plan persisted to data/plans.json before v39 has
    # working_stop set to the old breakeven -- or, for the oldest records,
    # to None. The None fallback resolves to the v39 floor (not entry), so
    # legacy live runners are tightened too and the reason label stays
    # correct rather than mislabelling a floor exit as "trail".
    feed = FakePriceFeed()
    feed.set_series("AAPL", [103.0])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_plan(direction="bullish", entry_type="market",
                    trigger_price=100.0, entry_price=100.0, stop_loss=95.0,
                    tp1=110.0, tp2=None, status=PlanStatus.PARTIAL,
                    working_stop=None,
                    legs_realized=[{"fraction": 0.5, "exit_price": 110.0,
                                    "r": 2.0, "reason": "tp1"}]))
    mgr = PlanManager(store, feed.get_price)
    events = mgr.poll()
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_be"
    assert events[0].detail["exit_price"] == pytest.approx(103.0)
