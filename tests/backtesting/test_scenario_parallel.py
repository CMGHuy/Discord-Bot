"""v47: parallel scenario replay must be output-identical to sequential.

This is the gate protecting the closed pre-registrations in
docs/claude/backtest-methodology.md -- a changed aggregate here would silently
invalidate measurements that must not be re-run.
"""
import pytest

from swingbot.core.backtesting import backtest_scenarios
from swingbot.core.backtesting.backtest_scenarios import run_scenario_backtest
from swingbot.core.market.strategy_types import HORIZONS
from tests.helpers import make_ohlcv

# Every test here runs real replay_scenarios work over 400-bar frames: ~11s for
# the cheapest, ~50s for the one that replays twice to compare. That is the
# heavy-backtest tier the `slow` marker exists for (pytest.ini), not something
# the ~40s fast tier should carry. Measured: the process pool is NOT the cost --
# deselecting the real-pool test below changed the file's runtime by ~8s.
pytestmark = pytest.mark.slow


@pytest.fixture
def frames():
    """A handful of tickers with enough bars for the slowest horizon's
    indicators to have a value at all."""
    import numpy as np
    rng = np.random.default_rng(44)
    out = {}
    for i, ticker in enumerate(["AAA", "BBB", "CCC", "DDD"]):
        base = 100.0 + i * 10
        walk = base + np.cumsum(rng.normal(0, 1.0, 400))
        out[ticker] = make_ohlcv([float(x) for x in walk])
    return out


def test_parallel_matches_sequential(frames):
    """The one test here that builds a REAL ProcessPoolExecutor -- and the
    reason it is marked slow. On Windows a spawned worker re-imports the whole
    package, so this costs ~90s where every fake-pool test below costs under a
    second. It is still worth having exactly once: a fake pool proves the
    aggregation is order-independent, but only a real one proves the tasks are
    picklable and the workers produce the same numbers."""
    horizons = list(HORIZONS)[:3]
    gates = backtest_scenarios.CONFLUENCE_GATES

    sequential = run_scenario_backtest(frames, None, None, gates=gates,
                                       horizons=horizons, workers=1)
    parallel = run_scenario_backtest(frames, None, None, gates=gates,
                                     horizons=horizons, workers=4)

    # Guards against a vacuous pass: two empty aggregates compare equal, and
    # this test is the gate protecting closed pre-registrations.
    assert sequential["pooled"]["n"] > 0
    assert parallel["pooled"] == sequential["pooled"]
    assert parallel["by_horizon"] == sequential["by_horizon"]


def test_worker_completion_order_cannot_change_the_result(frames, monkeypatch):
    """Results are grouped by the horizon carried in each task's RESULT, so a
    pool whose workers finish out of order still aggregates identically."""
    horizons = list(HORIZONS)[:3]
    gates = backtest_scenarios.CONFLUENCE_GATES

    expected = run_scenario_backtest(frames, None, None, gates=gates,
                                     horizons=horizons, workers=1)

    class _OutOfOrderPool:
        def __init__(self, max_workers=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def map(self, fn, items):
            # Compute in reverse, return in input order -- exactly what
            # ProcessPoolExecutor.map guarantees. This catches any dependency
            # on the order work actually COMPLETES in.
            items = list(items)
            computed = {i: fn(a) for i, a in reversed(list(enumerate(items)))}
            return [computed[i] for i in range(len(items))]

    monkeypatch.setattr(backtest_scenarios, "ProcessPoolExecutor", _OutOfOrderPool)

    shuffled = run_scenario_backtest(frames, None, None, gates=gates,
                                     horizons=horizons, workers=4)

    assert expected["pooled"]["n"] > 0
    assert shuffled["pooled"] == expected["pooled"]
    assert shuffled["by_horizon"] == expected["by_horizon"]


def test_date_window_still_filters_signals(frames):
    gates = backtest_scenarios.CONFLUENCE_GATES
    horizons = list(HORIZONS)[:2]

    # workers=1: this test is about the date window, not the pool, and two
    # real pool spawns would cost ~90s to prove nothing about filtering.
    everything = run_scenario_backtest(frames, None, None, gates=gates,
                                       horizons=horizons, workers=1)
    windowed = run_scenario_backtest(frames, "2025-01-01", "2025-06-30",
                                     gates=gates, horizons=horizons, workers=1)

    assert windowed["pooled"]["n"] <= everything["pooled"]["n"]


def test_single_worker_never_builds_a_pool(frames, monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("workers=1 must stay sequential")

    monkeypatch.setattr(backtest_scenarios, "ProcessPoolExecutor", _boom)

    result = run_scenario_backtest(frames, None, None,
                                   gates=backtest_scenarios.CONFLUENCE_GATES,
                                   horizons=list(HORIZONS)[:2], workers=1)

    assert "pooled" in result
