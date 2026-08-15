import pandas as pd

from swingbot.core.charts.trendline_fit import fit_trendline

_PERIOD = 20
_AMPLITUDE = 8.0
_DRIFT = -0.3
_VOLUME_SPIKE = 2.5


def _frame(n=140):
    """A descending series that oscillates on confirmed volume.

    Three properties, each load-bearing, and all three are needed to reach
    the code this module actually runs in production:

    1. **It oscillates.** A straight ramp has no swing pivots at all, so
       `strongest_trendline_pair` returns None outright -- no fit, not a
       weak one.
    2. **The swings clear `PIVOT_THRESHOLD_PCT` (3%).** A smaller wave
       registers no pivots.
    3. **Volume spikes at the turns.** `_volume_confirmed_pivots` wants a
       ratio over `VOL_MIN_RATIO` (1.05) against a 20-bar mean. On flat
       volume the custom scanner finds nothing and the whole call silently
       drops to the trendln fallback, which returns lines with EMPTY
       touches -- so a fixture with flat volume can never exercise the
       pivots this module exists to preserve.
    """
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    values, volumes = [], []
    for i in range(n):
        phase = (i % _PERIOD) / _PERIOD
        triangle = 1.0 - abs(2.0 * phase - 1.0) * 2.0  # in [-1, 1]
        values.append(200.0 + _DRIFT * i + _AMPLITUDE * triangle)
        at_turn = i % _PERIOD == 0 or i % _PERIOD == _PERIOD // 2
        volumes.append(1_000_000.0 * (_VOLUME_SPIKE if at_turn else 1.0))
    close = pd.Series(values, index=idx)
    return pd.DataFrame({
        "Open": close, "High": close + 1.0, "Low": close - 1.0,
        "Close": close, "Volume": pd.Series(volumes, index=idx),
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


def test_pivots_are_the_touches_and_not_the_line_ends():
    """The distinction the whole chart rests on.

    `points` are where the drawn segment starts and stops. `pivots` are the
    bars that actually touched the line and earned it its strength. Drawing
    the ends as diamonds puts two markers under a label claiming `strength`
    of them -- a bug trade_chart.py has already had once.
    """
    fit = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    assert len(fit["points"]) == 2
    assert fit["pivots"], "a line with strength must carry the touches that earned it"
    assert len(fit["pivots"]) >= 2
    for pivot in fit["pivots"]:
        assert isinstance(pivot["t"], int)
        assert isinstance(pivot["price"], float)
    # Every pivot sits inside the drawn segment's own time span.
    first, last = fit["points"][0]["t"], fit["points"][1]["t"]
    for pivot in fit["pivots"]:
        assert first <= pivot["t"] <= last


def test_the_pair_is_kept_verbatim_for_the_png():
    """trade_chart.py reads a support/resistance pair at seven sites. Storing
    it whole is what lets the PNG read the stored fit through the identical
    shape it computes today."""
    fit = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    pair = fit["pair"]
    assert "window_bars" in pair
    assert set(pair) >= {"support", "resistance", "window_bars"}
    side = pair[fit["side"]]
    assert side["slope"] == fit["slope"]
    assert side["intercept"] == fit["intercept"]
    assert "touches" in side, "the diamonds the PNG draws come from here"


def test_a_bull_trade_fits_support_and_a_bear_fits_resistance():
    bull = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    bear = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=False)
    assert bull["side"] == "support"
    assert bear["side"] == "resistance"
