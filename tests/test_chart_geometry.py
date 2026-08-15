"""
Contract tests for chart_geometry.overlay_geometry() -- the confirming-
overlay geometry as plain data, extracted out of chart_strategy_overlay.py
so the PNG the bot posts to Discord and the interactive chart the SPA
draws cannot disagree about where a level sits.

These assert the SHAPE OF THE DATA. That the extraction left the PNG
byte-identical is a separate check with a separate instrument --
`python scripts/render_chart_fixtures.py --check <baseline>/SHA256`.
"""
import json

import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.charts.chart_geometry import overlay_geometry


def _epoch(ts) -> int:
    return int(pd.Timestamp(ts).value // 10**9)


def _trending(n=90, daily_pct=0.25, start_price=100.0):
    closes = start_price * (1 + daily_pct / 100) ** np.arange(n)
    return make_ohlcv(closes, spread_pct=1.5)


def _fvg_frame(n=60):
    """One unfilled bullish fair value gap near the right edge."""
    closes = [100 + i * 0.2 for i in range(n)]
    jump_at = n - 6
    for i in range(jump_at, n):
        closes[i] += 12.0
    df = make_ohlcv(closes, spread_pct=1.0)
    df.iloc[jump_at - 2, df.columns.get_loc("High")] = closes[jump_at - 2] + 0.1
    df.iloc[jump_at, df.columns.get_loc("Low")] = closes[jump_at] - 0.1
    return df


def _zigzag_frame(n=60):
    """A completed down-then-up swing inside the last 20 bars, big enough
    for zigzag_pivots(threshold_pct=3) to confirm a low there."""
    closes = [100.0 + i * 0.1 for i in range(n - 20)]
    closes += [closes[-1] * (1 - 0.012) ** i for i in range(1, 9)]
    closes += [closes[-1] * (1 + 0.014) ** i for i in range(1, 13)]
    return make_ohlcv(closes[:n], spread_pct=1.2)


def _geom(df, sources, side="target", **ctx):
    ctx.setdefault("recent_len", min(20, len(df)))
    return overlay_geometry(df, side, sources, **ctx)


# --------------------------------------------------------------------
# Nothing drawable
# --------------------------------------------------------------------

def test_returns_none_when_no_sources():
    assert _geom(_trending(), []) is None
    assert _geom(_trending(), None) is None


def test_returns_none_for_non_level_sources():
    """Candlestick patterns and squeeze flags are appended by
    confidence.py but are not price levels -- _pick_primary_source has
    always refused them and the geometry must too."""
    assert _geom(_trending(), ["Hammer", "Bullish Engulfing"]) is None


def test_returns_none_when_the_method_cannot_be_computed():
    """Too little history for the zigzag detector to confirm a pivot."""
    tiny = make_ohlcv([100.0, 100.5, 101.0], spread_pct=1.0)
    assert _geom(tiny, ["Pivot low"], horizon={"max_risk_pct": 5.0}) is None


# --------------------------------------------------------------------
# The envelope
# --------------------------------------------------------------------

def test_envelope_carries_side_source_and_shape():
    g = _geom(_trending(), ["EMA20"], side="stop")
    assert g["side"] == "stop"
    assert g["source"] == "EMA20"
    assert g["shape"]["kind"] == "curve"


def test_the_highest_priority_source_wins():
    """METHOD_PRIORITY ranks FVG above EMA; the dispatcher moved into
    this module with the geometry and must keep ranking, not take the
    first entry."""
    g = _geom(_fvg_frame(), ["EMA20", "FVG bullish"])
    assert g["source"] == "FVG bullish"


@pytest.mark.parametrize("sources,horizon,frame", [
    (["EMA20"], {}, _trending()),
    (["Fib 61.8%"], {"fib_lookback": 40}, _trending()),
    (["FVG bullish"], {}, _fvg_frame()),
    (["Rolling resistance"], {"sr_lookback": 20}, _trending()),
    (["Pivot low"], {"max_risk_pct": 3.0}, _zigzag_frame()),
])
def test_every_shape_is_json_serialisable(sources, horizon, frame):
    """The endpoint serialises this straight to the wire -- a numpy
    float or a NaN in here is a 500 at runtime, not a type error at
    import."""
    g = _geom(frame, sources, horizon=horizon)
    assert g is not None
    round_tripped = json.loads(json.dumps(g))
    assert round_tripped == g


# --------------------------------------------------------------------
# curve -- EMA / VWAP / Bollinger / Donchian
# --------------------------------------------------------------------

def test_curve_shape():
    df = _trending()
    g = _geom(df, ["EMA20"], recent_len=20)
    shape = g["shape"]
    assert shape["kind"] == "curve"
    assert shape["label"] == "EMA20"
    assert len(shape["points"]) == 20
    assert [t for t, _ in shape["points"]] == [_epoch(ts) for ts in df.index[-20:]]


def test_curve_is_computed_over_the_full_frame_then_sliced():
    """NO-LOOKAHEAD in reverse: an EMA over the visible 20 bars alone
    would differ from an EMA over all history sliced to 20. The last
    value must not depend on how many bars are visible."""
    df = _trending(n=200)
    short = _geom(df, ["EMA20"], recent_len=20)["shape"]["points"][-1]
    long = _geom(df, ["EMA20"], recent_len=120)["shape"]["points"][-1]
    assert short == long


def test_curve_carries_none_not_nan_for_undefined_bars():
    """Donchian shifts a 20-bar rolling window, so the oldest bars have
    no value. JSON has no NaN; the renderer turns None back into one."""
    df = _trending(n=30)
    shape = _geom(df, ["Donchian high"], recent_len=25)["shape"]
    assert shape["points"][0][1] is None
    assert shape["points"][-1][1] is not None
    json.dumps(shape)


# --------------------------------------------------------------------
# fib_fan
# --------------------------------------------------------------------

def test_fib_fan_shape():
    df = _trending(n=70, daily_pct=0.4)
    g = _geom(df, ["Fib 61.8%"], horizon={"fib_lookback": 40})
    shape = g["shape"]
    assert shape["kind"] == "fib_fan"
    # origin is the 0% anchor (the swing high), anchor the 100% (swing low)
    assert shape["origin"][1] == pytest.approx(float(df["High"].iloc[-40:].max()))
    assert shape["anchor"][1] == pytest.approx(float(df["Low"].iloc[-40:].min()))
    assert [r for r, _p, _m in shape["ratios"]] == [0.236, 0.382, 0.5, 0.618, 0.786]
    assert shape["matched"] == "Fib 61.8%"


def test_fib_fan_marks_which_ratio_confirmed_the_level():
    df = _trending(n=70, daily_pct=0.4)
    shape = _geom(df, ["Fib 38.2%"], horizon={"fib_lookback": 40})["shape"]
    matched = [r for r, _p, is_match in shape["ratios"] if is_match]
    assert matched == [0.382]


def test_swing_high_and_low_are_fib_fan_with_the_anchor_matched():
    df = _trending(n=70, daily_pct=0.4)
    for label, key in (("Swing high", "origin"), ("Swing low", "anchor")):
        shape = _geom(df, [label], horizon={"fib_lookback": 40})["shape"]
        assert shape["kind"] == "fib_fan"
        assert shape["matched"] == label
        assert not any(m for _r, _p, m in shape["ratios"])
        assert shape["matched_price"] == pytest.approx(shape[key][1])


def test_fib_anchors_are_real_bars_in_the_frame():
    df = _trending(n=70, daily_pct=0.4)
    shape = _geom(df, ["Fib 61.8%"], horizon={"fib_lookback": 40})["shape"]
    stamps = {_epoch(ts) for ts in df.index}
    assert shape["origin"][0] in stamps
    assert shape["anchor"][0] in stamps


# --------------------------------------------------------------------
# fvg_zone
# --------------------------------------------------------------------

def test_fvg_zone_shape():
    from swingbot.core.fvg import find_fair_value_gaps_detailed

    df = _fvg_frame()
    gap = [g for g in find_fair_value_gaps_detailed(df) if g["direction"] == "bullish"][-1]
    shape = _geom(df, ["FVG bullish"], recent_len=20)["shape"]
    assert shape["kind"] == "fvg_zone"
    assert shape["price_low"] == pytest.approx(gap["bottom"])
    assert shape["price_high"] == pytest.approx(gap["top"])
    assert shape["price_high"] > shape["price_low"]
    assert shape["t_from"] == _epoch(df.index[gap["bar_index"]])
    assert shape["t_to"] == _epoch(df.index[-1])


def test_fvg_zone_returns_none_when_no_gap_of_that_direction_exists():
    assert _geom(_trending(), ["FVG bearish"]) is None


# --------------------------------------------------------------------
# horizontal -- Rolling / Floor / Volume Profile
# --------------------------------------------------------------------

def test_rolling_level_is_a_bounded_segment():
    df = _trending(n=60, daily_pct=0.15)
    shape = _geom(df, ["Rolling resistance"], horizon={"sr_lookback": 20}, recent_len=40)["shape"]
    assert shape["kind"] == "horizontal"
    assert shape["full_width"] is False
    # the segment spans its own lookback, not the whole visible window
    assert shape["t_from"] == _epoch(df.index[-20])
    assert shape["t_to"] == _epoch(df.index[-1])
    expected = float(df["High"].rolling(20).max().shift(1).iloc[-1])
    assert shape["price"] == pytest.approx(expected)


def test_floor_pivot_spans_the_visible_window():
    """The PNG draws floor pivots with axhline -- edge to edge, not a
    segment -- so the geometry has to say so or the refactor changes the
    picture."""
    df = _trending(n=60)
    shape = _geom(df, ["Floor S1"], recent_len=20)["shape"]
    assert shape["kind"] == "horizontal"
    assert shape["full_width"] is True
    assert shape["t_from"] == _epoch(df.index[-20])
    assert shape["t_to"] == _epoch(df.index[-1])


def test_volume_profile_label_carries_the_volume_share():
    df = _trending(n=80, daily_pct=0.1)
    shape = _geom(df, ["Volume Profile HVN"], horizon={"sr_lookback": 30})["shape"]
    assert shape["kind"] == "horizontal"
    assert shape["label"].startswith("Volume Profile HVN (")
    assert shape["label"].endswith("%)")


def test_unknown_floor_pivot_name_returns_none():
    assert _geom(_trending(), ["Floor R9"]) is None


# --------------------------------------------------------------------
# marker -- zigzag pivots
# --------------------------------------------------------------------

def test_pivot_is_a_marker_at_a_real_bar():
    df = _zigzag_frame()
    g = _geom(df, ["Pivot low"], horizon={"max_risk_pct": 3.0})
    shape = g["shape"]
    assert shape["kind"] == "marker"
    assert shape["pivot_kind"] == "low"
    assert shape["t"] in {_epoch(ts) for ts in df.index}
    assert shape["label"] == "Pivot low"


# --------------------------------------------------------------------
# trendline
# --------------------------------------------------------------------

def test_trendline_shape_is_built_from_the_fit_the_caller_already_did():
    """The fit needs the entry price and the full frame, and happens in
    generate_trade_chart before the display window is decided -- so the
    geometry converts that result rather than re-fitting it, which would
    be a second source of truth for the same line."""
    df = _trending(n=120, daily_pct=0.3)
    trend_info = {
        "support": {"slope": 0.5, "intercept": 100.0, "strength": 4,
                    "touches": [(0, 100.0), (30, 115.0), (59, 129.5)]},
        "window_bars": 60,
    }
    g = _geom(df, ["Trendline (support)"], side="stop", recent_len=60,
              trend_info=trend_info, trendline_window_bars=60)
    shape = g["shape"]
    assert shape["kind"] == "trendline"
    assert shape["p1"] == [_epoch(df.index[-60]), pytest.approx(100.0)]
    assert shape["p2"] == [_epoch(df.index[-1]), pytest.approx(100.0 + 0.5 * 59)]
    assert len(shape["pivots"]) == 3
    assert shape["pivots"][0] == [_epoch(df.index[-60]), pytest.approx(100.0)]
    assert shape["label"] == "Trendline (4x)"


def test_trendline_without_a_fit_returns_none():
    """A caller that did not fit a line cannot get one back -- better a
    null overlay than a fabricated one."""
    df = _trending(n=120)
    assert _geom(df, ["Trendline (support)"], recent_len=60) is None


def _stored_fit(**over):
    """A trade's persisted fit, in charts/trendline_fit.py's shape."""
    fit = {
        "slope": 0.5, "intercept": 100.0, "side": "support", "strength": 4,
        "window_bars": 60, "lookback": 120, "fit_at": "2026-08-15T08:00:00Z",
        "points": [{"t": 1767225600, "price": 100.0},
                   {"t": 1779235200, "price": 129.5}],
        "pivots": [{"t": 1769040000, "price": 106.2},
                   {"t": 1773878400, "price": 118.4},
                   {"t": 1777420800, "price": 125.1}],
        "pair": {
            "support": {"slope": 0.5, "intercept": 100.0, "strength": 4,
                        "touches": [(0, 100.0), (30, 115.0), (59, 129.5)]},
            "resistance": {"slope": 0.6, "intercept": 110.0, "strength": 3,
                           "touches": []},
            "window_bars": 60,
        },
    }
    fit.update(over)
    return fit


def test_a_stored_fit_draws_its_own_side_from_absolute_points():
    """The stored numbers, drawn unchanged. The endpoint's frame is whatever
    range the browser asked for, so converting window-relative bar
    coordinates against it would slide the line; the stored points are
    absolute epochs and cannot slide. This is what makes the SPA and the PNG
    draw the same line."""
    df = _trending(n=120, daily_pct=0.3)
    g = _geom(df, ["Trendline (support)"], side="stop", recent_len=60,
              trend_fit=_stored_fit())
    shape = g["shape"]
    assert shape["kind"] == "trendline"
    assert shape["p1"] == [1767225600, pytest.approx(100.0)]
    assert shape["p2"] == [1779235200, pytest.approx(129.5)]
    assert shape["pivots"] == [[1769040000, pytest.approx(106.2)],
                               [1773878400, pytest.approx(118.4)],
                               [1777420800, pytest.approx(125.1)]]
    assert shape["label"] == "Trendline (4x)"


def test_a_stored_fit_draws_the_other_side_from_its_pair():
    """A fit is taken for the side the trade rests on, so only that side has
    absolute points. The opposite side still has to be drawable -- both
    overlays appear on the chart -- and comes from the pair the fit stored
    verbatim, converted the same way the PNG converts it."""
    df = _trending(n=120, daily_pct=0.3)
    g = _geom(df, ["Trendline (resistance)"], side="target", is_bull=True,
              recent_len=60, trend_fit=_stored_fit())
    shape = g["shape"]
    assert shape["label"] == "Trendline (3x)"
    assert shape["p1"] == [_epoch(df.index[-60]), pytest.approx(110.0)]


def test_a_stored_fit_without_pivots_still_draws_its_line():
    """Fits taken before the pivots key existed, and the trendln fallback,
    both arrive with no touches. A line with no diamonds beats no line."""
    df = _trending(n=120, daily_pct=0.3)
    g = _geom(df, ["Trendline (support)"], side="stop", recent_len=60,
              trend_fit=_stored_fit(pivots=[]))
    assert g["shape"]["pivots"] == []
    assert g["shape"]["p1"] == [1767225600, pytest.approx(100.0)]


def test_the_stored_fit_wins_over_a_live_one():
    """Both supplied is not a conflict to resolve at render time: the stored
    fit is the one the trade was planned on and the PNG already drew."""
    df = _trending(n=120, daily_pct=0.3)
    live = {"support": {"slope": 99.0, "intercept": 0.0, "strength": 1,
                        "touches": []},
            "window_bars": 60}
    g = _geom(df, ["Trendline (support)"], side="stop", recent_len=60,
              trend_info=live, trendline_window_bars=60, trend_fit=_stored_fit())
    assert g["shape"]["p1"] == [1767225600, pytest.approx(100.0)]
    assert g["shape"]["label"] == "Trendline (4x)"


def test_trendline_side_selects_support_for_stop_and_resistance_for_target():
    df = _trending(n=120, daily_pct=0.3)
    trend_info = {
        "support": {"slope": 0.5, "intercept": 100.0, "strength": 4, "touches": []},
        "resistance": {"slope": 0.6, "intercept": 110.0, "strength": 3, "touches": []},
        "window_bars": 60,
    }
    ctx = dict(recent_len=60, trend_info=trend_info, trendline_window_bars=60)
    long_target = _geom(df, ["Trendline (resistance)"], side="target", is_bull=True, **ctx)
    long_stop = _geom(df, ["Trendline (support)"], side="stop", is_bull=True, **ctx)
    assert long_target["shape"]["label"] == "Trendline (3x)"
    assert long_stop["shape"]["label"] == "Trendline (4x)"
