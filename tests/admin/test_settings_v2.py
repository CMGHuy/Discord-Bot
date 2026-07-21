"""Settings v2: diff preview, audit trail, export/import profiles,
changed-only filter + resets."""
import json
import os


def test_settings_diff_masks_sensitive_and_includes_only_changed(admin_app):
    from swingbot.admin.helpers import settings_diff
    existing = {"SCAN_INTERVAL_MINUTES": "30", "DISCORD_TOKEN": "real-secret-token"}
    form = {"SCAN_INTERVAL_MINUTES": "45", "DISCORD_TOKEN": "real-secret-token"}  # unchanged
    diff = settings_diff(form, existing)
    assert len(diff) == 1
    assert diff[0]["key"] == "SCAN_INTERVAL_MINUTES"
    assert diff[0]["old"] == "30" and diff[0]["new"] == "45"


def test_settings_diff_masks_changed_sensitive_field(admin_app):
    from swingbot.admin.helpers import settings_diff
    existing = {"DISCORD_TOKEN": "old-secret"}
    form = {"DISCORD_TOKEN": "new-secret"}
    diff = settings_diff(form, existing)
    row = next(d for d in diff if d["key"] == "DISCORD_TOKEN")
    assert row["old"] == "•••" and row["new"] == "•••"
    assert row["sensitive"] is True


def test_settings_preview_route_renders_diff_table(client, auth):
    r = client.post("/settings/preview", data={"SCAN_INTERVAL_MINUTES": "45"}, headers=auth)
    assert r.status_code == 200
    assert b"SCAN_INTERVAL_MINUTES" in r.data


def test_settings_preview_route_no_changes(client, auth):
    from swingbot.admin.helpers import _read_env_values
    existing = _read_env_values()
    r = client.post("/settings/preview", data=existing, headers=auth)
    assert b"Nothing changed" in r.data


def test_settings_save_appends_masked_audit_line(client, auth, admin_app):
    from swingbot import config
    r = client.post("/settings/save", data={"SCAN_INTERVAL_MINUTES": "7"}, headers=auth)
    assert r.status_code == 302
    audit_path = os.path.join(config.DATA_DIR, "settings_audit.jsonl")
    assert os.path.exists(audit_path)
    entry = json.loads(open(audit_path).readlines()[0])
    changed_keys = [c["key"] for c in entry["changes"]]
    assert "SCAN_INTERVAL_MINUTES" in changed_keys


def test_settings_page_shows_recent_changes_panel(client, auth, admin_app):
    from swingbot import config
    audit_path = os.path.join(config.DATA_DIR, "settings_audit.jsonl")
    entry = {"ts": "2026-07-11T00:00:00+00:00",
             "changes": [{"key": "SCAN_INTERVAL_MINUTES", "old": "30", "new": "7"}]}
    with open(audit_path, "w") as f:
        f.write(json.dumps(entry) + "\n")
    r = client.get("/settings", headers=auth)
    html = r.data.decode("utf-8")
    assert "Recent changes" in html
    assert "SCAN_INTERVAL_MINUTES" in html


def test_settings_export_excludes_sensitive_fields_entirely(client, auth):
    r = client.get("/settings/export", headers=auth)
    assert r.status_code == 200
    assert b"DISCORD_TOKEN" not in r.data
    assert b"ADMIN_PASSWORD" not in r.data


def test_import_env_text_applies_known_skips_unknown():
    from swingbot.admin.helpers import import_env_text
    applied, unknown = import_env_text("SCAN_INTERVAL_MINUTES=7\nBOGUS=1")
    assert applied == 1
    assert unknown == ["BOGUS"]


def test_settings_import_route_applies_and_redirects(client, auth, admin_app):
    r = client.post("/settings/import", data={"env_text": "SCAN_INTERVAL_MINUTES=7\nBOGUS=1"}, headers=auth)
    assert r.status_code == 302
    from swingbot.admin.helpers import _read_env_values
    assert _read_env_values()["SCAN_INTERVAL_MINUTES"] == "7"
