"""v140 fixed trade: entry next open, 1.5 ATR stop, 3 ATR target, gaps at the open."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import race as race_mod
from tests.backtesting.screen.helpers import frame

QUIET = (100.0, 101.0, 99.0, 100.0)     # never reaches stop 97 or target 106


def _frame(bars):
    """Bar 0 is the signal bar; ``bars`` are (O, H, L, C) for bars 1.."""
    rows = [QUIET] + list(bars)
    o, h, l, c = (np.array(col, dtype=float) for col in zip(*rows))
    return frame(c, opens=o, highs=h, lows=l)


def _atr(df, value=2.0):
    return pd.Series(value, index=df.index)   # risk 3.0: stop 97, target 106


def _one(bars, cap, **costs):
    df = _frame(bars)
    costs.setdefault("slippage_bps", 0.0)
    costs.setdefault("commission", 0.0)
    return race_mod.race(df, [0], cap, atr=_atr(df), **costs)


def test_stop_is_checked_first_on_a_bar_touching_both():
    out = _one([(100.0, 107.0, 96.0, 100.0), QUIET], cap=2)
    assert out.outcome.tolist() == ["stop"]
    assert out.gross_r.tolist() == [pytest.approx(-1.0)]
    assert out.exit_pos.tolist() == [1]


def test_target_hit_exits_at_the_target():
    out = _one([QUIET, (101.0, 106.5, 100.0, 105.0), QUIET], cap=3)
    assert out.outcome.tolist() == ["target"]
    assert out.gross_r.tolist() == [pytest.approx(2.0)]
    assert out.exit_pos.tolist() == [2]


def test_gap_through_the_stop_exits_at_the_open_below_minus_one_r():
    out = _one([QUIET, (95.0, 96.0, 94.0, 95.0), QUIET], cap=3)
    assert out.outcome.tolist() == ["gap_stop"]
    assert out.gross_r[0] == pytest.approx(-5.0 / 3.0)
    assert out.gross_r[0] < -1.0


def test_gap_over_the_target_exits_at_the_open():
    out = _one([QUIET, (108.0, 109.0, 107.0, 108.0), QUIET], cap=3)
    assert out.outcome.tolist() == ["gap_target"]
    assert out.gross_r[0] == pytest.approx(8.0 / 3.0)


def test_time_cap_exits_at_the_close_of_the_last_bar():
    out = _one([QUIET, QUIET, (100.0, 102.0, 99.0, 101.5), QUIET], cap=3)
    assert out.outcome.tolist() == ["timeout"]
    assert out.gross_r[0] == pytest.approx(0.5)
    assert out.exit_pos.tolist() == [3]


def test_costs_are_slippage_on_both_fills_plus_commission_in_r():
    out = _one([QUIET, (101.0, 106.5, 100.0, 105.0), QUIET], cap=3,
               slippage_bps=5.0, commission=0.02)
    entry_fill, exit_fill = 100.0 * 1.0005, 106.0 * 0.9995
    assert out.r[0] == pytest.approx((exit_fill - entry_fill) / 3.0 - 0.02)
    assert out.r[0] == pytest.approx(1.945667, abs=1e-6)
    assert out.gross_r[0] == pytest.approx(2.0)


def test_default_costs_come_from_config(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 0.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)
    df = _frame([QUIET, (101.0, 106.5, 100.0, 105.0), QUIET])
    out = race_mod.race(df, [0], 3, atr=_atr(df))
    assert out.r[0] == pytest.approx(2.0 - 0.02)


def test_a_race_that_would_read_past_the_frame_is_refused():
    df = _frame([QUIET, QUIET])
    with pytest.raises(ValueError):
        race_mod.race(df, [0], 3, atr=_atr(df))


def test_no_events_is_an_empty_result():
    df = _frame([QUIET, QUIET])
    out = race_mod.race(df, [], 2, atr=_atr(df))
    assert len(out) == 0 and out.r.size == 0


def test_warm_mask_needs_positive_atr_and_sma200():
    atr = pd.Series([np.nan, 0.0, 2.0, 2.0])
    sma = pd.Series([100.0, 100.0, np.nan, 100.0])
    assert race_mod.warm_mask(atr, sma).tolist() == [False, False, False, True]


def _book_frame(n=30):
    return frame(np.full(n, 100.0))     # quiet bars: every race times out


def test_run_book_counts_every_drop_and_skip():
    df = _book_frame()
    events = np.zeros(len(df), dtype=bool)
    events[[2, 4, 7, 9, 20, 27]] = True
    member = np.ones(len(df), dtype=bool)
    member[9] = False
    warm = np.ones(len(df), dtype=bool)
    warm[20] = False
    booked, counts = race_mod.run_book(
        df, events, 5, member=member, warm=warm, atr=_atr(df),
        slippage_bps=0.0, commission=0.0)
    assert booked.event_pos.tolist() == [2, 7]          # 4 sits inside 2's race
    assert booked.exit_pos.tolist() == [7, 12]
    assert counts == {"dropped_nonmember": 1, "dropped_warmup": 1,
                      "dropped_window": 1, "skipped_overlap": 1}


def test_an_event_on_the_exit_bar_opens_a_new_race():
    keep = race_mod.non_overlapping(np.array([2, 6, 7]), np.array([7, 11, 12]))
    assert keep.tolist() == [True, False, True]


def test_take_filters_every_field():
    df = _book_frame()
    out = race_mod.race(df, [1, 3], 5, atr=_atr(df), slippage_bps=0.0, commission=0.0)
    kept = out.take(np.array([False, True]))
    assert kept.event_pos.tolist() == [3] and len(kept.outcome) == 1


def test_a_bar_after_the_event_does_not_change_the_earlier_race():
    """No lookahead: truncating the frame after the race leaves it unchanged."""
    full = _frame([QUIET, (101.0, 106.5, 100.0, 105.0), QUIET, QUIET])
    cut = full.iloc[:4]
    a = race_mod.race(full, [0], 3, atr=_atr(full), slippage_bps=0.0, commission=0.0)
    b = race_mod.race(cut, [0], 3, atr=_atr(cut), slippage_bps=0.0, commission=0.0)
    assert a.r.tolist() == b.r.tolist() and a.exit_pos.tolist() == b.exit_pos.tolist()
