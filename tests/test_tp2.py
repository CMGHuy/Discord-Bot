"""Tests for select_tp2 -- the next structural level beyond TP1 (Task 16)."""
from swingbot.core.levels import Level
from swingbot.core.plan_engine import build_strategy_plan, select_tp2

from tests.helpers import make_ohlcv


def test_bullish_selects_first_level_beyond_tp1():
    # entry=100, tp1=102 -> leg1=2, cap=6. 104 is the first level past tp1
    # and within the cap; 108 is further out and should be ignored.
    tp2 = select_tp2([104.0, 108.0], [], "bullish", entry=100.0, tp1=102.0)
    assert tp2 == 104.0


def test_bearish_selects_first_level_beyond_tp1():
    # entry=100, tp1=98 -> leg1=2, cap=6. 96 is the first level past tp1
    # (moving down) and within the cap; 90 is further out.
    tp2 = select_tp2([], [96.0, 90.0], "bearish", entry=100.0, tp1=98.0)
    assert tp2 == 96.0


def test_returns_none_when_no_level_beyond_tp1():
    # Only a level below tp1 exists on the bullish (above) side -> no
    # candidate strictly beyond tp1 in the trade direction.
    tp2 = select_tp2([101.0], [], "bullish", entry=100.0, tp1=102.0)
    assert tp2 is None


def test_returns_none_when_empty_candidate_list():
    tp2 = select_tp2([], [], "bullish", entry=100.0, tp1=102.0)
    assert tp2 is None


def test_returns_none_when_beyond_cap():
    # leg1 = tp1 - entry = 2, cap = 3 * 2 = 6. A level at 120 is a leg2 of
    # 18 past tp1 -- way beyond the cap -- so it's dropped, not clamped.
    tp2 = select_tp2([120.0], [], "bullish", entry=100.0, tp1=102.0)
    assert tp2 is None


def test_level_exactly_at_cap_boundary_is_included():
    # leg1=2, cap=6. A level at 108 is exactly leg2=6 past tp1 -- the cap
    # is inclusive.
    tp2 = select_tp2([108.0], [], "bullish", entry=100.0, tp1=102.0)
    assert tp2 == 108.0


def test_level_equal_to_tp1_does_not_count_as_beyond():
    # A level sitting exactly on tp1 isn't "strictly beyond" it.
    tp2 = select_tp2([102.0, 105.0], [], "bullish", entry=100.0, tp1=102.0)
    assert tp2 == 105.0


def test_build_strategy_plan_fills_tp2_from_level_map():
    df = make_ohlcv([100 + i * 0.5 for i in range(80)])
    close = float(df["Close"].iloc[79])
    # supports/resistances mirror levels.build_level_map's return shape:
    # (supports, resistances), nearest-first Level lists either side of price.
    supports = [Level(price=close - 10, sources=["EMA20"])]
    resistances = [
        Level(price=close + 2, sources=["EMA20"]),
        Level(price=close + 4, sources=["Fib 61.8%"]),
    ]
    p = build_strategy_plan(df, 79, ticker="AAPL", strategy="MACD",
                            horizon_key="4w", direction="bullish",
                            level_map=(supports, resistances))
    assert p.tp2 is not None
    assert p.tp2 > p.tp1


def test_build_strategy_plan_tp2_stays_none_without_level_map():
    df = make_ohlcv([100 + i * 0.5 for i in range(80)])
    p = build_strategy_plan(df, 79, ticker="AAPL", strategy="MACD",
                            horizon_key="4w", direction="bullish")
    assert p.tp2 is None


# --- Task 31 regression: exit_params_for() wiring into build_strategy_plan ---
#
# These two tests use the SAME level_map (which, on its own, is sufficient
# to populate tp2 -- see test_build_strategy_plan_fills_tp2_from_level_map
# above) against two strategies that differ only in whether they have an
# EXIT_V2_PARAMS override, to prove the override actually reaches the built
# plan and isn't just correct in exit_params_for()'s own unit tests.

def _level_map_beyond_tp1(close):
    supports = [Level(price=close - 10, sources=["EMA20"])]
    resistances = [
        Level(price=close + 2, sources=["EMA20"]),
        Level(price=close + 4, sources=["Fib 61.8%"]),
    ]
    return supports, resistances


def test_build_strategy_plan_applies_exit_v2_override_trail_and_drops_tp2():
    # RSI Divergence: EXIT_V2_PARAMS = {"trail_atr_mult": 2.0, "tp2": False}
    # (grid winner, docs/superpowers/results/2026-07-exit-v2-train-grid.txt:99).
    # Even with a level_map that WOULD otherwise populate tp2 (as it does for
    # a no-override strategy below), tp2 must come back None and
    # trail_atr_mult must be the strategy's 2.0 override, not the 2.5 default.
    df = make_ohlcv([100 + i * 0.5 for i in range(80)])
    close = float(df["Close"].iloc[79])
    p = build_strategy_plan(df, 79, ticker="AAPL", strategy="RSI Divergence",
                            horizon_key="4w", direction="bullish",
                            level_map=_level_map_beyond_tp1(close))
    assert p.trail_atr_mult == 2.0
    assert p.tp2 is None


def test_build_strategy_plan_no_override_strategy_keeps_defaults():
    # EMA Crossover has no EXIT_V2_PARAMS entry (grid: "no config qualifies
    # -- KEEP DEFAULTS"). With the identical level_map from the test above,
    # it must fall back to trail_atr_mult=2.5 (TRAIL_ATR_MULT) and tp2 must
    # actually get populated from the level map (tp2 defaults to True).
    df = make_ohlcv([100 + i * 0.5 for i in range(80)])
    close = float(df["Close"].iloc[79])
    p = build_strategy_plan(df, 79, ticker="AAPL", strategy="EMA Crossover",
                            horizon_key="4w", direction="bullish",
                            level_map=_level_map_beyond_tp1(close))
    assert p.trail_atr_mult == 2.5
    assert p.tp2 is not None
    assert p.tp2 > p.tp1
