"""v129 trap (spec § Code changes, "Known trap, designed out"): v92's stall
exit was unmeasurable because backtest-built plans never set its field. These
assert acceptance_level on BACKTEST-constructed plans for both populations,
and on the live constructors that share the same helper."""
import types

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.market.entry_filters import break_retest_level_at
from swingbot.core.planning.builders import build_confluence_plan, build_strategy_plan
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df
from tests.fixtures.ohlcv_parity import load_ohlcv
from tests.helpers import make_ohlcv

pytestmark = pytest.mark.slow


def _captured_break_retest(monkeypatch, horizon_key="2m"):
    """(signal_index, plan) for every plan run_backtest's v2 loop built."""
    seen = []
    real = bt.simulate_exit

    def capture(df, i, plan, **kw):
        seen.append((int(i), plan))
        return real(df, i, plan, **kw)

    monkeypatch.setattr(bt, "simulate_exit", capture)
    df = load_ohlcv("DELL")
    bt.run_backtest("DELL", df, "Break & Retest", horizon_key,
                    exit_model="v2", scale_out=True, tp2_mode="levels")
    return df, seen


def test_backtest_break_retest_plans_carry_acceptance_level(monkeypatch):
    _, seen = _captured_break_retest(monkeypatch)
    assert seen, "DELL 2m must still produce Break & Retest plans"
    assert all(plan.acceptance_level is not None for _, plan in seen)


def test_backtest_break_retest_level_is_the_broken_level(monkeypatch):
    df, seen = _captured_break_retest(monkeypatch)
    for i, plan in seen:
        assert plan.acceptance_level == break_retest_level_at(df, i, "2m", plan.direction)


def test_live_break_retest_plan_carries_the_same_level(monkeypatch):
    df, seen = _captured_break_retest(monkeypatch)
    for i, plan in seen:
        live = build_strategy_plan(df, i, ticker="DELL", strategy="Break & Retest",
                                   horizon_key="2m", direction=plan.direction)
        assert live is not None
        assert live.acceptance_level == plan.acceptance_level


def test_confluence_replay_plans_carry_acceptance_level():
    out = bs.replay_scenarios("AAPL", _structured_df(), "4w", gates=GATES)
    assert out, "fixture must produce at least one confluence plan"
    assert all(plan.acceptance_level is not None for _, plan in out)


def test_confluence_acceptance_level_is_the_pre_clamp_stop(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    scenario = types.SimpleNamespace(
        direction="bullish", entry=100.0, stop_loss=96.0, take_profit=104.0,
        target_sources=["Rolling S/R"], stop_sources=["Rolling S/R"])
    plan = build_confluence_plan(scenario, make_ohlcv([100.0] * 60), ticker="XYZ",
                                 horizon_key="4w", primary_strategy="S/R Confluence")
    assert plan is not None
    assert plan.stop_loss == pytest.approx(98.25)       # clamped, unchanged by v129
    assert plan.acceptance_level == pytest.approx(96.0)  # the level, pre-clamp
