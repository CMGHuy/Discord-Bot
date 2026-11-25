"""v245 V245-8: every prefix (none, own, yesterday's, tampered, other side) gives the
pre-v245 result (``_reference_best``: the old loop and old ``_score_candidate``, copied)."""
import copy
import dataclasses

import pandas as pd
import pytest

from swingbot.core.market import trendlines as tl

_PERIOD = 20


def _wave(n, drift=-0.3, jitter=0.37, volume=True):
    idx = pd.date_range("2018-01-01", periods=n, freq="B")
    vals, vols = [], []
    for i in range(n):
        phase = (i % _PERIOD) / _PERIOD
        vals.append(200.0 + drift * i + 8.0 * (1.0 - abs(2.0 * phase - 1.0) * 2.0) + jitter * (i % 7))
        turn = i % _PERIOD in (0, _PERIOD // 2)
        vols.append((2_500_000.0 if turn else 1_000_000.0) if volume else 0.0)
    close = pd.Series(vals, index=idx)
    return pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                         "Close": close, "Volume": pd.Series(vols, index=idx)}, index=idx)


FRAMES = {
    "short_140": lambda: _wave(140),
    "flat_ties": lambda: _wave(200, drift=0.0, jitter=0.0),   # every low equal: pairs tie
    "steep_140": lambda: _wave(140, drift=-0.6),              # the slope gate rejects
    "no_volume": lambda: _wave(160, volume=False),
    "exactly_1500": lambda: _wave(1500, drift=-0.02),
    "long_1700": lambda: _wave(1700, drift=-0.01),            # the 1500-bar trim applies
}
PRICE_MULTS = [1.0, 0.9, 1.1, 0.5]
SIDES = ["support", "resistance"]


def _kind(side):
    return "low" if side == "support" else "high"


def _old_score(slope, intercept, pivots, n_bars, price, side):
    line_at_now = slope * (n_bars - 1) + intercept
    if side == "support" and line_at_now > price * 1.01:
        return None
    if side == "resistance" and line_at_now < price * 0.99:
        return None
    if price > 0 and abs(slope / price * 100) > tl.MAX_SLOPE_PCT_PER_BAR:
        return None
    touches = []
    for b, p, v in pivots:
        here = slope * b + intercept
        if here > 0 and abs(p - here) / here * 100 <= tl.TOUCH_TOLERANCE_PCT:
            touches.append((b, p, v))
    if len(touches) < 2:
        return None
    avg = sum(v for _, _, v in touches) / len(touches)
    recency = max(b for b, _, _ in touches) / max(n_bars - 1, 1)
    return {"slope": slope, "intercept": intercept, "touches": touches, "strength": len(touches),
            "score": len(touches) * avg * (0.4 + 0.6 * recency), "line_at_now": line_at_now}


def _pairs(pivots):
    for i in range(len(pivots)):
        for j in range(i + 1, len(pivots)):
            (x0, y0, _), (x1, y1, _) = pivots[i], pivots[j]
            if x1 != x0 and y0 > 0 and y1 > 0:
                slope = (y1 - y0) / (x1 - x0)
                yield slope, y0 - slope * x0


def _reference_best(df, price, side):
    """The pre-v245 _find_best_trendline."""
    trim = max(len(df) - tl.MAX_PIVOT_SCAN_BARS, 0)
    frame = df.tail(tl.MAX_PIVOT_SCAN_BARS) if trim else df
    pivots = tl._volume_confirmed_pivots(frame, _kind(side))
    best = None
    for slope, intercept in _pairs(pivots):
        r = _old_score(slope, intercept, pivots, len(frame), price, side)
        if r and (best is None or r["score"] > best["score"]):
            best = r
    if best is not None and trim:
        best["intercept"] -= best["slope"] * trim
        best["touches"] = [(b + trim, p, v) for b, p, v in best["touches"]]
    return best


def _census(df, price, side):
    """(scores of accepted pairs, side-gate rejects, slope-gate rejects)."""
    frame, _ = tl.trimmed_frame(df)
    pivots, n = tl._volume_confirmed_pivots(frame, _kind(side)), len(frame)
    scores, side_rej, slope_rej = [], 0, 0
    for slope, intercept in _pairs(pivots):
        now = slope * (n - 1) + intercept
        if (side == "support" and now > price * 1.01) or (side == "resistance" and now < price * 0.99):
            side_rej += 1
        elif abs(slope / price * 100) > tl.MAX_SLOPE_PCT_PER_BAR:
            slope_rej += 1
        elif (r := _old_score(slope, intercept, pivots, n, price, side)):
            scores.append(r["score"])
    return scores, side_rej, slope_rej


def _prefix_for(df, side):
    trimmed, _ = tl.trimmed_frame(df)
    return tl.build_trendline_prefix(trimmed, side, tl.prefix_length(trimmed))


def _price(df, mult=1.0):
    return float(df["Close"].iloc[-1]) * mult


@pytest.mark.parametrize("name", sorted(FRAMES))
@pytest.mark.parametrize("mult", PRICE_MULTS)
@pytest.mark.parametrize("side", SIDES)
def test_no_prefix_and_own_prefix_equal_the_old_algorithm(name, mult, side):
    df = FRAMES[name]()
    want = _reference_best(df, _price(df, mult), side)
    assert tl._find_best_trendline(df, _price(df, mult), side) == want
    assert tl._find_best_trendline(df, _price(df, mult), side, prefix=_prefix_for(df, side)) == want


@pytest.mark.parametrize("name", sorted(FRAMES))
@pytest.mark.parametrize("side", SIDES)
def test_yesterdays_prefix_carried_into_today_equals_the_old_algorithm(name, side):
    df = FRAMES[name]()
    carried = _prefix_for(df.iloc[:-1], side)           # built by yesterday's scans
    for mult in PRICE_MULTS:
        assert tl._find_best_trendline(df, _price(df, mult), side, prefix=carried) == \
            _reference_best(df, _price(df, mult), side)


@pytest.mark.parametrize("name", ["short_140", "flat_ties", "exactly_1500", "long_1700"])
@pytest.mark.parametrize("side", SIDES)
def test_own_prefix_is_verified_and_used(name, side):
    df = FRAMES[name]()
    pre = _prefix_for(df, side)
    pivots = tl._volume_confirmed_pivots(tl.trimmed_frame(df)[0], _kind(side))
    assert len(pre.confirmed) >= 2, "the fixture must give the prefix pairs to cache"
    assert tl._verified_prefix(pre, pivots, side) is pre


@pytest.mark.parametrize("variant", ["tampered", "other_side"])
def test_a_wrong_prefix_falls_back_to_todays_algorithm(variant):
    df = FRAMES["short_140"]()
    pre = _prefix_for(df, "support")
    if variant == "tampered":
        b, p, v = pre.confirmed[0]
        pre = tl.TrendlinePrefix("support", pre.m, ((b, p + 0.5, v),) + pre.confirmed[1:], pre.pairs)
    else:
        pre = _prefix_for(df, "resistance")
    pivots = tl._volume_confirmed_pivots(df, "low")
    assert tl._verified_prefix(pre, pivots, "support") == tl.TrendlinePrefix("support", 0, (), ())
    assert tl._find_best_trendline(df, _price(df), "support", prefix=pre) == \
        _reference_best(df, _price(df), "support")


def test_fixtures_exercise_ties_and_both_price_gates():
    """On failure, change the fixture's drift, never the assertion."""
    flat = FRAMES["flat_ties"]()
    scores, _, _ = _census(flat, _price(flat), "support")
    assert scores and scores.count(max(scores)) >= 2
    short = FRAMES["short_140"]()
    assert _census(short, _price(short, 0.9), "support")[1] > 0
    steep = FRAMES["steep_140"]()
    assert _census(steep, _price(steep), "support")[2] > 0


def test_cached_pairs_skip_the_full_touch_scan(monkeypatch):
    df = FRAMES["long_1700"]()
    pre = _prefix_for(df, "support")
    calls = {"n": 0}
    real = tl._score_candidate

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(tl, "_score_candidate", counting)
    tl._find_best_trendline(df, _price(df), "support")
    uncached, calls["n"] = calls["n"], 0
    tl._find_best_trendline(df, _price(df), "support", prefix=pre)
    assert calls["n"] < uncached


def test_prefix_window_and_unstable_pivots():
    df = FRAMES["short_140"]()
    trimmed, start = tl.trimmed_frame(df)
    m = tl.prefix_length(trimmed)
    assert start == 0 and m == len(df) - tl.TRENDLINE_PREFIX_TAIL_BARS
    found = tl._volume_confirmed_pivots(trimmed.iloc[:m], "low")
    pre = tl.build_trendline_prefix(trimmed, "support", m)
    assert list(pre.confirmed) == found[:max(len(found) - tl.UNSTABLE_PREFIX_PIVOTS, 0)]
    assert tl.build_trendline_prefix(trimmed, "support", 10).confirmed == ()
    assert tl.trimmed_frame(FRAMES["long_1700"]())[1] == 200


def test_prefix_is_frozen_and_unchanged_by_scans():
    df = FRAMES["long_1700"]()
    pre = _prefix_for(df, "support")
    before = copy.deepcopy(pre)
    for mult in (1.0, 0.95):
        best = tl._find_best_trendline(df, _price(df, mult), "support", prefix=pre)
        if best:
            best["touches"].append(("junk",))
            best["intercept"] = 0.0
    assert pre == before
    assert isinstance(pre.confirmed, tuple) and all(isinstance(row, tuple) for row in pre.pairs)
    with pytest.raises(dataclasses.FrozenInstanceError):
        pre.m = 0


@pytest.mark.parametrize("name", sorted(FRAMES))
def test_custom_scanner_levels_with_prefixes_is_unchanged(name):
    df = FRAMES[name]()
    prefixes = {side: _prefix_for(df, side) for side in SIDES}
    assert tl.custom_scanner_levels(df, _price(df), prefixes=prefixes) == \
        tl.custom_scanner_levels(df, _price(df))
