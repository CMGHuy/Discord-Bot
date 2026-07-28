import numpy as np
import pandas as pd

from tests.test_admin_pages import client  # noqa: F401  (authed fixture)


def _fake_df(n=300):
    idx = pd.bdate_range("2024-01-01", periods=n)
    c = pd.Series(50 + np.cumsum(np.random.default_rng(3).normal(0, .5, n)), index=idx)
    return pd.DataFrame({"Open": c, "High": c + .5, "Low": c - .5, "Close": c, "Volume": 9_999}, index=idx)


def test_ohlcv_shape_and_default_cap(client, monkeypatch):
    monkeypatch.setattr("swingbot.admin.app._ohlcv_frame", lambda t: _fake_df())
    data = client.get("/api/ohlcv/AAPL").get_json()
    assert data["ticker"] == "AAPL"
    assert len(data["bars"]) == 260  # default cap
    b = data["bars"][-1]
    assert set(b) == {"time", "open", "high", "low", "close", "volume"}
    import re
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", b["time"])  # ISO date string


def test_ohlcv_bars_param_and_max(client, monkeypatch):
    monkeypatch.setattr("swingbot.admin.app._ohlcv_frame", lambda t: _fake_df(1500))
    assert len(client.get("/api/ohlcv/AAPL?bars=50").get_json()["bars"]) == 50
    assert len(client.get("/api/ohlcv/AAPL?bars=99999").get_json()["bars"]) == 1000  # hard max


def test_ohlcv_no_data_404(client, monkeypatch):
    monkeypatch.setattr("swingbot.admin.app._ohlcv_frame", lambda t: None)
    assert client.get("/api/ohlcv/NOPE").status_code == 404


def test_ohlcv_requires_auth():
    from swingbot.admin.app import app
    app.config["TESTING"] = True
    with app.test_client() as anon:
        assert anon.get("/api/ohlcv/AAPL").status_code == 401


def test_ohlcv_levels_from_trade(client, monkeypatch):
    monkeypatch.setattr("swingbot.admin.app._ohlcv_frame", lambda t: _fake_df())
    fake = {"id": "t1", "ticker": "AAPL", "entry": 100.0, "stop_loss": 95.0,
            "take_profit": 108.0, "target2_price": 115.0, "direction": "bullish"}
    monkeypatch.setattr("swingbot.admin.app._trade_for_levels", lambda tid: fake)
    data = client.get("/api/ohlcv/AAPL?trade_id=t1").get_json()
    assert data["levels"] == {"entry": 100.0, "stop_loss": 95.0, "tp1": 108.0,
                             "tp2": 115.0, "direction": "bullish"}
