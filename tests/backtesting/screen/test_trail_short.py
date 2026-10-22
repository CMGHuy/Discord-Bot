"""v182 short trail race: the exact mirror of the v163 long trail (spec § Part A)."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen import race as race_mod
from swingbot.core.backtesting.screen import sides, trail
from swingbot.core.edge import frictions
from tests.backtesting.screen.helpers import frame, random_walk

QUIET = (100.0, 101.0, 99.0, 100.0)     # bar 0 = signal bar; entry = bar 1's open = 100
DN1 = (100.0, 100.5, 96.0, 97.0)        # the stop on the next bar: 96 + 6 = 102
DN2 = (97.0, 97.5, 92.0, 93.0)          # next: 92 + 6 = 98
DN3 = (93.0, 93.5, 90.0, 91.0)          # next: 90 + 6 = 96
MIRROR_C = 256.0                        # dyadic prices and a power of two: reflection is exact


def _frame(bars):
    rows = [QUIET] + list(bars)
    o, h, l, c = (np.array(col, dtype=float) for col in zip(*rows))
    return frame(c, opens=o, highs=h, lows=l)


def _atr(df, value=2.0):
    return pd.Series(value, index=df.index)   # 1R = 3.0: initial short stop 103


def _reflect(df, c=MIRROR_C):
    """P' = c - P; High' = c - Low, Low' = c - High (spec § Part A, item 1)."""
    return pd.DataFrame({"Open": c - df["Open"], "High": c - df["Low"],
                         "Low": c - df["High"], "Close": c - df["Close"],
                         "Volume": df["Volume"]}, index=df.index)


def _race(df, pos, cap, atr, direction, **costs):
    costs.setdefault("slippage_bps", 0.0)
    costs.setdefault("commission", 0.0)
    return trail.race_trail(df, pos, cap, atr=atr, direction=direction, **costs)


def _short(bars, cap, **costs):
    df = _frame(bars)
    return _race(df, [0], cap, _atr(df), "short", **costs)


CASES = {
    "trail": ([DN1, DN2, DN3, (92.0, 96.5, 91.5, 95.0)], 4),
    "gap_trail": ([DN1, DN2, (99.0, 99.5, 97.0, 98.0)], 3),
    "gap_stop": ([QUIET, (104.0, 105.0, 103.5, 104.5)], 2),
    "stop": ([QUIET, (100.0, 103.5, 99.5, 101.0)], 2),
    "timeout": ([QUIET, QUIET, QUIET], 3),
}


def test_the_short_stop_sits_three_atr_over_the_lowest_prior_low_never_raised():
    lows = np.array([[96.0, 92.0, 95.0, 90.0]])
    entry, risk = np.array([100.0]), np.array([3.0])
    real = -trail.trail_stops(-lows, -entry, risk)[0]     # the short race's own call, un-negated
    assert real.tolist() == [103.0, 102.0, 98.0, 98.0]
    assert (np.diff(real) <= 0).all()


def test_a_short_rides_the_trail_down_and_exits_on_the_trail():
    out = _short(*CASES["trail"])
    assert out.outcome.tolist() == ["trail"]
    assert out.exit_pos.tolist() == [4]
    assert out.entry.tolist() == [100.0]                    # the real fill, not -100
    assert out.gross_r[0] == pytest.approx(4.0 / 3.0)       # (100 - 96) / 3


def test_a_short_gap_up_through_a_lowered_stop_is_gap_trail_at_the_open():
    out = _short(*CASES["gap_trail"])
    assert out.outcome.tolist() == ["gap_trail"]
    assert out.gross_r[0] == pytest.approx(1.0 / 3.0)       # (100 - 99) / 3, a gain


def test_a_short_gap_up_through_the_initial_stop_is_a_gap_loss_beyond_one_r():
    out = _short(*CASES["gap_stop"])
    assert out.outcome.tolist() == ["gap_stop"]
    assert out.gross_r[0] == pytest.approx(-4.0 / 3.0)
    assert out.gross_r[0] < -1.0


def test_a_short_high_touching_the_initial_stop_exits_at_minus_one_r():
    out = _short(*CASES["stop"])
    assert out.outcome.tolist() == ["stop"]
    assert out.gross_r[0] == pytest.approx(-1.0)


def test_a_short_with_no_exit_times_out_at_the_last_close():
    out = _short(*CASES["timeout"])
    assert out.outcome.tolist() == ["timeout"]
    assert out.exit_pos.tolist() == [3]
    assert out.gross_r[0] == 0.0


@pytest.mark.parametrize("name", sorted(CASES))
def test_short_on_p_is_long_on_the_reflected_frame_exactly(name):
    bars, cap = CASES[name]
    df = _frame(bars)
    short = _race(df, [0], cap, _atr(df), "short")
    long_ = _race(_reflect(df), [0], cap, _atr(df), "long")
    assert short.outcome.tolist() == long_.outcome.tolist() == [name]
    assert short.exit_pos.tolist() == long_.exit_pos.tolist()
    assert short.gross_r.tolist() == long_.gross_r.tolist()      # exact: dyadic prices


def _near_tie(df, pos, cap, atr, tol=1e-9):
    """Rows where a reflected open or low lies within tol of the trail stop:
    their outcome code may legitimately differ by rounding."""
    o, h, l = (df[col].to_numpy(dtype=float) for col in ("Open", "High", "Low"))
    bars = pos[:, None] + 1 + np.arange(cap)[None, :]
    entry = o[pos + 1]
    risk = race_mod.STOP_ATR * atr.to_numpy(dtype=float)[pos]
    stops = trail.trail_stops(h[bars], entry, risk)
    near = (np.abs(o[bars] - stops) < tol) | (np.abs(l[bars] - stops) < tol)
    return near.any(axis=1)


@pytest.mark.parametrize("seed", [3, 5, 8])
def test_random_frames_mirror_within_tolerance(seed):
    df = random_walk(400, seed=seed)
    atr = indicators.atr(df)
    pos = np.arange(20, 330, 7)
    short = _race(df, pos, 60, atr, "short")
    mirrored = _reflect(df, 512.0)
    long_ = _race(mirrored, pos, 60, atr, "long")
    np.testing.assert_allclose(short.gross_r, long_.gross_r, rtol=0.0, atol=1e-9)
    clear = ~_near_tie(mirrored, pos, 60, atr)
    assert clear.sum() > 30                                    # non-vacuous
    assert (short.outcome[clear] == long_.outcome[clear]).all()
    assert (short.exit_pos[clear] == long_.exit_pos[clear]).all()


def test_short_net_r_charges_sell_entry_buy_exit_and_borrow():
    days = 3                                                   # Tue 2010-01-05 -> Fri 2010-01-08
    borrow = 100.0 * frictions.BORROW_RATE_ANNUAL / 365.0 * days / 3.0
    out = _short(*CASES["trail"])
    assert out.r[0] == pytest.approx(4.0 / 3.0 - borrow)
    slipped = _short(*CASES["trail"], slippage_bps=10.0, commission=0.02)
    sell_in, buy_out = 100.0 * (1 - 0.001), 96.0 * (1 + 0.001)
    assert slipped.r[0] == pytest.approx((sell_in - buy_out) / 3.0 - 0.02 - borrow)


def _count_borrow(monkeypatch):
    """Counts trades charged: patched where sides may look the name up."""
    seen = []
    real = frictions.borrow_r

    def spy(entry, risk, days):
        seen.append(int(np.size(days)))
        return real(entry, risk, days)

    monkeypatch.setattr(frictions, "borrow_r", spy)
    monkeypatch.setattr(sides, "borrow_r", spy, raising=False)
    return seen


def test_borrow_is_charged_once_per_short_trade_and_never_for_a_long(monkeypatch):
    seen = _count_borrow(monkeypatch)
    df = random_walk(400, seed=5)
    pos = np.arange(20, 330, 7)
    _race(df, pos, 60, indicators.atr(df), "long")
    assert seen == []
    _race(df, pos, 60, indicators.atr(df), "short")
    assert seen == [len(pos)]


def test_the_default_direction_is_long_and_its_arrays_are_unchanged():
    df = random_walk(400, seed=8)
    atr = indicators.atr(df)
    pos = np.arange(20, 330, 7)
    default = trail.race_trail(df, pos, 60, atr=atr)
    explicit = trail.race_trail(df, pos, 60, atr=atr, direction="long")
    for name in ("event_pos", "exit_pos", "entry", "risk", "gross_r", "r", "outcome"):
        assert np.array_equal(getattr(default, name), getattr(explicit, name)), name


def test_run_book_races_a_short_trail_book():
    df = random_walk(400, seed=3)
    atr = indicators.atr(df)
    events = np.zeros(len(df), dtype=bool)
    events[[20, 100, 180]] = True                     # further apart than the cap: no overlap
    ones = np.ones(len(df), dtype=bool)
    booked, counts = race_mod.run_book(df, events, 60, member=ones, warm=ones, atr=atr,
                                       shape="trail", direction="short",
                                       slippage_bps=0.0, commission=0.0)
    direct = _race(df, np.array([20, 100, 180]), 60, atr, "short")
    assert counts["skipped_overlap"] == 0
    assert booked.gross_r.tolist() == direct.gross_r.tolist()
    assert booked.r.tolist() == direct.r.tolist()
