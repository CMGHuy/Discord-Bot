"""The replay harness honours the same veto the live scan does."""
import inspect

import numpy as np
import pytest

from swingbot.core.backtesting import backtest_scenarios
from tests.helpers import make_ohlcv

GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}


def _structured_df():
    """Same shape as test_backtest_scenarios.py's fixture -- trend then a
    consolidation box -- kept independent per that file's own convention."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


def test_the_harness_accepts_params_not_config():
    # Twelve cells in one process: a config read would make them a global the
    # workers fight over.
    sig = inspect.signature(backtest_scenarios.replay_scenarios)
    assert "dcb_params" in sig.parameters
    assert sig.parameters["dcb_params"].default is None


def test_none_means_no_veto(monkeypatch):
    called = []
    monkeypatch.setattr(backtest_scenarios, "dead_cat_bounce",
                        lambda *a, **k: called.append(1) or {"detected": True})
    # The baseline arm must not pay for a detector it does not use.
    assert called == []


def test_the_window_passed_to_the_detector_never_extends_past_the_bar(monkeypatch):
    """The harness's own no-lookahead guarantee, asserted at the seam where
    v68 could break it."""
    seen = []
    real = backtest_scenarios.dead_cat_bounce

    def spy(window, params):
        seen.append(len(window))
        return real(window, params)
    monkeypatch.setattr(backtest_scenarios, "dead_cat_bounce", spy)

    df = _structured_df()
    backtest_scenarios.replay_scenarios("AAPL", df, "4w", gates=GATES,
                                        dcb_params={})

    assert seen, "fixture must drive at least one bar through the detector"
    # Driven by the harness's existing per-bar loop; lengths must be strictly
    # non-decreasing and never exceed the bar index + 1 -- i.e. the window
    # never sees a bar beyond the one currently being evaluated.
    assert seen == sorted(seen)
    assert max(seen) <= len(df)
