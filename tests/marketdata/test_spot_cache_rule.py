"""v109 cache rule: a scaled spot frame is never written to either OHLCV
cache under XAUUSD/XAGUSD -- only the raw future is cached, under GC_F."""
import os

import pandas as pd
import pytest

from swingbot.core.marketdata import backtest_cache as bc
from swingbot.core.marketdata import data_refresh, data_store
from swingbot.core.marketdata import spot_metals as sm

READING = sm.SpotRatio("XAUUSD", 4151.70, "GC=F", 4175.30, 4151.70 / 4175.30)


def _bars(n=30, start="2026-08-01", freq="D", close=4000.0):
    idx = pd.date_range(start, periods=n, freq=freq)
    return pd.DataFrame({"Open": close, "High": close + 5, "Low": close - 5,
                         "Close": close, "Volume": 100.0}, index=idx)


def _no_spot_files(root):
    hits = [os.path.join(d, f) for d, _, files in os.walk(root) for f in files
            if f.upper().startswith(("XAUUSD", "XAGUSD"))]
    assert hits == []


def test_save_to_disk_refuses_spot_names(tmp_path):
    with pytest.raises(ValueError, match="never cached"):
        data_store.save_to_disk(_bars(), "XAUUSD", "daily", base_dir=str(tmp_path))
    _no_spot_files(tmp_path)
    data_store.save_to_disk(_bars(), "GC=F", "daily", base_dir=str(tmp_path))
    assert os.path.exists(data_store.cache_path("GC=F", "daily", base_dir=str(tmp_path)))


def test_merge_save_refuses_spot_names(tmp_path):
    with pytest.raises(ValueError, match="never cached"):
        data_refresh._merge_save(None, _bars(), "XAGUSD", "daily", str(tmp_path))
    _no_spot_files(tmp_path)


def test_intraday_caches_the_future_and_returns_it_scaled(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (READING, ""))
    asked = []

    def fetch(sym, iv):
        asked.append((sym, iv))
        return _bars(freq="h")
    df = data_store.get_intraday("XAUUSD", base_dir=str(tmp_path), fetch_fn=fetch)
    assert asked == [("GC=F", "1h")]
    assert df.attrs["source"] == "spot-scaled:GC=F"
    assert df["Close"].iloc[-1] == pytest.approx(4000.0 * READING.ratio)
    assert os.path.exists(data_store.cache_path("GC=F", "1h", base_dir=str(tmp_path)))
    _no_spot_files(tmp_path)


def test_intraday_outage_is_none_but_the_future_is_still_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "spot_ratio_detail", lambda s, **k: (None, "spot quote missing"))
    out = data_store.get_intraday("XAUUSD", base_dir=str(tmp_path),
                                  fetch_fn=lambda s, iv: _bars(freq="h"))
    assert out is None
    assert os.path.exists(data_store.cache_path("GC=F", "1h", base_dir=str(tmp_path)))
    _no_spot_files(tmp_path)


def test_refresh_all_refreshes_the_future_not_the_spot_name(tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(data_refresh, "fetch_interval_data",
                        lambda sym, tf: asked.append(sym) or _bars())
    result = data_refresh.refresh_all(["XAUUSD", "AAPL", "GC=F"], ["daily"],
                                      base_dir=str(tmp_path), persist_state=False)
    assert asked == ["GC=F", "AAPL"]
    assert not any(k.upper().startswith("XAUUSD") for k in result["state"])
    _no_spot_files(tmp_path)


def test_update_cache_maps_spot_to_the_future(tmp_path):
    asked = []
    out = data_store.update_cache(["XAGUSD"], "1d", base_dir=str(tmp_path),
                                  fetch_fn=lambda sym, start: asked.append(sym) or _bars())
    assert asked == ["SI=F"] and set(out) == {"SI=F"}
    _no_spot_files(tmp_path)


def test_backtest_cache_stores_the_future(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "CACHE_DIR", tmp_path / "backtest_cache")
    asked = []
    monkeypatch.setattr(bc, "fetch", lambda t: asked.append(t) or _bars(n=300))
    result = bc.ensure_cached("xauusd")
    assert asked == ["GC=F"] and result.ticker == "GC=F" and result.status == "ok"
    assert (tmp_path / "backtest_cache" / "GC_F.csv").exists()
    _no_spot_files(tmp_path)


def test_backtest_cache_background_stores_the_future(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "CACHE_DIR", tmp_path / "backtest_cache")
    asked = []
    monkeypatch.setattr(bc, "fetch", lambda t: asked.append(t) or _bars(n=300))
    bc.ensure_cached_background("XAGUSD").join(timeout=10)
    assert asked == ["SI=F"]
    _no_spot_files(tmp_path)
