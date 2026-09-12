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
