"""v230 A2 stage 3: null slots raced on their own ticker's frame and ATR14,
one frame resident at a time, checkpointed per null ticker, then scattered
back to their events."""
import gc
import weakref
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import forward, indicators, null_v2, trail
from swingbot.core.backtesting.screen import race as race_mod
from tests.backtesting.screen.helpers import random_walk

CAP = 10
COSTS = {"slippage_bps": 5.0, "commission": 0.01}
FRAMES = {t: random_walk(400, seed=s) for t, s in (("AAA", 1), ("BBB", 2), ("CCC", 3))}
QUIET = {"out": lambda *a, **k: None}
NEXT_OPEN = [("AAA", 300, "BBB", 250), ("AAA", 300, "CCC", 260),
             ("CCC", 310, "BBB", 270), ("AAA", 320, "BBB", 280)]


def _load(ticker):
    df = FRAMES.get(ticker)
    return None if df is None else (df, indicators.atr(df))


def _table(rows):
    """rows: (event_ticker, event_pos, null_ticker, null_pos[, fill])."""
    return null_v2._table([(e, ep, FRAMES["AAA"].index[ep], n, p, rest[0] if rest else np.nan)
                           for e, ep, n, p, *rest in rows])


def _race(table, load=_load, **kw):
    kw = {"shape": "fixed", "cap": CAP, "direction": "long", "costs": COSTS, **QUIET, **kw}
    return null_v2.race_pass(table, load, **kw)


def _one(ticker, pos, **kw):
    df = FRAMES[ticker]
    return race_mod.race(df, [pos], CAP, atr=indicators.atr(df), **COSTS, **kw)


def test_each_slot_is_raced_on_its_own_frame_and_atr():
    raced = _race(_table(NEXT_OPEN))
    for row in raced.itertuples():
        want = _one(row.null_ticker, row.null_pos)
        assert row.r == pytest.approx(want.r[0])
        assert row.gross_r == pytest.approx(want.gross_r[0])
        assert row.outcome == want.outcome[0]
        df = FRAMES[row.null_ticker]
        assert row.fwd_20 == pytest.approx(
            forward.forward_atr(df, indicators.atr(df), 20)[row.null_pos], nan_ok=True)


def test_rows_keep_their_order_and_extra_columns():
    table = _table(NEXT_OPEN).assign(arm=["null", "control", "null", "null"])
    raced = _race(table)
    pd.testing.assert_frame_equal(raced[list(table.columns)], table)
    assert list(raced.columns[len(table.columns):]) == [
        "r", "gross_r", "outcome", "fwd_5", "fwd_10", "fwd_20", "fwd_60"]


def test_a_short_idea_races_and_reads_its_null_short():
    raced = _race(_table(NEXT_OPEN[:1]), direction="short")
    assert raced.r.iloc[0] == pytest.approx(_one("BBB", 250, direction="short").r[0])
    df = FRAMES["BBB"]
    assert raced.fwd_5.iloc[0] == pytest.approx(
        forward.forward_atr(df, indicators.atr(df), 5, direction="short")[250])


def test_the_trail_shape_races_its_null_on_the_trail():
    raced = _race(_table(NEXT_OPEN[:1]), shape="trail", cap=60)
    df = FRAMES["BBB"]
    want = trail.race_trail(df, [250], 60, atr=indicators.atr(df), **COSTS)
    assert raced.r.iloc[0] == pytest.approx(want.r[0])


def test_level_slots_race_from_their_fill_with_the_level_factor():
    df = FRAMES["BBB"]
    fills = [float(df["Open"].iloc[p]) * 1.001 for p in (250, 251)]
    raced = _race(_table([("AAA", 300, "BBB", 250, fills[0]), ("AAA", 300, "BBB", 251, fills[1])]),
                  level_factor=3.0)
    want = race_mod.race(df, [250, 251], CAP, atr=indicators.atr(df), fill=fills,
                         level_factor=3.0, **COSTS)
    np.testing.assert_allclose(raced.r, want.r)


def test_blank_level_slots_are_not_raced_and_read_unfilled():
    calls = []
    raced = _race(_table([("AAA", 300, "BBB", 250, 101.0), ("AAA", 300, "", -1)]),
                  load=lambda t: calls.append(t) or _load(t))
    assert calls == ["BBB"]
    blank = raced.iloc[1]
    assert blank.outcome == null_v2.UNFILLED
    assert np.isnan(blank.r) and np.isnan(blank.gross_r) and np.isnan(blank.fwd_60)


def test_level_and_next_open_slots_on_one_ticker_are_refused():
    with pytest.raises(ValueError, match="level and next-open"):
        _race(_table([("AAA", 300, "BBB", 250, 101.0), ("AAA", 300, "BBB", 251)]))


def test_a_null_ticker_without_a_frame_is_refused():
    with pytest.raises(ValueError, match="ZZZ"):
        _race(_table([("AAA", 300, "ZZZ", 250)]))


def test_only_one_null_frame_is_resident_at_a_time():
    alive = []

    def load(ticker):
        gc.collect()
        assert all(ref() is None for ref in alive), "a previous null frame is still held"
        df = FRAMES[ticker].copy()
        alive.append(weakref.ref(df))
        return df, indicators.atr(df)

    _race(_table(NEXT_OPEN), load=load)
    assert len(alive) == 2                      # BBB, then CCC


def test_finished_null_tickers_resume_from_their_checkpoint(tmp_path):
    checkpoint = null_v2.open_stage(tmp_path, "race", {"idea": "x"}, **QUIET)
    first = _race(_table(NEXT_OPEN), checkpoint=checkpoint)
    assert checkpoint.done() == {"BBB", "CCC"}

    def refuse(ticker):
        raise AssertionError(f"{ticker} was raced again")

    again = _race(_table(NEXT_OPEN), load=refuse, checkpoint=checkpoint)
    pd.testing.assert_frame_equal(again, first)


def test_an_empty_table_races_nothing():
    raced = _race(null_v2._table([]))
    assert raced.empty and {"r", "gross_r", "outcome", "fwd_60"} <= set(raced.columns)


def _raced(rows):
    return pd.DataFrame(rows, columns=["event_ticker", "event_pos", "null_pos", "r",
                                       "gross_r", "outcome", "fwd_5"])


def test_scatter_groups_slots_back_to_their_events():
    got = null_v2.scatter(_raced([
        ("AAA", 300, 250, 1.0, 1.1, "target", 0.5),
        ("AAA", 300, 251, -1.0, -0.9, "stop", np.nan),
        ("AAA", 300, 252, 0.2, 0.3, "timeout", 1.5),
        ("BBB", 40, 10, 0.4, 0.5, "timeout", 0.1)]))
    assert set(got) == {("AAA", 300), ("BBB", 40)}
    a = got[("AAA", 300)]
    assert a.mean_r == pytest.approx(0.2 / 3) and a.mean_gross_r == pytest.approx(0.5 / 3)
    assert a.outcomes == Counter({"target": 1, "stop": 1, "timeout": 1})
    assert set(a.fwd) == {5} and a.fwd[5] == pytest.approx(1.0)
    assert a.timeout_r == (0.2,) and (a.slots, a.unfilled) == (3, 0)


def test_blank_slots_count_as_unfilled_and_stay_out_of_the_means():
    got = null_v2.scatter(_raced([
        ("AAA", 300, 250, 1.0, 1.1, "target", 0.5),
        ("AAA", 300, -1, np.nan, np.nan, null_v2.UNFILLED, np.nan),
        ("BBB", 40, -1, np.nan, np.nan, null_v2.UNFILLED, np.nan)]))
    a, b = got[("AAA", 300)], got[("BBB", 40)]
    assert (a.mean_r, a.slots, a.unfilled, a.outcomes) == (1.0, 2, 1, Counter({"target": 1}))
    assert np.isnan(b.mean_r) and np.isnan(b.fwd[5])
    assert (b.slots, b.unfilled, b.outcomes, b.timeout_r) == (1, 1, Counter(), ())


def test_scatter_of_nothing_is_empty():
    assert null_v2.scatter(_raced([])) == {}


def test_scatter_forward_means_exclude_infinities_without_dropping_slots():
    raced = _raced([
        ("AAA", 300, 250, 1.0, 1.1, "target", 0.5),
        ("AAA", 300, 251, -1.0, -0.9, "stop", np.inf),
        ("AAA", 300, 252, 0.6, 0.7, "timeout", -np.inf),
        ("AAA", 300, 253, 0.2, 0.3, "timeout", 1.5),
        ("BBB", 40, 10, 0.4, 0.5, "timeout", np.inf),
        ("BBB", 40, 11, 0.4, 0.5, "timeout", -np.inf),
        ("BBB", 40, 12, 0.4, 0.5, "timeout", np.nan)])
    raced["fwd_20"] = [np.inf, 2.0, 4.0, np.nan, np.nan, np.inf, -np.inf]
    original = raced.copy(deep=True)
    got = null_v2.scatter(raced)
    a, b = got[("AAA", 300)], got[("BBB", 40)]
    assert a.fwd == {5: 1.0, 20: 3.0}
    assert np.isnan(b.fwd[5]) and np.isnan(b.fwd[20])
    assert a.mean_r == pytest.approx(0.2)
    assert a.mean_gross_r == pytest.approx(0.3)
    assert a.outcomes == Counter({"target": 1, "stop": 1, "timeout": 2})
    assert (a.slots, a.unfilled, a.timeout_r) == (4, 0, (0.6, 0.2))
    assert b.mean_r == pytest.approx(0.4)
    assert (b.slots, b.unfilled, b.outcomes) == (3, 0, Counter({"timeout": 3}))
    pd.testing.assert_frame_equal(raced, original)


def test_race_then_scatter_gives_each_event_the_mean_of_its_raced_slots():
    raced = _race(_table(NEXT_OPEN))
    got = null_v2.scatter(raced)
    want = np.mean([_one("BBB", 250).r[0], _one("CCC", 260).r[0]])
    assert got[("AAA", 300)].mean_r == pytest.approx(want)
    assert got[("AAA", 300)].slots == 2
