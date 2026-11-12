"""Pins for scripts/ops/rollback_code.sh (v220). The script runs only on the VM
as root, so CI pins its step order and its never-touch rules as text; the
argument-parsing paths, which run before the script touches anything, also run
under bash where one can see the repo."""
import os
import pathlib
import re
import shutil
import subprocess

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ops" / "rollback_code.sh"


@pytest.fixture(scope="module")
def src():
    return SCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(src):
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


def body(src, name):
    start = src.index(f"\n{name}() {{")
    return src[start:src.index("\n}\n", start)]


def test_everything_lives_in_main_with_one_call_line(src):
    assert src.startswith("#!/usr/bin/env bash")
    assert "set -Eeuo pipefail" in src
    assert src.rstrip().endswith('main "$@"; exit $?')


def test_it_copies_itself_out_of_the_tree_and_reexecs_before_anything_else(src):
    m = body(src, "main")
    assert 'mktemp -d "$APP_DIR/backups/rollback.XXXXXX"' in m
    order = ["parse_args", 'cp "$SELF" "$WORK/rollback_code.sh"',
             'exec bash "$WORK/rollback_code.sh" "$@"', "fetch_tools"]
    pos = [m.index(x) for x in order]
    assert pos == sorted(pos)


def test_the_planner_modules_come_from_the_tools_ref(src):
    assert 'TOOLS="rollback_plan.py rollback_migrations.py rollback_checks.py rollback_window.py"' in src
    assert 'TOOLS_REF="${ROLLBACK_TOOLS_REF:-origin/main}"' in src
    assert 'git_d show "$TOOLS_REF:scripts/ops/$f" > "$WORK/$f"' in body(src, "fetch_tools")


def test_git_and_the_planner_run_as_deploy(code):
    assert 'git_d() { runuser -u deploy -- git -C "$APP_DIR" "$@"; }' in code
    assert 'planner() { runuser -u deploy -- python3 "$WORK/rollback_plan.py" "$@"; }' in code
    bare = [l for l in code.splitlines()
            if re.search(r"(^|[;&|(]|\bthen|\bdo)\s*git\s", l) and "git_d()" not in l]
    assert bare == []


def test_the_checks_run_before_the_dry_run_exit(src):
    b = body(src, "run_rollback")
    order = ["run_check", "host_checks", "print_plan", "Dry run: nothing changed."]
    pos = [b.index(x) for x in order]
    assert pos == sorted(pos)


def test_checks_refuse_with_exit_2_and_a_noop_exits_3(src):
    run = body(src, "run_check")
    assert "--allow-writer-drift" in run and "exit 3" in run and "refuse" in run
    assert "exit 2" in body(src, "refuse")
    hosts = body(src, "host_checks")
    assert 'docker manifest inspect "$IMAGE"' in hosts
    assert "git_d status --porcelain --untracked-files=no" in hosts


def test_the_report_decides_the_refresher_and_keep_refresher_overrides(src):
    run = body(src, "run_check")
    assert 'json_field "$WORK/report.json" refresher' in run
    assert 'if [ "$KEEP_REFRESHER" = 1 ]; then START_REFRESHER=keep-stopped; fi' in run


def test_the_rollback_steps_run_in_the_spec_order(src):
    b = body(src, "run_rollback")
    order = ["run_check", "host_checks", "print_plan", "Dry run: nothing changed.",
             "trap 'on_error $LINENO' ERR", "pull_and_probe", "safety_backup", "prepare_hold",
             "SWITCHING=1", "write_hold", 'git_d checkout -q --detach "$SHA"', "switch_image",
             "if ! smoke; then restore_previous; exit 1; fi", "SWITCHING=0", "record_line rollback"]
    pos = [b.index(x) for x in order]
    assert pos == sorted(pos)
    assert "not wired yet" not in src


def test_the_hold_carries_the_seven_contract_fields_and_lands_atomically(src):
    w = body(src, "write_hold")
    assert '("sha", "image", "from_sha", "from_image", "db_image", "reason", "at")' in w
    assert 'mv -f "$HOLD.tmp" "$HOLD"' in w and 'chmod 644 "$HOLD.tmp"' in w
    p = body(src, "prepare_hold")
    assert 'AT="$(json_field "$HOLD" at)"' in p
    assert 'KEYS="backups/rollback_keys_$AT.json"' in p
    assert 'rollback_window.py" snapshot --out "$KEYS"' in p


def test_a_failed_smoke_restores_and_writes_no_deploy_line(src):
    r = body(src, "restore_previous")
    assert "record_line" not in r
    assert r.index("trap - ERR") < r.index("set +e") < r.index("git_d checkout")
    assert 'git_d checkout -q --detach "$FROM_SHA"' in r and 'git_d checkout -q "$FROM_REF"' in r
    assert 'switch_image "$FROM_IMAGE" "$FROM_REFRESHER"' in r
    assert 'cp "$WORK/prior_hold.json" "$HOLD"' in r and 'rm -f "$HOLD"' in r
    assert 'if [ "${SWITCHING:-0}" = 1 ]; then restore_previous; fi' in body(src, "on_error")


def test_smoke_covers_health_heartbeat_and_the_write_free_evaluation(src):
    s = body(src, "smoke")
    assert "SMOKE_SECONDS=180" in src
    assert "bot_heartbeat" in src and '"$beat" -ge "$SWITCHED_AT"' in body(src, "heartbeat_fresh")
    assert "/api/v1/health" in body(src, "admin_answers")
    assert "200|401) return 0" in body(src, "admin_answers")
    life = body(src, "lifecycle_smoke")
    assert "import swingbot.core.infra.rollback_smoke" in life
    assert "docker compose exec -T admin python -m swingbot.core.infra.rollback_smoke" in life
    order = ["services_healthy", "heartbeat_fresh", "admin_answers", "lifecycle_smoke"]
    pos = [s.index(x) for x in order]
    assert pos == sorted(pos)
    forced = [l for l in src.splitlines() if "ROLLBACK_FORCE_SMOKE_FAIL" in l]
    assert forced and all('"$DRILL" = 1' in l for l in forced)


def test_the_drill_skips_backup_bot_and_heartbeat(src):
    assert 'if [ "$DRILL" = 1 ]; then log "drill: pgBackRest' in body(src, "safety_backup")
    assert 'if [ "$DRILL" = 1 ]; then s="admin"; fi' in body(src, "services_for")
    assert 'if [ "$DRILL" != 1 ]; then heartbeat_fresh' in body(src, "smoke")


def test_it_never_touches_schema_db_image_env_contents_or_market_data(code):
    assert "alembic" not in code
    assert "env_set.py SWING_BOT_DB_IMAGE" not in code
    assert "> .env" not in code and "sed -i" not in code
    assert "market_data" not in code
    ups = [l for l in code.splitlines() if "docker compose up" in l]
    assert ups and all("--no-deps" in l and "--no-build" in l for l in ups)
    assert not re.search(r"docker compose (down|rm|stop db)", code)
    assert all("--type=diff backup" in l for l in code.splitlines() if "pgbackrest" in l)


def test_the_refresher_is_probed_and_stopped_before_the_checkout(src):
    b = body(src, "run_rollback")
    assert "import swingbot.refresher" in body(src, "pull_and_probe")
    assert b.index("docker compose stop refresher") < b.index('git_d checkout -q --detach "$SHA"')


def test_the_deploy_line_is_written_by_the_planner(src):
    rec = body(src, "record_line")
    assert 'planner deploy-line --kind "$1"' in rec and ">> backups/deploys.jsonl" in rec


# --- argument parsing under bash (nothing is touched before it passes) ------

def _working_bash(*paths):
    """A bash that resolves these host paths, or None (WSL's bash cannot see C:/)."""
    git = shutil.which("git")
    candidates = [shutil.which("bash")]
    if git:
        candidates.append(str(pathlib.Path(git).resolve().parents[1] / "usr" / "bin" / "bash.exe"))
    test = " && ".join(f'test -e "{p.as_posix()}"' for p in paths)
    for bash in filter(None, candidates):
        try:
            if subprocess.run([bash, "-c", test], capture_output=True, timeout=20).returncode == 0:
                return bash
        except OSError:
            continue
    return None


@pytest.fixture
def bash(tmp_path):
    found = _working_bash(SCRIPT, tmp_path)
    if found is None:
        pytest.skip("no bash that can see both the repo and the tmp dir")
    return found


def test_the_script_parses(bash):
    assert subprocess.run([bash, "-n", SCRIPT.as_posix()], capture_output=True).returncode == 0


BAD_ARGS = [
    [], ["--resolve"], ["--resolve", "a", "b"], ["--candidates", "x"], ["--bogus"],
    ["abc123", "img", "--dry-run"], ["a" * 40, "img"], ["a" * 40, "img", "--now"],
    ["a" * 40, "img", "--dry-run", "--bogus"], ["a" * 40, "img", "--dry-run", "--reason"],
]


@pytest.mark.parametrize("args", BAD_ARGS)
def test_bad_arguments_refuse_before_touching_anything(bash, tmp_path, args):
    env = {**os.environ, "ROLLBACK_APP_DIR": tmp_path.as_posix()}
    proc = subprocess.run([bash, SCRIPT.as_posix(), *args], env=env,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 2
    assert "usage: rollback_code.sh" in proc.stderr
    assert list(tmp_path.iterdir()) == []
