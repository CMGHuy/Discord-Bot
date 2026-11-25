"""v245 V245-15: the shadow soak verdict from scan telemetry."""
import json
from datetime import date, datetime, timezone

import pytest

from scripts.perf import analysis_cache_soak_report as soak

DEPLOY = {"type": "deploy", "component": "bot", "sha": "abc", "at": "2026-11-23T12:00:00Z"}
# Mon 2026-11-23 .. Mon 2026-11-30, without Thu 2026-11-26 (Thanksgiving, closed).
WEEK = ["2026-11-23", "2026-11-24", "2026-11-25", "2026-11-27", "2026-11-30"]


@pytest.fixture(autouse=True)
def holidays(monkeypatch):
    monkeypatch.setattr(soak, "_HOLIDAYS", frozenset({date(2026, 11, 26)}))


def _row(at, compared=31, diffs=0, mode="shadow"):
    return {"at": at, "duration_s": 300.0, "tickers": 92, "phases_s": {"analysis": 60.0},
            "cache_mode": mode, "cache_compared": compared if mode == "shadow" else None,
            "cache_diffs": diffs if mode == "shadow" else None}


def _days(dates, **kw):
    return [{"date": d, "scans": 70, "compared": 2170, "diffs": 0, **kw} for d in dates]


def test_soak_days_groups_shadow_rows_by_new_york_date():
    rows = [DEPLOY,
            _row("2026-11-24T15:00:00+00:00"),
            _row("2026-11-25T03:00:00+00:00", compared=30, diffs=1),   # 22:00 New York, Nov 24
            _row("2026-11-25T15:00:00+00:00", compared=0),
            _row("2026-11-25T15:05:00+00:00", mode="on"),
            _row("2026-11-25T15:10:00+00:00", mode="off"),
            {**_row("2026-11-25T15:15:00+00:00"), "cache_compared": None}]
    assert soak.soak_days(rows) == [
        {"date": "2026-11-24", "scans": 2, "compared": 61, "diffs": 1},
        {"date": "2026-11-25", "scans": 1, "compared": 0, "diffs": 0}]
    assert soak.soak_days([]) == []


def test_trading_day_skips_weekends_and_holidays():
    assert soak.trading_day("2026-11-25")
    assert not soak.trading_day("2026-11-26")      # the patched holiday
    assert not soak.trading_day("2026-11-28")      # Saturday


def test_counted_days_need_a_compared_ticker_on_a_trading_day():
    days = _days(["2026-11-24", "2026-11-25"]) + _days(["2026-11-26", "2026-11-28"]) \
        + _days(["2026-11-27"], compared=0)
    assert soak.counted_days(days) == ["2026-11-24", "2026-11-25"]
    assert soak.counted_days(days, session_open="2026-11-25") == ["2026-11-24"]


@pytest.mark.parametrize("days, today, expect", [
    (_days(WEEK), None, "PASS"),
    (_days(WEEK[:4]), None, "WAIT"),
    (_days(WEEK), "2026-11-30", "WAIT"),                       # today's session is not over
    (_days(WEEK[:4]) + _days(["2026-11-28"]), None, "WAIT"),   # a Saturday never counts
    (_days(WEEK[:4]) + _days(["2026-11-28"], diffs=1), None, "FAIL"),  # but its diff does
    (_days(WEEK) + _days(["2026-12-01"], diffs=2), None, "FAIL"),
    ([], None, "WAIT"),
])
def test_verdict(days, today, expect):
    assert soak.verdict(days, open_day=today) == expect


def test_verdict_need_is_a_parameter():
    assert soak.verdict(_days(WEEK[:2]), need=2) == "PASS"


@pytest.mark.parametrize("now, expect", [
    (datetime(2026, 11, 25, 18, 0, tzinfo=timezone.utc), "2026-11-25"),   # 13:00 New York
    (datetime(2026, 11, 25, 21, 30, tzinfo=timezone.utc), None),          # 16:30, closed
    (datetime(2026, 11, 28, 18, 0, tzinfo=timezone.utc), None),           # Saturday
    (datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc), None),           # holiday
])
def test_open_day(now, expect):
    assert soak.open_day(now) == expect


def _write(path, rows, bad=False):
    lines = [json.dumps(r) for r in rows] + (["{not json"] if bad else [])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_main_since_deploy_restarts_the_count(tmp_path, capsys):
    path = tmp_path / "scan_telemetry.jsonl"
    before = _row("2026-11-20T15:00:00+00:00", diffs=3)          # a diff before the fix's deploy
    rows = [before, DEPLOY] + [_row(f"{d}T15:00:00+00:00") for d in WEEK]
    _write(path, rows, bad=True)
    argv = ["--path", str(path), "--since-deploy", "--now", "2026-11-30T22:00:00+00:00"]
    assert soak.main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "PASS" and out["counted"] == WEEK
    assert out["since"] == DEPLOY["at"] and out["bad_lines"] == 1 and out["need"] == 5
    assert soak.main(["--path", str(path), "--now", "2026-11-30T22:00:00+00:00"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "FAIL"


def test_main_excludes_the_open_session(tmp_path, capsys):
    path = tmp_path / "scan_telemetry.jsonl"
    _write(path, [_row(f"{d}T15:00:00+00:00") for d in WEEK])
    assert soak.main(["--path", str(path), "--now", "2026-11-30T18:00:00+00:00"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["open_day"] == "2026-11-30" and out["verdict"] == "WAIT"


def test_main_missing_file(tmp_path):
    assert soak.main(["--path", str(tmp_path / "absent.jsonl")]) == 1
