import numpy as np

from swingbot.core.macro.breadth import breadth, breadth_state
from tests.conftest import make_ohlcv


def _universe():
    """10 tickers with 220 bars: 7 in uptrends (above both DMAs),
    3 in downtrends (below both)."""
    bars = {}
    for i in range(7):
        bars[f"UP{i}"] = make_ohlcv(100.0 * (1 + 0.002) ** np.arange(220))
    for i in range(3):
        bars[f"DN{i}"] = make_ohlcv(100.0 * (1 - 0.002) ** np.arange(220))
    return bars


def test_golden_percentages():
    b = breadth(_universe())
    assert b == {"pct_above_50dma": 70.0, "pct_above_200dma": 70.0, "n": 10}
    assert breadth_state(b) == "healthy"          # >= 60%


def test_state_bands():
    assert breadth_state({"pct_above_50dma": 40.0}) == "weak"
    assert breadth_state({"pct_above_50dma": 50.0}) == "mixed"
    assert breadth_state({"pct_above_50dma": None}) == "unknown"


def test_short_history_excluded():
    bars = _universe()
    bars["NEW"] = make_ohlcv(np.full(100, 50.0))   # < 200 bars: not countable
    assert breadth(bars)["n"] == 10


def test_empty_universe():
    b = breadth({})
    assert b["n"] == 0 and b["pct_above_50dma"] is None
