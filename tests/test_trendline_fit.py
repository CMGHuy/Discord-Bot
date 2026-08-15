import pandas as pd

from swingbot.core.charts.trendline_fit import fit_trendline

_PERIOD = 10
_AMPLITUDE = 4.0
_DRIFT = -0.3


def _frame(n=140):
    """A descending series that OSCILLATES -- fittable, the same way twice.

    It has to oscillate. A perfectly straight line has no swing pivots, and a
    trendline is fitted to pivots that touch it, so
    `strongest_trendline_pair` returns None for a clean ramp -- not a weak
    fit, no fit at all. The triangle wave puts a run of lows on one
    descending line and a run of highs on another, which is what gives this
    frame both a support and a resistance side to choose between.
    """
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    values = []
    for i in range(n):
        phase = (i % _PERIOD) / _PERIOD
        triangle = 1.0 - abs(2.0 * phase - 1.0) * 2.0  # in [-1, 1]
        values.append(200.0 + _DRIFT * i + _AMPLITUDE * triangle)
    close = pd.Series(values, index=idx)
    return pd.DataFrame({
        "Open": close, "High": close + 1.0, "Low": close - 1.0,
        "Close": close, "Volume": 1_000_000.0,
    }, index=idx)


def test_returns_none_when_nothing_is_drawable():
    tiny = _frame(5)
    assert fit_trendline(tiny, lookback=120, current_price=100.0, is_bull=True) is None


def test_fit_is_serialisable_and_json_safe():
    fit = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    assert fit is not None
    assert set(fit) >= {"slope", "intercept", "points", "side", "lookback", "fit_at"}
    for point in fit["points"]:
        assert isinstance(point["t"], int)
        assert isinstance(point["price"], float)


def test_the_same_frame_fits_the_same_line_twice():
    """The whole point of extracting this: one fit, one answer."""
    a = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    b = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    assert a["slope"] == b["slope"]
    assert a["points"] == b["points"]


def test_a_bull_trade_fits_support_and_a_bear_fits_resistance():
    bull = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    bear = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=False)
    assert bull["side"] == "support"
    assert bear["side"] == "resistance"
