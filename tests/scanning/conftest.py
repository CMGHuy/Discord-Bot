import pytest

from swingbot.core.market.levels import Scenario


@pytest.fixture
def sample_scenario():
    """A representative bullish scenario with real Scenario field values --
    used to compare the legacy and unified score_confidence() paths (v32
    Task 6) without either path having to special-case a mock."""
    return Scenario(
        direction="bullish",
        entry=100.0,
        market_price=100.0,
        stop_loss=98.0,
        stop_sources=["EMA", "VWAP"],
        stop_distance_pct=2.0,
        tight_stop=False,
        atr_floor_pct=1.5,
        take_profit=106.0,
        target_distance_pct=6.0,
        target_sources=["EMA", "VWAP", "Fibonacci"],
        target2_price=None,
        target2_distance_pct=None,
        target2_sources=None,
    )
