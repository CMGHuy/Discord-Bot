"""v163 trail race: chandelier 3 ATR trailing stop, no target, gaps at the open."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen import race as race_mod
from swingbot.core.backtesting.screen import trail
from tests.backtesting.screen.helpers import frame, random_walk

QUIET = (100.0, 101.0, 99.0, 100.0)     # high 101 - 6 = 95 never lifts the stop off 97
UP1 = (100.0, 104.0, 99.5, 103.0)       # stop on the next bar: 104 - 6 = 98
UP2 = (103.0, 108.0, 102.5, 107.0)      # next: 108 - 6 = 102
UP3 = (107.0, 110.0, 105.0, 106.0)      # next: 110 - 6 = 104


def _frame(bars):
    """Bar 0 is the signal bar; ``bars`` are (O, H, L, C) for bars 1.."""
    rows = [QUIET] + list(bars)
    o, h, l, c = (np.array(col, dtype=float) for col in zip(*rows))
    return frame(c, opens=o, highs=h, lows=l)


def _atr(df, value=2.0):
    return pd.Series(value, index=df.index)   # 1R = 3.0: initial stop 97, trail 6.0 below the high


def _one(bars, cap, **costs):
    df = _frame(bars)
    costs.setdefault("slippage_bps", 0.0)
    costs.setdefault("commission", 0.0)
    return trail.race_trail(df, [0], cap, atr=_atr(df), **costs)


def _stops(highs, entry=100.0, risk=3.0):
    return trail.trail_stops(np.array([highs], dtype=float), np.array([entry]),
                             np.array([risk]))[0]


def test_the_stop_ratchets_on_prior_highs_only():
    assert trail.TRAIL_ATR == 3.0
    assert _stops([104.0, 108.0, 110.0, 109.0]).tolist() == [97.0, 98.0, 102.0, 104.0]


def test_the_stop_never_moves_down():
    stops = _stops([104.0, 108.0, 103.0, 101.0, 99.0])
    assert stops.tolist() == [97.0, 98.0, 102.0, 102.0, 102.0]
    assert (np.diff(stops) >= 0).all()


def test_the_first_bar_carries_the_initial_stop_not_nan():
    stops = _stops([150.0, 100.0])
    assert np.isfinite(stops).all()
    assert stops.tolist() == [97.0, 144.0]


def test_a_later_high_never_changes_an_earlier_stop():
    """No lookahead: column j reads columns 0..j-1 only."""
    highs = np.array([104.0, 108.0, 110.0, 109.0, 111.0])
    base = _stops(highs)
    for j in range(len(highs)):
        bumped = highs.copy()
        bumped[j:] += 50.0
        assert _stops(bumped)[: j + 1].tolist() == base[: j + 1].tolist()


def test_a_reversal_exits_as_trail_at_the_raised_stop():
    out = _one([UP1, UP2, UP3, (106.0, 106.5, 103.0, 103.5), QUIET], cap=5)
    assert out.outcome.tolist() == ["trail"]
    assert out.exit_pos.tolist() == [4]
    assert out.gross_r.tolist() == [pytest.approx((104.0 - 100.0) / 3.0)]
    assert out.risk.tolist() == [3.0]        # r stays in the initial 1R


def test_an_exit_at_the_unraised_stop_is_labelled_stop():
    out = _one([QUIET, (99.0, 99.5, 96.5, 97.0), QUIET], cap=3)
    assert out.outcome.tolist() == ["stop"]
    assert out.exit_pos.tolist() == [2]
    assert out.gross_r.tolist() == [pytest.approx(-1.0)]


def test_the_first_bar_touching_the_initial_stop_exits():
    out = _one([(100.0, 100.5, 96.5, 98.0), QUIET], cap=2)
    assert out.outcome.tolist() == ["stop"]
    assert out.exit_pos.tolist() == [1]
    assert out.gross_r.tolist() == [pytest.approx(-1.0)]


def test_a_gap_through_the_initial_stop_exits_at_the_open():
    out = _one([QUIET, (95.0, 96.0, 94.0, 95.0), QUIET], cap=3)
    assert out.outcome.tolist() == ["gap_stop"]
    assert out.gross_r.tolist() == [pytest.approx(-5.0 / 3.0)]


def test_a_gap_through_a_raised_stop_is_gap_trail_and_can_be_a_gain():
    out = _one([UP1, UP2, UP3, (103.0, 103.5, 101.0, 102.0), QUIET], cap=5)
    assert out.outcome.tolist() == ["gap_trail"]
    assert out.exit_pos.tolist() == [4]
    assert out.gross_r.tolist() == [pytest.approx(1.0)]       # open 103, entry 100


def test_a_stop_equal_to_the_initial_stop_is_not_raised():
    """raised_j is strict: a high exactly 1R above entry (103 - 6 = 97)
    leaves the stop where it was, so the exit is still a plain stop."""
    out = _one([(100.0, 103.0, 99.0, 100.0), (100.0, 100.0, 96.0, 97.0), QUIET], cap=3)
    assert out.outcome.tolist() == ["stop"]
    assert out.gross_r.tolist() == [pytest.approx(-1.0)]


def test_no_exit_by_the_cap_is_a_timeout_at_the_cap_close():
    out = _one([QUIET, QUIET, (100.0, 101.0, 99.0, 100.5), QUIET], cap=3)
    assert out.outcome.tolist() == ["timeout"]
    assert out.exit_pos.tolist() == [3]
    assert out.gross_r.tolist() == [pytest.approx(0.5 / 3.0)]


def test_a_bar_own_high_never_raises_its_own_stop():
    """Bar 2's high 112 would put its stop at 106, above its low 101: it
    must not. Bar 3 is the first bar that stop is in force on."""
    out = _one([QUIET, (100.0, 112.0, 101.0, 111.0), (111.0, 111.5, 105.5, 110.0),
                (110.0, 111.0, 109.0, 110.0)], cap=4)
    assert out.outcome.tolist() == ["trail"]
    assert out.exit_pos.tolist() == [3]
    assert out.gross_r.tolist() == [pytest.approx(2.0)]       # stop 106, entry 100


def test_costs_are_slippage_on_both_fills_plus_commission_in_r():
    out = _one([UP1, UP2, UP3, (106.0, 106.5, 103.0, 103.5), QUIET], cap=5,
               slippage_bps=5.0, commission=0.02)
    entry_fill, exit_fill = 100.0 * 1.0005, 104.0 * 0.9995
    assert out.r[0] == pytest.approx((exit_fill - entry_fill) / 3.0 - 0.02)


def test_default_costs_come_from_config(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 0.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)
    df = _frame([UP1, UP2, UP3, (106.0, 106.5, 103.0, 103.5), QUIET])
    out = trail.race_trail(df, [0], 5, atr=_atr(df))
    assert out.r[0] == pytest.approx(4.0 / 3.0 - 0.02)


def test_a_race_that_would_read_past_the_frame_is_refused():
    df = _frame([QUIET, QUIET])
    with pytest.raises(ValueError):
        trail.race_trail(df, [0], 3, atr=_atr(df))


def test_no_events_is_an_empty_result():
    df = _frame([QUIET, QUIET])
    out = trail.race_trail(df, [], 2, atr=_atr(df))
    assert len(out) == 0 and out.r.size == 0


def test_several_events_race_independently_at_once():
    df = _frame([UP1, UP2, UP3, (106.0, 106.5, 103.0, 103.5), QUIET, QUIET, QUIET])
    both = trail.race_trail(df, [0, 2], 5, atr=_atr(df), slippage_bps=0.0, commission=0.0)
    for k, pos in enumerate([0, 2]):
        alone = trail.race_trail(df, [pos], 5, atr=_atr(df), slippage_bps=0.0,
                                 commission=0.0)
        assert both.take(np.array([k])).r.tolist() == alone.r.tolist()
        assert both.exit_pos[k] == alone.exit_pos[0]


def _perturb_after(df, pos):
    out = df.copy()
    rng = np.random.default_rng(99)
    scale = rng.uniform(0.5, 1.5, len(out) - pos - 1)
    for col in ("Open", "High", "Low", "Close"):
        out.iloc[pos + 1:, out.columns.get_loc(col)] *= scale
    return out


def test_a_bar_after_the_exit_does_not_change_the_race():
    """No lookahead on a fixture: rewrite every bar after the exit."""
    df = _frame([UP1, UP2, UP3, (106.0, 106.5, 103.0, 103.5), QUIET, QUIET])
    a = trail.race_trail(df, [0], 6, atr=_atr(df), slippage_bps=0.0, commission=0.0)
    changed = _perturb_after(df, int(a.exit_pos[0]))
    b = trail.race_trail(changed, [0], 6, atr=_atr(df), slippage_bps=0.0, commission=0.0)
    assert (a.r.tolist(), a.exit_pos.tolist(), a.outcome.tolist()) == (
        b.r.tolist(), b.exit_pos.tolist(), b.outcome.tolist())


def test_no_lookahead_on_a_random_walk():
    df = random_walk(900)
    atr = indicators.atr(df)
    events = np.arange(30, 820, 37)
    full = trail.race_trail(df, events, 60, atr=atr, slippage_bps=0.0, commission=0.0)
    for k, pos in enumerate(events):
        changed = _perturb_after(df, int(full.exit_pos[k]))
        one = trail.race_trail(changed, [pos], 60, atr=atr, slippage_bps=0.0,
                               commission=0.0)
        assert one.r[0] == pytest.approx(full.r[k], abs=1e-12)
        assert (one.exit_pos[0], one.outcome[0]) == (full.exit_pos[k], full.outcome[k])


def test_a_random_walk_race_is_never_stop_less_and_never_fixed_only():
    df = random_walk(900)
    atr = indicators.atr(df)
    events = np.arange(30, 820, 11)
    o, h = df["Open"].to_numpy(), df["High"].to_numpy()
    bars = events[:, None] + 1 + np.arange(60)[None, :]
    entry, risk = o[events + 1], race_mod.STOP_ATR * atr.to_numpy()[events]
    stops = trail.trail_stops(h[bars], entry, risk)
    assert np.isfinite(stops).all() and (stops >= (entry - risk)[:, None]).all()
    out = trail.race_trail(df, events, 60, atr=atr, slippage_bps=0.0, commission=0.0)
    assert set(out.outcome.tolist()) <= set(race_mod.SHAPE_OUTCOMES["trail"])
    assert {"trail", "timeout"} & set(out.outcome.tolist())
    assert (out.risk == risk).all()
