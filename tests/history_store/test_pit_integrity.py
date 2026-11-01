"""v190 section 2.3 / 3: the _integrity.json reader and the frame trim that
removes a reused symbol's foreign bars inside history_store.load, before any
indicator or exit walk reads them. Fixture stores under tmp_path only."""
import hashlib
import json

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import history_store as hs
from swingbot.core.marketdata import pit_integrity as pi

#: MON's shape: a member until mid-2018, then the symbol reused by another issuer.
DOC = {
    "schema": 1, "generated_at": "2026-10-25T10:00:00Z",
    "store_start": "2016-01-04", "store_end": "2025-12-31",
    "thresholds": {}, "detector_sha": {},
    "manifest_sha256": {"daily": "d" * 64, "hourly": "h" * 64, "15min": None},
    "no_bars": ["FB"],
    "tickers": {
        "MON": {"admitted": True, "reason": None,
                "signal_cuts": [["2017-03-01", "2017-03-20", "missing run of 9 sessions"]],
                "trim": {"keep_from": None, "keep_before": "2018-06-08",
                         "reason": "break after last membership end"}},
        "ABC": {"admitted": True, "reason": None, "signal_cuts": [],
                "trim": {"keep_from": "2016-03-01", "keep_before": None,
                         "reason": "break before first membership start"}},
        "OK1": {"admitted": True, "reason": None, "signal_cuts": [], "trim": None},
        "BAD": {"admitted": False, "reason": "unresolved break 2019-05-02",
                "signal_cuts": [], "trim": None},
        "MUTE": {"admitted": False, "reason": None, "signal_cuts": [], "trim": None},
    },
}


def _write_doc(root, doc=DOC):
    root.mkdir(parents=True, exist_ok=True)
    path = root / pi.INTEGRITY_NAME
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _bars(start, end, freq="B"):
    idx = pd.date_range(start, end, freq=freq)
    n = len(idx)
    return pd.DataFrame({"Open": [10.0] * n, "High": [11.0] * n, "Low": [9.0] * n,
                         "Close": [10.0] * n, "Volume": [1000.0] * n}, index=idx)


@pytest.fixture
def pit_root(tmp_path, monkeypatch):
    """A PIT store under DATA_DIR; HISTORY_STORE_DIR points elsewhere on purpose."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HISTORY_STORE_DIR", str(tmp_path / "watchlist_store"))
    return tmp_path / "data" / "market_data_pit"


def _csv(root, ticker, timeframe, frame):
    folder = root / timeframe
    folder.mkdir(parents=True, exist_ok=True)
    frame.to_csv(folder / f"{ticker}.csv", index_label=hs.INDEX_NAMES[timeframe])


# --- the reader -----------------------------------------------------------------------

def test_absent_report_is_none(tmp_path):
    assert pi.load_integrity(tmp_path) is None
    assert pi.integrity_path(tmp_path) == tmp_path / "_integrity.json"


def test_report_carries_the_sha256_of_its_bytes(tmp_path):
    path = _write_doc(tmp_path)
    got = pi.load_integrity(tmp_path)
    assert got.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert got.doc == DOC


def test_unknown_schema_is_refused(tmp_path):
    _write_doc(tmp_path, {**DOC, "schema": 2})
    with pytest.raises(ValueError, match="_integrity.json"):
        pi.load_integrity(tmp_path)


def test_trim_window_signal_cuts_and_manifest_hashes(tmp_path):
    _write_doc(tmp_path)
    got = pi.load_integrity(tmp_path)
    assert got.trim_window("MON") == (None, "2018-06-08")
    assert got.trim_window(" abc ") == ("2016-03-01", None)
    assert got.trim_window("OK1") == (None, None)
    assert got.trim_window("ZZZ") == (None, None)
    assert got.signal_cuts("MON") == [("2017-03-01", "2017-03-20")]
    assert got.signal_cuts("OK1") == [] and got.signal_cuts("ZZZ") == []
    assert got.manifest_sha256("daily") == "d" * 64
    assert got.manifest_sha256("15min") is None


def test_exclusion_states_a_reason_for_every_refusal(tmp_path):
    _write_doc(tmp_path)
    got = pi.load_integrity(tmp_path)
    assert got.exclusion("MON") is None and got.exclusion("OK1") is None
    assert got.exclusion("BAD") == "unresolved break 2019-05-02"
    assert got.exclusion("MUTE") == pi.NOT_ADMITTED
    assert got.exclusion("FB") == pi.NO_BARS_REASON
    assert got.exclusion("ZZZ") == pi.NOT_IN_REPORT


def test_cached_integrity_rereads_a_rewritten_file(tmp_path):
    _write_doc(tmp_path)
    first = pi.cached_integrity(tmp_path)
    assert pi.cached_integrity(tmp_path) is first
    _write_doc(tmp_path, {**DOC, "no_bars": ["FB", "XYZW"]})
    assert pi.cached_integrity(tmp_path).exclusion("XYZW") == pi.NO_BARS_REASON


# --- apply_trim -------------------------------------------------------------------------

def test_trim_keeps_the_bars_before_a_break_after_the_last_membership_end():
    frame = _bars("2018-06-01", "2018-06-15")
    got = pi.apply_trim(frame, (None, "2018-06-08"))
    assert got.index.max() == pd.Timestamp("2018-06-07")
    assert got.index.min() == pd.Timestamp("2018-06-01")


def test_trim_keeps_the_bars_after_a_break_before_the_first_membership_start():
    frame = _bars("2016-02-22", "2016-03-04")
    got = pi.apply_trim(frame, ("2016-03-01", None))
    assert got.index.min() == pd.Timestamp("2016-03-01")
    assert got.index.max() == pd.Timestamp("2016-03-04")


def test_trim_is_date_level_on_intraday_bars():
    frame = _bars("2018-06-07 09:30", "2018-06-08 15:30", freq="h")
    got = pi.apply_trim(frame, (None, "2018-06-08"))
    assert got.index.max() < pd.Timestamp("2018-06-08")
    assert (got.index.date == pd.Timestamp("2018-06-07").date()).all()


def test_trim_edge_cases():
    frame = _bars("2018-06-01", "2018-06-15")
    assert pi.apply_trim(frame, (None, None)) is frame
    assert pi.apply_trim(None, ("2016-01-04", None)) is None
    assert pi.apply_trim(frame, (None, "2018-06-01")) is None          # trimmed to nothing
    assert pi.apply_trim(frame, ("2018-06-10", "2018-06-10")) is None


# --- history_store.load(store="pit") --------------------------------------------------

def test_pit_load_applies_the_trim_on_every_timeframe(pit_root):
    _write_doc(pit_root)
    _csv(pit_root, "MON", "daily", _bars("2018-05-01", "2022-12-30"))
    _csv(pit_root, "MON", "hourly", _bars("2018-06-06 09:30", "2018-06-12 15:30", freq="h"))
    _csv(pit_root, "MON", "15min", _bars("2018-06-07 09:30", "2018-06-08 15:45", freq="15min"))
    for timeframe in hs.TIMEFRAMES:
        got = hs.load("MON", timeframe, store="pit")
        assert got.index.max() < pd.Timestamp("2018-06-08"), timeframe


def test_pit_load_trimmed_to_nothing_is_none(pit_root):
    _write_doc(pit_root)
    _csv(pit_root, "MON", "daily", _bars("2019-01-02", "2019-03-29"))   # only reused-issuer bars
    assert hs.load("MON", "daily", store="pit") is None


def test_pit_load_without_a_report_refuses(pit_root):
    _csv(pit_root, "OK1", "daily", _bars("2016-01-04", "2016-03-31"))
    with pytest.raises(hs.MissingStoreError, match="_integrity.json"):
        hs.load("OK1", "daily", store="pit")


def test_untrimmed_pit_ticker_loads_whole(pit_root):
    _write_doc(pit_root)
    frame = _bars("2016-01-04", "2016-03-31")
    _csv(pit_root, "OK1", "daily", frame)
    assert len(hs.load("OK1", "daily", store="pit")) == len(frame)


def test_watchlist_load_never_reads_a_report(tmp_path, monkeypatch, store_root):
    """The watchlist store's load is today's: a stray _integrity.json in it is ignored."""
    _write_doc(store_root)
    _csv(store_root, "MON", "daily", _bars("2018-05-01", "2018-12-31"))
    got = hs.load("MON", "daily")
    assert got.index.max() == pd.Timestamp("2018-12-31")
