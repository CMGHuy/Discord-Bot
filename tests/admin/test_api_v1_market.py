"""NG17 — /api/v1/market/ohlcv/{ticker}.

The bar serialisation and the level mapping are shared with the Jinja route
(app.py's `ohlcv_bars` / `trade_levels`), and
`test_v1_and_jinja_return_identical_bars` is what keeps that true. Both
charts are live for the whole migration: a second serialisation would let
them disagree about rounding, and a second level mapping would let one draw
a take-profit line at the wrong price -- which looks entirely plausible on
screen and is not something anyone would catch by eye.
"""
import json

import numpy as np
import pandas as pd
import pytest

from tests.admin.api_v1_contract import NULLABLE_NUMBER, assert_error, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _fake_df(n=300):
    idx = pd.bdate_range("2024-01-01", periods=n)
    c = pd.Series(50 + np.cumsum(np.random.default_rng(3).normal(0, .5, n)), index=idx)
    return pd.DataFrame({"Open": c, "High": c + .5, "Low": c - .5,
                         "Close": c, "Volume": 9_999}, index=idx)


@pytest.fixture
def frame(monkeypatch):
    """The OHLCV source, stubbed. _ohlcv_frame reaches the network first and
    the CSV cache second; neither is what these tests are about."""
    def _use(n=300):
        monkeypatch.setattr("swingbot.admin.app._ohlcv_frame", lambda t: _fake_df(n))
    _use()
    return _use


_TRADE = {"id": "t1", "ticker": "AAPL", "entry": 100.0, "stop_loss": 95.0,
          "take_profit": 108.0, "target2_price": 115.0, "direction": "bullish"}


def test_requires_auth(client, frame):
    assert_error(client.get("/api/v1/market/ohlcv/AAPL"), "auth", 401)


def test_default_is_260_bars(logged_in, frame):
    """~1 trading year. The client picks how much work this request does, so
    the default is what a chart actually shows rather than everything held."""
    body = logged_in.get("/api/v1/market/ohlcv/AAPL").get_json()
    assert body["ticker"] == "AAPL"
    assert len(body["bars"]) == 260


def test_bar_shape(logged_in, frame):
    bar = logged_in.get("/api/v1/market/ohlcv/AAPL").get_json()["bars"][-1]
    assert_shape(bar, {"time": str, "open": float, "high": float,
                       "low": float, "close": float, "volume": float},
                 where="bar")
    import re
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", bar["time"])


def test_bars_param_and_hard_cap(logged_in, frame):
    frame(1500)
    assert len(logged_in.get("/api/v1/market/ohlcv/AAPL?bars=50").get_json()["bars"]) == 50
    assert len(logged_in.get("/api/v1/market/ohlcv/AAPL?bars=99999").get_json()["bars"]) == 1000


def test_a_non_integer_bar_count_is_rejected(logged_in, frame):
    """The Jinja route silently falls back to 260. A caller that sent
    bars=banana has a bug, and a full-looking chart tells it nothing."""
    assert_error(logged_in.get("/api/v1/market/ohlcv/AAPL?bars=banana"), "invalid", 400)


def test_a_ticker_with_no_data_is_404(logged_in, monkeypatch):
    monkeypatch.setattr("swingbot.admin.app._ohlcv_frame", lambda t: None)
    assert_error(logged_in.get("/api/v1/market/ohlcv/NOPE"), "not_found", 404)


def test_ticker_is_upper_cased(logged_in, frame):
    assert logged_in.get("/api/v1/market/ohlcv/aapl").get_json()["ticker"] == "AAPL"


def test_levels_are_absent_without_a_trade_id(logged_in, frame):
    assert "levels" not in logged_in.get("/api/v1/market/ohlcv/AAPL").get_json()


def test_levels_come_from_the_trade(logged_in, frame, monkeypatch):
    monkeypatch.setattr("swingbot.admin.app._trade_for_levels", lambda tid: _TRADE)
    body = logged_in.get("/api/v1/market/ohlcv/AAPL?trade_id=t1").get_json()
    assert body["levels"] == {"entry": 100.0, "stop_loss": 95.0, "tp1": 108.0,
                              "tp2": 115.0, "direction": "bullish"}


def test_an_unresolvable_trade_id_is_404(logged_in, frame, monkeypatch):
    """Not a chart with the levels quietly missing. The request was "this
    trade's chart"; answering with a plain one that looks complete is how
    someone reads a chart believing the lines are simply not set. A client
    wanting bars regardless omits the parameter."""
    monkeypatch.setattr("swingbot.admin.app._trade_for_levels", lambda tid: None)
    assert_error(logged_in.get("/api/v1/market/ohlcv/AAPL?trade_id=nope"),
                 "not_found", 404)


def test_the_csv_cache_backs_a_failed_live_fetch(logged_in, tmp_path, monkeypatch):
    """The chart still renders offline. This reads data/backtest_cache --
    the flat per-ticker dailies -- NOT market_data/, which is timeframe-first
    and belongs to the edge engine. Reusing _ohlcv_frame is how this endpoint
    avoids having to know which of the two it wants."""
    from swingbot import config as cfg

    cache = tmp_path / "backtest_cache"
    cache.mkdir()
    _fake_df(60).rename_axis("Date").to_csv(cache / "ZZZZ.csv")
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr("swingbot.core.data.get_daily_data",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("net down")))

    assert len(logged_in.get("/api/v1/market/ohlcv/ZZZZ").get_json()["bars"]) == 60


def test_v1_and_jinja_return_identical_bars(logged_in, auth, frame, monkeypatch):
    """One serialisation, two charts. If either grows its own, they start
    disagreeing about rounding while both are live."""
    monkeypatch.setattr("swingbot.admin.app._trade_for_levels", lambda tid: _TRADE)

    v1 = logged_in.get("/api/v1/market/ohlcv/AAPL?bars=40&trade_id=t1").get_json()
    jinja = json.loads(
        logged_in.get("/api/ohlcv/AAPL?bars=40&trade_id=t1", headers=auth).get_data())

    assert v1["bars"] == jinja["bars"]
    assert v1["levels"] == jinja["levels"]


# =====================================================================
# SR33 -- GET /api/v1/market/chart/{trade_id}
#
# Everything the interactive chart draws, in one request, computed by the
# same Python that draws the PNG posted to Discord (spec Decision 10).
# The overlay geometry comes from SR32's chart_geometry.overlay_geometry,
# so the browser and the image cannot disagree about where a level sits.
# =====================================================================

_CHART_TRADE = {
    "id": "c1", "ticker": "AAPL", "direction": "bullish",
    "entry": 100.0, "stop_loss": 95.0, "take_profit": 108.0,
    "target2_price": 115.0, "horizon_key": "4w",
    "target_sources": ["EMA20"], "stop_sources": ["Rolling support"],
}


@pytest.fixture
def chart_trade(monkeypatch):
    """The trade the chart is for, stubbed. Returns a setter so a test can
    swap in a record with different sources/levels."""
    def _use(**overrides):
        record = {**_CHART_TRADE, **overrides}
        monkeypatch.setattr("swingbot.admin.app._trade_for_levels", lambda tid: record)
        return record
    _use()
    return _use


def _chart(logged_in, query=""):
    return logged_in.get(f"/api/v1/market/chart/c1{query}")


def test_chart_requires_auth(client, frame):
    assert_error(client.get("/api/v1/market/chart/c1"), "auth", 401)


def test_chart_top_level_shape(logged_in, frame, chart_trade):
    """The exact key set. Extra keys fail as loudly as missing ones -- an
    endpoint returning a field nobody declared is an undocumented contract
    change the SPA will grow a dependency on."""
    body = _chart(logged_in).get_json()
    assert_shape(body, {
        "ohlcv": list, "indicators": dict, "volume_profile": list,
        "levels": dict, "overlay": (dict, type(None)), "currency": str,
    }, where="chart")


def test_chart_bar_shape_is_epoch_seconds(logged_in, frame, chart_trade):
    """`t` is an int epoch, not the "YYYY-MM-DD" string /market/ohlcv
    returns. One time type across the whole payload: the overlay shapes
    carry epoch seconds, and lightweight-charts' primitives convert both
    through the same timeToCoordinate -- mixing the two representations in
    one chart is how a shape lands a year away from its candle."""
    bar = _chart(logged_in).get_json()["ohlcv"][-1]
    assert_shape(bar, {"t": int, "o": float, "h": float,
                       "l": float, "c": float, "v": float}, where="bar")


def test_chart_window_defaults_and_bounds(logged_in, frame, chart_trade):
    assert len(_chart(logged_in).get_json()["ohlcv"]) == 120
    assert len(_chart(logged_in, "?window=60").get_json()["ohlcv"]) == 60


@pytest.mark.parametrize("bad", ["19", "501", "0", "-5"])
def test_a_window_outside_the_range_is_rejected_not_clamped(logged_in, frame, chart_trade, bad):
    """/market/ohlcv clamps its `bars`; this rejects. There, "more than the
    cap" sensibly means "all you have". Here the window is what the chart
    SHOWS, and silently handing back 500 bars to a caller that asked for
    5000 gives it a chart it did not ask for and no way to know."""
    assert_error(_chart(logged_in, f"?window={bad}"), "invalid", 400)


def test_a_non_integer_window_is_rejected(logged_in, frame, chart_trade):
    assert_error(_chart(logged_in, "?window=banana"), "invalid", 400)


def test_an_unknown_trade_id_is_404(logged_in, frame, monkeypatch):
    monkeypatch.setattr("swingbot.admin.app._trade_for_levels", lambda tid: None)
    assert_error(logged_in.get("/api/v1/market/chart/nope"), "not_found", 404)


def test_a_trade_whose_ticker_has_no_data_is_404(logged_in, chart_trade, monkeypatch):
    monkeypatch.setattr("swingbot.admin.app._ohlcv_frame", lambda t: None)
    assert_error(_chart(logged_in), "not_found", 404)


def test_levels_use_the_chart_names(logged_in, frame, chart_trade):
    """Spec Decision 10's names, not trade_levels()' tp1/tp2 -- this
    payload feeds price lines whose axis tags read "target 1", and
    `working_stop` (the live breakeven/trail floor) has no equivalent
    there at all."""
    levels = _chart(logged_in).get_json()["levels"]
    assert_shape(levels, {
        "entry": NULLABLE_NUMBER, "stop": NULLABLE_NUMBER,
        "target1": NULLABLE_NUMBER, "target2": NULLABLE_NUMBER,
        "working_stop": NULLABLE_NUMBER,
    }, where="levels")
    assert levels["entry"] == 100.0
    assert levels["stop"] == 95.0
    assert levels["target1"] == 108.0
    assert levels["target2"] == 115.0


def test_a_null_second_target_stays_null(logged_in, frame, chart_trade):
    """Omitted, not drawn at zero -- a target2 line at 0.0 rescales the
    whole price axis and reads as a real level."""
    chart_trade(target2_price=None)
    assert _chart(logged_in).get_json()["levels"]["target2"] is None


def test_indicator_series_are_aligned_to_the_bars(logged_in, frame, chart_trade):
    body = _chart(logged_in, "?window=60").get_json()
    ind = body["indicators"]
    assert set(ind) == {"macd", "rsi", "kc"}
    assert set(ind["macd"]) == {"line", "signal", "hist"}
    assert set(ind["kc"]) == {"upper", "lower"}
    for series in (ind["macd"]["line"], ind["macd"]["signal"], ind["macd"]["hist"],
                   ind["rsi"], ind["kc"]["upper"], ind["kc"]["lower"]):
        assert len(series) == len(body["ohlcv"]) == 60


def test_indicators_carry_null_not_nan(logged_in, frame, chart_trade):
    """JSON has no NaN. Flask would emit a bare `NaN` token that
    JSON.parse rejects outright, so the whole chart fails to load over one
    warm-up bar."""
    raw = _chart(logged_in).get_data(as_text=True)
    assert "NaN" not in raw and "Infinity" not in raw


def test_an_indicator_without_enough_history_is_omitted(logged_in, frame, chart_trade):
    """Spec Decision 10's third degraded state: the pane is omitted, not
    drawn empty. Mirrors what the PNG generator already does, so a trade
    that renders without MACD in Discord renders without it here."""
    frame(25)
    ind = _chart(logged_in, "?window=20").get_json()["indicators"]
    assert "macd" not in ind


def test_no_lookahead_the_last_value_does_not_move_with_the_window(logged_in, frame, chart_trade):
    """Indicators are computed over the LOADED frame and then sliced to the
    visible one. Computing them over the visible slice alone changes every
    value near its left edge -- and, for an EMA-based series, every value
    everywhere. The last bar is the same bar in both requests, so its RSI
    and MACD must be identical."""
    narrow = _chart(logged_in, "?window=30").get_json()["indicators"]
    wide = _chart(logged_in, "?window=250").get_json()["indicators"]
    assert narrow["rsi"][-1] == wide["rsi"][-1]
    assert narrow["macd"]["line"][-1] == wide["macd"]["line"][-1]
    assert narrow["kc"]["upper"][-1] == wide["kc"]["upper"][-1]


def test_volume_profile_bins(logged_in, frame, chart_trade):
    profile = _chart(logged_in).get_json()["volume_profile"]
    assert profile, "expected bins for a 300-bar frame"
    for row in profile:
        assert_shape(row, {"price": float, "volume": float}, where="volume_profile row")


def test_overlay_comes_from_the_geometry_module(logged_in, frame, chart_trade):
    """Not a second implementation. The same call the PNG renderer makes,
    so the browser and the image draw the same EMA."""
    overlay = _chart(logged_in).get_json()["overlay"]
    assert overlay["side"] == "target"
    assert overlay["shape"]["kind"] == "curve"
    assert overlay["shape"]["label"] == "EMA20"


def test_overlay_is_null_without_drawable_sources(logged_in, frame, chart_trade):
    """Spec Decision 10's second degraded state -- an older trade with no
    `target_sources` draws candles, indicators and plan lines only."""
    chart_trade(target_sources=[], stop_sources=[])
    assert _chart(logged_in).get_json()["overlay"] is None


def test_overlay_falls_back_to_the_stop_side(logged_in, frame, chart_trade):
    """One overlay per chart, target preferred -- it is the side the trade
    is aiming at. A trade confirmed only on its stop still gets its
    method drawn rather than nothing."""
    chart_trade(target_sources=["Hammer"], stop_sources=["EMA20"])
    overlay = _chart(logged_in).get_json()["overlay"]
    assert overlay["side"] == "stop"


def test_overlay_timestamps_line_up_with_the_bars(logged_in, frame, chart_trade):
    """The whole point of one time type: every overlay anchor must be a
    real bar the client can convert to a coordinate."""
    body = _chart(logged_in, "?window=60").get_json()
    stamps = {bar["t"] for bar in body["ohlcv"]}
    points = body["overlay"]["shape"]["points"]
    assert [t for t, _p in points] == sorted(stamps)


def test_currency_follows_the_ticker(logged_in, frame, chart_trade):
    assert isinstance(_chart(logged_in).get_json()["currency"], str)
