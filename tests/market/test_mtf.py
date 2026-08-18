import pandas as pd
import pytest

from swingbot.core.market.mtf import (
    horizon_trend, adjacent_horizon, MACRO_ANCHOR_HORIZON, adjacent_aligned, macro_aligned,
)


def _frame(closes):
    return pd.DataFrame({
        "Open": closes, "High": [c * 1.01 for c in closes],
        "Low": [c * 0.99 for c in closes], "Close": closes,
        "Volume": [1_000_000] * len(closes),
    })


def test_rising_series_is_bullish():
    """ema_fast above ema_slow = bullish, using the horizon's own pair."""
    assert horizon_trend(_frame([100 + i for i in range(120)]), "4w") == "bullish"


def test_falling_series_is_bearish():
    assert horizon_trend(_frame([300 - i for i in range(120)]), "4w") == "bearish"


def test_insufficient_history_returns_none():
    """None means 'unknown', which callers must treat as an exemption --
    never as agreement."""
    assert horizon_trend(_frame([100, 101, 102]), "6m") is None


@pytest.mark.parametrize("horizon,expected", [
    ("2w", "4w"), ("4w", "2m"), ("2m", "3m"), ("3m", "4m"),
    ("4m", "5m"), ("5m", "6m"), ("6m", "7m"), ("7m", "8m"), ("8m", "9m"),
])
def test_adjacent_horizon_chains_upward(horizon, expected):
    assert adjacent_horizon(horizon) == expected


def test_longest_horizon_has_no_adjacent():
    """9m is the top of the ladder: exempt, not failed."""
    assert adjacent_horizon("9m") is None


def test_macro_anchor_is_six_months():
    assert MACRO_ANCHOR_HORIZON == "6m"


def test_adjacent_aligned_when_next_horizon_agrees():
    df = _frame([100 + i for i in range(300)])
    r = adjacent_aligned(df, "2w", "bullish")
    assert r["status"] == "aligned"
    assert r["trend"] == "bullish"


def test_adjacent_opposed_when_next_horizon_disagrees():
    df = _frame([100 + i for i in range(300)])
    r = adjacent_aligned(df, "2w", "bearish")
    assert r["status"] == "opposed"


def test_longest_horizon_is_exempt_not_aligned():
    """The distinction that matters: 9m has nothing above it. If this returned
    'aligned' the gate would silently pass every 9m scenario as confirmed."""
    df = _frame([100 + i for i in range(300)])
    r = adjacent_aligned(df, "9m", "bullish")
    assert r["status"] == "exempt"
    assert "no higher horizon" in r["reason"]


def test_short_history_is_exempt_not_opposed():
    r = adjacent_aligned(_frame([100, 101, 102]), "2w", "bullish")
    assert r["status"] == "exempt"


def test_macro_exempt_at_and_above_the_anchor():
    """6m..9m cannot anchor to 6m -- a horizon cannot check itself."""
    df = _frame([100 + i for i in range(300)])
    for horizon in ("6m", "7m", "8m", "9m"):
        assert macro_aligned(df, horizon, "bullish")["status"] == "exempt"


def test_macro_evaluates_below_the_anchor():
    df = _frame([100 + i for i in range(300)])
    assert macro_aligned(df, "2w", "bullish")["status"] == "aligned"
    assert macro_aligned(df, "2w", "bearish")["status"] == "opposed"
