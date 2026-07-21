"""Settings v2: diff preview, audit trail, export/import profiles,
changed-only filter + resets."""


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
