from pathlib import Path

import numpy as np
import pytest

from swingbot.core.market import fib_leg as fl
from tests.market.fib_leg_fixtures import (BROKEN, CLEAN, MIRROR, RESTART, TIE, path_frame,
                                           walk_frame)

SIDES = [(False, "bullish"), (True, "bearish")]


def leg(path, mirror, direction, t, k=3):
    return fl.impulse_leg(path_frame(path[:t + 1], mirror=mirror), direction, k).iloc[-1]


def expect(row, expected, mirror):
    for key, value in expected.items():
        want = MIRROR - value if mirror and key in fl.PRICE_COLUMNS else value
        assert row[key] == pytest.approx(want), key


def assert_no_leg(row):
    assert row.isna().all(), row[row.notna()]


@pytest.mark.parametrize("horizon_key,divisor,expected", [
    ("1w", 6, 3), ("2w", 6, 3), ("4w", 6, 7), ("9m", 6, 63), ("9m", 4, 94), ("9m", 8, 47), ("2w", 8, 3)])
def test_origin_strength(horizon_key, divisor, expected):
    assert fl.origin_strength(horizon_key, divisor) == expected


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_clean_leg_bounds(mirror, direction):
    expect(leg(CLEAN, mirror, direction, 16),
           {"origin_idx": 7, "origin_price": 8.5, "end_idx": 13, "end_price": 15.5, "leg_bars": 6}, mirror)


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_end_younger_than_three_bars_is_no_leg(mirror, direction):
    assert_no_leg(leg(CLEAN, mirror, direction, 15))      # end bar 13 is 2 bars old


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_equal_highs_take_the_first_bar(mirror, direction):
    row = leg(TIE, mirror, direction, 16)                  # last-occurrence would be 2 bars old -> NaN
    assert row["end_idx"] == 13


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_broken_origin_is_no_leg(mirror, direction):
    assert_no_leg(leg(BROKEN, mirror, direction, 18))


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_higher_major_low_restarts_the_leg(mirror, direction):
    assert leg(RESTART, mirror, direction, 20)["origin_idx"] == 7    # bar 18 not confirmed yet
    assert_no_leg(leg(RESTART, mirror, direction, 21))               # new origin, end is bar 21 itself
    expect(leg(RESTART, mirror, direction, 25),
           {"origin_idx": 18, "origin_price": 11.0, "end_idx": 22, "end_price": 16.5, "leg_bars": 4}, mirror)


@pytest.mark.parametrize("n", [0, 1, 2, 5, 9])
@pytest.mark.parametrize("mirror,direction", SIDES)
def test_short_frames_are_all_nan(n, mirror, direction):
    df = path_frame(CLEAN[:n], mirror=mirror)
    out = fl.impulse_leg(df, direction, 3)
    assert out.shape == (n, len(fl.LEG_COLUMNS))
    assert out.isna().all().all()
    assert all(np.isnan(v) for v in fl.leg_at(df, direction, 3).values())


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_nan_bar_inside_the_leg_is_no_leg(mirror, direction):
    df = path_frame(CLEAN[:17], mirror=mirror)
    df.iloc[10, df.columns.get_indexer(["High", "Low"])] = np.nan
    assert_no_leg(fl.impulse_leg(df, direction, 3).iloc[-1])


def test_flat_frame_is_all_nan():
    out = fl.impulse_leg(path_frame([10.0] * 40), "bullish", 3)
    assert out.isna().all().all()


@pytest.mark.parametrize("origin_k", [3, 7])
@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_row_t_equals_last_row_of_prefix(direction, origin_k):
    df = walk_frame()
    full = fl.impulse_leg(df, direction, origin_k)
    for t in range(len(df)):
        prefix = df.iloc[:t + 1]
        np.testing.assert_array_equal(fl.impulse_leg(prefix, direction, origin_k).iloc[-1].to_numpy(),
                                      full.iloc[t].to_numpy(), err_msg=f"t={t}")
        last = fl.leg_at(prefix, direction, origin_k)
        np.testing.assert_array_equal(np.array([last[c] for c in fl.LEG_COLUMNS], dtype=float),
                                      full.iloc[t].to_numpy(), err_msg=f"leg_at t={t}")
    if origin_k == 3:
        assert full["end_idx"].notna().any()     # the walk really produces legs


def test_no_live_module_imports_fib_leg():
    root = Path(__file__).resolve().parents[2]
    sources = [*(root / "swingbot").rglob("*.py"), root / "bot.py", root / "admin_ui.py"]
    hits = [str(path) for path in sources
            if path.name != "fib_leg.py" and "fib_leg" in path.read_text(encoding="utf-8")]
    assert hits == []
