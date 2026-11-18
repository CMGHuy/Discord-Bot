"""v230 A2 stage 2: the level-entry draw on the null ticker's own bars and
ATR14, the avoid control draw, and the dispatcher that ends in the refusal."""
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators, null, null_v2
from swingbot.core.backtesting.screen.ideas import Idea
from tests.backtesting.screen.helpers import random_walk

IDEA = "x"
DAYS = pd.bdate_range("2015-01-05", periods=5)
OPEN = 100.0


def _panel(ticker, *, high=103.0, low=97.0, atr=2.0, event=(), control=None, n=len(DAYS),
           dates=DAYS):
    ev = np.zeros(n, dtype=bool)
    ev[list(event)] = True
    bars = np.column_stack([np.full(n, OPEN), np.full(n, high), np.full(n, low),
                            np.full(n, atr)])
    return null_v2.TickerPanel(ticker, dates.to_numpy(), ~ev, np.full(n, True),
                               np.full(n, 0.02), ev,
                               None if control is None else np.asarray(control, dtype=bool),
                               bars)


def _universe(n=30, **special):
    panels = {f"T{i:02d}": _panel(f"T{i:02d}", **special.get(f"T{i:02d}", {}))
              for i in range(n)}
    return null_v2.cross_section(panels), panels


def _level(xs, panels, booked, depths):
    return null_v2.draw_ticker_level(xs, panels, booked, depths, idea=IDEA, direction="long")


def _idea(**kw):
    return Idea(name=IDEA, events=lambda df: df["Close"] > 0, time_cap_bars=4, **kw)


@pytest.mark.parametrize("row, direction, expected", [
    ((100.0, 103.0, 97.0, 2.0), "long", 102.0),
    ((100.0, 102.0, 97.0, 2.0), "long", 102.0),      # High == level fills (v1 >=)
    ((100.0, 101.9, 97.0, 2.0), "long", np.nan),
    ((100.0, 103.0, 98.0, 2.0), "short", 98.0),      # Low == level fills (v1 <=)
    ((100.0, 103.0, 98.1, 2.0), "short", np.nan),
    ((100.0, 103.0, 97.0, np.nan), "long", np.nan),  # row 0: no previous ATR
    ((100.0, 103.0, 97.0, 0.0), "long", np.nan),
])
def test_level_fill_reads_open_high_low_and_the_previous_atr(row, direction, expected):
    got = null_v2.level_fill(np.asarray(row), 1.0, direction)
    assert (np.isnan(got) and np.isnan(expected)) or got == pytest.approx(expected)


def test_level_fill_refuses_an_unknown_direction():
    with pytest.raises(ValueError, match="direction"):
        null_v2.level_fill(np.array([100.0, 103.0, 97.0, 2.0]), 1.0, "flat")


@pytest.mark.parametrize("direction", ["long", "short"])
def test_level_fill_matches_the_v1_rule_bar_for_bar(direction):
    df = random_walk(300, seed=11)
    atr = indicators.atr(df).to_numpy(dtype=float)
    bars = np.column_stack([df["Open"], df["High"], df["Low"], np.r_[np.nan, atr[:-1]]])
    positions = np.arange(len(df))
    fill, ok = null._null_fills(df, positions, 0.3, atr, direction)
    ours = np.array([null_v2.level_fill(bars[p], 0.3, direction) for p in positions])
    np.testing.assert_allclose(ours[ok], fill[ok])
    assert np.isnan(ours[~ok]).all()


def test_level_fills_use_the_null_tickers_own_open_and_atr():
    panels = {f"T{i:02d}": _panel(f"T{i:02d}", high=150.0, atr=1.0 + i / 10,
                                  event=(2,) if i == 0 else ()) for i in range(30)}
    xs = null_v2.cross_section(panels)
    table = _level(xs, panels, {"T00": [2]}, {"T00": [0.5]}).table
    assert len(table) == null.K and (table.null_pos == 2).all()
    atr = table.null_ticker.map(lambda t: 1.0 + int(t[1:]) / 10)
    np.testing.assert_allclose(table.fill, OPEN + 0.5 * atr)
    assert "T00" not in set(table.null_ticker)


def test_unfilled_first_draws_are_replaced_in_child_permutation_order():
    # odd tickers reach the level 101, even ones (High 100.5) never do
    panels = {f"T{i:02d}": _panel(f"T{i:02d}", high=150.0 if i % 2 else 100.5,
                                  event=(1,) if i == 0 else ()) for i in range(61)}
    xs = null_v2.cross_section(panels)
    got = _level(xs, panels, {"T00": [1]}, {"T00": [0.5]})
    pool = null_v2.ticker_pool(xs, 1, 0)
    seed = null_v2.date_seed(IDEA, DAYS[1])
    first = np.random.default_rng(seed).choice(pool, size=null.K, replace=False)
    kept = [j for j in first.tolist() if j % 2]
    order = np.random.default_rng(null.child_seed(seed)).permutation(np.setdiff1d(pool, first))
    kept += [j for j in order.tolist() if j % 2][: null.K - len(kept)]
    assert list(got.table.null_ticker) == [xs.tickers[j] for j in sorted(kept)]
    assert (got.slots, got.unfilled, got.dropped) == (null.K, 0, Counter())


def test_slots_left_unfilled_stay_as_blank_rows():
    panels = {f"T{i:02d}": _panel(f"T{i:02d}", high=150.0 if i in (1, 2, 3) else 100.5,
                                  event=(1,) if i == 0 else ()) for i in range(11)}
    xs = null_v2.cross_section(panels)
    got = _level(xs, panels, {"T00": [1]}, {"T00": [0.5]})
    assert got.slots == len(got.table) == 10            # pool of 10 < K
    assert got.unfilled == int((got.table.null_pos < 0).sum()) == 7
    assert list(got.table.null_ticker) == ["T01", "T02", "T03"] + [""] * 7
    assert got.table.fill[3:].isna().all() and got.dropped == Counter()


def test_an_event_without_any_fill_drops_but_does_not_starve():
    panels = {f"T{i:02d}": _panel(f"T{i:02d}", high=100.5, event=(1,) if i == 0 else ())
              for i in range(11)}
    xs = null_v2.cross_section(panels)
    got = _level(xs, panels, {"T00": [1]}, {"T00": [0.5]})
    assert got.dropped == Counter({"T00": 1}) and got.starved_dates == 0
    assert (got.slots, got.unfilled, len(got.table)) == (10, 10, 10)


def test_a_short_level_pool_drops_and_starves():
    xs, panels = _universe(4, T00={"event": (1,)})
    got = _level(xs, panels, {"T00": [1]}, {"T00": [0.5]})
    assert got.dropped == Counter({"T00": 1}) and (got.starved_dates, got.slots) == (1, 0)


def test_depths_need_one_value_per_booked_event():
    xs, panels = _universe()
    with pytest.raises(ValueError, match="depth"):
        _level(xs, panels, {"T00": [1, 2]}, {"T00": [0.5]})


def test_control_draw_requires_the_flag_and_uses_its_own_seed():
    xs, panels = _universe(40, **{f"T{i:02d}": {"control": [i % 3 != 0] * 5}
                                  for i in range(40)})
    got = null_v2.draw_control(xs, {"T01": [2]}, idea=IDEA)
    cols = [xs.tickers.index(t) for t in got.table.null_ticker]
    assert all(xs.control[2, j] for j in cols)
    pool = null_v2.ticker_pool(xs, 2, 1, require_control=True)
    rng = np.random.default_rng(null.null_seed("x:v2:control", "2015-01-07"))
    assert cols == np.sort(rng.choice(pool, size=null.K, replace=False)).tolist()


def test_control_below_the_floor_is_counted_never_refused():
    xs, _ = _universe(30, **{"T02": {"control": [True] * 5}, "T03": {"control": [True] * 5}})
    got = null_v2.draw_control(xs, {"T01": [2]}, idea=IDEA)
    assert got.dropped == Counter({"T01": 1}) and got.table.empty


def test_control_draw_without_a_control_flag_is_refused():
    xs, _ = _universe()
    with pytest.raises(ValueError, match="control"):
        null_v2.draw_control(xs, {"T01": [2]}, idea=IDEA)


def test_draw_dispatches_the_ticker_scope_next_open_draw():
    xs, panels = _universe()
    got = null_v2.draw(xs, panels, {"T01": [2]}, idea=_idea())
    want = null_v2.draw_ticker_scope(xs, {"T01": [2]}, idea=IDEA)
    pd.testing.assert_frame_equal(got.table, want.table)


def test_draw_dispatches_a_level_idea_and_needs_its_depths():
    xs, panels = _universe()
    idea = _idea(entry="level", levels=lambda df: df["Open"])
    with pytest.raises(ValueError, match="depth"):
        null_v2.draw(xs, panels, {"T01": [2]}, idea=idea)
    got = null_v2.draw(xs, panels, {"T01": [2]}, idea=idea, depths={"T01": [0.5]})
    pd.testing.assert_frame_equal(got.table,
                                  _level(xs, panels, {"T01": [2]}, {"T01": [0.5]}).table)


def _market_panels(event_pos):
    dates = pd.bdate_range("2015-01-05", periods=300)
    return {"AAA": _panel("AAA", n=300, dates=dates, event=(event_pos,))}


def test_draw_dispatches_a_market_idea_without_a_cross_section():
    panels = _market_panels(290)
    got = null_v2.draw(None, panels, {"AAA": [290]}, idea=_idea(scope="market"))
    want = null_v2.draw_market_scope(panels, {"AAA": [290]}, idea=IDEA, cap=4)
    pd.testing.assert_frame_equal(got.table, want.table)


def test_draw_refuses_a_starved_ticker_scope_before_any_race():
    xs, panels = _universe(3)
    with pytest.raises(null_v2.NullRefusal) as exc:
        null_v2.draw(xs, panels, {"T01": [2]}, idea=_idea())
    assert exc.value.code == null_v2.SCOPE_MISMATCH


def test_draw_refuses_a_starved_market_scope_before_any_race():
    with pytest.raises(null_v2.NullRefusal) as exc:
        null_v2.draw(None, _market_panels(3), {"AAA": [3]}, idea=_idea(scope="market"))
    assert exc.value.code == null_v2.NULL_STARVED
