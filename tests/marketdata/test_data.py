import numpy as np
import pandas as pd
import pytest

from swingbot.core.marketdata import data as data_mod
from tests.conftest import make_ohlcv


def _batch_frame(prices: dict) -> pd.DataFrame:
    """Builds a yf.download(..., group_by="ticker") -shaped multi-index
    frame: level 0 = ticker, level 1 = OHLCV field -- verified against a
    real yfinance 0.2.66 batch response during the v55 investigation."""
    per_ticker = {ticker: make_ohlcv(closes) for ticker, closes in prices.items()}
    return pd.concat(per_ticker, axis=1)


def test_get_daily_data_batch_keys_each_ticker_to_its_own_slice(monkeypatch):
    frame = _batch_frame({"AAA": [10.0, 11.0], "BBB": [200.0, 201.0]})
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: frame)

    out = data_mod.get_daily_data_batch(["AAA", "BBB"])

    assert set(out) == {"AAA", "BBB"}
    assert out["AAA"]["Close"].iloc[-1] == 11.0
    assert out["BBB"]["Close"].iloc[-1] == 201.0


def test_get_daily_data_batch_omits_a_ticker_with_no_data(monkeypatch):
    """A batch response only ever contains columns for the tickers Yahoo
    actually recognized -- a delisted/bad symbol is simply absent, not a
    column of NaNs, but the same "absent means unavailable" contract must
    hold for a slice that IS present but comes back all-NaN too."""
    frame = _batch_frame({"AAA": [10.0, 11.0]})
    nan_cols = pd.concat(
        {"BAD": pd.DataFrame({"Open": [np.nan], "High": [np.nan], "Low": [np.nan],
                              "Close": [np.nan], "Volume": [np.nan]},
                             index=frame.index[-1:])},
        axis=1)
    frame = pd.concat([frame, nan_cols], axis=1)
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: frame)

    out = data_mod.get_daily_data_batch(["AAA", "BAD", "MISSING"])

    assert set(out) == {"AAA"}


def test_get_daily_data_batch_empty_response_returns_empty_dict(monkeypatch):
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: pd.DataFrame())
    assert data_mod.get_daily_data_batch(["AAA", "BBB"]) == {}


def test_get_daily_data_batch_raising_download_returns_empty_dict(monkeypatch):
    def _boom(*a, **kw):
        raise ConnectionError("no route to host")
    monkeypatch.setattr(data_mod.yf, "download", _boom)
    assert data_mod.get_daily_data_batch(["AAA"]) == {}


def test_get_daily_data_batch_empty_ticker_list_never_calls_download(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("must not call yf.download for an empty ticker list")
    monkeypatch.setattr(data_mod.yf, "download", _boom)
    assert data_mod.get_daily_data_batch([]) == {}


def test_get_current_price_batch_uses_last_close_per_ticker(monkeypatch):
    frame = _batch_frame({"AAA": [10.0, 11.0, 12.5], "BBB": [200.0, 199.0]})
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: frame)

    out = data_mod.get_current_price_batch(["AAA", "BBB"])

    assert out == {"AAA": 12.5, "BBB": 199.0}


def test_get_current_price_batch_omits_a_ticker_with_no_price(monkeypatch):
    frame = _batch_frame({"AAA": [10.0, 11.0]})
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **kw: frame)

    out = data_mod.get_current_price_batch(["AAA", "MISSING"])

    assert set(out) == {"AAA"}
