"""Tests for strategy_types constants and entry_filters."""
import pytest


def test_rr_override_single_source_and_floor():
    from swingbot.core.strategy_types import STRATEGY_RR_OVERRIDE, BREAKEVEN_TRIGGER_FRACTION
    from swingbot.core.backtest import STRATEGY_RR_OVERRIDE as BT_RR, ALL_STRATEGIES

    assert BT_RR is STRATEGY_RR_OVERRIDE          # same object, not a copy
    assert set(STRATEGY_RR_OVERRIDE) == set(ALL_STRATEGIES)
    assert all(rr >= 0.30 for rr in STRATEGY_RR_OVERRIDE.values()), \
        "R:R below 0.30 makes 80% win rate unprofitable (spec hard floor)"
    assert 0.0 < BREAKEVEN_TRIGGER_FRACTION < 1.0


def test_strategy_gates_shape():
    from swingbot.core.strategy_types import STRATEGY_GATES
    for strat, gates in STRATEGY_GATES.items():
        assert set(gates) <= {"directions", "horizons"}
