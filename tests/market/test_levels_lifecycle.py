"""P1 level lifecycle ("Sigils") -- dsgex.ai's Fresh/Tested/Delivered/Decaying
state machine, rebuilt on pure OHLCV.

Fixtures are hand-built rather than generated: each one exists to make exactly
one transition unambiguous. `test_classification_is_truncation_invariant` is
the structural NO-LOOKAHEAD proof -- if any state at bar i is computed from
bars after i, deleting the future changes the answer.
"""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import levels_lifecycle as ll


def _frame(closes, lows=None, highs=None, start="2020-01-01"):
    """OHLCV with explicit highs/lows so a touch can be placed precisely."""
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    lows = np.asarray(lows, dtype=float) if lows is not None else closes - 1.0
    highs = np.asarray(highs, dtype=float) if highs is not None else closes + 1.0
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes,
         "Volume": np.full(n, 1_000_000.0)},
        index=pd.bdate_range(start, periods=n),
    )


def _oscillating(n=200, lo=106.0, hi=114.0):
    """Price ranging well clear of a level at 100 -- never touches it."""
    closes = lo + (hi - lo) * (np.sin(np.arange(n) / 3.0) * 0.5 + 0.5)
    return closes


FLOOR = 100.0


def _states(df, levels, i=None, horizon_key="4w"):
    i = len(df) - 1 if i is None else i
    out = ll.classify_levels(df, i, levels, horizon_key=horizon_key)
    return {round(lv.price, 2): lv for lv in out}


# --- states -----------------------------------------------------------------

def test_untouched_level_is_fresh():
    df = _frame(_oscillating())
    lv = _states(df, [FLOOR])[FLOOR]

    assert lv.state == "fresh"
    assert lv.touches == 0


def test_touched_and_held_level_is_tested():
    closes = _oscillating()
    lows = closes - 1.0
    closes[180], lows[180] = 106.0, 100.1      # wick into the level, close back above
    df = _frame(closes, lows=lows)

    lv = _states(df, [FLOOR])[FLOOR]
    assert lv.state == "tested"
    assert lv.touches == 1


def test_repeated_touches_accumulate():
    closes = _oscillating()
    lows = closes - 1.0
    for b in (150, 170, 185):
        closes[b], lows[b] = 106.0, 100.1
    df = _frame(closes, lows=lows)

    assert _states(df, [FLOOR])[FLOOR].touches == 3


def test_decisive_close_below_a_floor_delivers_it():
    closes = _oscillating()
    lows = closes - 1.0
    closes[185:], lows[185:] = 88.0, 87.0      # gone, and stayed gone
    df = _frame(closes, lows=lows)

    lv = _states(df, [FLOOR])[FLOOR]
    assert lv.state == "delivered"


def test_a_touch_after_a_break_reclaims_the_level():
    # Order matters: the most recent decisive event wins, so a level that
    # broke and was then reclaimed must not stay "delivered" forever.
    closes = _oscillating()
    lows = closes - 1.0
    closes[140], lows[140] = 88.0, 87.0        # broken
    closes[141:], lows[141:] = 106.0, 105.0    # back above
    closes[190], lows[190] = 106.0, 100.1      # retested and held
    df = _frame(closes, lows=lows)

    assert _states(df, [FLOOR])[FLOOR].state == "tested"


def test_an_old_touch_decays():
    closes = _oscillating()
    lows = closes - 1.0
    closes[20], lows[20] = 106.0, 100.1        # touched once, long ago
    df = _frame(closes, lows=lows)

    lv = _states(df, [FLOOR])[FLOOR]
    assert lv.state == "decaying"
    assert lv.bars_since_touch > 0


# --- roles ------------------------------------------------------------------

def test_role_is_assigned_relative_to_the_current_bar():
    df = _frame(_oscillating())
    got = _states(df, [FLOOR, 130.0])

    assert got[100.0].role == "floor"
    assert got[130.0].role == "ceiling"


def test_exactly_one_king_is_crowned():
    closes = _oscillating()
    lows = closes - 1.0
    for b in (150, 170, 185):                  # make 100 the strongest level
        closes[b], lows[b] = 106.0, 100.1
    df = _frame(closes, lows=lows)

    out = ll.classify_levels(df, len(df) - 1, [FLOOR, 130.0, 95.0], horizon_key="4w")
    kings = [lv for lv in out if lv.is_king]

    assert len(kings) == 1
    assert kings[0].price == pytest.approx(FLOOR)


def test_no_king_when_there_are_no_levels():
    df = _frame(_oscillating())
    assert ll.classify_levels(df, len(df) - 1, [], horizon_key="4w") == []


# --- scale invariance -------------------------------------------------------

def test_tolerance_is_atr_relative_not_a_fixed_percentage():
    """The same shape at 10x the price must classify identically.

    A fixed-percentage tolerance would drift here; an ATR-relative one holds.
    """
    closes = _oscillating()
    lows = closes - 1.0
    closes[180], lows[180] = 106.0, 100.1
    cheap = _frame(closes, lows=lows)
    rich = _frame(closes * 10, lows=lows * 10)

    a = _states(cheap, [FLOOR])[FLOOR]
    b = _states(rich, [FLOOR * 10])[FLOOR * 10]
    assert a.state == b.state
    assert a.touches == b.touches


# --- no lookahead -----------------------------------------------------------

def test_classification_is_truncation_invariant():
    closes = _oscillating(220)
    lows = closes - 1.0
    closes[180], lows[180] = 106.0, 100.1
    closes[200:], lows[200:] = 88.0, 87.0      # a break AFTER the bar we ask about
    df = _frame(closes, lows=lows)
    i = 190

    full = ll.classify_levels(df, i, [FLOOR], horizon_key="4w")[0]
    truncated = ll.classify_levels(df.iloc[:i + 1], i, [FLOOR], horizon_key="4w")[0]

    assert full.state == truncated.state == "tested", "the later break must not leak backwards"
    assert full.touches == truncated.touches


def test_a_future_break_does_not_change_a_past_bar():
    closes = _oscillating(220)
    lows = closes - 1.0
    closes[180], lows[180] = 106.0, 100.1
    df_clean = _frame(closes.copy(), lows=lows.copy())

    closes[205:], lows[205:] = 80.0, 79.0
    df_broken = _frame(closes, lows=lows)

    assert (ll.classify_levels(df_clean, 190, [FLOOR], horizon_key="4w")[0].state
            == ll.classify_levels(df_broken, 190, [FLOOR], horizon_key="4w")[0].state)


# --- consumers --------------------------------------------------------------

def test_stop_anchor_prefers_a_tested_floor_over_a_fresh_one():
    closes = _oscillating()
    lows = closes - 1.0
    closes[185], lows[185] = 106.0, 100.1      # 100 is tested; 103 stays fresh
    df = _frame(closes, lows=lows)

    levels = ll.classify_levels(df, len(df) - 1, [FLOOR, 103.0], horizon_key="4w")
    anchor = ll.preferred_stop_anchor(levels, direction="bullish")

    assert anchor is not None
    assert anchor.price == pytest.approx(FLOOR)


def test_stop_anchor_never_returns_a_delivered_level():
    closes = _oscillating()
    lows = closes - 1.0
    closes[185:], lows[185:] = 88.0, 87.0
    df = _frame(closes, lows=lows)

    levels = ll.classify_levels(df, len(df) - 1, [FLOOR], horizon_key="4w")
    assert levels[0].state == "delivered"
    assert ll.preferred_stop_anchor(levels, direction="bullish") is None


# --- input tolerance --------------------------------------------------------

def test_accepts_levels_objects_as_well_as_floats():
    from swingbot.core.market.levels import Level as RawLevel

    df = _frame(_oscillating())
    out = ll.classify_levels(df, len(df) - 1,
                             [RawLevel(price=FLOOR, sources=["pivot"])], horizon_key="4w")

    assert len(out) == 1
    assert out[0].price == pytest.approx(FLOOR)
    assert out[0].sources == ["pivot"]


def test_short_history_yields_no_levels_rather_than_raising():
    df = _frame(_oscillating(12))
    assert ll.classify_levels(df, 11, [FLOOR], horizon_key="4w") == []
