import pytest
from swingbot.core.market.strategy_types import HORIZONS


def test_every_horizon_defines_an_rs_window():
    for key, settings in HORIZONS.items():
        assert "rs_window" in settings, f"{key} is missing rs_window"


def test_rs_windows_increase_with_horizon_length():
    """A 2w setup asks 'strong lately?'; a 9m setup asks 'strong for months?'.
    A laggard-over-6-months says little about a two-week swing."""
    windows = [HORIZONS[k]["rs_window"] for k in HORIZONS]
    assert windows == sorted(windows)


def test_shortest_and_longest_windows_are_sane():
    assert HORIZONS["2w"]["rs_window"] == 21      # ~1 trading month
    assert HORIZONS["9m"]["rs_window"] == 189     # ~9 trading months
