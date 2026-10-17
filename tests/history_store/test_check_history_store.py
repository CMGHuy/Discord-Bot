"""v162 AH9: row counts against the SPY calendar (half-days, holidays,
listings, thin names) and the manifest hash check."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
# Thanksgiving week 2024: Thursday 28 closed, Friday 29 a 13:00 half-day.
SESSIONS = {"2024-11-25": "full", "2024-11-26": "full", "2024-11-27": "full",
            "2024-11-29": "half", "2024-12-02": "full"}
INDEX = {"15min": "Datetime", "hourly": "Datetime", "daily": "Date"}


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_history_store", ROOT / "scripts" / "data" / "check_history_store.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stamps(day: str, kind: str, tf: str) -> list[pd.Timestamp]:
    end = "16:00" if kind == "full" else "13:00"
    if tf == "daily":
        return [pd.Timestamp(day)]
    if tf == "hourly":
        return list(pd.date_range(f"{day} 09:30", f"{day} {end}", freq="60min", inclusive="left"))
    rth = pd.date_range(f"{day} 09:30", f"{day} {end}", freq="15min", inclusive="left")
    return list(rth) + [pd.Timestamp(f"{day} 08:00"), pd.Timestamp(f"{day} 17:00")]


class Store:
    """Writes CSVs and hand-built manifests in the v162 store layout."""

    def __init__(self, root: Path):
        self.root = root
        self.manifests = {tf: {"timeframe": tf, "feed": "sip", "adjustment": "all", "tickers": {}}
                          for tf in INDEX}

    def add(self, ticker: str, sessions: dict[str, str] = SESSIONS, *, drop_15min: int = 0) -> None:
        for tf in INDEX:
            stamps = sorted(s for day, kind in sessions.items() for s in _stamps(day, kind, tf))
            if tf == "15min" and drop_15min:
                stamps = stamps[drop_15min:]
            frame = pd.DataFrame({c: 1.0 for c in ("Open", "High", "Low", "Close", "Volume")},
                                 index=pd.DatetimeIndex(stamps, name=INDEX[tf]))
            path = self.root / tf / f"{ticker}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(path)
            self.manifests[tf]["tickers"][ticker] = {
                "status": "ok", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def skip(self, ticker: str, reason: str) -> None:
        for tf in INDEX:
            self.manifests[tf]["tickers"][ticker] = {"status": reason, "sha256": None}

    def save(self) -> Path:
        for tf, manifest in self.manifests.items():
            (self.root / tf).mkdir(parents=True, exist_ok=True)
            (self.root / tf / "_manifest.json").write_text(json.dumps(manifest))
        return self.root


@pytest.fixture
def store(store_root) -> Store:
    s = Store(store_root)
    s.add("SPY")
    return s


def _calendar(chk, root, tf):
    return chk.session_counts(chk.read_frame(root, "SPY", tf))


def test_session_counts_are_bars_per_date():
    chk = _load()
    idx = pd.DatetimeIndex(["2024-11-25 09:30", "2024-11-25 09:45", "2024-11-26 09:30"])
    counts = chk.session_counts(pd.DataFrame({"Close": [1.0, 1.0, 1.0]}, index=idx))
    assert counts.to_dict() == {pd.Timestamp("2024-11-25"): 2, pd.Timestamp("2024-11-26"): 1}


@pytest.mark.parametrize("tf", ["15min", "hourly", "daily"])
def test_a_clean_ticker_explains_every_session(store, tf):
    chk = _load()
    store.add("AAPL")
    root = store.save()
    res = chk.check_ticker("AAPL", tf, root=root, calendar=_calendar(chk, root, tf))
    assert res["unexplained"] == []
    assert (res["sessions"], res["holiday"], res["pre_listing"], res["sparse"]) == (5, 1, 0, 0)
    if tf == "daily":
        assert res["full"] == 5
    else:
        assert (res["full"], res["half_day"]) == (4, 1)


def test_extended_hours_15min_bars_are_not_counted(store):
    chk = _load()
    root = store.save()
    frame = chk.read_frame(root, "SPY", "15min")
    assert frame.index.min().strftime("%H:%M") == "09:30"
    assert frame.index.max().strftime("%H:%M") == "15:45"


def test_a_thin_name_is_sparse_not_unexplained(store):
    chk = _load()
    store.add("THIN", drop_15min=8)
    root = store.save()
    res = chk.check_ticker("THIN", "15min", root=root, calendar=_calendar(chk, root, "15min"))
    assert res["sparse"] == 1 and res["unexplained"] == []


def test_a_missing_session_is_unexplained(store):
    chk = _load()
    store.add("GAPPY", {d: k for d, k in SESSIONS.items() if d != "2024-11-26"})
    root = store.save()
    res = chk.check_ticker("GAPPY", "15min", root=root, calendar=_calendar(chk, root, "15min"))
    assert res["unexplained"] == ["2024-11-26: 0 of 26 bars"]


def test_a_late_listing_is_pre_listing_and_an_early_end_is_unexplained(store):
    chk = _load()
    store.add("NEWCO", {d: k for d, k in SESSIONS.items() if d >= "2024-11-27"})
    store.add("STALE", {d: k for d, k in SESSIONS.items() if d <= "2024-11-26"})
    root = store.save()
    new = chk.check_ticker("NEWCO", "hourly", root=root, calendar=_calendar(chk, root, "hourly"))
    assert new["pre_listing"] == 2 and new["unexplained"] == []
    stale = chk.check_ticker("STALE", "daily", root=root, calendar=_calendar(chk, root, "daily"))
    assert stale["unexplained"] == ["ends 2024-11-26, 3 sessions before SPY"]


def test_a_bar_on_a_day_spy_does_not_trade_is_unexplained(store):
    chk = _load()
    store.add("ODD", {**SESSIONS, "2024-11-28": "full"})
    root = store.save()
    res = chk.check_ticker("ODD", "daily", root=root, calendar=_calendar(chk, root, "daily"))
    assert res["unexplained"] == ["2024-11-28: bars on a day SPY did not trade"]


def test_verify_hashes_finds_tampered_and_missing_files(store):
    chk = _load()
    store.add("AAPL")
    store.add("MSFT")
    root = store.save()
    assert chk.verify_hashes(root) == []
    (root / "hourly" / "AAPL.csv").write_text("Datetime,Open\n")
    (root / "daily" / "MSFT.csv").unlink()
    problems = chk.verify_hashes(root)
    assert len(problems) == 2
    assert any(p.startswith("hourly/AAPL: sha256") for p in problems)
    assert any(p.startswith("daily/MSFT: file missing") for p in problems)


def test_verify_hashes_reports_a_missing_manifest(store_root):
    chk = _load()
    problems = _load().verify_hashes(store_root)
    assert len(problems) == 3 and all("no manifest" in p for p in problems)
    assert chk.RTH_15MIN_FULL == 26 and chk.HOURLY_HALF == 4


def test_main_exit_codes_and_skip_lines(store, capsys):
    chk = _load()
    store.add("AAPL")
    store.add("GAPPY", {d: k for d, k in SESSIONS.items() if d != "2024-11-26"})
    store.skip("GC=F", "skipped: futures")
    root = store.save()
    assert chk.main(["--root", str(root), "--tickers", "AAPL"]) == 0
    assert chk.main(["--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "SKIP GC=F" in out and "2024-11-26: 0 of 26 bars" in out
    (root / "daily" / "AAPL.csv").write_text("Date,Open\n")
    assert chk.main(["--root", str(root), "--tickers", "AAPL", "--verify-hashes"]) == 1
    assert "HASH daily/AAPL" in capsys.readouterr().out


def test_main_fails_without_a_spy_calendar(store_root, capsys):
    chk = _load()
    s = Store(store_root)
    s.add("AAPL")
    root = s.save()
    assert chk.main(["--root", str(root)]) == 1
    assert "no SPY calendar" in capsys.readouterr().out
