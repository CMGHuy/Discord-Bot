"""The restore script's safety properties."""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "restore_db.sh"


@pytest.fixture(scope="module")
def source():
    assert SCRIPT.exists(), "scripts/ops/restore_db.sh is missing"
    return SCRIPT.read_text(encoding="utf-8")


def test_it_fails_fast(source):
    assert re.search(r"^set -euo pipefail", source, re.M)


def test_the_target_database_has_no_default(source):
    """A restore whose default target is production eventually restores over
    production."""
    assert "usage" in source.lower()
    assert re.search(r'\$\{?2', source), "no second positional argument"
    assert "swingbot}" not in source, "the target must not default to swingbot"


def test_it_refuses_the_production_database_without_an_explicit_flag(source):
    assert "--i-mean-it" in source or "FORCE" in source


def test_it_verifies_the_dump_exists_before_touching_anything(source):
    dump_check = source.index("-f ") if "-f " in source else source.index("-s ")
    psql_at = source.index("psql")
    assert dump_check < psql_at


def test_it_uses_lf_line_endings():
    assert b"\r" not in SCRIPT.read_bytes()
