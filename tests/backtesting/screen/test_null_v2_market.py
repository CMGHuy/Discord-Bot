"""v230 A2 stage 2, market scope: the same ticker's trailing 252 sessions,
same trend state, embargo of CAP bars around every raw event, floor 5, one
generator per ticker. No null bar postdates its event."""
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import null, null_v2

IDEA = "x"
CAP = 10
N = 600


def _panel(ticker="AAA", events=(), trend=None, eligible=None):
    dates = pd.bdate_range("2012-01-02", periods=N).to_numpy()
    ev = np.zeros(N, dtype=bool)
    ev[list(events)] = True
    elig = (np.ones(N, dtype=bool) if eligible is None else eligible) & ~ev
    tr = np.ones(N, dtype=bool) if trend is None else trend
    return null_v2.TickerPanel(ticker, dates, elig, tr, np.full(N, 0.02), ev)


def _pool(panel, pos):
    return null_v2.market_pool(panel, pos, cap=CAP).tolist()


def test_pool_is_the_trailing_window_short_of_the_event_embargo():
    assert null_v2.TRAILING_DAYS == 252
    assert _pool(_panel(events=(400,)), 400) == list(range(400 - 252, 400 - CAP))


def test_pool_starts_at_the_first_bar_when_history_is_short():
    assert _pool(_panel(events=(100,)), 100) == list(range(0, 100 - CAP))


def test_pool_skips_bars_within_cap_of_an_earlier_event():
    pool = _pool(_panel(events=(300, 400)), 400)
    assert pool == [p for p in range(148, 390) if abs(p - 300) > CAP]


def test_pool_matches_the_event_bar_trend_state_and_eligibility():
    trend = np.arange(N) % 2 == 1                            # bar 400 is down-trend
    eligible = np.ones(N, dtype=bool)
    eligible[200:250] = False
    pool = _pool(_panel(events=(400,), trend=trend, eligible=eligible), 400)
    assert pool and all(p % 2 == 0 for p in pool)
    assert not set(range(200, 250)) & set(pool)


def test_later_events_never_change_the_pool():
    alone = _pool(_panel(events=(400,)), 400)
    assert _pool(_panel(events=(400, 405, 420, 500)), 400) == alone
    assert max(alone) < 400 - CAP


def test_draw_takes_k_bars_from_the_same_ticker_on_its_own_seed():
    panel = _panel(events=(400,))
    result = null_v2.draw_market_scope({"AAA": panel}, {"AAA": [400]}, idea=IDEA, cap=CAP)
    table = result.table
    assert tuple(table.columns) == null_v2.DRAW_COLUMNS
    assert (table.null_ticker == "AAA").all() and (table.event_ticker == "AAA").all()
    assert (table.event_date == pd.Timestamp(panel.dates[400])).all()
    assert table.fill.isna().all()
    rng = np.random.default_rng(null.null_seed("x:v2", "AAA"))
    expected = np.sort(rng.choice(null_v2.market_pool(panel, 400, cap=CAP),
                                  size=null.K, replace=False))
    assert table.null_pos.tolist() == expected.tolist()
    assert (result.slots, result.unfilled, result.event_dates, result.starved_dates) == (
        null.K, 0, 1, 0)


def test_events_are_consumed_ascending_and_other_tickers_leave_a_ticker_alone():
    aaa = _panel(events=(300, 400))
    one = null_v2.draw_market_scope({"AAA": aaa}, {"AAA": [400, 300]}, idea=IDEA, cap=CAP)
    assert one.table.event_pos.tolist() == [300] * null.K + [400] * null.K
    panels = {"AAA": aaa, "BBB": _panel("BBB", events=(350,))}
    two = null_v2.draw_market_scope(panels, {"BBB": [350], "AAA": [300, 400]},
                                    idea=IDEA, cap=CAP)
    mine = two.table[two.table.event_ticker == "AAA"].reset_index(drop=True)
    pd.testing.assert_frame_equal(mine, one.table)


def test_a_short_pool_drops_the_event_and_starves_its_date_once():
    panels = {"AAA": _panel(events=(3, 400)), "BBB": _panel("BBB", events=(3,))}
    result = null_v2.draw_market_scope(panels, {"AAA": [3, 400], "BBB": [3]},
                                       idea=IDEA, cap=CAP)
    assert result.dropped == Counter({"AAA": 1, "BBB": 1})
    assert (result.event_dates, result.starved_dates) == (2, 1)
    null_v2.check_starvation(result, "market")                # 1 of 2: not above half


def test_null_starved_fires_before_any_race():
    panels = {"AAA": _panel(events=(3,)), "BBB": _panel("BBB", events=(3,))}
    result = null_v2.draw_market_scope(panels, {"AAA": [3], "BBB": [3]}, idea=IDEA, cap=CAP)
    assert result.table.empty
    with pytest.raises(null_v2.NullRefusal) as caught:
        null_v2.check_starvation(result, "market")
    assert caught.value.code == null_v2.NULL_STARVED


def test_an_unknown_booked_ticker_is_refused():
    with pytest.raises(ValueError, match="ZZZ"):
        null_v2.draw_market_scope({"AAA": _panel()}, {"ZZZ": [400]}, idea=IDEA, cap=CAP)
