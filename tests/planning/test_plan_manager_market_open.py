"""V192-8: PlanManager drives a market plan waiting for its next open -- the open
decision (fill, through-stop and risk-cap cancels, the gap-target scratch, the
reclaim order), the premarket stop-cross debounce and the missed open. The
reclaim wait itself is V192-9. DB-backed (PlanStore on the shared swing-db)."""
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning import market_open as mo
from swingbot.core.planning import next_open_entry
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.risk_limits import planned_loss_pct
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan


def _et(day, hh, mm=0):
    return dt.datetime(2026, 10, day, hh, mm, tzinfo=US_MARKET_TZ)


ISSUED = _et(13, 15)            # Tuesday after the open: Wednesday's open decides
OPEN = _et(14, 9, 31)
PREMARKET = _et(14, 8)
AFTER_HOURS = _et(13, 16, 30)
PRE_TAPE = _et(14, 2, 30)


@pytest.fixture(autouse=True)
def _flags(monkeypatch):
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", True)
    monkeypatch.setattr(config, "QUIET_HOURS_START_BERLIN", 23)
    monkeypatch.setattr(config, "QUIET_HOURS_END_BERLIN", 8)


def _bull(**kw):
    base = dict(source="confluence", strategy="S/R Confluence", created_at="2026-10-13",
                issued_at=ISSUED.isoformat(), entry_type="market", direction="bullish",
                trigger_price=100.0, stop_loss=98.5, tp1=103.0, tp2=105.0,
                status=PlanStatus.PENDING, waits_next_open=True)
    base.update(kw)
    return _plan(**base)


def _bear(**kw):
    base = dict(direction="bearish", stop_loss=101.5, tp1=97.0, tp2=95.0)
    base.update(kw)
    return _bull(**base)


class _Log:
    """Records the trade-log hooks PlanManager._on_event calls."""

    def __init__(self):
        self.calls = []

    def record_plan_fill(self, plan_id, price):
        self.calls.append(("fill", plan_id, price))
        return "t1"

    def discard_plan_placeholder(self, plan_id):
        self.calls.append(("discard", plan_id))
        return True

    def close_plan_trade(self, plan_id, leg, status, conn=None):
        self.calls.append(("close", plan_id, leg["r"], status))

    def log_trade(self, **kw):
        self.calls.append(("log", kw["plan_id"]))
        return "t2"


def _env(plan, prices, trade_log=None):
    feed = FakePriceFeed()
    feed.set_series(plan.ticker, list(prices))
    store = PlanStore()
    store.add(plan)
    return store, PlanManager(store, feed.get_price, trade_log=trade_log)


def _tr(events):
    return [e.transition for e in events]


# --- routing ------------------------------------------------------------------

def test_a_waiting_plan_never_takes_the_stop_entry_fill():
    store, mgr = _env(_bull(), [100.5])          # >= trigger: _step_pending would fill
    assert mgr.poll(_et(13, 15, 30)) == []
    assert store.get("p1").status == PlanStatus.PENDING


def test_a_pending_market_plan_without_the_marker_keeps_todays_rule():
    store, mgr = _env(_bull(waits_next_open=None), [100.5])
    assert _tr(mgr.poll(_et(13, 15, 30))) == ["filled"]
    assert store.get("p1").entry_price == 100.5


# --- the open decision ----------------------------------------------------------

@pytest.mark.parametrize("make, price", [(_bull, 99.8), (_bear, 100.2)])
def test_the_open_fills_the_plan_at_the_open(make, price):
    store, mgr = _env(make(), [price])
    events = mgr.poll(OPEN)
    assert _tr(events) == ["filled"]
    assert events[0].detail == {"entry_price": price, "live_price": price, "fill": "open"}
    plan = store.get("p1")
    assert plan.status == PlanStatus.ACTIVE and plan.entry_price == price
    assert plan.status_history[-1]["reason"] == "next_open_fill"


@pytest.mark.parametrize("make, price", [(_bull, 98.5), (_bull, 97.0),
                                         (_bear, 101.5), (_bear, 103.0)])
def test_an_open_at_or_through_the_stop_cancels(make, price):
    store, mgr = _env(make(), [price])
    events = mgr.poll(OPEN)
    assert _tr(events) == ["cancelled_open_through_stop"]
    assert events[0].detail == {"live_price": price, "phase": "open"}
    plan = store.get("p1")
    assert plan.status == PlanStatus.CANCELLED and plan.entry_price is None
    assert plan.status_history[-1]["reason"] == "open_through_stop"
    assert plan.status_history[-1]["phase"] == "open"


@pytest.mark.parametrize("make, price", [(_bull, 100.6), (_bear, 99.4)])
def test_an_open_past_the_stop_ceiling_cancels_risk_cap(make, price):
    store, mgr = _env(make(), [price])
    events = mgr.poll(OPEN)
    assert _tr(events) == ["cancelled_risk_cap"]
    plan = store.get("p1")
    assert events[0].detail == {
        "entry_price": price, "stop_loss": plan.stop_loss,
        "planned_loss_pct": round(planned_loss_pct(price, plan.stop_loss), 4),
        "max_planned_loss_pct": 2.0}
    assert plan.status == PlanStatus.CANCELLED
    assert plan.status_history[-1]["reason"] == "risk_cap"


@pytest.mark.parametrize("make, level, price, order", [
    (_bull, 99.5, 99.5, "buy_stop"), (_bull, 99.5, 99.0, "buy_stop"),
    (_bear, 100.5, 100.5, "sell_stop"), (_bear, 100.5, 101.0, "sell_stop"),
])
def test_an_open_at_or_beyond_x_rests_for_a_reclaim(make, level, price, order):
    store, mgr = _env(make(reclaim_level=level, reclaim_atr=2.0), [price])
    events = mgr.poll(OPEN)
    assert _tr(events) == ["gap_reclaim_order"]
    assert events[0].detail == {"entry_price": 100.0, "open_price": price,
                                "reclaim_level": level, "order": order, "tif": "DAY"}
    plan = store.get("p1")
    assert plan.status == PlanStatus.PENDING and plan.entry_price is None
    assert plan.reclaim_session == "2026-10-14"
    assert (plan.reclaim_level, plan.reclaim_atr) == (level, 2.0)


@pytest.mark.parametrize("make, level, price", [(_bull, 99.5, 99.51), (_bear, 100.5, 100.49)])
def test_an_open_short_of_x_fills_at_the_open(make, level, price):
    store, mgr = _env(make(reclaim_level=level, reclaim_atr=2.0), [price])
    assert _tr(mgr.poll(OPEN)) == ["filled"]
    plan = store.get("p1")
    assert plan.entry_price == price and plan.reclaim_session is None


@pytest.mark.parametrize("make, price", [(_bull, 103.2), (_bear, 96.8)])
def test_an_open_beyond_tp1_is_a_0r_gap_target_scratch(make, price):
    log = _Log()
    store, mgr = _env(make(stop_ceiling_pct=10.0), [price], trade_log=log)
    events = mgr.poll(OPEN)
    assert _tr(events) == ["filled", "closed"]
    assert events[1].detail["reason"] == pm.GAP_TARGET_REASON == next_open_entry.GAP_TARGET_REASON
    assert events[1].detail["exit_price"] == price
    assert events[1].detail["leg"] == {"fraction": 1.0, "exit_price": price, "r": 0.0,
                                       "reason": "gap_target"}
    plan = store.get("p1")
    assert plan.status == PlanStatus.CLOSED and plan.entry_price == price
    assert [h["reason"] for h in plan.status_history] == ["next_open_fill", "gap_target"]
    # the fill moves the placeholder first; only then is the trade closed, at 0R
    assert log.calls == [("fill", "p1", price), ("close", "p1", 0.0, "closed")]


def test_the_open_fill_moves_the_placeholder_trade():
    log = _Log()
    _store, mgr = _env(_bull(), [99.8], trade_log=log)
    mgr.poll(OPEN)
    assert log.calls == [("fill", "p1", 99.8)]


# --- the premarket stop cross -----------------------------------------------------

@pytest.mark.parametrize("make, price", [(_bull, 98.4), (_bear, 101.6)])
def test_two_consecutive_extended_polls_through_the_stop_cancel(make, price):
    store, mgr = _env(make(), [price, price])
    assert mgr.poll(PREMARKET) == []
    assert store.get("p1").status == PlanStatus.PENDING
    events = mgr.poll(PREMARKET + dt.timedelta(minutes=1))
    assert _tr(events) == ["cancelled_open_through_stop"]
    assert events[0].detail == {"live_price": price, "phase": "premarket"}
    assert store.get("p1").status_history[-1]["phase"] == "premarket"
    assert mgr._premarket_hits == {}


def test_a_poll_back_inside_the_stop_resets_the_count():
    store, mgr = _env(_bull(), [98.4, 98.9, 98.4, 98.4])
    for minute in range(3):
        assert mgr.poll(PREMARKET + dt.timedelta(minutes=minute)) == []
    assert store.get("p1").status == PlanStatus.PENDING
    assert _tr(mgr.poll(PREMARKET + dt.timedelta(minutes=3))) == ["cancelled_open_through_stop"]


def test_the_alert_days_after_hours_count_too():
    _store, mgr = _env(_bull(), [98.0, 98.0])
    assert mgr.poll(AFTER_HOURS) == []
    assert _tr(mgr.poll(AFTER_HOURS + dt.timedelta(minutes=1))) == ["cancelled_open_through_stop"]


def test_a_pre_tape_print_never_counts():
    store, mgr = _env(_bull(), [98.0, 98.0])
    assert mgr.poll(PRE_TAPE) == []
    assert mgr.poll(PRE_TAPE + dt.timedelta(minutes=1)) == []
    assert store.get("p1").status == PlanStatus.PENDING and mgr._premarket_hits == {}


def test_one_premarket_hit_then_an_open_inside_the_stop_fills():
    _store, mgr = _env(_bull(), [98.4, 99.8])
    assert mgr.poll(PREMARKET) == []
    assert _tr(mgr.poll(OPEN)) == ["filled"]
    assert mgr._premarket_hits == {}


# --- the missed open ----------------------------------------------------------------

@pytest.mark.parametrize("now", [_et(14, 16, 30), _et(15, 10)])
def test_a_missed_deciding_open_expires_and_drops_the_placeholder(now):
    log = _Log()
    store, mgr = _env(_bull(), [99.8], trade_log=log)
    events = mgr.poll(now)
    assert _tr(events) == ["cancelled_expired"]
    assert events[0].detail == {"reason": "missed_open", "bars_waited": 0,
                                "session": "2026-10-14", "cancel_resting_order": True}
    plan = store.get("p1")
    assert plan.status == PlanStatus.CANCELLED and plan.entry_price is None
    assert plan.status_history[-1]["reason"] == "missed_open"
    assert log.calls == [("discard", "p1")]


def test_the_phase_table_covers_every_phase():
    assert set(pm._MARKET_PHASE_STEPS) == {mo.BEFORE, mo.EXTENDED, mo.OPEN, mo.MISSED,
                                          mo.WAITING, mo.AFTER_CLOSE}
    assert all(hasattr(PlanManager, name) for name in pm._MARKET_PHASE_STEPS.values())
