"""stable_snapshot.sh's step order (v120 section 1). It runs on the VM only, so
this pins the order and the flags an edit could break."""
import pathlib

import pytest

BS_N = chr(10)
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
    assert "trap cleanup EXIT" in src
    body = src[src.index("cleanup() {"):src.index("trap cleanup EXIT")]
    assert 'rm -rf "$DIR.partial"' in body


def test_env_copy_is_private(src):
    assert 'install -m 600 .env "$DIR.partial/env"' in src


def test_restic_call_carries_all_three_tags(src):
    assert "--tag market_data --tag stable --tag \"$NAME\"" in src
    assert "--json" in src and "env_set.py --get RESTIC_PASSWORD" in src


def test_build_then_verify_then_the_final_move(src):
    build = src.index("backup_manifest.py build")
    verify = src.index("backup_manifest.py verify")
    move = src.index('mv -T "$DIR.partial" "$DIR"')
    assert build < verify < move


def test_row_counts_come_from_the_dump_after_it_is_copied(src):
    assert "backup_manifest.py count-dump" in src
    assert src.index("backup_manifest.py count-dump") > src.index('db.sql.gz"')
    assert "information_schema" not in src and "count(*)" not in src
    assert '> "$WORK/rows.json"' in src


def test_log_line(src):
    assert "logs/stable_snapshot.log" in src


def test_failed_run_forgets_its_restic_snapshot_without_masking_status(src):
    assert "DONE=0" in src and "SNAP_ID=" in src
    assert 'restic forget "$SNAP_ID"' in src and "--prune" not in src.split("restic forget")[1].split(BS_N)[0]
    assert "rc=$?" in src and 'exit "$rc"' in src
    assert src.index('mv -T "$DIR.partial" "$DIR"') < src.index("DONE=1")


def test_stale_partial_removed_before_mkdir_and_mv_is_hardened(src):
    assert src.index('rm -rf "$DIR.partial"' + BS_N + 'mkdir') < src.index("./scripts/ops/backup_db.sh")
    assert 'chmod 600 "$DIR.partial/db.sql.gz"' in src and 'chmod 700 "$DIR.partial"' in src


def test_dump_path_comes_from_backup_db_output(src):
    assert "ls -t" not in src
    assert "backup_db: wrote" in src


# ---- v120 final-review fixes -------------------------------------------------
import re  # noqa: E402

GIT_CMD = re.compile(r"(?<![\w./-])git\s+(rev-parse|checkout|status|log|diff|fetch|reset|describe|pull|clone)\b")


def bare_git_lines(text):
    bad = []
    for ln in text.splitlines():
        if ln.lstrip().startswith("#"):
            continue
        for m in GIT_CMD.finditer(ln):
            if not ln[:m.start()].endswith("runuser -u deploy -- "):
                bad.append(ln)
    return bad


def test_git_runs_as_the_deploy_user_and_an_empty_sha_fails_first(src):
    assert "runuser -u deploy -- git rev-parse HEAD" in src
    assert bare_git_lines(src) == []
    guard = src.index('[ -n "$GIT_SHA" ]')
    assert src.index("runuser -u deploy -- git rev-parse HEAD") < guard
    assert guard < src.index("backup_manifest.py build")
    assert guard < src.index("./scripts/ops/backup_db.sh")
    assert '--git-sha "$GIT_SHA"' in src


def test_restic_backup_takes_the_cron_lock(src):
    assert "flock logs/restic.lock restic backup" in src


def test_snapshot_id_is_parsed_before_the_exit_status_is_acted_on(src):
    run = src.index("flock logs/restic.lock restic backup")
    assert "|| RESTIC_RC=$?" in src[run:run + 400]
    parse = src.index('SNAP_ID="$(')
    act = src.index('"$RESTIC_RC"', parse)
    assert run < parse < act
    tail = src[act:act + 900]
    assert "3)" in tail and "WARNING" in tail      # exit 3: files vanished, snapshot exists
    assert "exit 1" in tail                        # anything else fails; cleanup forgets SNAP_ID
