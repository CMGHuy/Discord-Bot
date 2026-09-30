"""v113 §3: the fade's plan -- sell limit at the signal close, 2% stop, m x R target, 7-bar hold."""
import pytest

from swingbot import config
from swingbot.core.backtesting.backtest import run_backtest
from swingbot.core.market.entry_filters import DEFAULT_PARAMS, gate_override
from swingbot.core.market.short_entries import FADE
from swingbot.core.planning import short_builders as sb
from swingbot.core.planning import stop_scope
from swingbot.core.planning.builders import build_strategy_plan
from swingbot.core.planning.lifecycle import apply_level_lifecycle
from swingbot.core.planning.params import EXIT_V2_PARAMS, PLAN_SHAPES
from swingbot.core.planning.plan_types import PlanStatus
from tests.market.test_fade_entries import HZ, UNMASKED, fade_df


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "REGIME_GATES_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", False, raising=False)


@pytest.mark.parametrize("m", [1.0, 1.25, 1.5])
def test_plan_short_fixes_the_geometry(monkeypatch, m):
    df, t = fade_df()
    monkeypatch.setitem(DEFAULT_PARAMS[FADE], "m", m)
    entry = float(df["Close"].iloc[t])
    stop, tp1, candidates = sb.plan_short(df, t, FADE, HZ, "bearish", entry=entry, atr_val=1.0)
    assert stop == pytest.approx(entry * 1.02)
    assert tp1 == pytest.approx(entry - m * (stop - entry))
    assert candidates == [tp1]


def test_plan_short_refuses_bullish_and_a_bar_without_a_signal():
    df, t = fade_df()
    assert sb.plan_short(df, t, FADE, HZ, "bullish", entry=float(df["Close"].iloc[t]), atr_val=1.0) is None
    assert sb.plan_short(df, t - 1, FADE, HZ, "bearish",
                         entry=float(df["Close"].iloc[t - 1]), atr_val=1.0) is None


def test_live_builder_emits_the_resting_order_plan():
    df, t = fade_df()
    entry = float(df["Close"].iloc[t])
    plan = build_strategy_plan(df, t, ticker="T", strategy=FADE, horizon_key=HZ, direction="bearish")
    assert (plan.entry_type, plan.expiry_bars, plan.entry_price, plan.status) == ("limit", 1, None, PlanStatus.PENDING)
    assert plan.trigger_price == pytest.approx(entry)
    assert plan.stop_loss == pytest.approx(entry * 1.02) and plan.tp1 == pytest.approx(entry * 0.98)
    assert plan.tp2 is None and plan.tp1_fraction == 1.0 and plan.breakeven_trigger_fraction == 1.0
    assert stop_scope.in_scope(FADE, "bearish")   # v104 fail-closed dollar-risk sizing applies


def test_the_level_lifecycle_never_moves_the_fade(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", True, raising=False)
    df, t = fade_df()
    entry = float(df["Close"].iloc[t])
    stop, tp1 = entry * 1.02, entry * 0.98
    out = apply_level_lifecycle(df, t, entry=entry, stop=stop, tp1=tp1, atr_val=1.0, direction="bearish",
                                strategy=FADE, horizon_key=HZ, candidate_levels=[tp1])
    assert out[:2] == (stop, tp1)


def _trades(df, gates=UNMASKED):
    with gate_override(FADE, gates):
        return run_backtest("T", df, FADE, HZ, exit_model="v2", scale_out=True, tp2_mode="levels").trades


def test_backtest_fills_on_the_next_bar_and_wins_at_one_r():
    df, t = fade_df()
    (trade,) = _trades(df)
    assert trade.entry_date == str(df.index[t].date()) and trade.direction == "bearish"
    assert trade.outcome == "win" and trade.r_multiple == pytest.approx(1.0) and trade.holding_days == 3


def test_a_masked_fade_trades_nothing():
    df, _ = fade_df()
    assert _trades(df, {"directions": ()}) == []


def test_no_trade_when_the_next_bar_never_reaches_the_limit():
    df, t = fade_df()
    close = float(df["Close"].iloc[t])
    df.iloc[t + 1, :4] = [close * 0.97, close * 0.99, close * 0.96, close * 0.975]
    assert _trades(df) == []


def test_the_time_stop_closes_at_the_seventh_bar_after_entry():
    df, _ = fade_df(tail=12, tail_step=0.999)
    (trade,) = _trades(df)
    assert trade.outcome == "timeout" and trade.holding_days == 8


def test_exit_params_and_plan_shape_rows():
    assert EXIT_V2_PARAMS[FADE] == {"trail_atr_mult": 2.5, "tp2": False}
    assert PLAN_SHAPES[FADE] == {"entry_type": "limit", "expiry_bars": 1,
                                 "tp1_fraction": 1.0, "breakeven_trigger_fraction": 1.0}
