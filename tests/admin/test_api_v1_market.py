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

from tests.admin.api_v1_contract import assert_error, assert_shape

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
