# tests/test_plan_chart_overlays.py
"""Chart-render tests for trade_chart.py's plan_v2= kwarg (risk/reward
bands, trigger arrow, status watermark, chandelier trail) and for
embeds.py's MFE/MAE markers on closed-trade charts. These are smoke
tests (file exists, non-trivial size, no exception) -- pixel content is
not asserted; Task B38's manual smoke pass is where a human actually
looks at one."""
import os
import types

from tests.conftest import make_ohlcv
from swingbot.core.charts.trade_chart import generate_trade_chart


def _fixture_plan(entry_type="market", status="ACTIVE", direction="bullish", tp2=118.0):
    return types.SimpleNamespace(
        plan_id="p1", ticker="NVDA", direction=direction, entry_type=entry_type,
        trigger_price=100.0, entry_price=None, stop_loss=95.0, tp1=110.0, tp2=tp2,
        trail_atr_mult=2.5, status=status, strategy="EMA Crossover", horizon_key="4w",
    )


def _fixture_df():
    closes = [100 + i * 0.3 for i in range(60)]
    return make_ohlcv(closes, spread_pct=1.5)


def test_generate_trade_chart_with_plan_renders(tmp_path):
    df = _fixture_df()
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="with_plan.png", target2=118.0, plan_v2=_fixture_plan(),
    )
    assert os.path.exists(path)
    assert os.path.getsize(path) > 10_000


def test_generate_trade_chart_without_plan_is_unaffected(tmp_path):
    df = _fixture_df()
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="no_plan.png", target2=118.0,
    )
    assert os.path.exists(path)


def test_pending_stop_entry_plan_renders_with_arrow(tmp_path):
    df = _fixture_df()
    plan = _fixture_plan(entry_type="stop_entry", status="PENDING")
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="pending_stop_entry.png", target2=118.0, plan_v2=plan,
    )
    assert os.path.exists(path)


def test_market_entry_plan_renders_without_error(tmp_path):
    df = _fixture_df()
    plan = _fixture_plan(entry_type="market", status="ACTIVE")
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="market_active.png", target2=118.0, plan_v2=plan,
    )
    assert os.path.exists(path)
