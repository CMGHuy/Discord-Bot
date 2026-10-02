import hashlib
import json

import pytest

from swingbot.core.marketdata import universe
from swingbot.core.marketdata.universe import short_snapshot

ROWS = [{"symbol": "AAA", "name": "A", "sector": "Tech", "etf": False},
        {"symbol": "BBB", "name": "B", "sector": "Energy", "etf": False}]


@pytest.fixture
def udir(tmp_path, monkeypatch):
    monkeypatch.setattr(universe, "UNIVERSE_DIR", str(tmp_path))
    return tmp_path


def _write_hist(udir, sector_rows=True):
    (udir / "sp500_membership.csv").write_text(
        "ticker,start_date,end_date\nAAA,2020-01-01,2024-01-03\nBBB,2024-01-03,\n")
    if sector_rows:
        (udir / "sp500_sector_history.csv").write_text(
            "ticker,start_date,end_date,sector\n"
            "AAA,2020-01-01,2024-01-03,Tech\n"
            "BBB,2024-01-03,,Energy\n"
            "CCC,2020-01-01,2024-01-03,Old\nCCC,2024-01-03,,New\n")


def _write_live(udir, as_of, source="manual_csv", sha=None):
    p = udir / "sp500.json"
    p.write_text(json.dumps(ROWS))
    sha = sha or hashlib.sha256(p.read_bytes()).hexdigest()
    (udir / "sp500.snapshot.json").write_text(json.dumps(
        {"as_of": as_of, "source": source, "raw_sha256": "x", "universe_sha256": sha}))


def test_historical_membership_is_half_open(udir):
    _write_hist(udir)
    before = short_snapshot("2024-01-02", live=False)
    after = short_snapshot("2024-01-03", live=False)
    assert "AAA" in before.symbols and "AAA" not in after.symbols
    assert "BBB" not in before.symbols and "BBB" in after.symbols
    assert short_snapshot("2024-01-03", live=True) is None


def test_missing_membership_returns_none(udir):
    assert short_snapshot("2024-01-02", live=False) is None


def test_sector_switches_at_interval_boundary_and_omits_unknown(udir):
    (udir / "sp500_membership.csv").write_text(
        "ticker,start_date,end_date\nCCC,2020-01-01,\nDDD,2020-01-01,\n")
    (udir / "sp500_sector_history.csv").write_text(
        "ticker,start_date,end_date,sector\n"
        "CCC,2020-01-01,2024-01-03,Old\nCCC,2024-01-03,,New\n")
    assert short_snapshot("2024-01-02", live=False).sector_of == {"CCC": "Old"}
    snap = short_snapshot("2024-01-03", live=False)
    assert snap.sector_of == {"CCC": "New"} and "DDD" in snap.symbols


def test_missing_sector_history_returns_none(udir):
    _write_hist(udir, sector_rows=False)
    assert short_snapshot("2024-01-02", live=False) is None


def test_live_fresh_snapshot(udir):
    _write_live(udir, "2024-01-02")
    snap = short_snapshot("2024-01-03", live=True)
    assert snap.symbols == ("AAA", "BBB") and snap.membership_asof == "2024-01-02"
    assert snap.sector_of == {"AAA": "Tech", "BBB": "Energy"}


def test_live_missing_stale_future_or_tampered_returns_none(udir):
    assert short_snapshot("2024-01-03", live=True) is None
    _write_live(udir, "2023-12-01")
    assert short_snapshot("2024-01-03", live=True) is None  # stale
    _write_live(udir, "2024-01-05")
    assert short_snapshot("2024-01-03", live=True) is None  # as_of after day
    _write_live(udir, "2024-01-02", source="guess")
    assert short_snapshot("2024-01-03", live=True) is None
    _write_live(udir, "2024-01-02", sha="0" * 64)
    assert short_snapshot("2024-01-03", live=True) is None  # overwritten file


def test_live_age_counts_sessions_not_calendar_days(udir):
    # 2024-01-02 -> 2024-01-09 is 5 sessions (calendar gap 7): fresh; 01-10 is 6: stale
    _write_live(udir, "2024-01-02")
    assert short_snapshot("2024-01-09", live=True) is not None
    assert short_snapshot("2024-01-10", live=True) is None


def test_legacy_load_unchanged(udir):
    _write_live(udir, "2023-12-01")
    assert [r["symbol"] for r in universe.load("sp500")] == ["AAA", "BBB"]
    assert set(universe.load("sp500")[0]) == {"symbol", "name", "sector", "etf"}


def test_build_universe_as_of_writes_validating_snapshot(udir, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_universe", "scripts/data/build_universe.py")
    bu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bu)
    monkeypatch.setattr(bu, "UNIVERSE_DIR", str(udir))
    raw = udir / "raw.csv"
    raw.write_text("Symbol,Name,Sector\nAAA,A,Tech\nBBB,B,Energy\n")
    bu.build(str(raw), None, "2024-01-02")
    snap = short_snapshot("2024-01-03", live=True)
    assert snap.symbols == ("AAA", "BBB") and snap.membership_asof == "2024-01-02"
    bu.build(str(raw), None)  # no --as-of: legacy output only
    assert short_snapshot("2024-01-03", live=True) is not None  # old meta still matches bytes
