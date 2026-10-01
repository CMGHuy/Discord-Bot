"""stable_snapshot.sh's step order (v120 section 1). It runs on the VM only, so
this pins the order and the flags an edit could break."""
import pathlib

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ops" / "stable_snapshot.sh"


@pytest.fixture(scope="module")
def src():
    return SCRIPT.read_text(encoding="utf-8")


def test_house_rules(src):
    assert src.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in src
    assert "sed -i" not in src
    assert b"\r" not in SCRIPT.read_bytes()


def test_name_is_validated_and_an_existing_folder_refused_before_the_dump(src):
    assert "^stable-[0-9]{4}-[0-9]{2}-[0-9]{2}(-[0-9]+)?$" in src
    refuse = src.index('-e "backups/stable/$NAME"')
    assert refuse < src.index("./scripts/ops/backup_db.sh")
    assert "exit 2" in src


def test_builds_in_a_partial_folder_that_a_trap_removes(src):
    assert ".partial" in src
    trap = src.index("trap ")
    assert "rm -rf" in src[trap:src.index("\n", trap)]


def test_env_copy_is_private(src):
    assert 'install -m 600 .env "$DIR.partial/env"' in src


def test_restic_call_carries_all_three_tags(src):
    assert "--tag market_data --tag stable --tag \"$NAME\"" in src
    assert "--json" in src and "env_set.py --get RESTIC_PASSWORD" in src


def test_build_then_verify_then_the_final_move(src):
    build = src.index("backup_manifest.py build")
    verify = src.index("backup_manifest.py verify")
    move = src.index('mv "$DIR.partial" "$DIR"')
    assert build < verify < move


def test_exact_row_counts_and_log(src):
    assert "count(*)" in src and "information_schema.tables" in src
    assert "logs/stable_snapshot.log" in src
