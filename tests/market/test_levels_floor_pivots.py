import pytest

from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS
from tests.helpers import make_ohlcv


def test_floor_pivot_matches_standard_formula():
    # The prior bar (df.iloc[-2], what collect_candidate_levels actually
    # reads) carries a deliberately asymmetric H/L/C so the standard and
    # buggy formulas provably diverge -- at a symmetric close (C at the
    # H/L midpoint) the old bug's R2 coincidentally matched standard R3,
    # masking the error.
    rows = [(100.0, 100.0, 100.0, 100.0)] * 30
    rows.append((104.0, 110.0, 100.0, 108.0))  # becomes df.iloc[-2]
    rows.append((108.0, 108.0, 108.0, 108.0))  # last bar
    df = make_ohlcv(rows)
    h = HORIZONS["4w"]
    price = float(df["Close"].iloc[-1])

    candidates = {
        label: p for p, label in levels.collect_candidate_levels(df, h, price)
        if label.startswith("Floor")
    }

    H, L, C = 110.0, 100.0, 108.0
    pp = (H + L + C) / 3
    assert candidates["Floor Pivot"] == pytest.approx(pp)
    assert candidates["Floor R1"] == pytest.approx(2 * pp - L)
    assert candidates["Floor S1"] == pytest.approx(2 * pp - H)
    assert candidates["Floor R2"] == pytest.approx(pp + (H - L))
    assert candidates["Floor S2"] == pytest.approx(pp - (H - L))
