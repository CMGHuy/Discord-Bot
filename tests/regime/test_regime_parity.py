"""v239 V239-16: live-vs-replay parity (spec § Parity) on the committed export."""
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.reports import regime_parity as rp
from swingbot.core.market import bear_regime as br

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "regime"
EXPORT = FIXTURES / "market_regime_days_export.json"
REPLAY = FIXTURES / "spy_vix_replay.csv"


@pytest.fixture(scope="module")
def frames():
    raw = pd.read_csv(REPLAY, parse_dates=["Date"], index_col="Date")
    spy = raw.rename(columns={"spy_high": "High", "spy_close": "Close"})[["High", "Close"]]
    vix = raw[["vix_close"]].rename(columns={"vix_close": "Close"}).dropna()
    return spy, vix


@pytest.fixture
def stored():
    return json.loads(EXPORT.read_text(encoding="utf-8"))


def _pick(stored, **want):
    """The first non-boundary row whose fields equal ``want``."""
    for row in stored:
        if not rp.boundary_day(br.RegimeDay.from_row(row)) and all(
                row[k] == v for k, v in want.items()):
            return row
    raise AssertionError(f"the export has no non-boundary row with {want}")


def test_export_fixture_is_a_table_export(stored):
    assert set(br.ROW_COLUMNS) | {"doc", "computed_at"} <= set(stored[0])
    assert (stored[0]["session_date"], stored[-1]["session_date"]) == ("2026-10-15", "2026-11-23")


def test_the_export_replays_clean(stored, frames):
    result = rp.compare(stored, *frames)
    assert (result.matches, result.boundary, result.failures, result.uncovered) == (
        len(stored), [], [], [])


def test_a_non_boundary_state_mismatch_fails_and_names_both_closes(stored, frames):
    row = dict(_pick(stored, state="CORRECTION"), state="NORMAL")
    result = rp.compare([row], *frames)
    assert result.matches == 0 and result.boundary == []
    (failure,) = result.failures
    assert failure["session_date"] == row["session_date"]
    assert (failure["stored"], failure["replayed"]) == ("NORMAL", "CORRECTION")
    assert failure["stored_spy_close"] == row["spy_close"]
    assert failure["replayed_spy_close"] == pytest.approx(row["spy_close"])
    assert (failure["spy_provider"], failure["last_bar_date"]) == ("alpaca", row["last_bar_date"])


def test_a_stress_mismatch_fails(stored, frames):
    row = dict(_pick(stored, stress=True), stress=False)
    assert len(rp.compare([row], *frames).failures) == 1


def test_a_missing_stress_on_one_side_is_not_compared(stored, frames):
    row = dict(_pick(stored, stress=True), stress=None)
    assert rp.compare([row], *frames).matches == 1


def test_a_boundary_mismatch_is_reported_not_failed(stored, frames, monkeypatch):
    row = dict(stored[-1], state="BEAR" if stored[-1]["state"] != "BEAR" else "NORMAL")
    monkeypatch.setattr(rp, "boundary_day", lambda day: True)
    result = rp.compare([row], *frames)
    assert (result.matches, len(result.boundary), result.failures) == (0, 1, [])


def test_rows_the_cache_cannot_replay_are_uncovered(stored, frames):
    late = dict(stored[-1], session_date="2026-11-25", last_bar_date="2026-11-24")
    blank = dict(stored[-1], last_bar_date=None)
    result = rp.compare([late, blank], *frames)
    assert (result.matches, result.failures, len(result.uncovered)) == (0, [], 2)


@pytest.mark.parametrize("fields, boundary", [
    (dict(spy_close=100.05, sma200=100.0), True),          # C within 0.1% of SMA200
    (dict(spy_close=100.2, sma50=100.1), True),            # C within 0.1% of SMA50
    (dict(sma200=100.0, sma200_lag20=99.95), True),        # slow slope flat
    (dict(sma50=100.0, sma50_lag5=100.05), True),          # fast slope flat
    (dict(sma50=100.0, sma200=100.09), True),              # SMA50 at SMA200
    (dict(vix_close=25.02), True),                         # V within 0.1% of 25
    (dict(vix_close=25.03), False),
])
def test_boundary_day(fields, boundary):
    far = dict(spy_close=90.0, sma50=120.0, sma50_lag5=110.0, sma200=150.0,
               sma200_lag20=140.0, vix_close=15.0)
    day = br.RegimeDay(session_date=None, last_bar_date=None, state="NORMAL", **{**far, **fields})
    assert rp.boundary_day(day) is boundary


def test_an_unknown_day_is_never_a_boundary_day():
    assert rp.boundary_day(br.RegimeDay(None, None, br.UNKNOWN)) is False


def _cache(tmp_path, frames):
    spy, vix = frames
    spy.rename_axis("Date").to_csv(tmp_path / "SPY.csv", lineterminator="\n")
    vix.rename_axis("Date").to_csv(tmp_path / "^VIX.csv", lineterminator="\n")
    return tmp_path


def test_main_clean_run(tmp_path, frames, capsys):
    assert rp.main(["--rows", str(EXPORT), "--cache-dir", str(_cache(tmp_path, frames))]) == 0
    assert "parity: 28 match · 0 boundary · 0 fail · 0 uncovered" in capsys.readouterr().out


def test_main_fails_on_a_mismatch_and_prints_the_inputs(tmp_path, frames, stored, capsys):
    row = dict(_pick(stored, state="CORRECTION"), state="NORMAL")
    rows = tmp_path / "rows.json"
    rows.write_text(json.dumps([row]), encoding="utf-8")
    assert rp.main(["--rows", str(rows), "--cache-dir", str(_cache(tmp_path, frames))]) == 1
    out = capsys.readouterr().out
    assert f"FAIL {row['session_date']}" in out and "spy_provider=alpaca" in out


def test_main_export_writes_the_rows_and_stops(tmp_path, monkeypatch):
    rows = [{"session_date": "2026-11-23", "state": "CORRECTION"}]
    monkeypatch.setattr(rp, "_stored_rows", lambda args: rows)
    out = tmp_path / "export.json"
    assert rp.main(["--export", str(out), "--cache-dir", str(tmp_path / "none")]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == rows
    assert b"\r\n" not in out.read_bytes()


def test_main_cannot_run_without_the_cache(tmp_path):
    assert rp.main(["--rows", str(EXPORT), "--cache-dir", str(tmp_path / "none")]) == 2
