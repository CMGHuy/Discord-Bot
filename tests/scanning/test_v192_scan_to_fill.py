"""V192-13: the live scan builds a waiting market plan with a_t and X from
completed bars and the alert time stamped; the manager fills it at the next open
and moves the placeholder trade there. DB-backed for the manager half."""
import datetime as dt
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning import gap_reclaim as gr
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.core.scanning import engine, strategy_pass
from tests.fake_feed import FakePriceFeed
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_market_open import _Log, _flags  # noqa: F401

AFTER_CLOSE = dt.datetime(2026, 10, 13, 16, 30, tzinfo=US_MARKET_TZ)
INTRADAY = dt.datetime(2026, 10, 13, 12, 0, tzinfo=US_MARKET_TZ)
OPEN = dt.datetime(2026, 10, 14, 9, 31, tzinfo=US_MARKET_TZ)


@pytest.fixture(autouse=True)
def v2_on(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)


@pytest.fixture
def knobs(monkeypatch):
    def set_(next_open, g):
        monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", next_open)
        monkeypatch.setattr(config, "GAP_RECLAIM_ATR", g)
    return set_


def _frame(n=60):
    """Bars ending Tuesday 2026-10-13, ATR14 real (H - L = 5% of the price, so
    a_t = 5 and X = E -/+ 1.25 sits inside the 1.5 stop). The 20-bar high (102.5)
    and low (97.5) stay beyond the scenario target, so the plan is a market plan,
    not a breakout stop entry."""
    df = make_ohlcv([100.0] * n, spread=0.025)
    df.index = pd.bdate_range(end="2026-10-13", periods=n)
    return df


def _scenario(direction="bullish"):
    stop, target = (98.5, 102.4) if direction == "bullish" else (101.5, 97.6)
    return SimpleNamespace(direction=direction, entry=100.0, stop_loss=stop, take_profit=target,
                           target_sources=["EMA21"], stop_sources=["Rolling support"])


def _attach(df, now, direction="bullish"):
    item = SimpleNamespace(plan_v2=None)
    engine.attach_plan_v2(item, _scenario(direction), df, "AAPL", "4w", level_map=None,
                          issued_at=now.isoformat(), now=now)
    return item.plan_v2


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_after_the_close_the_scan_builds_a_waiting_plan_from_bar_t(knobs, direction):
    knobs(True, 0.25)
    df = _frame()
    plan = _attach(df, AFTER_CLOSE, direction)
    assert plan.status == PlanStatus.PENDING and plan.entry_price is None
    assert gr.waits_for_open(plan) and plan.issued_at == AFTER_CLOSE.isoformat()
    a_t = gr.atr_at(df, len(df) - 1)
    assert plan.reclaim_atr == a_t
    assert plan.reclaim_level == gr.reclaim_level_for(plan.trigger_price, a_t, 0.25, direction)


def test_intraday_the_forming_bar_never_reaches_a_t(knobs):
    knobs(True, 0.25)
    df = _frame()
    plan = _attach(df, INTRADAY)
    assert plan.reclaim_atr == gr.atr_at(df.iloc[:-1], len(df) - 2)
    moved = df.copy()
    moved.iloc[-1, moved.columns.get_loc("High")] *= 1.3     # the forming bar's range moves
    moved.iloc[-1, moved.columns.get_loc("Low")] *= 0.8
    again = _attach(moved, INTRADAY)
    assert (again.reclaim_atr, again.reclaim_level) == (plan.reclaim_atr, plan.reclaim_level)


def test_next_open_alone_stamps_no_veto(knobs):
    knobs(True, 0.0)
    plan = _attach(_frame(), AFTER_CLOSE)
    assert gr.waits_for_open(plan)
    assert plan.reclaim_atr is None and plan.reclaim_level is None


def test_knob_off_the_scan_plan_is_todays(knobs):
    knobs(False, 0.0)
    plan = _attach(_frame(), INTRADAY)
    assert plan.status == PlanStatus.ACTIVE and plan.entry_price == plan.trigger_price
    assert not {"reclaim_atr", "reclaim_level", "reclaim_session", "waits_next_open"} & set(
        plan_to_dict(plan))


def _run(plan, prices, polls):
    log = _Log()
    store = PlanStore()
    store.add(plan)
    feed = FakePriceFeed()
    feed.set_series(plan.ticker, prices)
    mgr = PlanManager(store, feed.get_price, trade_log=log)
    events = [e for now in polls for e in mgr.poll(now)]
    return store.get(plan.plan_id), events, log


def test_scan_to_fill_at_the_next_open(knobs):
    knobs(True, 0.25)
    plan = _attach(_frame(), AFTER_CLOSE)
    open_price = round(plan.trigger_price - 0.1, 2)            # short of X: the baseline fill
    stored, events, log = _run(plan, [open_price], [OPEN])
    assert "filled" in [e.transition for e in events]
    assert stored.status == PlanStatus.ACTIVE and stored.entry_price == open_price
    assert ("fill", plan.plan_id, open_price) in log.calls


def test_scan_to_reclaim_fill_at_e(knobs):
    knobs(True, 0.25)
    plan = _attach(_frame(), AFTER_CLOSE)
    open_price = round((plan.reclaim_level + plan.stop_loss) / 2, 2)   # at/beyond X, inside the stop
    through = round(plan.trigger_price + gr.tick_for(plan.trigger_price), 2)
    stored, events, log = _run(plan, [open_price, through],
                               [OPEN, OPEN + dt.timedelta(minutes=30)])
    assert [e.transition for e in events][:1] == ["gap_reclaim_order"]
    assert stored.status == PlanStatus.ACTIVE and stored.entry_price == plan.trigger_price
    assert ("fill", plan.plan_id, plan.trigger_price) in log.calls


def test_scan_to_no_reclaim_cancel_drops_the_placeholder(knobs):
    knobs(True, 0.25)
    plan = _attach(_frame(), AFTER_CLOSE)
    open_price = round((plan.reclaim_level + plan.stop_loss) / 2, 2)
    stored, events, log = _run(plan, [open_price, open_price],
                               [OPEN, dt.datetime(2026, 10, 14, 16, 5, tzinfo=US_MARKET_TZ)])
    assert "cancelled_gap_no_reclaim" in [e.transition for e in events]
    assert stored.status == PlanStatus.CANCELLED
    assert ("discard", plan.plan_id) in log.calls


# --- the strategy pass's alert time --------------------------------------------------

NOW = dt.datetime(2026, 10, 13, 14, 0, tzinfo=dt.timezone.utc)


def test_a_waiting_strategy_plan_gets_the_alert_time():
    plan = _plan(status=PlanStatus.PENDING, waits_next_open=True, issued_at=None)
    strategy_pass._stamp_issued_for_open(plan, NOW)
    assert plan.issued_at == NOW.isoformat()


@pytest.mark.parametrize("kw", [dict(status=PlanStatus.ACTIVE, waits_next_open=None),
                                dict(entry_type="stop_entry", waits_next_open=None),
                                dict(status=PlanStatus.PENDING, waits_next_open=True,
                                     issued_at="2026-10-13T12:00:00+00:00")])
def test_every_other_strategy_plan_is_left_alone(kw):
    plan = _plan(**kw)
    before = plan.issued_at
    strategy_pass._stamp_issued_for_open(plan, NOW)
    assert plan.issued_at == before
