"""Checks that only make sense once every Part 3 task has landed."""
import pathlib
import re

from swingbot.core.db import events, notify

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_the_four_flag_files_have_exactly_one_owner_module():
    """Every .flag path constant lives in one of the two runstate modules.
    A third module building its own path is a flag nothing stage-branches."""
    hits = []
    for path in (REPO / "swingbot").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if ".flag" in text:
            hits.append(path.relative_to(REPO).as_posix())
    allowed = {
        "swingbot/core/scanning/runstate.py",
        "swingbot/commands/scanning/runstate.py",
        "swingbot/admin/events/watcher.py",   # deleted in Part 6
    }
    assert set(hits) <= allowed, f"unexpected .flag references: {sorted(set(hits) - allowed)}"


def test_every_channel_has_at_least_one_table_or_a_stated_reason():
    raised = set(events.TABLE_CHANNELS.values())
    # `analytics` arrives with Part 5's snapshot table.
    unraised = set(notify.CHANNELS) - raised - {"analytics"}
    assert not unraised, f"channels nothing raises: {sorted(unraised)}"


def test_the_committed_env_example_promotes_no_store():
    """Exit criterion 7: DB_STORES is empty in every committed file. A
    promotion is a per-deployment setting, never a committed default."""
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    lines = re.findall(r"^DB_STORES=(.*)$", text, flags=re.MULTILINE)
    assert lines, ".env.example has no DB_STORES= line"
    assert all(value.strip() == "" for value in lines), (
        f".env.example promotes a store: DB_STORES={lines}"
    )
