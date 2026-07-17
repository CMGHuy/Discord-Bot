import os

import pytest

from swingbot.core.charts.trade_chart import generate_trade_chart
from tests.helpers import make_ohlcv
from tests.test_plan_engine_model import _plan


@pytest.mark.parametrize("tp2", [104.0, None])
def test_chart_renders_with_plan_overlays(tmp_path, tp2):
    df = make_ohlcv([100 + i * 0.2 for i in range(120)])
    plan = _plan(entry_type="stop_entry", trigger_price=102.5,
                stop_loss=98.0, tp1=103.5, tp2=tp2)
    path = generate_trade_chart("AAPL", df, entry=102.5, stop_loss=98.0,
                                take_profit=103.5, direction="bullish",
                                strategy="Fibonacci", horizon_label="4-Week Swing",
                                out_dir=str(tmp_path), plan_v2=plan)
    assert path and os.path.exists(path)
    assert os.path.getsize(path) > 10_000     # non-trivial PNG (convention)


def test_chart_without_plan_unchanged(tmp_path):
    df = make_ohlcv([100 + i * 0.2 for i in range(120)])
    path = generate_trade_chart("AAPL", df, entry=102.5, stop_loss=98.0,
                                take_profit=103.5, direction="bullish",
                                strategy="Fibonacci", horizon_label="4-Week Swing",
                                out_dir=str(tmp_path))
    assert path and os.path.exists(path)      # legacy call keeps working


def test_partial_plan_renders_trail_and_banked_annotation(tmp_path):
    from swingbot.core.plan_engine import PlanStatus, record_transition
    df = make_ohlcv([100 + i * 0.3 for i in range(120)])
    plan = _plan(entry_price=100.0, stop_loss=95.0, tp1=110.0,
                working_stop=112.0, runner_high_close=float(df["Close"].max()))
    record_transition(plan, PlanStatus.ACTIVE, at="t")
    record_transition(plan, PlanStatus.PARTIAL, at="t")
    path = generate_trade_chart("AAPL", df, entry=100.0, stop_loss=95.0,
                                take_profit=110.0, direction="bullish",
                                strategy="Fibonacci", horizon_label="4-Week Swing",
                                out_dir=str(tmp_path), plan_v2=plan)
    assert path and os.path.getsize(path) > 10_000
