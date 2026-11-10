"""v211 V211-3: BREADTH_ATR1[t] = share of PIT members with a finite move
(Close[t] - Close[t-1]) / ATR14[t-1] at or below -1.0; reads bars <= t only."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import breadth
from tests.backtesting.screen.helpers import assert_prefix_stable, random_walk

ALWAYS = [("2000-01-01", "9999-12-31")]
SESSIONS = pd.bdate_range("2010-01-04", periods=5)


def _fixed_moves(monkeypatch, moves: dict):
    """member_atr_moves returns the given per-session values for each frame."""
    by_id = {id(frame): pd.Series(values, index=frame.index, dtype=float)
             for frame, values in moves.values()}
    monkeypatch.setattr(breadth, "member_atr_moves", lambda df: by_id[id(df)])
    return {name: frame for name, (frame, _) in moves.items()}


def _flat(index=SESSIONS) -> pd.DataFrame:
    return pd.DataFrame({c: 1.0 for c in ("Open", "High", "Low", "Close", "Volume")}, index=index)


def test_constants():
    assert breadth.NAME == "BREADTH_ATR1"
    assert breadth.ATR_MOVE == -1.0


def test_share_counts_moves_at_or_below_minus_one_atr(monkeypatch):
    nan = np.nan
    frames = _fixed_moves(monkeypatch, {
        "A": (_flat(), [nan, 0.0, -1.0, 0.5, 0.0]),       # exactly -1.0 counts
        "B": (_flat(), [nan, 0.0, -0.999, 0.5, 0.0]),
        "C": (_flat(), [nan, 0.0, -2.5, 0.5, 0.0]),
        "D": (_flat(), [nan, 0.0, nan, 0.5, 0.0]),        # no finite move: out of the denominator
    })
    table = breadth.breadth_atr1(frames, {k: ALWAYS for k in frames}, SESSIONS)
    assert table["Close"].iloc[2] == pytest.approx(2 / 3)
    assert table["Volume"].iloc[2] == 3
    assert table["Close"].iloc[3] == 0.0 and table["Volume"].iloc[3] == 4


def test_a_session_without_any_finite_move_is_zero_not_nan(monkeypatch):
    frames = _fixed_moves(monkeypatch, {"A": (_flat(), [np.nan] * 5)})
    table = breadth.breadth_atr1(frames, {"A": ALWAYS}, SESSIONS)
    assert table["Close"].tolist() == [0.0] * 5
    assert table["Volume"].tolist() == [0] * 5
    assert np.isfinite(table.to_numpy(dtype=float)).all()


def test_shape_is_a_contiguous_ohlcv_frame(monkeypatch):
    frames = _fixed_moves(monkeypatch, {"A": (_flat(), [np.nan, -3.0, 0.0, 0.0, 0.0])})
    table = breadth.breadth_atr1(frames, {"A": ALWAYS}, SESSIONS)
    assert list(table.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert table.index.name == "Date" and table.index.equals(SESSIONS)
    for column in ("Open", "High", "Low"):
        assert table[column].equals(table["Close"])
    assert table["Close"].iloc[1] == 1.0


def test_membership_is_point_in_time_and_half_open(monkeypatch):
    frames = _fixed_moves(monkeypatch, {
        "A": (_flat(), [-2.0] * 5),
        "B": (_flat(), [0.0] * 5),
    })
    # Session 0 has no previous session, so nobody counts there. B joins on
    # session 1 and leaves before session 3 (end is exclusive).
    spans = {"A": ALWAYS, "B": [("2010-01-05", "2010-01-07")]}
    table = breadth.breadth_atr1(frames, spans, SESSIONS)
    assert table["Volume"].tolist() == [0, 2, 2, 1, 1]
    assert table["Close"].tolist() == [0.0, 0.5, 0.5, 1.0, 1.0]


def test_member_mask_reads_the_open_end_without_overflow():
    mask = breadth.member_mask([("2010-01-06", "9999-12-31")], SESSIONS)
    assert mask.tolist() == [False, False, True, True, True]


def test_symbols_missing_a_frame_or_spans_are_ignored(monkeypatch):
    frames = _fixed_moves(monkeypatch, {"A": (_flat(), [-2.0] * 5), "Z": (_flat(), [-2.0] * 5)})
    table = breadth.breadth_atr1(frames, {"A": ALWAYS, "Y": ALWAYS}, SESSIONS)
    assert table["Volume"].tolist() == [0, 1, 1, 1, 1]


def test_a_missing_bar_leaves_the_denominator_that_day_and_the_next():
    sessions = pd.bdate_range("2010-01-04", periods=60)
    full = random_walk(60, seed=3)
    holed = random_walk(60, seed=5).drop(sessions[40])
    table = breadth.breadth_atr1({"A": holed, "B": full}, {"A": ALWAYS, "B": ALWAYS}, sessions)
    assert table["Volume"].iloc[38:43].tolist() == [2, 2, 1, 1, 2]


def test_member_moves_read_the_atr_dated_t_minus_1():
    df = random_walk(80, seed=11)
    before = breadth.member_atr_moves(df)
    wider = df.copy()
    wider.iloc[50, wider.columns.get_loc("High")] += 50.0      # widens TR (and ATR) at bar 50 only
    after = breadth.member_atr_moves(wider)
    assert after.iloc[50] == before.iloc[50]                   # ATR[49] divides bar 50
    assert after.iloc[51] != before.iloc[51]


def test_member_moves_are_prefix_stable():
    assert_prefix_stable(breadth.member_atr_moves, random_walk(120, seed=2), [20, 60, 119])


def test_breadth_at_t_ignores_every_later_bar():
    sessions = pd.bdate_range("2010-01-04", periods=120)
    frames = {name: random_walk(120, seed=seed) for name, seed in (("A", 1), ("B", 2), ("C", 4))}
    spans = {name: ALWAYS for name in frames}
    full = breadth.breadth_atr1(frames, spans, sessions)
    for t in (20, 75, 119):
        cut = {name: df.iloc[: t + 1] for name, df in frames.items()}
        part = breadth.breadth_atr1(cut, spans, sessions[: t + 1])
        pd.testing.assert_frame_equal(part, full.iloc[: t + 1], check_exact=False, rtol=1e-12)
