import pandas as pd

from swingbot.core.charts.trendline_fit import TRENDLINE_FIT_KEY, fit_trendline

_PERIOD = 20
_AMPLITUDE = 8.0
_DRIFT = -0.3
_VOLUME_SPIKE = 2.5


def _frame(n=140):
    """Same shape as tests/test_trendline_fit.py's helper, repeated on purpose
    -- the two files are read independently.

    It oscillates, clears the 3% pivot threshold, and spikes volume at the
    turns; all three are needed to reach the real scanner rather than the
    touch-less trendln fallback. See that file for the longer note.
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


def test_a_new_plan_carries_its_trendline_fit():
    """Written at creation, against the data the decision was made on."""
    fit = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    record = {"ticker": "AAPL", TRENDLINE_FIT_KEY: fit}
    assert record[TRENDLINE_FIT_KEY]["points"][0]["t"] > 0


def test_a_record_without_a_fit_is_still_valid():
    """Every trade written before this change has no fit and must stay
    readable. The field is optional forever."""
    record = {"ticker": "AAPL"}
    assert record.get(TRENDLINE_FIT_KEY) is None


def test_log_trade_stores_the_fit_it_is_given(tmp_path):
    """The real writer: swingbot.core.performance.TradeLog.log_trade."""
    from swingbot.core.performance import TradeLog

    log = TradeLog(path=str(tmp_path / "trades.json"))
    fit = fit_trendline(_frame(), lookback=120, current_price=160.0, is_bull=True)
    assert fit is not None

    trade_id = log.log_trade(
        ticker="AAPL", strategy="RSI", horizon_key="4w", direction="bullish",
        confidence_level=4, confidence_label="Strong", entry=160.0,
        stop_loss=150.0, take_profit=180.0, trendline_fit=fit,
    )

    stored = log.get_trade_by_id(trade_id)
    assert stored[TRENDLINE_FIT_KEY]["side"] == "support"
    for point in stored[TRENDLINE_FIT_KEY]["points"]:
        assert isinstance(point["t"], int)


def test_log_trade_omits_the_key_entirely_when_there_is_no_fit(tmp_path):
    """`if fit:` at the call site, so "absent" means one thing -- no line --
    rather than two."""
    from swingbot.core.performance import TradeLog

    log = TradeLog(path=str(tmp_path / "trades.json"))
    trade_id = log.log_trade(
        ticker="AAPL", strategy="RSI", horizon_key="4w", direction="bullish",
        confidence_level=4, confidence_label="Strong", entry=160.0,
        stop_loss=150.0, take_profit=180.0,
    )

    stored = log.get_trade_by_id(trade_id)
    assert TRENDLINE_FIT_KEY not in stored
