"""v140 turn_of_month: t is the last trading day of its calendar month, from
the ticker's own bar dates (frozen reading F1)."""
import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen.ideas import turn_of_month
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk


def _on(dates):
    return turn_of_month.events(frame(np.full(len(dates), 100.0), index=dates)).tolist()


def test_last_bar_of_each_month_from_the_bar_dates():
    dates = ["2019-01-29", "2019-01-30", "2019-01-31", "2019-02-01",
             "2019-02-27", "2019-02-28", "2019-03-01"]
    assert _on(dates) == [False, False, True, False, False, True, False]


def test_a_holiday_month_end_uses_the_last_bar_actually_traded():
    # Good Friday 2018-03-30: the last March session was Thursday the 29th.
    assert _on(["2018-03-28", "2018-03-29", "2018-04-02", "2018-04-03"]) == [
        False, True, False, False]


def test_the_final_bar_of_a_frame_is_never_an_event():
    assert _on(["2019-01-31"]) == [False]
    empty = frame(np.array([], dtype=float), index=pd.DatetimeIndex([]))
    assert turn_of_month.events(empty).tolist() == []


def test_turn_of_month_reads_no_prices():
    a = random_walk(300)
    b = a.copy()
    b[:] = np.random.default_rng(1).uniform(1.0, 500.0, size=b.shape)
    assert turn_of_month.events(a).equals(turn_of_month.events(b))
    assert turn_of_month.events(a).name == "turn_of_month"


def test_reads_no_later_bar_except_the_truncated_frames_last_date():
    assert_prefix_stable(turn_of_month.events, random_walk(300),
                         [20, 21, 22, 150, 299], skip_last=True)
