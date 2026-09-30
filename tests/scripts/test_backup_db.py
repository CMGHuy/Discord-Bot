"""The backup script's shape. It cannot be executed in CI, so what is
asserted is the properties a broken edit would remove."""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "backup_db.sh"


@pytest.fixture(scope="module")
def source():
    assert SCRIPT.exists(), "scripts/ops/backup_db.sh is missing"
    return SCRIPT.read_text(encoding="utf-8")


def test_it_fails_fast(source):
    """A dump script that continues after a failed pg_dump writes a truncated
    file over a good one and reports success."""
    assert re.search(r"^set -euo pipefail", source, re.M)


def test_it_dumps_with_a_timestamped_name(source):
    assert "pg_dump" in source
    assert "%Y" in source or "date " in source


def test_it_writes_into_the_backups_directory(source):
    assert "data/backups/db" in source


def test_it_prunes_by_age_not_by_count(source):
    """90 DAYS (v116: day-level restores beyond the 30-day PITR window), not
    90 files: a day with three manual dumps must not evict older nightly ones."""
    assert "-mtime +90" in source


def test_it_verifies_the_dump_is_non_empty_before_pruning(source):
    """Prune-then-dump, or prune without checking, is how a bad night deletes
    the last good backup."""
    dump_at = source.index("pg_dump")
    prune_at = source.rindex("-mtime") if "-mtime" in source else len(source)
    assert dump_at < prune_at, "pruning must come after a verified dump"
    assert "-s " in source or "wc -c" in source or "test -s" in source
    assert source.index("-s ") < prune_at


def test_it_uses_lf_line_endings():
    assert b"\r" not in SCRIPT.read_bytes()


def test_the_makefile_exposes_it():
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "backup-db:" in makefile
    phony = next(l for l in makefile.splitlines() if l.startswith(".PHONY"))
    assert "backup-db" in phony


def test_the_deploy_doc_carries_the_cron_line():
    doc = (REPO / "docs" / "deploy" / "DEPLOY_HETZNER.md").read_text(
        encoding="utf-8")
    assert ("0 3 * * *  cd /opt/swing-bot && ./scripts/ops/backup_db.sh"
            " >> logs/backup.log 2>&1") in doc
    assert "Nightly backups do not exist yet" not in doc
