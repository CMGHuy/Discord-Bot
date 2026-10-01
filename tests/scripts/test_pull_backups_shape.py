"""pull_backups.sh's step order and safety rules (v120 section 2). It needs the
VM, so this pins what an edit could silently break."""
import pathlib
import re

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ops" / "pull_backups.sh"


@pytest.fixture(scope="module")
def src():
    return SCRIPT.read_text(encoding="utf-8")


def test_house_rules(src):
    assert src.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in src
    assert "sed -i" not in src
    assert b"\r" not in SCRIPT.read_bytes()


def test_only_the_wrapper_reaches_the_vm(src):
    assert 'SSH_HETZNER="${SSH_HETZNER:-' in src
    assert 'bash "$SSH_HETZNER"' in src
    assert not re.search(r"(^|[\s;|&(])(ssh|scp)\s", src, re.M)
    assert "bash -s" in src


def test_remote_args_are_plain_not_inline_substitutions(src):
    assert "bash -s -- " in src
    for line in src.splitlines():
        if "bash -s" in line and "SSH_HETZNER" in line:
            assert "$(" not in line, line


def test_outbox_cleanup_runs_from_a_trap(src):
    assert re.search(r"trap\s+\S+\s+EXIT", src)
    body = src[src.index("cleanup_outbox() {"):]
    body = body[:body.index("\n}")]
    assert "clean" in body
    assert re.search(r'rm -rf "?backups/outbox/', src)


def test_verify_precedes_extraction_and_the_good_pull_write(src):
    verify = src.index("backup_manifest.py verify backups/pulls/")
    assert verify < src.index("xf backups/pulls/$STAMP/market_data.tar")
    assert verify < src.index("> backups/LAST_GOOD_PULL")


def test_fail_branch_writes_last_pull_but_never_last_good(src):
    start = src.index("FAILED")
    block = src[start - 200:src.index("exit 1", start)]
    assert "LAST_PULL" in block
    assert "LAST_GOOD_PULL" not in block


def test_prune_comes_after_the_good_pull_write(src):
    assert src.index("> backups/LAST_GOOD_PULL") < src.index("backup_manifest.py prune backups --keep 10")


def test_no_rm_touches_the_mirror_or_stable_folders(src):
    rm_lines = [ln for ln in src.splitlines() if re.search(r"\brm\b", ln) and not ln.lstrip().startswith("#")]
    assert rm_lines
    for ln in rm_lines:
        assert "backups/market_data" not in ln, ln
        assert "backups/stable" not in ln, ln


def test_market_data_tar_is_kept_for_later_verify(src):
    assert not re.search(r"\brm\b[^\n]*market_data\.tar", src)


def test_stable_mode_refuses_existing_and_writes_no_last_files(src):
    stable = src[src.index("pull_stable() {"):]
    stable = stable[:stable.index("\n}")]
    assert "refusing" in stable
    assert "LAST_" not in stable
    assert "mv " in stable and ".partial" in stable
    assert stable.index("backup_manifest.py verify") < stable.index("mv ")


def test_row_counts_come_from_the_dump(src):
    assert "count-dump" in src
    assert "--row-counts" in src
    assert "SHOW server_version" in src
