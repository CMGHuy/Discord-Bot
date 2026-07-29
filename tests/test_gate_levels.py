import numpy as np

from swingbot.core.gate.levels import SwingLevel, swing_levels
from swingbot.core.indicators import atr
from tests.conftest import make_ohlcv


def _three_touch_resistance(level=110.0, base=100.0, n=120):
    closes = []
    for _ in range(3):
        # [1:] drops the duplicated peak/valley joints so every extremum
        # is unique (the pivot rule rejects ties)
        closes += list(np.linspace(base, level, 15)) + list(np.linspace(level, base, 15))[1:]
    closes += list(np.linspace(base, base * 1.01, n - len(closes)))
    return make_ohlcv(np.asarray(closes), spread_pct=0.5)


def test_three_touch_level_clustered_and_counted():
    levels = swing_levels(_three_touch_resistance(), pivot_span=5)
    res = [l for l in levels if l.kind == "resistance"]
    assert res, "no resistance found"
    assert res[0].touches == 3                       # strongest first
    assert abs(res[0].price - 110.0) / 110.0 < 0.01
    assert res[0].last_touch >= "2019-01-01"


def test_flat_series_has_no_levels():
    assert swing_levels(make_ohlcv(np.full(120, 100.0))) == []


def _ascending_pivot_staircase(n_cycles=30, step=0.15, amplitude=3.0, base=100.0):
    """Zigzag with n_cycles ascending resistance apexes, one `step` apart --
    a slow monotonic drift small enough relative to ATR that a chaining
    split rule (old running-mean comparison, or a nearest-neighbor/
    bucket[-1] comparison) merges many apexes into one smeared level, while
    an anchor (bucket[0]) comparison keeps every closed bucket's total span
    capped at 0.5*ATR."""
    closes = []
    for i in range(n_cycles):
        peak = base + i * step
        closes += list(np.linspace(peak - amplitude, peak, 4))[1:]
        closes += list(np.linspace(peak, peak - amplitude, 4))[1:]
    return make_ohlcv(np.asarray(closes), spread_pct=0.5)


def test_ascending_staircase_keeps_each_level_within_half_atr_span():
    """Regression for G47: swing_levels() must cap each closed bucket's
    TOTAL span (max - min touch price) at 0.5*ATR. A running-mean
    comparison or a nearest-neighbor (bucket[-1]) comparison both let a
    slow monotonic drift chain many pivots into one smeared level instead
    -- confirmed by exec'ing both variants against this same fixture: the
    mean-based rule produces a bucket spanning 1.05 (touches=8) and the
    bucket[-1] rule collapses all 30 apexes into one bucket spanning 4.35,
    both far over the 0.5*ATR ~= 0.64 budget this fixture's ATR implies.
    The staircase step is uniform, so each level's touch count alone
    determines its exact span: (touches - 1) * step.
    """
    step = 0.15
    df = _ascending_pivot_staircase(step=step)
    atr_val = float(atr(df).iloc[-1])
    threshold = 0.5 * atr_val

    levels = swing_levels(df, pivot_span=2)
    res = sorted((l for l in levels if l.kind == "resistance"), key=lambda l: l.price)

    assert len(res) > 1, "staircase collapsed into a single smeared level"
    for level in res:
        span = (level.touches - 1) * step
        assert span <= threshold + 1e-9, (
            f"level at {level.price} spans {span:.4f}, exceeds 0.5*ATR="
            f"{threshold:.4f} -- clustering is chaining/smearing"
        )
