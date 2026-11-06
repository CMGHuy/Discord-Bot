import json

from swingbot import config
from swingbot.admin import release_windows as windows


def test_windows_close_only_at_the_next_version_of_the_same_component(monkeypatch):
    monkeypatch.setattr(windows, "read_markers", lambda: [
        {"component": "bot", "bot": "1.7.1", "at": "2026-09-01T00:00:00Z"},
        {"component": "admin", "ui": "1.17.0", "at": "2026-09-03T00:00:00Z"},
        {"component": "bot", "bot": "1.7.2", "at": "2026-09-05T00:00:00Z"},
    ])
    rows = [row for row in windows.windows() if row["component"] == "bot"]
    assert [row["version"] for row in rows] == ["1.7.2", "1.7.1"]
    assert rows[-1]["to"] == "2026-09-05T00:00:00Z"


def test_same_version_restart_does_not_split_a_window(monkeypatch):
    monkeypatch.setattr(windows, "read_markers", lambda: [
        {"component": "bot", "bot": "1.7.2", "at": "2026-09-05T00:00:00Z"},
        {"component": "bot", "bot": "1.7.2", "at": "2026-09-06T00:00:00Z"},
    ])
    assert len(windows.windows()) == 1


def test_scan_telemetry_is_scoped_to_the_window(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    (tmp_path / "scan_telemetry.jsonl").write_text("\n".join(json.dumps(row) for row in [
        {"at": "2026-09-02T00:00:00Z", "duration_s": 100},
        {"at": "2026-09-06T00:00:00Z", "duration_s": 40},
        {"at": "2026-09-07T00:00:00Z", "duration_s": 60},
    ]), encoding="utf-8")
    telemetry = windows.telemetry_for({"from": "2026-09-05T00:00:00Z", "to": None})
    assert telemetry["median_scan_sec"] == 50.0
    assert telemetry["n_days"] == 2
    assert telemetry["error_rate"] is None


def _write_rows(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_window_bounds_are_from_inclusive_to_exclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    _write_rows(tmp_path / "scan_telemetry.jsonl", [
        {"at": "2026-09-05T00:00:00Z", "duration_s": 10},
        {"at": "2026-09-06T00:00:00Z", "duration_s": 20},
        {"at": "2026-09-07T00:00:00Z", "duration_s": 99},
        {"type": "deploy", "at": "2026-09-06T12:00:00Z", "duration_s": 500},
        {"duration_s": 7},
        {"at": 12345, "duration_s": 7},
    ])
    telemetry = windows.telemetry_for({"from": "2026-09-05T00:00:00Z", "to": "2026-09-07T00:00:00Z"})
    assert telemetry["median_scan_sec"] == 15.0
    assert telemetry["n_days"] == 2


def test_empty_or_missing_telemetry_gives_nulls(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    window = {"from": "2026-09-05T00:00:00Z", "to": None}
    assert windows.telemetry_for(window)["median_scan_sec"] is None
    (tmp_path / "scan_telemetry.jsonl").write_text("", encoding="utf-8")
    assert windows.telemetry_for(window) == {
        "uptime_pct": None, "error_rate": None, "median_scan_sec": None, "n_days": 0}


def test_scan_file_is_parsed_once_until_it_changes(tmp_path, monkeypatch):
    """/versions asks once per release (~180): the 6 MB file must not be re-parsed each time."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    path = tmp_path / "scan_telemetry.jsonl"
    _write_rows(path, [{"at": "2026-09-06T00:00:00Z", "duration_s": 40}])
    calls = []
    real_loads = windows.json.loads
    monkeypatch.setattr(windows.json, "loads", lambda line: calls.append(1) or real_loads(line))
    window = {"from": "2026-09-05T00:00:00Z", "to": None}
    for _ in range(50):
        assert windows.telemetry_for(window)["median_scan_sec"] == 40.0
    assert len(calls) == 1

    _write_rows(path, [{"at": "2026-09-06T00:00:00Z", "duration_s": 40},
                       {"at": "2026-09-08T00:00:00Z", "duration_s": 60}])
    assert windows.telemetry_for(window)["median_scan_sec"] == 50.0
