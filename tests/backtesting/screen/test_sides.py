"""v182 sides: orientation, holding days and per-fill net R by direction."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import sides
from swingbot.core.edge.frictions import apply_frictions, borrow_r, commission_r


def _ohlc():
    return (np.array([100.0, 101.0]), np.array([102.0, 103.0]),
            np.array([99.0, 98.5]), np.array([101.0, 100.0]))


def test_long_orientation_returns_the_same_arrays():
    o, h, l, c = _ohlc()
    out = sides.oriented(o, h, l, c, "long")
    assert all(a is b for a, b in zip(out, (o, h, l, c)))


def test_short_orientation_negates_and_swaps_high_and_low():
    o, h, l, c = _ohlc()
    so, sh, sl, sc = sides.oriented(o, h, l, c, "short")
    assert so.tolist() == (-o).tolist() and sc.tolist() == (-c).tolist()
    assert sh.tolist() == (-l).tolist() and sl.tolist() == (-h).tolist()
    assert (sh >= sl).all()


def test_an_unknown_direction_is_refused():
    with pytest.raises(ValueError, match="direction"):
        sides.oriented(*_ohlc(), "sideways")
    with pytest.raises(ValueError, match="direction"):
        sides.net_r(np.array([1.0]), np.array([1.0]), np.array([1.0]),
                    direction="both", days=np.array([1.0]))


def test_holding_days_are_calendar_days():
    index = pd.bdate_range("2015-03-04", periods=6)    # Wed .. next Wed
    days = sides.holding_days(index, np.array([0, 2, 1]), np.array([0, 3, 5]))
    assert days.tolist() == [0.0, 3.0, 6.0]            # same day; Fri->Mon; Thu->Wed


def test_long_net_r_is_todays_expression_bit_for_bit():
    rng = np.random.default_rng(3)
    entry = rng.uniform(20, 200, 50)
    price = entry * rng.uniform(0.9, 1.1, 50)
    risk = rng.uniform(0.5, 5.0, 50)
    for bps, comm in ((None, None), (5.0, 0.02), (0.0, 0.0)):
        cost = commission_r() if comm is None else comm
        old = (apply_frictions(price, "sell", bps)
               - apply_frictions(entry, "buy", bps)) / risk - cost
        new = sides.net_r(entry, price, risk, direction="long", days=None,
                          slippage_bps=bps, commission=comm)
        assert new.tolist() == old.tolist()


def test_long_net_r_never_charges_borrow(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("borrow_r called on a long trade")
    monkeypatch.setattr(sides, "borrow_r", boom)
    sides.net_r(np.array([100.0]), np.array([103.0]), np.array([2.0]),
                direction="long", days=np.array([5.0]))


def test_short_net_r_sells_the_entry_and_buys_the_exit():
    entry, price, risk, days = np.array([100.0]), np.array([94.0]), np.array([3.0]), np.array([7.0])
    out = sides.net_r(entry, price, risk, direction="short", days=days,
                      slippage_bps=5.0, commission=0.02)
    expected = (99.95 - 94.047) / 3.0 - 0.02 - borrow_r(100.0, 3.0, 7.0)
    assert out[0] == pytest.approx(expected, rel=1e-12)
    exact = ((apply_frictions(entry, "sell", 5.0) - apply_frictions(price, "buy", 5.0)) / risk
             - 0.02 - borrow_r(entry, risk, days))
    assert out.tolist() == exact.tolist()


def test_short_net_r_charges_borrow_on_calendar_days():
    args = (np.array([100.0, 100.0, 100.0]), np.array([97.0, 97.0, 97.0]),
            np.array([2.0, 2.0, 2.0]))
    out = sides.net_r(*args, direction="short", days=np.array([0.0, 1.0, 3.0]),
                      slippage_bps=0.0, commission=0.0)
    assert out[0] == pytest.approx(1.5, rel=1e-12)              # same day: no borrow
    assert out[0] - out[2] == pytest.approx(3 * (out[0] - out[1]), rel=1e-9)
    assert out[0] - out[2] == pytest.approx(borrow_r(100.0, 2.0, 3.0), rel=1e-9)


def test_entry_bps_moves_only_the_entry_fill():
    e, p, r, d = np.array([100.0]), np.array([95.0]), np.array([2.0]), np.array([0.0])
    short = sides.net_r(e, p, r, direction="short", days=d, slippage_bps=5.0,
                        entry_bps=10.0, commission=0.0)
    assert short[0] == pytest.approx(((100.0 - 0.10) - (95.0 + 0.0475)) / 2.0, rel=1e-12)
    long = sides.net_r(p, e, r, direction="long", days=d, slippage_bps=5.0,
                       entry_bps=10.0, commission=0.0)
    assert long[0] == pytest.approx(((100.0 - 0.05) - (95.0 + 0.095)) / 2.0, rel=1e-12)
