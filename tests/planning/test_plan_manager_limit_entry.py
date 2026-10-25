"""v187 D3: live limit entries fill like the backtest.

A buy limit fills when a tick trades at or below it, a sell limit at or
above it, always AT the limit (the conservative twin of exit_sim's non-gap
limit fill). Beyond limit_cancel_level the order is cancelled; a tick
already at or through the stop opens nothing (the live twin of the
backtest's 0R gap_through_stop scratch). Every other entry type keeps the
stop-entry branch unchanged."""
import pytest

from swingbot import config
from swingbot.core.planning.exit_sim import _limit_entry_exit
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking.performance import TradeLog
from tests.fake_feed import FakePriceFeed
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

DIRECTIONS = ("bullish", "bearish")

#: Levels per side. The stop sits 1.5% from the 100.00 limit, inside the
#: default 2% stop ceiling, so a clean fill is never risk-capped.
_LEVELS = {
    "bullish": dict(trigger_price=100.0, stop_loss=98.5, tp1=102.0, tp2=104.0,
                    limit_cancel_level=101.0),
    "bearish": dict(trigger_price=100.0, stop_loss=101.5, tp1=98.0, tp2=96.0,
                    limit_cancel_level=99.0),
}

#: Ticks per side, named by what they do to a resting 100.00 limit.
_TICKS = {
    "bullish": dict(touch=100.0, through=99.4, short_of=100.5, beyond_cancel=101.2,
                    through_stop=98.4, at_stop=98.5),
    "bearish": dict(touch=100.0, through=100.6, short_of=99.5, beyond_cancel=98.8,
                    through_stop=101.6, at_stop=101.5),
}


@pytest.fixture(autouse=True)
def _plain_ceiling_and_clock(monkeypatch):
    # Out-of-scope plans keep the 2% stop ceiling; poll() reads the wall
    # clock, and the Berlin quiet window (23:00-08:00) would return [].
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)


def _limit(direction="bullish", **kw):
    base = dict(entry_type="limit", direction=direction, expiry_bars=5, **_LEVELS[direction])
    base.update(kw)
    return _plan(**base)


def _step(plan, price, **mgr_kw):
    """One _step_pending tick at `price`; returns (stored plan, events)."""
    store = PlanStore()
    store.add(plan)
    mgr = PlanManager(store, lambda ticker: price, **mgr_kw)
    events = mgr._step_pending(plan, price)
    return store.get(plan.plan_id), events


def _reason(plan):
    return plan.status_history[-1]["reason"]


# --- fills ---------------------------------------------------------------------

@pytest.mark.parametrize("direction", DIRECTIONS)
def test_a_touch_fills_at_the_limit(direction):
    plan, events = _step(_limit(direction), _TICKS[direction]["touch"])
    assert [e.transition for e in events] == ["filled"]
    assert events[0].detail == {"entry_price": 100.0, "live_price": 100.0}
    assert plan.status == PlanStatus.ACTIVE
    assert plan.entry_price == 100.0
    assert _reason(plan) == "limit_fill"


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_a_tick_through_the_limit_fills_at_the_limit_not_at_the_tick(direction):
    tick = _TICKS[direction]["through"]
    plan, events = _step(_limit(direction), tick)
    assert [e.transition for e in events] == ["filled"]
    assert events[0].detail == {"entry_price": 100.0, "live_price": tick}
    assert plan.entry_price == 100.0


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_strict_fill_refuses_an_exact_touch(direction):
    plan, events = _step(_limit(direction, limit_strict_fill=True), _TICKS[direction]["touch"])
    assert events == []
    assert plan.status == PlanStatus.PENDING


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_strict_fill_takes_a_trade_through(direction):
    plan, events = _step(_limit(direction, limit_strict_fill=True),
                         _TICKS[direction]["through"])
    assert [e.transition for e in events] == ["filled"]
    assert plan.entry_price == 100.0


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_a_tick_short_of_the_limit_does_nothing(direction):
    plan, events = _step(_limit(direction), _TICKS[direction]["short_of"])
    assert events == []
    assert plan.status == PlanStatus.PENDING


# --- cancel level --------------------------------------------------------------

@pytest.mark.parametrize("direction", DIRECTIONS)
def test_beyond_the_cancel_level_cancels(direction):
    tick = _TICKS[direction]["beyond_cancel"]
    plan, events = _step(_limit(direction), tick)
    assert [e.transition for e in events] == ["cancelled_limit"]
    assert events[0].detail == {"live_price": tick,
                                "limit_cancel_level": _LEVELS[direction]["limit_cancel_level"]}
    assert plan.status == PlanStatus.CANCELLED
    assert _reason(plan) == "limit_cancelled"
    assert plan.entry_price is None


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_an_equal_print_at_the_cancel_level_does_not_cancel(direction):
    level = _LEVELS[direction]["limit_cancel_level"]
    plan, events = _step(_limit(direction), level)
    assert events == []
    assert plan.status == PlanStatus.PENDING


def test_a_limit_without_a_cancel_level_never_cancels():
    plan, events = _step(_limit("bullish", limit_cancel_level=None), 150.0)
    assert events == []
    assert plan.status == PlanStatus.PENDING


@pytest.mark.parametrize("direction, cancel_level, tick", [
    ("bullish", 99.0, 99.5),      # fills (<= 100) and is above the 99.0 level
    ("bearish", 101.0, 100.5),    # fills (>= 100) and is below the 101.0 level
])
def test_a_tick_that_fills_and_is_beyond_the_cancel_level_fills(direction, cancel_level, tick):
    plan, events = _step(_limit(direction, limit_cancel_level=cancel_level), tick)
    assert [e.transition for e in events] == ["filled"]
    assert plan.entry_price == 100.0


# --- the stop ------------------------------------------------------------------

@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize("which", ["through_stop", "at_stop"])
def test_a_fill_at_or_through_the_stop_opens_nothing(direction, which):
    tick = _TICKS[direction][which]
    plan, events = _step(_limit(direction), tick)
    assert [e.transition for e in events] == ["cancelled_gap_through_stop"]
    assert events[0].detail == {"entry_price": 100.0, "live_price": tick,
                                "stop_loss": _LEVELS[direction]["stop_loss"]}
    assert plan.status == PlanStatus.CANCELLED
    assert _reason(plan) == "gap_through_stop"
    assert plan.entry_price is None


def test_a_stop_on_the_wrong_side_of_the_limit_is_a_gap_not_a_small_risk():
    # planned_loss_pct(100.0, 100.5) is 0.5% by abs() -- under the cap -- yet a
    # long filled at 100 with its stop at 100.5 is already stopped out.
    plan, events = _step(_limit("bullish", stop_loss=100.5), 99.8)
    assert [e.transition for e in events] == ["cancelled_gap_through_stop"]
    assert plan.status == PlanStatus.CANCELLED


@pytest.mark.parametrize("direction, stop", [("bullish", 97.0), ("bearish", 103.0)])
def test_a_limit_fill_over_the_risk_cap_is_cancelled(direction, stop):
    plan, events = _step(_limit(direction, stop_loss=stop), _TICKS[direction]["touch"])
    assert [e.transition for e in events] == ["cancelled_risk_cap"]
    assert events[0].detail == {"entry_price": 100.0, "stop_loss": stop,
                                "planned_loss_pct": pytest.approx(3.0),
                                "max_planned_loss_pct": pytest.approx(2.0)}
    assert plan.status == PlanStatus.CANCELLED
    assert _reason(plan) == "risk_cap"


# --- what stays as it was ------------------------------------------------------

def test_a_limit_plan_still_expires_on_its_bar_count_first():
    plan, events = _step(_limit("bullish"), 100.0, bar_count_fn=lambda ticker, created: 6)
    assert [e.transition for e in events] == ["cancelled_expired"]
    assert plan.status == PlanStatus.CANCELLED


def test_a_stop_entry_plan_keeps_its_fill_price_and_reason():
    plan, events = _step(_plan(entry_type="stop_entry", trigger_price=105.0,
                               stop_loss=104.0, tp1=110.0), 106.0)
    assert [e.transition for e in events] == ["filled"]
    assert events[0].detail == {"entry_price": 106.0, "live_price": 106.0}
    assert _reason(plan) == "stop_entry_fill"


# --- parity with the backtest --------------------------------------------------

#: (signal bar, non-gap fill bar, quiet bars): the fill bar opens on the far side
#: of the limit and trades back through it, so the backtest fills AT the limit.
_PARITY_BARS = {
    "bullish": [(100.5, 101.0, 99.5, 100.0), (100.6, 100.8, 99.7, 100.2),
                (100.2, 100.6, 99.9, 100.3), (100.3, 100.6, 99.9, 100.2)],
    "bearish": [(99.5, 100.5, 99.0, 100.0), (99.4, 100.3, 99.2, 99.8),
                (99.8, 100.1, 99.4, 99.7), (99.7, 100.1, 99.4, 99.8)],
}
#: The live tick is the fill bar's extreme print through the limit.
_PARITY_TICK = {"bullish": 99.7, "bearish": 100.3}


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_live_limit_fill_matches_the_backtest_on_a_non_gap_bar(direction):
    backtest = _limit_entry_exit(make_ohlcv(_PARITY_BARS[direction]), 0,
                                 _limit(direction, plan_id="bt"), False, 10)
    _, events = _step(_limit(direction), _PARITY_TICK[direction])
    assert backtest.entry_index == 1
    assert events[0].transition == "filled"
    assert events[0].detail["entry_price"] == backtest.entry_price == 100.0


# --- end to end through poll(): no trade behind a gap --------------------------

@pytest.fixture
def tlog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
        "sizing_mode": "risk_pct", "balance_history": [],
    })
    return TradeLog()


def test_a_gap_through_the_stop_leaves_no_trade_behind(tlog):
    tlog.log_trade(ticker="AAPL", strategy="Fibonacci", horizon_key="4w",
                   direction="bullish", confidence_level=4, confidence_label="High",
                   entry=100.0, stop_loss=98.5, take_profit=102.0, plan_id="p1")
    store = PlanStore()
    store.add(_limit("bullish"))
    mgr = PlanManager(store, FakePriceFeed([("AAPL", 98.4)]).get_price, trade_log=tlog)

    events = mgr.poll()

    assert [e.transition for e in events] == ["cancelled_gap_through_stop"]
    assert store.get("p1").status == PlanStatus.CANCELLED
    assert [t for t in tlog.get_trades(status=None, limit=None)
            if t.get("plan_id") == "p1"] == []
