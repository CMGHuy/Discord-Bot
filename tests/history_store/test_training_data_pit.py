"""v190 section 2.2 / 3: training_data on the point-in-time Alpaca store --
admission (no-reference in, short-overlap/price-mismatch/integrity out), the
frozen-report refusals, frame trims, the research_end cut on daily, intraday
and context frames, signal cuts, provenance, and the store choice reaching
pool workers. The watchlist store keeps every rule it has today."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import history_store, pit_integrity, training_data

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

UNTIL = "2025-12-31"

#: Daily manifest statuses on the PIT store.
PIT_ENTRIES = {"AAA": "ok", "DEL": "flagged: no-reference", "SHO": "flagged: short-overlap",
               "MIS": "flagged: price-mismatch", "MON": "ok", "BAD": "ok", "GONE": "ok",
               "ZOMB": "ok", "LATE": "ok", "SPY": "ok", "FB": "skipped: no bars"}
#: Daily files on disk: GONE has none; ZOMB's bars all fall in its trimmed side;
#: LATE lists after the cut; AAA and SPY run into the sealed 2026.
PIT_FILES = {"AAA": ("2016-01-04", "2026-03-31"), "DEL": ("2016-01-04", "2019-06-28"),
             "SHO": ("2016-01-04", "2016-06-30"), "MIS": ("2016-01-04", "2016-06-30"),
             "MON": ("2016-01-04", "2022-12-30"), "BAD": ("2016-01-04", "2020-12-31"),
             "ZOMB": ("2019-01-02", "2019-06-28"), "LATE": ("2026-02-02", "2026-03-31"),
             "SPY": ("2016-01-04", "2026-03-31")}
ADMIT = {"admitted": True, "reason": None, "signal_cuts": [], "trim": None}
REPORT_TICKERS = {
    "AAA": {**ADMIT, "signal_cuts": [["2017-03-01", "2017-03-20", "missing run of 9 sessions"]]},
    "DEL": ADMIT, "SHO": ADMIT, "MIS": ADMIT, "GONE": ADMIT, "LATE": ADMIT, "SPY": ADMIT,
    "MON": {**ADMIT, "trim": {"keep_from": None, "keep_before": "2018-06-08",
                              "reason": "break after last membership end"}},
    "ZOMB": {**ADMIT, "trim": {"keep_from": None, "keep_before": "2018-01-01",
                               "reason": "break after last membership end"}},
    "BAD": {**ADMIT, "admitted": False, "reason": "unresolved break 2019-05-02"},
}
EXPECTED_EXCLUDED = {"BAD": "integrity: unresolved break 2019-05-02",
                     "FB": "skipped: no bars", "GONE": "no file",
                     "MIS": "flagged: price-mismatch", "SHO": "flagged: short-overlap"}


def _bars(start, end, freq="B"):
    idx = pd.date_range(start, end, freq=freq)
    n = len(idx)
    return pd.DataFrame({"Open": [10.0] * n, "High": [11.0] * n, "Low": [9.0] * n,
                         "Close": [10.0] * n, "Volume": [1000.0] * n}, index=idx)


def _csv(root, ticker, timeframe, frame):
    folder = root / timeframe
    folder.mkdir(parents=True, exist_ok=True)
    frame.to_csv(folder / f"{ticker}.csv", index_label=history_store.INDEX_NAMES[timeframe])


def _write_manifest(root, entries) -> bytes:
    path = root / "daily" / "_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"timeframe": "daily", "feed": "sip", "adjustment": "all",
                                "hash": "pit-h",
                                "tickers": {t: {"status": s} for t, s in entries.items()}}))
    return path.read_bytes()


def _write_report(root, manifest_bytes) -> Path:
    path = root / pit_integrity.INTEGRITY_NAME
    path.write_text(json.dumps({
        "schema": 1, "generated_at": "2026-10-25T10:00:00Z", "store_start": "2016-01-04",
        "store_end": UNTIL, "thresholds": {}, "detector_sha": {},
        "manifest_sha256": {"daily": hashlib.sha256(manifest_bytes).hexdigest(),
                            "hourly": None, "15min": None},
        "no_bars": ["FB"], "tickers": REPORT_TICKERS}), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _fresh_switch(monkeypatch):
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    training_data.reset()
    yield
    training_data.reset()


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """Both stores on disk: the watchlist store through HISTORY_STORE_DIR (as on
    the VM and in every other test), the PIT store under DATA_DIR."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    watch = tmp_path / "market_data"
    monkeypatch.setenv("HISTORY_STORE_DIR", str(watch))
    _csv(watch, "AAPL", "daily", _bars("2016-01-04", "2016-03-31"))
    _csv(watch, "DEL", "daily", _bars("2016-01-04", "2016-03-31"))
    (watch / "daily" / "_manifest.json").write_text(json.dumps(
        {"timeframe": "daily", "feed": "sip", "adjustment": "all", "hash": "w-h",
         "tickers": {"AAPL": {"status": "ok"}, "DEL": {"status": "flagged: no-reference"}}}))
    pit = tmp_path / "data" / "market_data_pit"
    for ticker, (start, end) in PIT_FILES.items():
        _csv(pit, ticker, "daily", _bars(start, end))
    _csv(pit, "AAA", "hourly", _bars("2025-12-30 09:30", "2026-01-02 15:30", freq="h"))
    _csv(pit, "MON", "hourly", _bars("2018-06-06 09:30", "2018-06-12 15:30", freq="h"))
    _write_report(pit, _write_manifest(pit, PIT_ENTRIES))
    return watch, pit


def _select_pit():
    return training_data.select("alpaca", "pit", UNTIL)


# --- the default never moves ----------------------------------------------------------

def test_default_selection_never_picks_the_pit_store(stores):
    assert training_data.select() == "alpaca"
    assert training_data.active_store() == "watchlist"
    assert training_data.available_tickers() == ["AAPL"]
    assert training_data.signal_cuts() is None
    assert training_data.selection_args() == ("alpaca",)


def test_watchlist_exclusions_still_reject_no_reference(stores):
    """Both stores share the status strings; only the PIT store admits no-reference."""
    training_data.select("alpaca")
    assert training_data.excluded() == {"DEL": "flagged: no-reference"}
    manifest = {"tickers": {"X": {"status": "flagged: no-reference"}}}
    assert training_data._manifest_exclusions(manifest) == {"X": "flagged: no-reference"}


def test_yfinance_selection_args_are_unchanged(stores):
    training_data.select("yfinance")
    assert training_data.selection_args() == ("yfinance",)
    assert training_data.active_store() == "watchlist"


# --- admission ------------------------------------------------------------------------

def test_pit_admission_follows_section_2_2(stores):
    assert _select_pit() == "alpaca"
    assert training_data.active_store() == "pit"
    assert training_data.excluded() == EXPECTED_EXCLUDED
    assert training_data.available_tickers() == ["AAA", "DEL", "LATE", "MON", "SPY", "ZOMB"]


def test_pit_admitted_strings_are_the_fetchers_identity_statuses():
    from alpaca_history import identity
    assert training_data.PIT_ADMITTED == (identity.OK, identity.NO_REFERENCE)


def test_pit_exclusions_function_directly(stores):
    _, pit = stores
    manifest = history_store.require_manifest("daily", store="pit")
    integrity = pit_integrity.load_integrity(pit)
    assert training_data._pit_exclusions(manifest, integrity, store="pit") == EXPECTED_EXCLUDED


def test_pit_requires_the_integrity_report(stores):
    _, pit = stores
    (pit / pit_integrity.INTEGRITY_NAME).unlink()
    with pytest.raises(history_store.MissingStoreError, match="_integrity.json"):
        _select_pit()
    assert training_data._SELECTION is None


def test_a_store_refreshed_after_the_freeze_is_refused(stores):
    _, pit = stores
    _write_manifest(pit, {**PIT_ENTRIES, "NEW": "ok"})          # a --mode update ran
    with pytest.raises(training_data.StaleIntegrityError, match="check_history_store.py --pit"):
        _select_pit()
    assert issubclass(training_data.StaleIntegrityError, history_store.MissingStoreError)
    assert training_data._SELECTION is None


@pytest.mark.parametrize("args, match", [
    (("yfinance", "pit", UNTIL), "PIT store"),
    (("alpaca", None, UNTIL), "until"),
    (("alpaca", "sp500_pit", None), "unknown history store"),
])
def test_store_argument_errors(stores, args, match):
    with pytest.raises(ValueError, match=match):
        training_data.select(*args)


# --- frames: trims and the research_end cut ---------------------------------------------

def test_pit_daily_and_context_frames_stop_at_until(stores):
    _select_pit()
    for ticker in ("AAA", "SPY"):
        frame = training_data.load_daily(ticker)
        assert frame.index.max() == pd.Timestamp(UNTIL), ticker


def test_pit_daily_applies_the_trim(stores):
    _select_pit()
    assert training_data.load_daily("MON").index.max() < pd.Timestamp("2018-06-08")


def test_no_reference_member_loads_whole(stores):
    _select_pit()
    assert training_data.load_daily("DEL").index.max() == pd.Timestamp("2019-06-28")


def test_trimmed_to_nothing_is_excluded_with_a_reason(stores):
    _select_pit()
    assert training_data.load_daily("ZOMB") is None
    assert training_data.excluded()["ZOMB"] == training_data.TRIMMED_EMPTY


def test_no_bar_by_until_is_excluded_with_a_reason(stores):
    _select_pit()
    assert training_data.load_daily("LATE") is None
    assert training_data.excluded()["LATE"] == training_data.NO_BARS_BY_UNTIL


def test_no_intraday_bar_on_or_after_the_holdout_is_reachable(stores):
    _select_pit()
    aaa = training_data.load_intraday("AAA", "hourly")
    assert aaa.index.max() < pd.Timestamp("2026-01-01")
    assert aaa.index.max() >= pd.Timestamp("2025-12-31 09:30")
    assert training_data.load_intraday("MON", "hourly").index.max() < pd.Timestamp("2018-06-08")
    assert training_data.load_intraday("BAD", "hourly") is None      # excluded
    assert training_data.load_intraday("QQQQ", "hourly") is None     # not in the store


def test_watchlist_intraday_is_todays_direct_read(stores):
    watch, _ = stores
    _csv(watch, "AAPL", "hourly", _bars("2025-12-30 09:30", "2026-01-02 15:30", freq="h"))
    training_data.select("alpaca")
    pd.testing.assert_frame_equal(training_data.load_intraday("AAPL", "hourly"),
                                  history_store.load("AAPL", "hourly"))


# --- signal cuts, provenance ---------------------------------------------------------------

def test_signal_cuts_cover_every_admitted_ticker(stores):
    _select_pit()
    cuts = training_data.signal_cuts()
    assert cuts["AAA"] == [("2017-03-01", "2017-03-20")]
    assert cuts["DEL"] == [] and "BAD" not in cuts and "SHO" not in cuts


def test_pit_provenance_names_the_store_and_the_report(stores):
    _, pit = stores
    _select_pit()
    report = pit / pit_integrity.INTEGRITY_NAME
    assert training_data.provenance() == {
        "data_source": "alpaca", "feed": "sip", "adjustment": "all", "manifest_hash": "pit-h",
        "store": "pit", "integrity_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "store_dir": str(pit), "excluded": EXPECTED_EXCLUDED}


# --- workers ---------------------------------------------------------------------------------

def test_a_worker_reselecting_from_selection_args_lands_on_the_same_store_and_cut(stores):
    _select_pit()
    args = training_data.selection_args()
    assert args == ("alpaca", "pit", UNTIL)
    training_data.reset()                         # what a spawned worker starts from
    training_data.select(*args)
    assert training_data.active_store() == "pit"
    assert training_data.load_daily("AAA").index.max() == pd.Timestamp(UNTIL)


def test_pool_kwargs_hand_workers_the_pit_store(stores):
    import cache_dir_source as cds
    _select_pit()
    assert cds.pool_kwargs() == {"initializer": training_data.select,
                                 "initargs": ("alpaca", "pit", UNTIL)}


@pytest.mark.parametrize("script", ["measure_arms.py", "measure_acceptance_exits.py",
                                    "measure_fvg_bullish_diagnostic.py"])
def test_measure_pools_pass_the_whole_selection(script):
    source = (ROOT / "scripts" / "backtest" / script).read_text(encoding="utf-8")
    assert "initargs=training_data.selection_args()" in source
    assert "initargs=(training_data.active(),)" not in source
