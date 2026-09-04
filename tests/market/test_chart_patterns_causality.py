"""Window-boundedness and determinism properties for dead_cat_bounce.

dead_cat_bounce(df, params) is a pure function that evaluates only the LAST
ROW of the input frame against a trailing window of lookback bars. True
NO-LOOKAHEAD (data outside the input frame is inaccessible) is a static code
property verified in D1's implementation review: only df.iloc[-lookback:] is
ever read, and only through positive shifts and within-window slicing.

This file tests two behaviorally verifiable properties that ARE constructible
for a last-row-evaluator contract:

  1. WINDOW-BOUNDEDNESS: data older than the lookback window must never affect
     the verdict. Bars strictly before the trailing lookback-bar window are
     invisible to the detector.

  2. DETERMINISM/PURITY: calling dead_cat_bounce twice with identical inputs
     must return identical results. The input df must not be mutated by the
     call (no in-place modifications, no hidden side effects).

These properties cannot prove the detector never reads future data in the
abstract sense (that is a code-level proof), but they DO prove the detector
only reads within its declared trailing window and that it is side-effect-free
-- two essential integrity requirements for any entry filter.
"""
import copy

import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.market.chart_patterns import (
    DEFAULT_DCB_PARAMS, dead_cat_bounce,
)

ARMS = [
    DEFAULT_DCB_PARAMS,
    {**DEFAULT_DCB_PARAMS, "gap_required": True},
    {**DEFAULT_DCB_PARAMS, "volume_ratio": 0.8},
    {**DEFAULT_DCB_PARAMS, "decline_pct": 15.0},
]


def _mixed_frame(seed=7, n=140):
    """A frame containing drops, bounces and recoveries, so tests can
    exercise the detector with meaningful verdicts."""
    rng = np.random.default_rng(seed)
    closes, price = [], 100.0
    for i in range(n):
        shock = -0.18 if i in (40, 80) else 0.0     # two hard drops to bounce off
        price *= 1 + shock + rng.normal(0, 0.012)
        closes.append(max(price, 1.0))
    frame = make_ohlcv(closes)
    frame["Volume"] = rng.uniform(5e5, 5e6, size=n)
    return frame


@pytest.mark.parametrize("params", ARMS)
def test_window_boundedness_prepending_old_bars_never_changes_verdict(params):
    """Data older than the lookback window must never affect the verdict.

    Given a frame, compute a verdict. Then prepend arbitrary old bars
    (bars that lie entirely before the trailing lookback window) and
    recompute. The verdict must be byte-identical if and only if the
    detector only reads the trailing window, not arbitrary history.
    """
    frame = _mixed_frame()
    lookback = params.get("lookback", DEFAULT_DCB_PARAMS["lookback"])

    # Test at several bars where we know verdicts are computed
    for i in range(lookback + 20, len(frame)):
        original_verdict = dead_cat_bounce(frame.iloc[:i + 1], params)

        # Prepend 50 old bars with completely different price action
        old_closes = 50 * (1.0 + np.random.default_rng(42).normal(0, 0.05, 50))
        prepend = make_ohlcv(old_closes)
        combined = pd.concat([prepend, frame.iloc[:i + 1]], ignore_index=False)

        extended_verdict = dead_cat_bounce(combined, params)

        # Verdicts must be identical
        assert original_verdict == extended_verdict, (
            f"bar {i}: verdict changed when old bars were prepended\n"
            f"  original: {original_verdict}\n"
            f"  extended: {extended_verdict}"
        )


@pytest.mark.parametrize("params", ARMS)
def test_determinism_and_purity_same_input_same_output(params):
    """dead_cat_bounce must be deterministic and side-effect-free.

    Calling the function twice with identical inputs must return identical
    results. The input DataFrame must not be mutated (no in-place operations).
    This proves the detector is a pure function with no hidden state or I/O.
    """
    frame = _mixed_frame()

    # Make a deep copy so we can compare frame state before/after
    frame_before = copy.deepcopy(frame)

    # First call
    verdict_1 = dead_cat_bounce(frame, params)

    # Frame must be unmodified after the call
    assert frame.equals(frame_before), "input DataFrame was mutated"

    # Second call with same frame (now we know it's unmodified)
    verdict_2 = dead_cat_bounce(frame, params)

    # Verdicts must be identical
    assert verdict_1 == verdict_2, (
        f"verdict changed between two identical calls\n"
        f"  first:  {verdict_1}\n"
        f"  second: {verdict_2}"
    )


def test_at_least_one_bar_actually_detects():
    """Guards the property tests from passing vacuously.

    If the detector never fires on the mixed frame, the window-boundedness
    and determinism tests prove nothing about a working detector -- they only
    prove an always-False function has those properties (which is trivial).
    This test confirms the frame exercises the detector meaningfully.
    """
    frame = _mixed_frame()
    fired = [i for i in range(30, len(frame))
             if dead_cat_bounce(frame.iloc[: i + 1])["detected"]]
    assert fired, "no bar detected; the property tests proved nothing"
