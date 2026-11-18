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


from swingbot.core.backtesting.instrument.contract import V2_FILLS, ZERO_COSTS, resolve  # noqa: E402
from swingbot.core.planning import exit_sim, exit_sim_v2  # noqa: E402
from swingbot.core.planning.exit_sim import ExitResult  # noqa: E402

F = (100.0, 100.6, 99.6, 100.0)
D1 = (100.0, 100.8, 99.6, 100.5)            # 2026-10-06: issue and live fill session
LONG_ROWS = {
    "win": [F, D1, (100.5, 101.0, 100.0, 100.8), (100.8, 104.5, 100.5, 104.0)]
           + [(104.0, 104.4, 103.6, 104.0)] * 6,
    "loss": [F, D1, (100.5, 100.9, 99.9, 100.2), (100.0, 100.3, 97.5, 97.8)]
            + [(97.8, 98.2, 97.4, 97.8)] * 6,
    "scratch": [F, D1, (100.5, 102.5, 100.4, 102.0), (101.5, 101.8, 100.0, 100.5)]
               + [(100.5, 100.9, 100.1, 100.5)] * 6,
    "timeout": [F, (100.0, 100.5, 99.9, 100.2)] + [(100.2, 100.5, 99.9, 100.2)] * 8,
}


def _mirror(rows):
    """A long fixture reflected around 100: a short with the same path."""
    return [(200 - o, 200 - lo, 200 - hi, 200 - c) for o, hi, lo, c in rows]


def _bars(outcome, direction="bullish"):
    rows = LONG_ROWS[outcome]
    return make_ohlcv(rows if direction == "bullish" else _mirror(rows), start=START)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("outcome", ["win", "loss", "scratch", "timeout"])
def test_each_outcome_long_and_short_telescopes(direction, outcome):
    rec = _rec(direction, **({"hold_cap_bars": 3} if outcome == "timeout" else {}))
    live = layer1.r_live(rec)
    for model in layer1.FILL_MODELS:
        v = layer1.score(rec, _bars(outcome, direction), model)
        if model == "v1":
            assert v.exit_only_outcome == outcome and v.exit_only_class == outcome
        eff = layer1.effects(live, v)
        assert live - v.r_as_backtest == pytest.approx(eff["exit"] + eff["entry"])


def test_as_backtest_is_converted_to_the_live_unit_with_the_rebased_figure_beside_it():
    v = layer1.score(_rec(), _bars("win"), "v1")
    assert v.r_exit_only == pytest.approx(3.8 / 2.2, abs=1e-3)
    assert v.r_rebased == pytest.approx(1.4, abs=1e-3)            # entry at the 10-06 close, 100.5
    assert v.r_as_backtest == pytest.approx(1.4 * 2.5 / 2.2, abs=1e-3)
    assert v.stop_shift_pct == pytest.approx((2.5 / 2.2 - 1) * 100)
    assert v.backtest_no_fill is False


def test_the_rebased_figure_equals_the_live_unit_when_the_entries_match():
    v = layer1.score(_rec(trade_kw={"entry": 100.5}), _bars("win"), "v1")
    assert v.r_as_backtest == pytest.approx(v.r_rebased)
    assert v.stop_shift_pct == pytest.approx(0.0)


def test_v1_values_match_the_engines():
    rec, df = _rec(), _bars("loss")
    v = layer1.score(rec, df, "v1")
    plan, _ = records.rehydrate(rec.plan)
    assert v.r_rebased == exit_sim.simulate_exit(df, 1, plan, scale_out=False).r_total
    plan, _ = records.rehydrate(rec.plan)
    assert v.r_exit_only == exit_sim.simulate_exit_from_fill(
        df, 1, 100.2, plan, scale_out=False, fill_bar_check=False).r_total


def test_exit_only_starts_the_bar_after_the_fill():
    rows = list(LONG_ROWS["win"])
    rows[1] = (100.0, 100.8, 97.0, 100.5)          # the fill day's wick runs through the stop
    v = layer1.score(_rec(), make_ohlcv(rows, start=START), "v1")
    assert v.exit_only_outcome == "win"


def test_v2_values_are_gross():
    assert layer1.GROSS_V2.cost_model == ZERO_COSTS
    assert layer1.GROSS_V2.fill_model == V2_FILLS
    rec, df = _rec(), _bars("win")
    v = layer1.score(rec, df, "v2")
    plan, _ = records.rehydrate(rec.plan)
    gross = exit_sim_v2.simulate_exit_v2_from_fill(df, 1, 100.2, plan, layer1.GROSS_V2,
                                                   scale_out=False, fill_bar_check=False)
    plan, _ = records.rehydrate(rec.plan)
    costed = exit_sim_v2.simulate_exit_v2_from_fill(df, 1, 100.2, plan, resolve("v2"),
                                                    scale_out=False, fill_bar_check=False)
    assert v.r_exit_only == gross.r_total
    assert costed.r_total < gross.r_total
    plan, _ = records.rehydrate(rec.plan)
    assert v.r_rebased == exit_sim_v2.simulate_exit_v2(
        df, 1, plan, layer1.GROSS_V2, scale_out=False).r_total


def test_scale_out_follows_tp1_fraction():
    rec, df = _rec(tp1_fraction=0.5, tp2=108.0), _bars("win")
    plan, _ = records.rehydrate(rec.plan)
    expected = exit_sim.simulate_exit(df, 1, plan, scale_out=True).r_total
    assert layer1.score(rec, df, "v1").r_rebased == expected


def test_a_trigger_the_backtest_never_reaches_is_a_backtest_no_fill():
    rec = _rec(entry_type="stop_entry", trigger_price=106.0, entry_price=None)
    v = layer1.score(rec, _bars("win"), "v1")
    assert v.backtest_no_fill is True
    assert (v.r_as_backtest, v.r_rebased, v.stop_shift_pct) == (None, None, None)
    eff = layer1.effects(0.3, v)
    assert eff["entry"] is None and eff["exit"] == pytest.approx(0.3 - v.r_exit_only)


def test_a_gap_through_stop_scratch_counts_as_no_fill():
    gap = ExitResult(outcome="scratch", runner_outcome=None, entry_index=2, exit_index=2,
                     entry_price=97.0, r_total=0.0,
                     legs=[{"fraction": 1.0, "exit_price": 97.0, "r": 0.0,
                            "reason": "gap_through_stop"}])
    assert layer1._no_fill(gap) is True
    clean = ExitResult(outcome="scratch", runner_outcome=None, entry_index=2, exit_index=4,
                       entry_price=100.0, r_total=0.0,
                       legs=[{"fraction": 1.0, "exit_price": 100.0, "r": 0.0,
                              "reason": "breakeven_stop"}])
    assert layer1._no_fill(clean) is False


@pytest.mark.parametrize("trade_kw,plan_kw,what", [
    ({"opened_at": "2026-10-20T15:00:00+00:00"}, {}, "fill"),
    ({}, {"issued_at": "2026-09-28T15:00:00+00:00"}, "signal"),
])
def test_a_missing_bar_raises(trade_kw, plan_kw, what):
    with pytest.raises(ValueError, match=what):
        layer1.score(_rec(trade_kw=trade_kw, **plan_kw), _bars("win"), "v1")


def test_an_unknown_fill_model_raises():
    with pytest.raises(ValueError, match="fill model"):
        layer1.score(_rec(), _bars("win"), "v3")


def test_score_never_mutates_the_exported_plan_doc():
    rec = _rec(tp1_fraction=0.5, tp2=108.0)
    before = dict(rec.plan)
    layer1.score(rec, _bars("win"), "v1")
    layer1.score(rec, _bars("win"), "v2")
    assert rec.plan == before


def test_would_fill_is_a_bare_boolean():
    df = _bars("win")
    never = _rec(entry_type="stop_entry", trigger_price=106.0, entry_price=None)
    assert layer1.would_fill(never, df, "v1") is False
    assert layer1.would_fill(_rec(), df, "v1") is True
    assert layer1.would_fill(_rec(issued_at="2026-09-28T15:00:00+00:00"), df, "v2") is None
