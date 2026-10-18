"""history_store is the only reader of data/market_data/: paths, manifests,
the session filter, and the one index convention (naive New York wall-clock,
bar start) pinned by a fetch-frame -> CSV -> load round trip across both 2026
DST changes."""
import json
from pathlib import Path

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import history_store as hs
from swingbot.core.marketdata.providers import base


def _write(frame, ticker, timeframe):
    path = hs.file_path(ticker, timeframe)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index_label=hs.INDEX_NAMES[timeframe])
    return path


def _manifest(root, timeframe, tickers):
    folder = root / timeframe
    folder.mkdir(parents=True, exist_ok=True)
    (folder / hs.MANIFEST_NAME).write_text(json.dumps(
        {"timeframe": timeframe, "feed": "sip", "adjustment": "all", "tickers": tickers}))


def _daily(dates, close=10.0):
    idx = pd.DatetimeIndex(pd.to_datetime(dates), name="Date")
    n = len(idx)
    return pd.DataFrame({"Open": [close] * n, "High": [close + 1] * n, "Low": [close - 1] * n,
                         "Close": [close] * n, "Volume": [1000.0] * n}, index=idx)


# --- paths --------------------------------------------------------------------

def test_default_root_is_data_market_data(monkeypatch):
    monkeypatch.delenv("HISTORY_STORE_DIR", raising=False)
    assert hs.store_root() == Path(config.DATA_DIR) / "market_data"


def test_env_override_is_read_on_every_call(monkeypatch, tmp_path):
    monkeypatch.setenv("HISTORY_STORE_DIR", str(tmp_path / "a"))
    assert hs.store_root() == tmp_path / "a"
    monkeypatch.setenv("HISTORY_STORE_DIR", str(tmp_path / "b"))
    assert hs.store_root() == tmp_path / "b"


def test_relative_override_resolves_against_the_project_root(monkeypatch):
    monkeypatch.setenv("HISTORY_STORE_DIR", "data/elsewhere")
    assert hs.store_root() == Path(config.DATA_DIR).parent / "data" / "elsewhere"


def test_unknown_timeframe_is_rejected(store_root):
    with pytest.raises(ValueError, match="1h"):
        hs.timeframe_dir("1h")


def test_file_names_use_safe_symbol(store_root):
    assert hs.file_path("brk-b", "daily") == store_root / "daily" / "BRK-B.csv"
    assert hs.file_path("GC=F", "15min") == store_root / "15min" / "GC_F.csv"


def test_paths_create_no_directories(store_root):
    hs.file_path("AAPL", "hourly")
    hs.manifest_path("hourly")
    assert not (store_root / "hourly").exists()


# --- manifests ----------------------------------------------------------------

def test_missing_manifest_is_none_and_require_raises_naming_the_path(store_root):
    assert hs.manifest("daily") is None
    with pytest.raises(hs.MissingStoreError) as info:
        hs.require_manifest("daily")
    assert str(store_root / "daily" / "_manifest.json") in str(info.value)
    assert "TRAINING_DATA_SOURCE=yfinance" in str(info.value)


def test_manifest_is_read_as_is(store_root):
    _manifest(store_root, "daily", {"AAPL": {"status": "ok"}})
    assert hs.require_manifest("daily")["tickers"] == {"AAPL": {"status": "ok"}}


def test_corrupt_manifest_raises(store_root):
    (store_root / "daily").mkdir()
    (store_root / "daily" / "_manifest.json").write_text("{not json")
    with pytest.raises(json.JSONDecodeError):
        hs.manifest("daily")


def test_ticker_status(store_root):
    assert hs.ticker_status("daily", "AAPL") == "missing"          # no manifest
    _manifest(store_root, "daily", {"AAPL": {"status": "ok"},
                                    "SNDK": {"status": "flagged: short-overlap"},
                                    "ODD": {}})
    assert hs.ticker_status("daily", "aapl") == "ok"
    assert hs.ticker_status("daily", "SNDK") == "flagged: short-overlap"
    assert hs.ticker_status("daily", "ODD") == "missing"
    assert hs.ticker_status("daily", "MSFT") == "missing"


# --- load ---------------------------------------------------------------------

def test_load_missing_file_is_none(store_root):
    assert hs.load("AAPL", "daily") is None


def test_load_daily_shape(store_root):
    _write(_daily(["2016-01-05", "2016-01-04", "2016-01-05"]), "AAPL", "daily")
    out = hs.load("AAPL", "daily")
    assert list(out.columns) == hs.OHLCV_COLUMNS
    assert all(out.dtypes == "float64")
    assert out.index.name == "Date" and out.index.tz is None
    assert list(out.index) == [pd.Timestamp("2016-01-04"), pd.Timestamp("2016-01-05")]


def test_load_rejects_bad_session(store_root):
    with pytest.raises(ValueError, match="session"):
        hs.load("AAPL", "15min", session="pre")


def test_load_rejects_a_tz_aware_file(store_root):
    path = hs.file_path("AAPL", "daily")
    path.parent.mkdir(parents=True)
    path.write_text("Date,Open,High,Low,Close,Volume\n"
                    "2016-01-04 00:00:00-05:00,1,2,0.5,1.5,100\n")
    with pytest.raises(ValueError, match="naive"):
        hs.load("AAPL", "daily")


def test_load_empty_file_is_none(store_root):
    path = hs.file_path("AAPL", "daily")
    path.parent.mkdir(parents=True)
    path.write_text("Date,Open,High,Low,Close,Volume\n")
    assert hs.load("AAPL", "daily") is None


# --- the DST round trip (spec §1, acceptance 3) -----------------------------------

DST_DAYS = ["2026-03-06", "2026-03-09", "2026-10-30", "2026-11-02"]   # EST, EDT, EDT, EST


def _raw_session(day, start, end, freq):
    """Alpaca-shaped raw bars (lowercase, UTC) for one New York day."""
    idx = pd.date_range(f"{day} {start}", f"{day} {end}", freq=freq, tz=base.NY).tz_convert("UTC")
    n = len(idx)
    return pd.DataFrame({"open": [1.0] * n, "high": [2.0] * n, "low": [0.5] * n,
                         "close": [float(i) for i in range(n)], "volume": [100.0] * n},
                        index=pd.DatetimeIndex(idx, name="timestamp"))


def _raw_days(start, end, freq):
    return pd.concat([_raw_session(d, start, end, freq) for d in DST_DAYS])


def test_15min_round_trip_across_both_dst_changes(store_root):
    fetched = base.to_store_intraday(_raw_days("04:00", "19:45", "15min"))
    _write(fetched, "AAPL", "15min")

    every = hs.load("AAPL", "15min", session="all")
    pd.testing.assert_frame_equal(every, fetched, check_freq=False)

    rth = hs.load("AAPL", "15min")
    per_day = rth.groupby(rth.index.date)
    assert per_day.size().tolist() == [26, 26, 26, 26]
    assert {t.strftime("%H:%M") for t in per_day.head(1).index} == {"09:30"}
    assert {t.strftime("%H:%M") for t in per_day.tail(1).index} == {"15:45"}


def test_hourly_round_trip_across_both_dst_changes(store_root):
    fetched = base.to_store_hourly(_raw_days("09:00", "16:00", "30min"))
    _write(fetched, "AAPL", "hourly")
    loaded = hs.load("AAPL", "hourly", session="all")
    pd.testing.assert_frame_equal(loaded, fetched, check_freq=False)
    assert hs.load("AAPL", "hourly").equals(loaded)       # session is ignored for hourly
    per_day = loaded.groupby(loaded.index.date).size().tolist()
    assert per_day == [7, 7, 7, 7]
    assert loaded.index[0].strftime("%H:%M") == "09:30"


def test_daily_round_trip_across_both_dst_changes(store_root):
    raw = pd.concat([_raw_session(d, "00:00", "00:00", "1D") for d in DST_DAYS])
    fetched = base.to_yf_daily(raw)
    _write(fetched, "AAPL", "daily")
    loaded = hs.load("AAPL", "daily")
    assert [d.strftime("%Y-%m-%d") for d in loaded.index] == DST_DAYS
    pd.testing.assert_frame_equal(loaded, fetched, check_freq=False)
