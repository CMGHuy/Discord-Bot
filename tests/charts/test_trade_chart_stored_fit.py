import inspect

import pandas as pd

from swingbot.core.charts import trade_chart
from swingbot.core.charts.trendline_fit import fit_trendline

_PERIOD = 20
_AMPLITUDE = 8.0
_DRIFT = -0.3
_VOLUME_SPIKE = 2.5


def _frame(n=140):
    """Same oscillating, volume-spiked frame as tests/test_trendline_fit.py.

    Repeated rather than imported, as in the other two files -- and for the
    same reason it grew there: a clean ramp has no pivots to fit, and flat
    volume drops the scanner to the touch-less trendln fallback.
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


def _render(tmp_path, **kwargs):
    return trade_chart.generate_trade_chart(
        "AAPL", _frame(), entry=160.0, stop_loss=150.0, take_profit=180.0,
        direction="bullish", strategy="RSI", horizon_label="2w",
        out_dir=str(tmp_path), **kwargs,
    )


def test_a_stored_fit_is_not_refitted(tmp_path, monkeypatch):
    """The whole guarantee: given a fit, the PNG must not compute one."""
    stored = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    assert stored is not None, "fixture must produce a fit for this test to mean anything"

    calls = []
    monkeypatch.setattr(
        trade_chart, "strongest_trendline_pair",
        lambda *a, **k: calls.append(a) or None,
    )

    path = _render(tmp_path, trendline_fit=stored)

    assert calls == []
    assert path


def test_without_a_stored_fit_it_still_fits_and_renders(tmp_path, monkeypatch):
    """Old trades and the diagnostic callers (!strategycharts) have no record
    to read from. The live fit stays reachable for them -- and this test fails
    loudly if the fallback is ever quietly removed, which would leave those
    callers with no trendline at all rather than a recomputed one.
    """
    calls = []
    real = trade_chart.strongest_trendline_pair
    monkeypatch.setattr(
        trade_chart, "strongest_trendline_pair",
        lambda *a, **k: calls.append(a) or real(*a, **k),
    )

    path = _render(tmp_path, trendline_fit=None)

    assert calls, "with no stored fit the PNG must still fit its own line"
    assert path


def test_the_stored_pair_is_what_gets_drawn(tmp_path, monkeypatch):
    """Not merely "no refit" -- the stored numbers are the ones that reach the
    drawing code. A refit that happened to be skipped while the drawer read
    some other pair would pass the test above and still draw the wrong line.
    """
    stored = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    monkeypatch.setattr(
        trade_chart, "strongest_trendline_pair",
        lambda *a, **k: {"support": {"slope": 99.0, "intercept": 0.0, "touches": [],
                                     "strength": 1},
                         "resistance": None, "window_bars": 120},
    )

    slopes = []
    real_draw = trade_chart._draw_trendline
    # _draw_trendline(ax, recent_len, window_bars, slope, intercept, ...)
    monkeypatch.setattr(
        trade_chart, "_draw_trendline",
        lambda *a, **k: slopes.append(a[3]) or real_draw(*a, **k),
    )

    _render(tmp_path, trendline_fit=stored)

    assert slopes, "the trendline drawer must run for a stored fit"
    assert 99.0 not in slopes, "the sentinel refit leaked into the drawing"
    assert stored["slope"] in slopes


def test_the_scan_hands_its_stored_fit_to_the_png():
    """The fit is written at plan creation and the PNG is rendered a few lines
    later, in the same function. Wiring the two is what makes the stored fit
    reach the live alert path at all -- unwired, every guarantee above is
    inert in production while every test still passes.
    """
    from swingbot.core.scanning import engine

    source = inspect.getsource(engine)
    # Anchored on the assignment, not the bare name: the function is also
    # named in a comment a few lines above, and splitting on that reads the
    # wrong block.
    _, _, after = source.partition("chart_path = generate_trade_chart(")
    assert after, "the scan no longer renders a chart under this name"
    assert "trendline_fit=trendline_fit" in after.split("\n                )", 1)[0]
