"""Shapes later Part 3 tasks depend on."""
import pytest
from swingbot.core.db import schema

PART3_TABLES = ("runtime_flags", "bot_heartbeat", "admin_jobs", "scheduled_jobs",
                "ui_preferences", "settings_audit", "killswitch", "manual_close_notify",
                "ticker_directory", "tuning_results", "tuning_proposals")

@pytest.mark.parametrize("name", PART3_TABLES)
def test_table_exists_and_is_registered(name):
    assert name in schema.METADATA.tables
    assert name in schema.PROMOTED

def test_manual_close_notify_is_not_keyed_store():
    assert "queued_at" in schema.manual_close_notify.c
    assert not schema.manual_close_notify.c.queued_at.unique
