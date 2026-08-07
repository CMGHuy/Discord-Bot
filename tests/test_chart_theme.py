# tests/test_chart_theme.py
from swingbot.core.charts import chart_style as cs
import pytest

# ~85% of suite runtime lives in nine files like this one; excluded from
# the fast tier (scripts/testrun.py fast). See docs/claude/testing-cost.md.
pytestmark = pytest.mark.slow


def test_theme_dict_matches_module_constants():
    assert cs.THEME["bg-1"] == cs.CHART_BG
    assert cs.THEME["border-1"] == cs.GRID_COLOR
    assert cs.THEME["border-2"] == cs.SPINE_COLOR
    assert cs.THEME["text-1"] == cs.TEXT_COLOR
    assert cs.THEME["text-3"] == cs.MUTED_TEXT_COLOR
    assert cs.THEME["up"] == cs.UP_COLOR
    assert cs.THEME["down"] == cs.DOWN_COLOR
    assert cs.THEME["accent"] == cs.ENTRY_COLOR
    assert cs.THEME["warn"] == cs.CURRENT_PRICE_COLOR
    assert cs.THEME["purple"] == cs.TARGET2_COLOR


def test_theme_matches_tokens_css():
    """Parse tokens.css and compare the shared hex values byte-for-byte."""
    import re
    from pathlib import Path
    css = Path("swingbot/admin/static/tokens.css").read_text(encoding="utf-8")
    tokens = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", css))
    for key in ("bg-1", "border-1", "border-2", "text-1", "text-3", "up", "down", "accent", "warn", "purple"):
        assert tokens[key].lower() == cs.THEME[key].lower(), key


def test_generate_trade_chart_smoke(tmp_path, monkeypatch):
    """End-to-end render on synthetic OHLCV: produces a non-trivial PNG.
    No golden pixels (brittle) — existence + size only."""
    import numpy as np
    import pandas as pd
    from swingbot.core.charts.trade_chart import generate_trade_chart

    idx = pd.bdate_range("2025-01-01", periods=120)
    close = pd.Series(100 + np.cumsum(np.random.default_rng(7).normal(0, 1, 120)), index=idx)
    df = pd.DataFrame({"Open": close.shift(1).fillna(close), "High": close + 1,
                       "Low": close - 1, "Close": close, "Volume": 1_000_000}, index=idx)
    out = generate_trade_chart(
        ticker="TEST", df=df, entry=float(close.iloc[-1]),
        stop_loss=float(close.iloc[-1]) * 0.95, take_profit=float(close.iloc[-1]) * 1.08,
        direction="bullish", strategy="RSI", horizon_label="2w", out_dir=str(tmp_path),
    )
    assert out is not None
    import os
    assert os.path.getsize(out) > 20_000  # a real rendered chart, not a stub
