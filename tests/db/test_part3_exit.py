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


def test_the_committed_env_example_mirrors_the_all_db_production_value():
    """Exit criterion 7 used to say DB_STORES is empty in every committed file.
    Since the 2026-10-01 cutover (v116) production runs every store at db and
    .env.example mirrors it: no store may be left at json or dual, and `events`
    is on. A partial list would silently put the missing stores back on json."""
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    lines = re.findall(r"^DB_STORES=(.*)$", text, flags=re.MULTILINE)
    assert len(lines) == 1, ".env.example needs exactly one DB_STORES= line"
    pairs = [item.split(":") for item in lines[0].strip().split(",") if item]
    assert pairs and all(stage == "db" for _, stage in pairs), (
        f".env.example leaves a store off db: DB_STORES={lines[0]}"
    )
    assert "events" in {name for name, _ in pairs}
