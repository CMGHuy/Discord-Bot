import pytest
from swingbot.core.market.strategy_types import HORIZONS


def test_every_horizon_defines_an_rs_window():
    for key, settings in HORIZONS.items():
        assert "rs_window" in settings, f"{key} is missing rs_window"


def test_rs_windows_increase_with_horizon_length():
    """A 2w setup asks 'strong lately?'; a 9m setup asks 'strong for months?'.
    A laggard-over-6-months says little about a two-week swing.

    `rs_window` has no live consumer in production -- the scan gate runs the
    flat `RS_WINDOW=63` (edge/factors.py) for every horizon regardless of
    this table. These assertions guard the table's shape only;
    `scripts/backtest/measure_rs_gate_effect.py` consumes it for a
    secondary/non-primary measurement arm."""
    windows = [HORIZONS[k]["rs_window"] for k in HORIZONS]
    assert windows == sorted(windows)


def test_shortest_and_longest_windows_are_sane():
    assert HORIZONS["2w"]["rs_window"] == 21      # ~1 trading month
    assert HORIZONS["9m"]["rs_window"] == 189     # ~9 trading months
