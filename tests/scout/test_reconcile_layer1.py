"""v232 V232-7 / V232-7b: layer 1 values in the live trade's risk unit."""
import datetime as dt
import sys
from pathlib import Path

import pytest

from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_to_dict
from tests.helpers import make_ohlcv

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import layer1, records  # noqa: E402

START = "2026-10-05"            # Monday; 2026-10-05..10-16 are all NYSE sessions
FRICTIONS = {"slippage_bps": 5.0, "commission_per_trade": 1.0,
             "commission_risk_basis": 100.0, "min_risk_fraction": 0.0}


def _plan_doc(direction="bullish", **kw):
    long = direction == "bullish"
    base = dict(plan_id="P1", ticker="AAA", created_at="2026-10-06T15:00:00+00:00",
                source="confluence", strategy="RSI", horizon_key="2w", direction=direction,
                entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=3,
                stop_loss=98.0 if long else 102.0, tp1=104.0 if long else 96.0,
                tp1_fraction=1.0, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.CLOSED, status_history=[],
                issued_at="2026-10-06T15:00:00+00:00")
    base.update(kw)
    return plan_to_dict(TradePlanV2(**base))


def _rec(direction="bullish", trade_kw=None, journal_kw=None, **plan_kw):
    long = direction == "bullish"
    plan = _plan_doc(direction, **plan_kw)
    trade = {"id": "T1", "plan_id": "P1", "ticker": "AAA", "direction": direction,
             "entry": 100.2 if long else 99.8, "stop_loss": plan["stop_loss"],
             "take_profit": plan["tp1"], "opened_at": "2026-10-06T15:01:00+00:00",
             "closed_at": "2026-10-08T17:00:00+00:00", "exit_price": 104.0 if long else 96.0,
             "close_reason": "tp1", "legs": []}
    trade.update(trade_kw or {})
    journal = {"trade_id": "T1", "outcome": "win", "r_realized": 0.5, **(journal_kw or {})}
    return records.LiveRecord("P1", "AAA", direction, plan, trade, journal)


def _slip(*prices):
    return sum(prices) * 5.0 / 10_000.0


def test_live_risk_and_r_live_use_the_live_fill_and_the_issued_stop():
    rec = _rec(trade_kw={"stop_loss": 97.8}, journal_kw={"r_realized": 1.0})
    assert layer1.live_risk(rec) == pytest.approx(2.2)
    assert layer1.r_live(rec) == pytest.approx(2.4 / 2.2)


def test_r_live_is_unchanged_when_the_trade_keeps_the_issued_stop():
    assert layer1.r_live(_rec(journal_kw={"r_realized": -1.0})) == pytest.approx(-1.0)


def test_a_fill_on_the_issued_stop_raises():
    with pytest.raises(ValueError, match="issued stop"):
        layer1.live_risk(_rec(trade_kw={"entry": 98.0}))


def test_costs_a_short_pays_borrow_a_long_does_not():
    assert layer1.live_cost_r(_rec(), FRICTIONS) == pytest.approx(_slip(100.2, 104.0) / 2.2 + 0.02)
    borrow = 99.8 * 0.005 / 365.0 * 2 / 2.2                     # 10-06 -> 10-08, two days
    assert layer1.live_cost_r(_rec("bearish"), FRICTIONS) == pytest.approx(
        _slip(99.8, 96.0) / 2.2 + 0.02 + borrow)


def test_a_same_day_short_pays_no_borrow():
    rec = _rec("bearish", trade_kw={"closed_at": "2026-10-06T19:00:00+00:00"})
    assert layer1.live_cost_r(rec, FRICTIONS) == pytest.approx(_slip(99.8, 96.0) / 2.2 + 0.02)


def test_costs_weight_each_exit_leg_by_its_fraction():
    legs = [{"fraction": 0.5, "exit_price": 104.0, "r": 1.7, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 100.2, "r": 0.0, "reason": "runner_be"}]
    cost = layer1.live_cost_r(_rec(trade_kw={"legs": legs}), FRICTIONS)
    assert cost == pytest.approx(_slip(100.2, 0.5 * 104.0, 0.5 * 100.2) / 2.2 + 0.02)


def test_a_trade_without_exit_price_or_legs_prices_its_exit_at_the_entry():
    cost = layer1.live_cost_r(_rec(trade_kw={"exit_price": None}), FRICTIONS)
    assert cost == pytest.approx(_slip(100.2, 100.2) / 2.2 + 0.02)


def test_zero_frictions_cost_nothing_on_a_long():
    zero = {**FRICTIONS, "slippage_bps": 0.0, "commission_per_trade": 0.0}
    assert layer1.live_cost_r(_rec(), zero) == 0.0


def test_bar_position():
    df = make_ohlcv([100.0] * 5, start=START)
    assert layer1.bar_position(df, dt.date(2026, 10, 6)) == 1
    assert layer1.bar_position(df, dt.date(2026, 10, 3)) is None
    assert layer1.bar_position(df.iloc[0:0], dt.date(2026, 10, 6)) is None
    assert layer1.bar_position(None, dt.date(2026, 10, 6)) is None


@pytest.mark.parametrize("outcome,r,expected", [
    ("win", -0.3, "win"), ("timeout", 0.8, "timeout"), ("scratch", 0.4, "scratch"),
    ("closed", 0.05, "scratch"), ("closed", -0.05, "scratch"), ("closed", 0.2, "win"),
    ("closed", -0.2, "loss"), (None, 0.5, "win"), ("no_trade", 0.0, "scratch"),
])
def test_outcome_class_keeps_engine_and_journal_labels(outcome, r, expected):
    assert layer1.outcome_class(outcome, r) == expected
