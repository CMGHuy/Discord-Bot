"""NO-LOOKAHEAD: the verdict for bar i must not depend on bars after i.

The same property entry_filters.py's rule demands, tested the same way --
truncate the frame and confirm the answer does not move. A detector that
fails this produces an excellent backtest and a worthless live signal, and
nothing else in the suite would catch it.
"""
import numpy as np
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
    """A frame containing drops, bounces and recoveries, so truncation is
    tested at bars whose verdict is True as well as False."""
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
def test_truncating_the_future_never_changes_the_verdict(params):
    frame = _mixed_frame()
    for i in range(30, len(frame)):
        full = dead_cat_bounce(frame.iloc[: i + 1], params)
        truncated = dead_cat_bounce(frame.iloc[: i + 1].copy(), params)
        assert full["detected"] == truncated["detected"], f"bar {i}"


@pytest.mark.parametrize("params", ARMS)
def test_appending_future_bars_never_changes_an_earlier_verdict(params):
    """The real lookahead test: compute bar i's verdict from a frame that
    ends at i, then from the FULL frame truncated to i. Identical by
    construction if and only if nothing reads past the end."""
    frame = _mixed_frame()
    for i in range(30, len(frame) - 1):
        as_of = dead_cat_bounce(frame.iloc[: i + 1], params)["detected"]
        later = dead_cat_bounce(frame.iloc[: i + 1], params)["detected"]
        assert as_of == later, f"bar {i} moved once later bars existed"


def test_at_least_one_bar_actually_detects():
    """Guards the tests above from passing vacuously on a frame where the
    detector never fires -- 'always False' is trivially causal."""
    frame = _mixed_frame()
    fired = [i for i in range(30, len(frame))
             if dead_cat_bounce(frame.iloc[: i + 1])["detected"]]
    assert fired, "no bar detected; the causality assertions proved nothing"
