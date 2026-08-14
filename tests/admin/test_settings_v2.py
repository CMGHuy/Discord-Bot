"""Settings v2: diff preview, audit trail, export/import profiles,
changed-only filter + resets.

NG19 TRIAGE — **MIXED · split at cutover.**

KEEP UNCHANGED: the four helper-level tests calling `settings_diff` and
`import_env_text` directly (masking, changed-only, known-vs-unknown keys).
Those functions are what /api/v1/system/settings routes through rather than
reimplements -- NG15 adapts JSON to their mapping shape precisely so there is
one definition of "blank means no change".

DELETE: the route and page-render tests (`..._route_renders_diff_table`,
`..._page_shows_recent_changes_panel`, `..._page_has_changed_only_toggle...`).
Their behavioural content is in test_api_v1_system_settings.py, which pins
more than these do -- masked values never being written back, omitted keys
left alone, and a checkbox not being turned off by its own absence."""
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


def test_import_env_text_applies_known_skips_unknown(admin_app):
    # admin_app is required (unused directly) -- it monkeypatches
    # config.DATA_DIR/ENV_PATH and reloads helpers.py so import_env_text
    # writes to an isolated tmp .env, not the real project .env. See
    # conftest.py's admin_app docstring: without this fixture, Settings
    # tests (C38-C41) that save/export/import would write the real file.
    from swingbot.admin.helpers import import_env_text
    applied, unknown = import_env_text("SCAN_INTERVAL_MINUTES=7\nBOGUS=1")
    assert applied == 1
    assert unknown == ["BOGUS"]


