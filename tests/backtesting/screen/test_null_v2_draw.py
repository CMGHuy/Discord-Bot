"""v230 A2 stage 2, ticker scope: other tickers on the event's date, same
trend state, same ATR% tercile, no event of the idea that day; K = 20, floor
5; one generator per date consumed in sorted-ticker order."""
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators, null, null_v2
from swingbot.core.backtesting.screen import race as race_mod
from tests.backtesting.screen.helpers import random_walk

IDEA = "x"
DAYS = pd.bdate_range("2015-01-05", periods=5)
CAP = 10


def _panel(ticker, *, eligible=True, trend=True, atr=0.02, event=(), control=None):
    n = len(DAYS)
    ev = np.zeros(n, dtype=bool)
    ev[list(event)] = True
    return null_v2.TickerPanel(ticker, DAYS.to_numpy(), np.full(n, eligible) & ~ev,
                               np.full(n, trend), np.full(n, atr, dtype=float), ev,
                               None if control is None else np.asarray(control, dtype=bool))


def _xs(n=30, **special):
    names = [f"T{i:02d}" for i in range(n)]
    return null_v2.cross_section({t: _panel(t, **special.get(t, {})) for t in names})


def _names(xs, cols):
    return [xs.tickers[j] for j in cols]


def test_date_seed_is_the_v1_seed_on_the_idea_v2_name_and_the_day():
    assert null_v2.date_seed(IDEA, DAYS[0]) == null.null_seed("x:v2", "2015-01-05")
    assert null_v2.date_seed(IDEA, DAYS[0]) != null_v2.date_seed(IDEA, DAYS[1])


def test_pool_drops_the_event_ticker_event_tickers_and_ineligible_ones():
    xs = _xs(T00={"event": (2,)}, T01={"event": (2,)}, T02={"eligible": False})
    assert _names(xs, null_v2.ticker_pool(xs, 2, 0)) == [f"T{i:02d}" for i in range(3, 30)]


def test_pool_matches_trend_state_and_atr_tercile():
    xs = _xs(T03={"trend": False}, T04={"atr": 0.05}, T05={"atr": 0.05}, T06={"atr": 0.05})
    pool = _names(xs, null_v2.ticker_pool(xs, 1, 0))
    assert not {"T03", "T04", "T05", "T06"} & set(pool) and len(pool) == 25
    assert _names(xs, null_v2.ticker_pool(xs, 1, 4)) == ["T05", "T06"]


def test_pool_can_require_the_control_flag():
    xs = _xs(**{f"T{i:02d}": {"control": [i % 2 == 0] * 5} for i in range(30)})
    pool = null_v2.ticker_pool(xs, 1, 0, require_control=True)
    assert _names(xs, pool) == [f"T{i:02d}" for i in range(2, 30, 2)]
    with pytest.raises(ValueError, match="control"):
        null_v2.ticker_pool(_xs(), 1, 0, require_control=True)


def test_draw_takes_k_sorted_pool_bars_and_their_own_positions():
    xs = _xs(T00={"event": (1,)}, T03={"event": (1, 3)})
    result = null_v2.draw_ticker_scope(xs, {"T00": [1], "T03": [1, 3]}, idea=IDEA)
    table = result.table
    assert tuple(table.columns) == null_v2.DRAW_COLUMNS
    first = table[(table.event_ticker == "T00")]
    assert len(first) == null.K and first.null_ticker.is_unique
    assert list(first.null_ticker) == sorted(first.null_ticker)
    assert not {"T00", "T03"} & set(first.null_ticker)
    assert (first.event_date == DAYS[1]).all() and (first.null_pos == 1).all()
    assert table.fill.isna().all()
    assert (result.slots, result.unfilled, result.event_dates, result.starved_dates) == (
        3 * null.K, 0, 2, 0)


def test_draw_replays_the_date_generator_in_sorted_ticker_order():
    xs = _xs(T00={"event": (1,)}, T05={"event": (1,)})
    table = null_v2.draw_ticker_scope(xs, {"T05": [1], "T00": [1]}, idea=IDEA).table
    rng = np.random.default_rng(null_v2.date_seed(IDEA, DAYS[1]))
    for col in (0, 5):
        pool = null_v2.ticker_pool(xs, 1, col)
        expected = _names(xs, np.sort(rng.choice(pool, size=null.K, replace=False)))
        assert list(table[table.event_ticker == xs.tickers[col]].null_ticker) == expected


def test_draw_is_deterministic_and_another_date_leaves_a_date_alone():
    xs = _xs(T00={"event": (1,)}, T07={"event": (4,)})
    once = null_v2.draw_ticker_scope(xs, {"T00": [1]}, idea=IDEA).table
    pd.testing.assert_frame_equal(once, null_v2.draw_ticker_scope(xs, {"T00": [1]}, idea=IDEA).table)
    both = null_v2.draw_ticker_scope(xs, {"T00": [1], "T07": [4]}, idea=IDEA).table
    pd.testing.assert_frame_equal(both[both.event_ticker == "T00"].reset_index(drop=True), once)


def test_the_floor_is_inclusive_and_a_short_pool_drops_and_starves():
    kept = null_v2.draw_ticker_scope(_xs(6, T00={"event": (1,)}), {"T00": [1]}, idea=IDEA)
    assert len(kept.table) == null.MIN_CANDIDATES and kept.starved_dates == 0
    short = null_v2.draw_ticker_scope(_xs(6, T00={"event": (1,)}, T05={"trend": False}),
                                      {"T00": [1]}, idea=IDEA)
    assert short.table.empty and tuple(short.table.columns) == null_v2.DRAW_COLUMNS
    assert short.dropped == Counter({"T00": 1})
    assert (short.event_dates, short.starved_dates, short.slots) == (1, 1, 0)


def test_an_unknown_booked_ticker_is_refused():
    with pytest.raises(ValueError, match="ZZZ"):
        null_v2.draw_ticker_scope(_xs(), {"ZZZ": [1]}, idea=IDEA)


def _result(dates, starved):
    return null_v2.DrawResult(null_v2._table([]), Counter(), dates, starved, 0, 0)


@pytest.mark.parametrize("scope, code", [("ticker", "SCOPE_MISMATCH"),
                                         ("market", "NULL_STARVED")])
def test_refusal_fires_only_above_half_the_event_dates(scope, code):
    null_v2.check_starvation(_result(4, 2), scope)          # exactly half: no refusal
    null_v2.check_starvation(_result(0, 0), scope)
    with pytest.raises(null_v2.NullRefusal) as caught:
        null_v2.check_starvation(_result(4, 3), scope)
    assert caught.value.code == code and str(caught.value).startswith(f"{code}: 3 of 4")
    assert isinstance(caught.value, ValueError)


def test_refusal_rejects_an_unknown_scope():
    with pytest.raises(ValueError, match="scope"):
        null_v2.check_starvation(_result(1, 0), "sector")


def _ctx(df):
    atr = indicators.atr(df)
    sma200 = indicators.sma(df["Close"], 200)
    prior_high = df["High"].shift(1).rolling(20).max()
    return {"raw": (df["Close"] > prior_high).to_numpy(dtype=bool),
            "member": np.ones(len(df), dtype=bool), "atr": atr,
            "warm": race_mod.warm_mask(atr, sma200), "trend": null.trend_state(df, sma200)}


def _frames_xs(frames):
    return null_v2.cross_section({t: null_v2.ticker_panel(t, df, _ctx(df), cap=CAP)
                                  for t, df in frames.items()})


def test_pools_change_under_truncation_only_through_completeness():
    """Spec Constraints: cut every ticker's tail; the pool at t changes only
    through the race-completeness flag."""
    frames = {f"T{i:02d}": random_walk(600, seed=i + 1) for i in range(12)}
    cut = 450
    full = _frames_xs(frames)
    part = _frames_xs({t: df.iloc[: cut + 1] for t, df in frames.items()})
    for row in range(200, cut - CAP + 1):
        for col in range(12):
            assert (null_v2.ticker_pool(part, row, col)
                    == null_v2.ticker_pool(full, row, col)).all(), (row, col)
    assert not part.eligible[cut - CAP + 1:].any()
