"""v140 matched null: same ticker, same month, same trend state, K = 20,
fewer than 5 candidates drops the event, never an event bar."""
import zlib

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import null
from swingbot.core.backtesting.screen import race as race_mod
from swingbot.core.marketdata.pit_membership import is_member
from tests.backtesting.screen.helpers import frame, random_walk

FEB_2019 = 2019 * 12 + 2


def _three_months():
    idx = pd.bdate_range("2019-01-01", "2019-03-29")
    return frame(np.full(len(idx), 100.0), index=idx)


def _atr(df):
    return pd.Series(2.0, index=df.index)


def _all(df):
    return np.ones(len(df), dtype=bool)


def _draw(df, event_pos, eligible, k, seed, trend=None):
    trend = _all(df) if trend is None else trend
    return null.matched_null(df, event_pos, eligible, k, seed, cap=4,
                             atr=_atr(df), trend=trend, slippage_bps=0.0,
                             commission=0.0)


def test_seed_is_deterministic_per_idea_and_ticker():
    assert null.null_seed("high52w", "AAPL") == [
        42, zlib.crc32(b"high52w"), zlib.crc32(b"AAPL")]
    assert null.null_seed("high52w", "AAPL") != null.null_seed("high52w", "MSFT")
    assert null.null_seed("high52w", "AAPL") != null.null_seed("gap_volume", "AAPL")


def test_month_key_and_trend_state():
    idx = pd.DatetimeIndex(["2019-01-31", "2019-02-01", "2019-02-04"])
    assert null.month_key(idx).tolist() == [2019 * 12 + 1, FEB_2019, FEB_2019]
    df = frame([1.0, 2.0, 3.0], index=idx)
    sma = pd.Series([np.nan, 1.5, 3.0], index=idx)
    assert null.trend_state(df, sma).tolist() == [False, True, False]


def test_member_mask_matches_is_member_bar_by_bar():
    idx = pd.bdate_range("2011-12-20", "2012-01-20")
    spans = [("2011-12-28", "2012-01-05"), ("2012-01-12", "9999-12-31")]
    expected = [is_member(d.strftime("%Y-%m-%d"), spans) for d in idx]
    assert null.member_mask(idx, spans).tolist() == expected
    assert null.member_mask(idx, None).all()
    assert not null.member_mask(idx, []).any()


def test_eligible_mask_needs_member_warm_complete_and_not_an_event():
    events = np.array([0, 1, 0, 0, 0, 0], dtype=bool)
    member = np.array([1, 1, 0, 1, 1, 1], dtype=bool)
    warm = np.array([1, 1, 1, 0, 1, 1], dtype=bool)
    out = null.eligible_mask(events, member, warm, cap=2)
    assert out.tolist() == [True, False, False, False, False, False]


def test_draws_match_month_and_trend_state():
    df = _three_months()
    trend = np.arange(len(df)) % 2 == 0
    events = np.zeros(len(df), dtype=bool)
    events[[4, 30]] = True
    eligible = null.eligible_mask(events, _all(df), _all(df), cap=4)
    draw = _draw(df, [4, 30], eligible, 20, [42, 1, 2], trend=trend)
    months = null.month_key(df.index)
    assert draw.event_pos.tolist() == [4, 30]
    for pos, group in zip(draw.event_pos, draw.groups):
        assert (months[group] == months[pos]).all()
        assert (trend[group] == trend[pos]).all()


def test_null_never_samples_an_event_bar():
    df = _three_months()
    events = np.zeros(len(df), dtype=bool)
    events[[2, 5, 6, 9, 12, 15]] = True
    eligible = null.eligible_mask(events, _all(df), _all(df), cap=4)
    assert not eligible[events].any()
    for seed in range(50):
        draw = _draw(df, [2, 9], eligible, 5, seed)
        drawn = np.concatenate(draw.groups)
        assert not np.isin(drawn, np.flatnonzero(events)).any()


def test_same_seed_gives_the_same_draw():
    df = _three_months()
    eligible = null.eligible_mask(np.zeros(len(df), dtype=bool), _all(df), _all(df), cap=4)
    a = _draw(df, [3, 30], eligible, 5, null.null_seed("x", "AAPL"))
    b = _draw(df, [3, 30], eligible, 5, null.null_seed("x", "AAPL"))
    assert all(np.array_equal(g, h) for g, h in zip(a.groups, b.groups))


def test_fewer_than_five_candidates_drops_the_event():
    df = _three_months()
    feb = np.flatnonzero(null.month_key(df.index) == FEB_2019)
    eligible = np.zeros(len(df), dtype=bool)
    eligible[feb[:4]] = True
    dropped = _draw(df, [feb[10]], eligible, 20, 1)
    assert dropped.dropped_no_match == 1
    assert dropped.event_pos.size == 0 and dropped.null_mean_r.size == 0
    eligible[feb[4]] = True
    kept = _draw(df, [feb[10]], eligible, 20, 1)
    assert kept.dropped_no_match == 0
    assert kept.event_pos.tolist() == [feb[10]]
    assert len(kept.groups[0]) == 5


def test_draw_size_is_k_or_every_candidate_when_fewer():
    df = _three_months()
    feb = np.flatnonzero(null.month_key(df.index) == FEB_2019)
    eligible = np.zeros(len(df), dtype=bool)
    eligible[feb[:12]] = True
    assert len(_draw(df, [feb[15]], eligible, 20, 1).groups[0]) == 12
    assert len(_draw(df, [feb[15]], eligible, 5, 1).groups[0]) == 5


def test_null_mean_is_the_mean_of_its_raced_bars():
    df = random_walk(70, start="2019-01-01")
    eligible = null.eligible_mask(np.zeros(len(df), dtype=bool), _all(df), _all(df), cap=4)
    draw = _draw(df, [5], eligible, 20, 3)
    expected = race_mod.race(df, draw.groups[0], 4, atr=_atr(df),
                             slippage_bps=0.0, commission=0.0).r.mean()
    assert draw.null_mean_r[0] == pytest.approx(expected)
    assert len(draw.null_race) == len(draw.groups[0])


from swingbot.core.backtesting.screen import trail  # noqa: E402


def _walk_null(shape=None):
    df = random_walk(400, start="2019-01-01")
    eligible = null.eligible_mask(np.zeros(len(df), dtype=bool), _all(df), _all(df), cap=60)
    shape_kw = {} if shape is None else {"shape": shape}
    draw = null.matched_null(df, [5, 30], eligible, 20, 3, cap=60, atr=_atr(df),
                             trend=_all(df), slippage_bps=0.0, commission=0.0, **shape_kw)
    return df, draw


def test_a_trail_null_races_the_same_draw_through_the_trail_race():
    _, fixed = _walk_null("fixed")
    df, drawn = _walk_null("trail")
    assert [g.tolist() for g in drawn.groups] == [g.tolist() for g in fixed.groups]
    for k, group in enumerate(drawn.groups):
        expected = trail.race_trail(df, group, 60, atr=_atr(df), slippage_bps=0.0,
                                    commission=0.0)
        assert drawn.null_mean_r[k] == pytest.approx(expected.r.mean())
    assert set(drawn.null_race.outcome.tolist()) <= set(race_mod.SHAPE_OUTCOMES["trail"])
    assert drawn.null_race.r.tolist() != fixed.null_race.r.tolist()


def test_matched_null_without_a_shape_is_the_fixed_null():
    _, default = _walk_null()
    _, fixed = _walk_null("fixed")
    assert default.null_mean_r.tolist() == fixed.null_mean_r.tolist()
    assert default.null_race.outcome.tolist() == fixed.null_race.outcome.tolist()


def test_matched_null_refuses_an_unknown_shape():
    with pytest.raises(ValueError, match="race shape"):
        _walk_null("donchian")
