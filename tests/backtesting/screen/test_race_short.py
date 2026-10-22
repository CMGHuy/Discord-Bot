"""v182 short fixed race: the exact mirror of the long race (spec Part A 1)."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators, race as race_mod, sides
from tests.backtesting.screen.helpers import frame, random_walk

QUIET = (100.0, 101.0, 99.0, 100.0)    # short entry 100: never reaches stop 103 or target 94
C_HAND = 256.0                          # a power of two: reflection is exact on 1/8 prices
C_RANDOM = 1024.0


def _frame(bars):
    rows = [QUIET] + list(bars)
    o, h, l, c = (np.array(col, dtype=float) for col in zip(*rows))
    return frame(c, opens=o, highs=h, lows=l)


def _mirror(df, c):
    """P' = c - P for Open/Close; High' = c - Low; Low' = c - High."""
    out = df.copy()
    out["Open"], out["Close"] = c - df["Open"], c - df["Close"]
    out["High"], out["Low"] = c - df["Low"], c - df["High"]
    return out


def _atr(df, value=2.0):
    return pd.Series(value, index=df.index)          # risk 3.0


def _short(df, positions, cap, **kw):
    kw.setdefault("slippage_bps", 0.0)
    kw.setdefault("commission", 0.0)
    return race_mod.race(df, positions, cap, direction="short", **kw)


def _long(df, positions, cap, **kw):
    kw.setdefault("slippage_bps", 0.0)
    kw.setdefault("commission", 0.0)
    return race_mod.race(df, positions, cap, **kw)


HAND = {   # name: (bars after the signal bar, cap, outcome, gross R, exit bar)
    "gap_stop": ([QUIET, (105.0, 106.0, 104.0, 105.0), QUIET], 3, "gap_stop", -5.0 / 3.0, 2),
    "gap_target": ([QUIET, (93.0, 94.0, 92.0, 93.0), QUIET], 3, "gap_target", 7.0 / 3.0, 2),
    "stop_first": ([(100.0, 104.0, 93.0, 100.0), QUIET], 2, "stop", -1.0, 1),
    "target": ([QUIET, (99.0, 100.0, 93.5, 94.0), QUIET], 3, "target", 2.0, 2),
    "stop": ([QUIET, (101.0, 103.125, 99.0, 102.0), QUIET], 3, "stop", -1.0, 2),
    "timeout": ([QUIET, QUIET, (100.0, 101.0, 99.0, 98.5)], 3, "timeout", 0.5, 3),
}


@pytest.mark.parametrize("name", sorted(HAND))
def test_short_race_on_hand_built_frames(name):
    bars, cap, outcome, gross, exit_bar = HAND[name]
    df = _frame(bars)
    out = _short(df, [0], cap, atr=_atr(df))
    assert out.outcome.tolist() == [outcome]
    assert out.gross_r.tolist() == [pytest.approx(gross, rel=1e-12)]
    assert out.exit_pos.tolist() == [exit_bar]
    assert out.entry.tolist() == [100.0]                # the real entry price
    assert out.risk.tolist() == [3.0]


@pytest.mark.parametrize("name", sorted(HAND))
def test_short_on_p_is_long_on_the_reflected_frame_exactly(name):
    bars, cap, *_ = HAND[name]
    df = _frame(bars)
    mirror = _mirror(df, C_HAND)
    short, long = _short(df, [0], cap, atr=_atr(df)), _long(mirror, [0], cap, atr=_atr(mirror))
    assert short.outcome.tolist() == long.outcome.tolist()
    assert short.exit_pos.tolist() == long.exit_pos.tolist()
    assert short.gross_r.tolist() == long.gross_r.tolist()       # dyadic: exact


def _tie_free(df, positions, cap, atr, tol=1e-9):
    """True where no Open/High/Low of the raced bars lies within tol of the
    short stop or target (a near-tie may flip under reflection rounding)."""
    o, h, l = (df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low"))
    a = atr.to_numpy(dtype=float)
    ok = []
    for p in positions:
        entry, risk = o[p + 1], race_mod.STOP_ATR * a[p]
        levels = np.array([entry + risk, entry - race_mod.REWARD_RISK * risk])
        prices = np.concatenate([o[p + 1:p + 1 + cap], h[p + 1:p + 1 + cap], l[p + 1:p + 1 + cap]])
        ok.append(np.abs(prices[:, None] - levels[None, :]).min() > tol)
    return np.asarray(ok)


@pytest.mark.parametrize("seed", [7, 11, 23])
def test_mirror_identity_on_random_frames(seed):
    df = random_walk(800, seed=seed)
    atr = indicators.atr(df)
    cap = 20
    positions = np.arange(20, len(df) - 1 - cap)
    short = _short(df, positions, cap, atr=atr)
    long = _long(_mirror(df, C_RANDOM), positions, cap, atr=atr)       # ATR unchanged
    np.testing.assert_allclose(short.gross_r, long.gross_r, rtol=0.0, atol=1e-9)
    ok = _tie_free(df, positions, cap, atr)
    assert ok.mean() > 0.99                                           # non-vacuous
    assert short.outcome[ok].tolist() == long.outcome[ok].tolist()
    assert short.exit_pos[ok].tolist() == long.exit_pos[ok].tolist()
    assert set(short.outcome) >= {"stop", "target", "timeout"}


def test_short_net_r_uses_sides_with_the_real_prices():
    df = _frame([QUIET, (99.0, 100.0, 93.5, 94.0), QUIET])
    out = race_mod.race(df, [0], 3, atr=_atr(df), slippage_bps=5.0, commission=0.02,
                        direction="short")
    days = sides.holding_days(df.index, np.array([1]), out.exit_pos)
    expected = sides.net_r(np.array([100.0]), np.array([94.0]), np.array([3.0]),
                           direction="short", days=days, slippage_bps=5.0, commission=0.02)
    assert out.r.tolist() == expected.tolist()
    assert out.r[0] < out.gross_r[0]


def test_borrow_is_charged_once_per_short_trade_and_never_on_a_long(monkeypatch):
    charged = []
    real = sides.borrow_r

    def counting(entry, risk, days):
        charged.append(int(np.size(days)))
        return real(entry, risk, days)

    monkeypatch.setattr(sides, "borrow_r", counting)
    df = random_walk(400, seed=5)
    positions = np.arange(20, 300, 7)
    race_mod.race(df, positions, 20)
    assert charged == []
    race_mod.race(df, positions, 20, direction="short")
    assert sum(charged) == len(positions)


def test_run_book_threads_the_direction():
    df = random_walk(500, seed=9)
    atr = indicators.atr(df)
    events = np.zeros(len(df), dtype=bool)
    events[30:400:9] = True
    member = np.ones(len(df), dtype=bool)
    warm = np.isfinite(atr.to_numpy())
    booked, counts = race_mod.run_book(df, events, 20, member=member, warm=warm, atr=atr,
                                       direction="short")
    cand, _ = race_mod.candidate_events(events, member, warm, 20)
    raced = race_mod.race(df, cand, 20, atr=atr, direction="short")
    keep = race_mod.non_overlapping(raced.event_pos, raced.exit_pos)
    assert booked.event_pos.tolist() == raced.event_pos[keep].tolist()
    assert booked.r.tolist() == raced.r[keep].tolist()
    assert counts["skipped_overlap"] == int((~keep).sum())


def test_run_book_long_never_passes_a_direction(monkeypatch):
    seen = []

    def fake_race(df, cand, cap, **kwargs):
        seen.append(kwargs)
        return race_mod.RaceResult.empty()

    monkeypatch.setattr(race_mod, "race_for", lambda shape: fake_race)
    df = random_walk(100, seed=1)
    race_mod.run_book(df, np.zeros(100, dtype=bool), 5, member=np.ones(100, bool),
                      warm=np.ones(100, bool), atr=indicators.atr(df))
    assert seen and "direction" not in seen[0]


def test_an_unknown_direction_is_refused_by_the_race():
    df = _frame([QUIET, QUIET])
    with pytest.raises(ValueError, match="direction"):
        race_mod.race(df, [0], 2, atr=_atr(df), direction="sideways")
