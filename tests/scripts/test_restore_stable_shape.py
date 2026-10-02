"""restore_stable.sh's step order (v120 section 1, Restore). The real restore is
proven by the V120 drill on the VM; this pins the order an edit could break."""
import pathlib

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ops" / "restore_stable.sh"


@pytest.fixture(scope="module")
def src():
    return SCRIPT.read_text(encoding="utf-8")


def test_the_steps_run_in_the_spec_order(src):
    markers = [
        "backup_manifest.py verify",                       # 1 refuse a damaged point
        "docker manifest inspect",                         # 2 images still on GHCR
        'if [ "$DRY_RUN" = 1 ]',                           # --dry-run stops here
        "git status --porcelain --untracked-files=no",     # dirty tree refused
        "--type=diff backup",                              # 4 checkpoint of now
        "scripts/ops/restic_hourly.sh",
        "docker compose stop bot admin",
        "restic restore",
        'cat "$DIR/env" > .env',                           # in place
        "chown deploy:deploy .env",
        "env_set.py SWING_BOT_IMAGE",
        'docker pull "$db_image"',
        "up -d --no-build --wait db",                      # recreate db on the pinned image
        "restore_db.sh",
        "git checkout --detach",
        "scan_paused",                                     # pause before start
        "docker compose up -d --no-build --wait bot admin",
    ]
    positions = [src.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_verify_and_image_check_precede_the_first_stop(src):
    stop = src.index("docker compose stop bot admin")
    assert src.index("backup_manifest.py verify") < src.index("docker manifest inspect") < stop


def test_i_mean_it_is_required_before_anything_stops(src):
    gate = src.index('"$MODE" = "--i-mean-it"')
    assert gate < src.index("docker compose stop bot admin")
    assert '"$CONFIRMED" != 1' in src and src.index('"$CONFIRMED" != 1') < src.index("--type=diff backup")


def test_no_flag_prints_usage_and_exits_two(src):
    assert "usage: restore_stable.sh" in src
    assert "exit 2" in src


def test_manifest_is_read_with_python_not_jq(src):
    assert "jq " not in src.replace("json", "")
    assert "python3" in src


def test_it_logs_and_never_sed(src):
    assert "restore_stable" in src and "logs/rollback.log" in src
    assert "sed -i" not in src
    assert "set -Eeuo pipefail" in src
    assert b"\r" not in SCRIPT.read_bytes()


def test_whole_body_is_parsed_before_the_checkout_can_rewrite_the_file(src):
    assert "main() {" in src
    assert src.splitlines()[-1] == 'main "$@"; exit $?'
    assert src.count('main "$@"') == 1


def test_the_name_is_validated_before_dir_is_built(src):
    assert "^stable-[0-9]{4}-[0-9]{2}-[0-9]{2}(-[0-9]+)?$" in src
    assert src.index("^stable-[0-9]{4}") < src.index('DIR="backups/stable/$NAME"')


def test_an_aborted_run_is_logged_without_masking_the_status(src):
    assert "restore_stable failed at line" in src
    assert " ERR" in src and "exit $rc" in src and "set -Eeuo pipefail" in src


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


def test_every_git_command_runs_as_the_deploy_user(src):
    assert "runuser -u deploy -- git status --porcelain --untracked-files=no" in src
    assert "runuser -u deploy -- git checkout --detach" in src
    assert bare_git_lines(src) == []


def test_an_empty_git_sha_is_refused_in_the_plan_stage_even_for_a_dry_run(src):
    guard = src.index('"$git_sha" = "None"')
    assert guard > src.index('git_sha="$(read_field git_sha)"')
    assert guard < src.index("docker manifest inspect")
    assert guard < src.index('if [ "$DRY_RUN" = 1 ]')
    assert guard < src.index("docker compose stop bot admin")
    assert "exit 2" in src[guard:guard + 300]
