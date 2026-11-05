"""v190 section 2: check_history_store.py --pit freezes the PIT store's
integrity verdict into _integrity.json -- identity re-derived against
backtest_cache_ext only, causal coverage cuts, the reused-symbol trim, the
context symbols admitted -- and the file round-trips through Part 1's reader
and training_data's PIT selection. Fixture stores under tmp_path only."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from alpaca_history import pit_coverage, reuse, store_io
from swingbot import config
from swingbot.core.marketdata import history_store, pit_integrity, training_data, universe

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc)
SESSIONS = pd.bdate_range("2016-01-04", "2018-12-31")      # SPY's bars: the fixture calendar
OPEN = "9999-12-31"
NO_BARS = "skipped: no Alpaca bars"
ETFS = {"SPY": "Broad Market", "XLK": "Information Technology"}
INTERVALS = {
    "AAA": [("2010-01-04", OPEN)], "MON": [("2010-01-04", "2017-06-01")],
    "DEL": [("2012-01-03", "2017-03-01")], "GAP": [("2010-01-04", OPEN)],
    "MIS": [("2010-01-04", OPEN)], "FALL": [("2010-01-04", OPEN)],
    "INS": [("2010-01-04", OPEN)], "FB": [("2012-05-18", OPEN)],
    "NOTF": [("2016-06-01", OPEN)], "OLD": [("2005-01-03", "2014-06-02")],
}
DETECTORS = ("scripts/data/alpaca_history/reuse.py", "scripts/data/alpaca_history/pit_coverage.py")


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_history_store", ROOT / "scripts" / "data" / "check_history_store.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _bars(days, close=100.0, volume=1e6) -> pd.DataFrame:
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close,
                         "Volume": volume}, index=pd.DatetimeIndex(days, name="Date"), dtype=float)


def _reissued(at: str) -> pd.DataFrame:
    """A $100, 1M-share name that becomes an $8, 20k-share name from `at` on."""
    frame = _bars(SESSIONS)
    frame.loc[frame.index >= at, "Close"] = 8.0
    frame.loc[frame.index >= at, "Volume"] = 2e4
    return frame


class PitStore:
    """Daily CSVs, references and hand-built manifests in the PIT store layout."""

    def __init__(self, tmp_path: Path):
        self.root = tmp_path / "data" / "market_data_pit"
        self.bt = tmp_path / "backtest_cache_ext"
        self.fallback = tmp_path / "market_data_daily"        # never passed to the check
        self.entries: dict[str, dict] = {}

    def add(self, ticker, frame, *, status="ok", reference=None, fallback=None, ident=None):
        path = self.root / "daily" / f"{ticker}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index_label="Date")
        for folder, ref in ((self.bt, reference), (self.fallback, fallback)):
            if ref is not None:
                folder.mkdir(parents=True, exist_ok=True)
                ref.to_csv(folder / f"{ticker}.csv", index_label="Date")
        self.entries[ticker] = {"status": status, "sha256": store_io.sha256_file(path),
                                "identity": ident or {"status": status, "dropped_before": None}}

    def skip(self, ticker, status, *, alias=None):
        self.entries[ticker] = {"status": status, "sha256": None, "identity": None,
                                **({"alias": alias} if alias else {})}

    def save(self) -> "PitStore":
        for tf in history_store.TIMEFRAMES:
            folder = self.root / tf
            folder.mkdir(parents=True, exist_ok=True)
            tickers = self.entries if tf == "daily" else {}
            (folder / "_manifest.json").write_text(json.dumps(
                {"timeframe": tf, "feed": "sip", "adjustment": "all", "hash": "h", "tickers": tickers}),
                encoding="utf-8")
        return self


def _store(tmp_path, *, spy=True) -> PitStore:
    s = PitStore(tmp_path)
    full = _bars(SESSIONS)
    if spy:
        s.add("SPY", full, reference=full)
    s.add("XLK", full, reference=full)
    late = SESSIONS[SESSIONS >= "2016-02-01"]
    s.add("AAA", _bars(late), reference=full,
          ident={"status": "ok", "median_ratio": 1.0, "overlap": len(late), "dropped_before": "2016-02-01"})
    s.add("MON", _reissued("2017-09-01"), reference=full[full.index < "2017-06-01"])
    s.add("DEL", _bars(SESSIONS[SESSIONS < "2017-03-01"]), status="flagged: no-reference")
    s.add("GAP", _bars(SESSIONS[(SESSIONS < "2017-03-01") | (SESSIONS > "2017-03-13")]),
          status="flagged: no-reference")
    s.add("MIS", full, status="flagged: price-mismatch", reference=full.assign(Close=200.0))
    s.add("FALL", full, fallback=full)                        # fetched "ok" through the old fallback
    s.add("INS", _reissued("2017-06-01"), status="flagged: no-reference")
    s.skip("FB", NO_BARS, alias="META")
    return s.save()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HISTORY_STORE_DIR", str(tmp_path / "watchlist_store"))
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(universe, "sector_map", lambda name: dict(ETFS) if name == "etfs" else {})
    training_data.reset()
    yield tmp_path
    training_data.reset()


def _build(chk, store):
    return chk.build_integrity(store.root, intervals=INTERVALS, backtest_dir=store.bt,
                               thresholds=reuse.THRESHOLDS, now=NOW)


@pytest.fixture
def built(env):
    chk = _load()
    store = _store(env)
    return chk, store, _build(chk, store)


# --- the document ------------------------------------------------------------------------

def test_header_thresholds_and_hashes(built):
    chk, store, doc = built
    assert (doc["schema"], doc["generated_at"]) == (pit_integrity.SCHEMA_VERSION, "2026-10-25T10:00:00Z")
    assert (doc["store_start"], doc["store_end"]) == ("2016-01-04", "2025-12-31")
    assert doc["thresholds"] == {"max_missing_run": 5, "trailing_sessions": 60, "min_trailing_share": 0.95,
                                 "break_move": 0.5, "break_ratio": 10.0, "revert_sessions": 20,
                                 "gap_sessions": 20, "edge_sessions": 20}
    for tf in history_store.TIMEFRAMES:      # V190-4 compares "daily" for freshness
        assert doc["manifest_sha256"][tf] == store_io.sha256_file(store.root / tf / "_manifest.json")


def test_detector_shas_are_the_git_blob_ids(built):
    _, _, doc = built
    assert set(doc["detector_sha"]) == set(DETECTORS)
    for rel in DETECTORS:
        want = subprocess.run(["git", "hash-object", rel], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
        assert doc["detector_sha"][rel] == want


def test_context_symbols_are_admitted(built):
    _, _, doc = built
    for symbol in ("SPY", "XLK"):
        entry = doc["tickers"][symbol]
        assert entry["admitted"] is True and entry["reason"] is None, symbol
        assert entry["reference"]["source"] == "backtest_cache_ext"
        assert entry["signal_cuts"] == [] and entry["trim"] is None


def test_mon_is_trimmed_after_its_exit(built):
    _, _, doc = built
    mon = doc["tickers"]["MON"]
    assert mon["admitted"] is True and mon["identity"] == "ok"
    assert mon["trim"] == {"keep_from": None, "keep_before": "2017-09-01",
                           "reason": "break after last membership end"}
    assert mon["breaks"] == [{"date": "2017-09-01", "kind": "price+volume", "resolution": "trim_after"}]
    assert {g["kind"] for g in mon["gaps"]} == {"end", "reference-end"}
    assert (mon["first_bar"], mon["last_bar"]) == ("2016-01-04", "2018-12-31")


def test_a_delisted_member_without_a_reference_is_admitted(built):
    _, _, doc = built
    dead = doc["tickers"]["DEL"]
    assert dead["admitted"] is True and dead["identity"] == "flagged: no-reference"
    assert dead["reference"] == {"source": None, "sha256": None}
    assert dead["signal_cuts"] == [] and dead["trim"] is None


def test_the_market_data_fallback_is_never_a_reference(built):
    _, _, doc = built
    fall = doc["tickers"]["FALL"]
    assert (fall["identity_manifest"], fall["identity"]) == ("ok", "flagged: no-reference")
    assert fall["reference"]["source"] is None and fall["admitted"] is True


def test_a_re_derived_mismatch_is_excluded_with_its_reason(built):
    _, store, doc = built
    mis = doc["tickers"]["MIS"]
    assert mis["admitted"] is False
    assert mis["reason"] == "identity re-derived: flagged: price-mismatch"
    assert mis["reference"]["sha256"] == store_io.sha256_file(store.bt / "MIS.csv")


def test_coverage_cuts_and_bars_dropped_before_the_reference(built):
    _, _, doc = built
    gap = doc["tickers"]["GAP"]
    assert ["2017-03-01", "2017-03-14", "missing run of 9 sessions"] in gap["signal_cuts"]
    assert gap["coverage"][0]["missing_runs"] == [["2017-03-01", "2017-03-14", 9]]
    assert gap["admitted"] is True
    aaa = doc["tickers"]["AAA"]
    assert aaa["dropped_before"] == len(SESSIONS[SESSIONS < "2016-02-01"])
    assert ["2016-01-04", "2016-02-01", "missing run of 20 sessions"] in aaa["signal_cuts"]


def test_an_in_span_break_waits_for_the_builder(built):
    _, _, doc = built
    ins = doc["tickers"]["INS"]
    assert ins["admitted"] is False and ins["trim"] is None
    assert ins["reason"] == "in-span break 2017-06-01 (price+volume): resolve by hand"


def test_no_bars_aliases_and_unfetched_members(built):
    _, _, doc = built
    assert doc["no_bars"] == ["FB"] and "FB" not in doc["tickers"]
    assert doc["aliases"] == {"FB": "META"}
    assert doc["tickers"]["NOTF"]["admitted"] is False
    assert doc["tickers"]["NOTF"]["reason"] == "not fetched"
    assert "OLD" not in doc["tickers"]                     # no span inside the store window


def test_the_check_never_reads_through_history_store_load(env, monkeypatch):
    """Constraint 3: history_store.load(store='pit') refuses until this very file exists."""
    chk = _load()
    store = _store(env)
    monkeypatch.setattr(history_store, "load", lambda *a, **k: pytest.fail("history_store.load called"))
    assert "MON" in _build(chk, store)["tickers"]


def test_no_spy_calendar_is_refused(env):
    chk = _load()
    with pytest.raises(ValueError, match="SPY"):
        _build(chk, _store(env, spy=False))


# --- the file and its readers ------------------------------------------------------------

def test_the_written_file_round_trips_through_the_reader(built):
    chk, store, doc = built
    path = chk.write_integrity(store.root, doc)
    assert path == store.root / pit_integrity.INTEGRITY_NAME
    assert path.read_bytes().endswith(b"\n") and b"\r\n" not in path.read_bytes()
    got = pit_integrity.load_integrity(store.root)
    assert got.doc == json.loads(json.dumps(doc))
    assert got.trim_window("MON") == (None, "2017-09-01")
    assert ("2017-03-01", "2017-03-14") in got.signal_cuts("GAP")
    assert got.exclusion("FB") == pit_integrity.NO_BARS_REASON
    assert got.exclusion("SPY") is None and got.exclusion("XLK") is None
    assert got.exclusion("MIS") == "identity re-derived: flagged: price-mismatch"


def test_training_data_selects_the_store_with_this_report_and_context_passes(built):
    """Constraints 1 and 2 end to end: fresh manifest hash, context symbols admitted."""
    import fetch_backtest_data as fbd
    chk, store, doc = built
    chk.write_integrity(store.root, doc)
    assert training_data.select("alpaca", "pit", "2025-12-31") == "alpaca"
    excluded = training_data.excluded()
    assert excluded["INS"].startswith("integrity: in-span break")
    assert {"MIS", "FB"} <= set(excluded)
    assert not {"SPY", "XLK", "MON", "DEL", "FALL", "AAA"} & set(excluded)
    fbd.require_context_frames()                           # no SystemExit
    assert training_data.load_daily("MON").index.max() < pd.Timestamp("2017-09-01")


def test_a_manifest_rewritten_after_the_freeze_is_stale(built):
    chk, store, doc = built
    chk.write_integrity(store.root, doc)
    manifest = store.root / "daily" / "_manifest.json"
    manifest.write_text(manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(training_data.StaleIntegrityError):
        training_data.select("alpaca", "pit", "2025-12-31")


# --- the summary and the CLI -------------------------------------------------------------

def test_the_summary_names_every_cut_and_its_reason(built):
    chk, _, doc = built
    text = chk.render_integrity_md(doc)
    for needle in ("MIS", "identity re-derived: flagged: price-mismatch", "INS", "resolve by hand",
                   "NOTF", "not fetched", "MON", "2017-09-01", "break after last membership end",
                   "FB", "META", "missing run of 9 sessions", "break_ratio",
                   "frozen before any strategy result is read"):
        assert needle in text, needle


def _membership_csv(env) -> None:
    folder = env / "data" / "universe"
    folder.mkdir(parents=True, exist_ok=True)
    rows = ["ticker,start_date,end_date"] + [
        f"{t},{s},{'' if e == OPEN else e}" for t, spans in INTERVALS.items() for s, e in spans]
    (folder / "sp500_membership.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_main_pit_writes_the_report_and_the_summary(env, capsys):
    chk = _load()
    store = _store(env)
    _membership_csv(env)
    results = env / "results"
    argv = ["--pit", "--root", str(store.root), "--backtest-dir", str(store.bt),
            "--results-dir", str(results)]
    assert chk.main(argv) == 0
    doc = pit_integrity.load_integrity(store.root).doc
    assert doc["tickers"]["MON"]["trim"]["keep_before"] == "2017-09-01"
    summaries = list(results.glob("*-v190-pit-integrity-report.md"))
    assert len(summaries) == 1 and "MON" in summaries[0].read_text(encoding="utf-8")
    assert "admitted" in capsys.readouterr().out


def test_main_pit_refuses_a_ticker_list_and_a_damaged_store(env):
    chk = _load()
    store = _store(env)
    _membership_csv(env)
    base = ["--pit", "--root", str(store.root), "--backtest-dir", str(store.bt),
            "--results-dir", str(env / "results")]
    assert chk.main([*base, "--tickers", "MON"]) == 2
    (store.root / "daily" / "AAA.csv").write_text("Date,Close\n2016-02-01,1\n", encoding="utf-8")
    assert chk.main(base) == 1
    assert not (store.root / pit_integrity.INTEGRITY_NAME).exists()


def test_the_watchlist_check_is_unchanged_by_default():
    args = _load().parse_args([])
    assert args.pit is False and args.backtest_dir is None
