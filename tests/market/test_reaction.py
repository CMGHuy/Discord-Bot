import numpy as np
import pytest

from swingbot.core.market import reaction as rx
from tests.helpers import make_ohlcv

L_BULL, L_BEAR, K, ATR = 98.5, 101.5, 0.25, 1.0


def _bars(*rows):
    return rx.Bars.from_frame(make_ohlcv(list(rows)))


def test_is_test_bullish_touch_pierce_and_miss():
    bars = _bars((100, 101, 99.0, 100.5), (100, 101, 98.7, 100.5), (99, 100, 97.0, 99.5))
    assert rx.is_test(bars, 0, L_BULL, "bullish", K, ATR) is False   # 99.0 > 98.75
    assert rx.is_test(bars, 1, L_BULL, "bullish", K, ATR) is True    # touch within k*ATR
    assert rx.is_test(bars, 2, L_BULL, "bullish", K, ATR) is True    # pierce
    assert rx.is_test(bars, 2, L_BULL, "bullish", K, float("nan")) is False


def test_is_test_bearish_mirror():
    bars = _bars((100, 101.0, 99, 100.5), (100, 101.3, 99, 100.5))
    assert rx.is_test(bars, 0, L_BEAR, "bearish", K, ATR) is False   # 101.0 < 101.25
    assert rx.is_test(bars, 1, L_BEAR, "bearish", K, ATR) is True


def test_rejection_bullish_fires_and_near_misses_do_not():
    bars = _bars((99.0, 99.6, 97.6, 99.4),   # wick 1.4 of 2.0, close in top third, above L
                 (99.0, 99.6, 97.6, 98.6),   # close not in the top third
                 (98.0, 98.4, 96.0, 98.3),   # shape right, but closes below L
                 (99.0, 99.0, 99.0, 99.0))   # zero range
    assert rx.is_rejection(bars, 0, L_BULL, "bullish") is True
    assert rx.is_rejection(bars, 1, L_BULL, "bullish") is False
    assert rx.is_rejection(bars, 2, L_BULL, "bullish") is False
    assert rx.is_rejection(bars, 3, L_BULL, "bullish") is False


def test_rejection_bearish_mirror():
    bars = _bars((101.0, 102.4, 100.4, 100.6))  # upper wick 1.4 of 2.0, close in bottom third, below L
    assert rx.is_rejection(bars, 0, L_BEAR, "bearish") is True


def test_follow_through_needs_a_prior_bar():
    bars = _bars((99.0, 99.5, 98.6, 99.2), (99.3, 100.2, 99.1, 99.8))
    assert rx.is_follow_through(bars, 0, "bullish") is False
    assert rx.is_follow_through(bars, 1, "bullish") is True
    bear = _bars((101.0, 101.4, 100.5, 100.8), (100.7, 100.9, 100.0, 100.2))
    assert rx.is_follow_through(bear, 1, "bearish") is True


def test_reclaim_only_counts_closes_inside_the_arm_window():
    bars = _bars((99, 99, 98, 98.2), (99, 99, 98, 98.3), (99, 99.2, 98.4, 98.9))
    assert rx.is_reclaim(bars, 2, L_BULL, "bullish", floor_index=0) is True
    assert rx.is_reclaim(bars, 2, L_BULL, "bullish", floor_index=1) is True   # bar 1 still closed below
    assert rx.is_reclaim(bars, 2, L_BULL, "bullish", floor_index=2) is False  # nothing earlier inside the window
    bear = _bars((101, 102, 101, 101.8), (101.5, 101.9, 101.0, 101.2))
    assert rx.is_reclaim(bear, 1, L_BEAR, "bearish", floor_index=0) is True


def test_reaction_kind_precedence_and_test_requirements():
    # bar 2 is both a reclaim and a follow-through -> R3 wins
    bars = _bars((99, 99, 98, 98.2), (98.2, 98.4, 97.8, 98.3), (98.4, 99.6, 98.3, 99.5))
    assert rx.reaction_kind(bars, 2, L_BULL, "bullish", tested_now=True,
                            tested_prev=True, floor_index=0) == rx.R3
    # a rejection that is also a follow-through, tested now -> R2 over R1
    ft = _bars((99.0, 99.3, 98.8, 99.1), (99.0, 99.6, 97.6, 99.4))
    assert rx.reaction_kind(ft, 1, L_BULL, "bullish", tested_now=True,
                            tested_prev=False, floor_index=0) == rx.R2
    # follow-through with no test on this bar or the one before -> nothing
    assert rx.reaction_kind(ft, 1, L_BULL, "bullish", tested_now=False,
                            tested_prev=False, floor_index=0) is None
    # a rejection must itself be the test bar
    rej = _bars((99.6, 99.9, 99.5, 99.8), (99.0, 99.6, 97.6, 99.4))
    assert rx.reaction_kind(rej, 1, L_BULL, "bullish", tested_now=False,
                            tested_prev=True, floor_index=0) is None
    assert rx.reaction_kind(rej, 1, L_BULL, "bullish", tested_now=True,
                            tested_prev=False, floor_index=0) == rx.R1


def test_predicates_never_read_past_t():
    """NO-LOOKAHEAD: every predicate at bar t is identical on the full frame
    and on the frame truncated right after t."""
    rng = np.random.default_rng(11)
    closes = 100 + np.cumsum(rng.normal(0, 1.2, 80))
    rows = [(c - rng.uniform(-1, 1), c + rng.uniform(0, 2), c - rng.uniform(0, 2), c)
            for c in closes]
    rows = [(o, max(o, h, c), min(o, l, c), c) for o, h, l, c in rows]
    df = make_ohlcv(rows)
    full = rx.Bars.from_frame(df)
    level = float(np.median(closes))
    for t in range(2, len(df)):
        trunc = rx.Bars.from_frame(df.iloc[:t + 1])
        for direction in ("bullish", "bearish"):
            args = dict(level=level, direction=direction)
            assert rx.is_test(full, t, k=K, atr_t=ATR, **args) == rx.is_test(trunc, t, k=K, atr_t=ATR, **args)
            assert rx.is_rejection(full, t, **args) == rx.is_rejection(trunc, t, **args)
            assert rx.is_follow_through(full, t, direction) == rx.is_follow_through(trunc, t, direction)
            assert rx.is_reclaim(full, t, floor_index=0, **args) == rx.is_reclaim(trunc, t, floor_index=0, **args)
            tested_now = rx.is_test(full, t, k=K, atr_t=ATR, **args)
            tested_prev = t >= 1 and rx.is_test(full, t - 1, k=K, atr_t=ATR, **args)
            assert rx.reaction_kind(full, t, floor_index=0, tested_now=tested_now,
                                    tested_prev=tested_prev, **args) == \
                   rx.reaction_kind(trunc, t, floor_index=0, tested_now=tested_now,
                                    tested_prev=tested_prev, **args)
