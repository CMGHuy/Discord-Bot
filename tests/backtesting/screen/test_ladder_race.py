"""v238 rung 2: close-anchored levels, open entry, gap fills priced, never dropped."""
import numpy as np
import pytest

from swingbot.core.backtesting.screen import indicators, ladder_race as lr, race, sides
from swingbot.core.backtesting.screen.ladder import LadderEvent
from swingbot.core.edge import frictions
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk

QUIET = (100.0, 101.0, 99.0, 100.0)     # signal bar: close 100
FREE = {"slippage_bps": 0.0, "commission": 0.0}


def _frame(bars):
    o, h, l, c = (np.array(col, dtype=float) for col in zip(*bars))
    return frame(c, start="2017-03-01", opens=o, highs=h, lows=l)


def _race(bars, cap=3, direction="long", **costs):
    """ATR 2.0 -> risk 3: long stop 97 / target 106; short stop 103 / target 94."""
    df = _frame(bars)
    atr = np.full(len(df), 2.0)
    stop, target = lr.orderable_levels(df, [0], atr=atr, direction=direction)
    return df, lr.race_levels(df, [0], cap, stop=stop, target=target,
                              direction=direction, **(costs or FREE))


def test_levels_are_anchored_on_the_signal_close():
    df = _frame([QUIET, QUIET])
    atr = np.full(2, 2.0)
    assert [a.tolist() for a in lr.orderable_levels(df, [0], atr=atr, direction="long")] == [[97.0], [106.0]]
    assert [a.tolist() for a in lr.orderable_levels(df, [0], atr=atr, direction="short")] == [[103.0], [94.0]]
    with pytest.raises(ValueError):
        lr.orderable_levels(df, [0], atr=atr, direction="up")


def test_target_is_measured_from_the_close_not_the_open():
    bars = [QUIET, (101.0, 102.0, 100.0, 101.0), (101.0, 106.5, 100.5, 106.0), QUIET]
    df, out = _race(bars)
    assert out.outcome.tolist() == ["target"]
    assert out.entry[0] == 101.0 and out.risk[0] == 3.0
    assert out.gross_r[0] == pytest.approx(5.0 / 3.0)
    screened = race.race(df, [0], 3, atr=np.full(len(df), 2.0), **FREE)
    assert screened.outcome.tolist() != ["target"]      # the open-anchored target sits at 107


def test_an_entry_open_below_the_stop_enters_and_exits_at_that_open():
    df, out = _race([QUIET, (95.0, 96.0, 94.0, 95.0), QUIET, QUIET],
                    slippage_bps=None, commission=None)
    assert out.outcome.tolist() == ["gap_stop"] and out.exit_pos.tolist() == [1]
    assert out.entry[0] == 95.0 and out.gross_r[0] == 0.0
    costs = (frictions.apply_frictions(95.0, "sell") - frictions.apply_frictions(95.0, "buy")) / 3.0
    assert out.r[0] == pytest.approx(costs - frictions.commission_r())
    assert out.r[0] < 0.0


def test_an_entry_open_above_the_target_exits_at_that_open():
    _, out = _race([QUIET, (108.0, 109.0, 107.0, 108.0), QUIET, QUIET])
    assert out.outcome.tolist() == ["gap_target"] and out.gross_r[0] == 0.0


def test_a_later_gap_through_the_stop_fills_at_the_open_below_minus_one_r():
    _, out = _race([QUIET, QUIET, (94.0, 95.0, 93.0, 94.0), QUIET])
    assert out.outcome.tolist() == ["gap_stop"]
    assert out.gross_r[0] == pytest.approx(-2.0) and out.gross_r[0] < -1.0
    assert lr.gap_through(out) == (1, pytest.approx(-2.0))


def test_the_time_cap_exits_at_the_close_and_no_gap_is_counted():
    _, out = _race([QUIET, QUIET, (100.0, 101.0, 99.0, 102.0), QUIET], cap=2)
    assert out.outcome.tolist() == ["timeout"] and out.exit_pos.tolist() == [2]
    assert out.gross_r[0] == pytest.approx(2.0 / 3.0)
    assert lr.gap_through(out) == (0, 0.0)


def test_short_mirror_pays_borrow_through_sides_net_r():
    bars = [QUIET, (99.0, 100.0, 98.0, 99.0), (95.0, 96.0, 93.5, 94.0), QUIET]
    df, out = _race(bars, direction="short", slippage_bps=None, commission=None)
    assert out.outcome.tolist() == ["target"] and out.entry[0] == 99.0
    assert out.gross_r[0] == pytest.approx(5.0 / 3.0)
    days = sides.holding_days(df.index, np.array([1]), out.exit_pos)
    expected = sides.net_r(np.array([99.0]), np.array([94.0]), np.array([3.0]),
                           direction="short", days=days)
    assert out.r[0] == pytest.approx(expected[0])


def test_bad_levels_and_short_frames_are_refused():
    df = _frame([QUIET, QUIET, QUIET])
    with pytest.raises(ValueError, match="stop"):
        lr.race_levels(df, [0], 1, stop=np.array([101.0]), target=np.array([106.0]))
    with pytest.raises(ValueError, match="stop"):
        lr.race_levels(df, [0], 1, stop=np.array([97.0]), target=np.array([99.0]))
    with pytest.raises(ValueError, match="past the frame"):
        lr.race_levels(df, [0], 5, stop=np.array([97.0]), target=np.array([106.0]))
    empty = lr.race_levels(df, [], 1, stop=np.array([]), target=np.array([]))
    assert len(empty) == 0


def test_levels_never_read_a_later_bar():
    df = random_walk(260, seed=11)

    def stops(d):
        return lr.orderable_levels(d, np.arange(len(d)), atr=indicators.atr(d), direction="long")[0]

    assert_prefix_stable(stops, df, [30, 120, 259])


def test_to_events_carries_dates_and_the_stress_book():
    bars = [QUIET, (101.0, 102.0, 100.0, 101.0), (101.0, 106.5, 100.5, 106.0), QUIET]
    df, out = _race(bars)
    _, stressed = _race(bars, slippage_bps=lr.STRESS_FACTOR * 5.0, commission=0.0)
    [event] = lr.to_events("AAA", df, out, stress=stressed)
    assert isinstance(event, LadderEvent)
    assert (event.signal_date, event.entry_date, event.exit_date) == (
        "2017-03-01", "2017-03-02", "2017-03-03")
    assert event.outcome == "target" and event.r == pytest.approx(5.0 / 3.0)
    assert event.r_stress == pytest.approx(float(stressed.r[0])) and event.r_stress < event.r
    assert event.r_null is None
    assert lr.to_events("AAA", df, out)[0].r_stress is None
    other = lr.race_levels(df, [1], 1, stop=np.array([98.0]), target=np.array([107.0]), **FREE)
    with pytest.raises(ValueError, match="same events"):
        lr.to_events("AAA", df, out, stress=other)
