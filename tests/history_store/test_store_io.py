"""Store I/O (spec §1-2): files are written to a temp name and renamed, hashed
byte-for-byte the same on Linux and Windows, and described by one manifest
per timeframe whose top-level hash covers every per-ticker hash."""
import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from alpaca_history import store_io
from swingbot.core.marketdata import history_store as hs

NOW = datetime(2026, 10, 18, 6, 31, 2, tzinfo=timezone.utc)


def _frame(index, name):
    idx = pd.DatetimeIndex(pd.to_datetime(index), name=name)
    n = len(idx)
    values = np.arange(1, n + 1, dtype=float)
    return pd.DataFrame({"Open": values, "High": values + 1, "Low": values - 0.5,
                         "Close": values + 0.25, "Volume": values * 1000}, index=idx)


DAILY = ["2016-01-04", "2016-01-05", "2016-01-06"]
INTRADAY = ["2016-01-04 04:00", "2016-01-04 09:30", "2016-01-04 19:45"]


# --- write_frame -----------------------------------------------------------------------

def test_daily_file_layout_and_hash(store_root):
    path = hs.file_path("AAPL", "daily")
    digest = store_io.write_frame(_frame(DAILY, "Date"), path, "daily")
    data = path.read_bytes()
    assert data.startswith(b"Date,Open,High,Low,Close,Volume\n2016-01-04,")
    assert b"\r\n" not in data
    assert digest == hashlib.sha256(data).hexdigest() == store_io.sha256_file(path)
    assert not path.with_name(path.name + store_io.TMP_SUFFIX).exists()


def test_intraday_round_trips_through_history_store(store_root):
    frame = _frame(INTRADAY, "Datetime")
    store_io.write_frame(frame, hs.file_path("AAPL", "15min"), "15min")
    assert hs.file_path("AAPL", "15min").read_text().splitlines()[1].startswith("2016-01-04 04:00:00,")
    pd.testing.assert_frame_equal(hs.load("AAPL", "15min", session="all"), frame, check_freq=False)


def test_same_frame_same_hash(tmp_path):
    frame = _frame(DAILY, "Date")
    assert (store_io.write_frame(frame, tmp_path / "a.csv", "daily")
            == store_io.write_frame(frame.copy(), tmp_path / "b.csv", "daily"))


def test_extra_columns_are_not_written(tmp_path):
    frame = _frame(DAILY, "Date").assign(vwap=1.0)
    store_io.write_frame(frame, tmp_path / "a.csv", "daily")
    assert (tmp_path / "a.csv").read_text().splitlines()[0] == "Date,Open,High,Low,Close,Volume"


@pytest.mark.parametrize("bad", [
    _frame(DAILY, "Date").tz_localize("America/New_York"),
    _frame(["2016-01-04", "2016-01-04"], "Date"),
    _frame(["2016-01-05", "2016-01-04"], "Date"),
])
def test_bad_index_is_refused_and_the_old_file_kept(tmp_path, bad):
    path = tmp_path / "AAPL.csv"
    store_io.write_frame(_frame(DAILY, "Date"), path, "daily")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        store_io.write_frame(bad, path, "daily")
    assert path.read_bytes() == before


def test_bad_timeframe_is_refused(tmp_path):
    with pytest.raises(ValueError):
        store_io.write_frame(_frame(DAILY, "Date"), tmp_path / "a.csv", "1h")


def test_a_failed_write_keeps_the_old_file_and_leaves_no_temp(tmp_path, monkeypatch):
    path = tmp_path / "AAPL.csv"
    store_io.write_frame(_frame(DAILY, "Date"), path, "daily")
    before = path.read_bytes()

    def half_write(self, target, **kwargs):
        open(target, "w").write("Date,Open\n2016-")
        raise OSError("disk full")
    monkeypatch.setattr(pd.DataFrame, "to_csv", half_write)
    with pytest.raises(OSError):
        store_io.write_frame(_frame(DAILY, "Date"), path, "daily")
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


# --- manifest -------------------------------------------------------------------------

def test_manifest_hash_is_order_independent_and_covers_every_entry():
    a = {"AAPL": {"sha256": "aa"}, "MSFT": {"sha256": "bb"}, "XAUUSD": {"sha256": None}}
    b = dict(reversed(list(a.items())))
    assert store_io.manifest_hash(a) == store_io.manifest_hash(b)
    expected = hashlib.sha256("AAPL:aa\nMSFT:bb\nXAUUSD:-".encode()).hexdigest()
    assert store_io.manifest_hash(a) == expected
    assert store_io.manifest_hash({**a, "MSFT": {"sha256": "bc"}}) != expected


def test_empty_manifest_shape():
    m = store_io.empty_manifest("hourly")
    assert m == {"timeframe": "hourly", "feed": "sip", "adjustment": "all", "updated_at": None,
                 "hash": store_io.manifest_hash({}), "tickers": {}}
    with pytest.raises(ValueError):
        store_io.empty_manifest("1h")


def test_absent_manifest_loads_empty(tmp_path):
    assert store_io.load_manifest(tmp_path, "daily") == store_io.empty_manifest("daily")


def test_save_then_load_and_read_through_history_store(store_root):
    m = store_io.load_manifest(store_root, "daily")
    m["tickers"]["MSFT"] = {"status": "flagged: short-overlap", "sha256": "bb"}
    m["tickers"]["AAPL"] = {"status": "ok", "sha256": "aa"}
    store_io.save_manifest(store_root, "daily", m, now=NOW)

    assert m["updated_at"] == "2026-10-18T06:31:02Z"
    assert m["hash"] == store_io.manifest_hash(m["tickers"])
    on_disk = json.loads((store_root / "daily" / "_manifest.json").read_text())
    assert on_disk == m and list(on_disk["tickers"]) == ["AAPL", "MSFT"]
    assert store_io.load_manifest(store_root, "daily") == m
    assert hs.manifest("daily") == m
    assert hs.ticker_status("daily", "MSFT") == "flagged: short-overlap"
    assert [p.name for p in (store_root / "daily").iterdir()] == ["_manifest.json"]


def test_utc_stamp():
    assert store_io.utc_stamp(NOW) == "2026-10-18T06:31:02Z"
    assert store_io.utc_stamp(datetime(2026, 10, 18, 6, 31, 2)) == "2026-10-18T06:31:02Z"


# --- entries --------------------------------------------------------------------------

IDENTITY = {"status": "ok", "median_ratio": 1.0001, "overlap": 2710, "dropped_before": None}


def test_ok_entry_daily():
    e = store_io.ok_entry(_frame(DAILY, "Date"), "daily", start="2016-01-01", sha256="aa",
                          identity=IDENTITY, status="ok", fetched_at="2026-10-18T06:12:40Z")
    assert e == {"status": "ok", "start": "2016-01-01", "first": "2016-01-04", "last": "2016-01-06",
                 "rows": 3, "sha256": "aa", "fetched_at": "2026-10-18T06:12:40Z",
                 "identity": IDENTITY}
    assert type(e["rows"]) is int


def test_ok_entry_intraday_and_flagged_status():
    e = store_io.ok_entry(_frame(INTRADAY, "Datetime"), "15min", start="2016-01-01", sha256="cc",
                          identity=IDENTITY, status="flagged: price-mismatch", fetched_at="t")
    assert (e["first"], e["last"], e["status"]) == ("2016-01-04 04:00", "2016-01-04 19:45",
                                                     "flagged: price-mismatch")


def test_ok_entry_empty_frame():
    e = store_io.ok_entry(_frame([], "Date"), "daily", start="2016-01-01", sha256="dd",
                          identity=IDENTITY, status="ok", fetched_at="t")
    assert (e["first"], e["last"], e["rows"]) == (None, None, 0)


@pytest.mark.parametrize("reason", ["skipped: futures", "futures"])
def test_skipped_entry(reason):
    assert store_io.skipped_entry(reason, start="2016-01-01", fetched_at="t") == {
        "status": "skipped: futures", "start": "2016-01-01", "first": None, "last": None,
        "rows": 0, "sha256": None, "fetched_at": "t", "identity": None}


@pytest.mark.parametrize("entry,start,complete", [
    ({"status": "ok", "start": "2016-01-01"}, "2016-01-01", True),
    ({"status": "ok", "start": "2016-01-01"}, "2018-01-01", True),     # covers a later start
    ({"status": "ok", "start": "2018-01-01"}, "2016-01-01", False),    # does not reach back
    ({"status": "flagged: short-overlap", "start": "2016-01-01"}, "2016-01-01", False),
    ({"status": "skipped: futures", "start": "2016-01-01"}, "2016-01-01", False),
    ({"status": "ok"}, "2016-01-01", False),
    (None, "2016-01-01", False),
])
def test_is_complete(entry, start, complete):
    assert store_io.is_complete(entry, start) is complete
