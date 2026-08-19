"""Characterization tests for RS value path (v34 Task 1).

These tests document today's behavior at each hop from refresh_rs_cache
through score_plan to pin down the unknown RS representation before
the gate implementation adds decision logic.
"""
from tests.conftest import make_trend_df
from swingbot.core.edge.factors import rs_percentile


def test_rs_percentile_returns_fifty_not_none_on_empty_universe():
    """Characterization: documents the sentinel this plan must work around.
    If this ever returns None, the gate's unknown-handling can be simplified."""
    spy_frame = make_trend_df(120, +0.05)
    ticker_frame = make_trend_df(120, +0.05)
    assert rs_percentile(ticker_frame, spy_frame, universe_rels=[]) == 50.0


def test_rs_percentile_returns_fifty_on_short_history():
    """Characterization: rs_percentile handles short history gracefully."""
    spy_frame = make_trend_df(120, +0.05)
    ticker_frame = make_trend_df(3, +0.05)
    assert rs_percentile(ticker_frame, spy_frame, universe_rels=[0.1]) == 50.0
