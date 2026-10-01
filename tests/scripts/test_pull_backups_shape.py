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


def _func(src, name):
    body = src[src.index(name + "() {"):]
    return body[:body.index(chr(10) + "}")]


def test_verify_fail_branch_marks_failed_without_touching_the_good_pull(src):
    branch = src[src.index("if ! python scripts/ops/backup_manifest.py verify backups/pulls/"):]
    branch = branch[:branch.index("exit 1")]
    assert "mark_pull_failed" in branch
    assert "market_data.tar" not in branch
    assert "LAST_GOOD_PULL" not in branch


def test_mark_pull_failed_writes_last_pull_before_the_rename(src):
    body = _func(src, "mark_pull_failed")
    assert body.index("> \"$B/LAST_PULL\"") < body.index("mv ")
    assert "FAIL pulls/$STAMP.FAILED" in body
    assert "LAST_GOOD_PULL" not in body


def test_exit_trap_marks_an_unfinished_pull_failed(src):
    body = _func(src, "cleanup_outbox")
    assert body.index("remote clean") < body.index("mark_pull_failed")
    assert "PULL_OK" in body
    assert "-d" in body
    assert "LAST_GOOD_PULL" not in body
    assert 'exit "$rc"' in body


def test_pull_ok_is_set_only_after_the_good_pull_write(src):
    assert src.index("> backups/LAST_GOOD_PULL") < src.index("PULL_OK=1")


def test_tar_exit_one_is_tolerated_and_others_are_not(src):
    assert "|| tar_rc=$?" in src
    assert re.search(r'\[ "\$tar_rc" -le 1 \]', src)
    assert "tolerated" in src


def test_empty_argument_guards_on_destructive_remote_modes(src):
    for mode in ("stream)", "clean)", "stream-stable)"):
        block = src[src.index("  " + mode):]
        block = block[:block.index(";;")]
        assert '[ -n "$ARG" ] || exit 2' in block, mode


def test_stage_calls_do_not_read_the_script_from_stdin(src):
    assert "./scripts/ops/backup_db.sh)\"" not in src
    assert "backup_db.sh </dev/null" in src
    assert "docker compose exec -T db psql" in src
    assert re.search(r"SHOW server_version'[^\n]*</dev/null", src)


def test_partial_hint_names_the_manual_cleanup(src):
    assert src.count("delete the .partial by hand") >= 2


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


def _bash():
    import shutil
    return shutil.which("bash")


@pytest.mark.skipif(_bash() is None, reason="needs bash")
def test_failed_stream_is_recorded_as_a_failed_pull(tmp_path):
    """Fake VM wrapper: stage succeeds, stream sends half a tar then fails."""
    import subprocess
    root = tmp_path / "repo"
    (root / "scripts" / "ops").mkdir(parents=True)
    for n in ("pull_backups.sh", "backup_manifest.py"):
        (root / "scripts" / "ops" / n).write_bytes((SCRIPT.parent / n).read_bytes())
    shim = tmp_path / "shim.sh"
    shim_lines = [
        "cat >/dev/null",
        'case "$1" in',
        # $1 is "bash -s -- stream <STAMP> <SINCE>": the 5th word is the stamp.
        '  *"stream "*) set -- $1; d="$(mktemp -d)"; mkdir "$d/$5"; echo hi > "$d/$5/f"; '
        'tar czf - -C "$d" "$5" | base64 -w0; exit 1 ;;',
        "  *) exit 0 ;;",
        "esac",
    ]
    shim.write_text(chr(10).join(shim_lines) + chr(10), encoding="utf-8", newline=chr(10))
    env = {**__import__("os").environ, "SSH_HETZNER": shim.as_posix()}
    r = subprocess.run([_bash(), (root / "scripts/ops/pull_backups.sh").as_posix()],
                       cwd=root, env=env, capture_output=True, text=True)
    assert r.returncode != 0, r.stdout + r.stderr
    last = (root / "backups" / "LAST_PULL").read_text(encoding="utf-8")
    assert " FAIL pulls/" in last and last.strip().endswith(".FAILED")
    assert not (root / "backups" / "LAST_GOOD_PULL").exists()
    names = [p.name for p in (root / "backups" / "pulls").iterdir()]
    assert all(n.endswith(".FAILED") for n in names), names
