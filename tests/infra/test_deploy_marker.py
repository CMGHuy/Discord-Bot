import json

from swingbot import config
from swingbot.core.infra import deploy_marker as marker


def test_boot_markers_append_to_the_existing_telemetry_stream(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    marker.record_boot("bot")
    marker.record_boot("admin")
    assert [row["component"] for row in marker.read_markers()] == ["bot", "admin"]


def test_marker_has_versions_and_unrelated_rows_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    path = tmp_path / "scan_telemetry.jsonl"
    path.write_text(json.dumps({"duration_s": 4}) + "\n{broken\n", encoding="utf-8")
    marker.record_boot("bot")
    row = marker.read_markers()[0]
    assert row["ui"] and row["bot"]
    assert row["at"].endswith("Z")


def test_write_failure_never_blocks_startup(monkeypatch):
    monkeypatch.setattr(marker, "_append", lambda _row: (_ for _ in ()).throw(OSError("read-only")))
    marker.record_boot("bot")
