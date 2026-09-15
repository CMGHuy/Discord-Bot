"""Unit tests for safe LISTEN/NOTIFY DDL generation."""
import pytest

from swingbot.core.db import notify


def test_channels_match_the_existing_watcher_concerns():
    assert notify.CHANNELS == (
        "trades", "account", "analytics", "scan", "journal", "bot", "risk", "watchlist", "jobs",
    )


def test_trigger_ddl_names_the_table_channel_and_statement_scope():
    sql = notify.trigger_ddl("trades", "trades")
    assert "AFTER INSERT OR UPDATE OR DELETE ON trades" in sql
    assert "FOR EACH STATEMENT" in sql
    assert "swingbot_notify('trades')" in sql
    assert notify.trigger_name("trades") in sql


def test_trigger_ddl_rejects_unknown_channels():
    with pytest.raises(ValueError, match="not a known channel"):
        notify.trigger_ddl("trades", "made_up")


@pytest.mark.parametrize("bad", ["tra des", "trades; drop table x", "'x'", "UPPER"])
def test_ddl_helpers_reject_nonidentifiers(bad):
    with pytest.raises(ValueError, match="identifier"):
        notify.trigger_ddl(bad, "trades")
    with pytest.raises(ValueError, match="identifier"):
        notify.drop_trigger_ddl(bad)
