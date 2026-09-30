"""Every Part 3 store is either registered for parity or explicitly exempt."""
from scripts.db.parity_report import STORES

REGISTERED = {"jobs", "scheduled_jobs", "preferences", "settings_audit",
              "killswitch", "ticker_directory", "tuning", "tuning_proposals"}

# Exempt, with the reason. An unexplained gap here is how a store gets flipped
# to db on evidence nobody gathered.
EXEMPT = {
    "flags": "existence-only state; nothing to compare across a cutover",
    "heartbeat": "overwritten every scan tick; any snapshot is stale by design",
    "notify_queue": "drained by the bot mid-comparison; a diff would be noise",
}

# Every Part 3 table, mapped to the STORES key or EXEMPT key that answers for it.
TABLE_OWNER = {
    "runtime_flags": "flags", "bot_heartbeat": "heartbeat",
    "manual_close_notify": "notify_queue",
    "admin_jobs": "jobs", "scheduled_jobs": "scheduled_jobs",
    "ui_preferences": "preferences", "settings_audit": "settings_audit",
    "killswitch": "killswitch", "ticker_directory": "ticker_directory",
    "tuning_results": "tuning", "tuning_proposals": "tuning_proposals",
}


def test_every_registered_part3_store_is_present():
    missing = REGISTERED - set(STORES)
    assert not missing, f"no parity registration for: {sorted(missing)}"


def test_no_part3_store_is_silently_unregistered():
    from swingbot.core.db import schema
    assert set(TABLE_OWNER) <= set(schema.METADATA.tables)
    # Every table is answered for by a registration or by a written reason.
    unanswered = {table: owner for table, owner in TABLE_OWNER.items()
                  if owner not in STORES and owner not in EXEMPT}
    assert not unanswered, f"neither registered nor exempt: {unanswered}"


def test_every_exemption_carries_a_reason():
    assert all(reason.strip() for reason in EXEMPT.values())


def test_the_directory_and_jsonl_stores_read_their_path_not_a_parsed_document():
    for name in ("settings_audit", "tuning", "tuning_proposals"):
        assert STORES[name].loader_takes_path, name
