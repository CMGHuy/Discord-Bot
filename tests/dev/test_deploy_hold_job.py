"""The CI deploy hold (v220): the workflow's first job reads the VM's
backups/deploy_hold.json and skips cleanup and deploy while it exists; the
job's scripts and hold_notice.sh run here under bash with stubbed git, python3
and curl."""
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys

import pytest

yaml = pytest.importorskip("yaml")
ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
NOTICE = ROOT / "scripts" / "ops" / "hold_notice.sh"
HOLD = {"sha": "a" * 40, "image": "ghcr.io/o/r:sha-aaaaaaaaaaaa", "from_sha": "b" * 40,
        "from_image": "ghcr.io/o/r:sha-bbbbbbbbbbbb", "db_image": "ghcr.io/o/r-db:pgcfg-1",
        "reason": "v230 broke exits", "at": "2026-11-20T10:00:00Z"}
MESSAGE = f"deploy held by rollback to {'a' * 40} (v230 broke exits, since 2026-11-20T10:00:00Z)"
URL = "https://discord.example/api/webhooks/secret-token"


def _jobs():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def test_the_hold_job_runs_first_and_publishes_held():
    hold = _jobs()["hold"]
    assert "needs" not in hold
    assert "refs/heads/main" in hold["if"]
    assert hold["outputs"]["held"] == "${{ steps.decide.outputs.held }}"
    read, decide = hold["steps"][0], hold["steps"][1]
    assert read["id"] == "read" and read["uses"] == "appleboy/ssh-action@v1.2.5"
    assert read["with"]["capture_stdout"] is True and read["with"]["envs"] == "APP_DIR"
    assert "script_stop" not in read["with"]
    assert decide["id"] == "decide" and decide["env"]["SSH_OUT"] == "${{ steps.read.outputs.stdout }}"


def test_the_deploy_script_rechecks_the_hold_before_deploy_sh():
    """A rollback landing between the hold job and the deploy step must still win."""
    script = _jobs()["deploy"]["steps"][0]["with"]["script"]
    check = script.index("deploy_hold.json")
    assert check < script.index("deploy/deploy.sh")
    assert "exit 0" in script[check:script.index("deploy/deploy.sh")]


def test_cleanup_runs_only_when_not_held():
    cleanup = _jobs()["cleanup"]
    assert cleanup["needs"] == ["hold"]
    assert "needs.hold.outputs.held == 'false'" in cleanup["if"]
    assert "always()" not in cleanup["if"]


def test_deploy_fails_closed_and_tolerates_a_skipped_cleanup():
    deploy = _jobs()["deploy"]
    assert {"hold", "cleanup", "docker-build", "db-image", "publish-image", "compose-lint"} <= set(deploy["needs"])
    cond = deploy["if"]
    for needle in ("always()", "github.ref == 'refs/heads/main'", "needs.hold.result == 'success'",
                   "needs.hold.outputs.held != 'true'",
                   "contains(fromJSON('[\"success\",\"skipped\"]'), needs.cleanup.result)"):
        assert needle in cond
    for job in ("docker-build", "db-image", "publish-image", "compose-lint"):
        assert f"needs.{job}.result == 'success'" in cond


# --- the job's scripts and hold_notice.sh under bash -------------------------

def _working_bash(*paths):
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
    found = _working_bash(NOTICE, tmp_path)
    if found is None:
        pytest.skip("no bash that can see both the repo and the tmp dir")
    return found


STUBS = (
    'python3() { "$PY" "$@"; }; '
    'curl() { printf "%s\\n" "$*" >> "$STUB/curl.log"; return "$(cat "$STUB/curl_rc" 2>/dev/null || echo 0)"; }; '
    'git() { if [ "$3" = fetch ]; then return "$(cat "$STUB/git_rc" 2>/dev/null || echo 0)"; fi; cat "$NOTICE_SRC"; }; '
    "export -f python3 curl git; "
)


@pytest.fixture
def app(tmp_path):
    root = tmp_path / "app"
    (root / "backups").mkdir(parents=True)
    (tmp_path / "stub").mkdir()
    (root / ".env").write_text(f"OPS_ALERT_WEBHOOK_URL={URL}\n", encoding="utf-8", newline="\n")
    return root


def _hold(app, text=None):
    (app / "backups" / "deploy_hold.json").write_text(text or json.dumps(HOLD), encoding="utf-8")


def _run(bash, app, script, **env):
    full = {**os.environ, "APP_DIR": app.as_posix(), "STUB": (app.parent / "stub").as_posix(),
            "PY": pathlib.Path(sys.executable).as_posix(), "NOTICE_SRC": NOTICE.as_posix(), **env}
    return subprocess.run([bash, "-c", STUBS + script], env=full, capture_output=True, text=True, timeout=60)


def _posts(app):
    log = app.parent / "stub" / "curl.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _ssh_script():
    return _jobs()["hold"]["steps"][0]["with"]["script"]


def test_the_ssh_script_says_not_held_without_a_hold_file(bash, app):
    proc = _run(bash, app, _ssh_script())
    assert proc.returncode == 0 and proc.stdout.strip() == "NOT_HELD"
    assert _posts(app) == []


def test_the_ssh_script_says_held_with_the_message_and_posts_once(bash, app):
    _hold(app)
    proc = _run(bash, app, _ssh_script())
    assert proc.returncode == 0
    assert proc.stdout.strip().splitlines()[-1] == f"HELD {MESSAGE}"
    assert len(_posts(app)) == 1 and URL not in proc.stdout + proc.stderr


def test_the_ssh_script_still_holds_when_the_notice_cannot_be_fetched(bash, app):
    _hold(app)
    (app.parent / "stub" / "git_rc").write_text("1", encoding="utf-8")
    proc = _run(bash, app, _ssh_script())
    assert proc.stdout.strip().splitlines()[-1].startswith("HELD deploy held")


@pytest.mark.parametrize("out, held, rc", [
    (f"HELD {MESSAGE}", "true", 0), ("NOT_HELD", "false", 0),
    ("NOT_HELD\r", "false", 0), ("", None, 1), ("ssh: connect refused", None, 1),
])
def test_the_decide_step_maps_the_verdict_and_fails_closed(bash, app, out, held, rc):
    output = app.parent / "gh_output"
    output.write_text("", encoding="utf-8")
    proc = _run(bash, app, _jobs()["hold"]["steps"][1]["run"], SSH_OUT=out, GITHUB_OUTPUT=output.as_posix())
    assert proc.returncode == rc
    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines == ([f"held={held}"] if held else [])


def test_notice_without_a_hold_prints_so_and_posts_nothing(bash, app):
    proc = _run(bash, app, f"bash {shlex.quote(NOTICE.as_posix())} \"$APP_DIR\"")
    assert proc.returncode == 0 and proc.stdout.strip() == "no deploy hold" and _posts(app) == []


def test_notice_prints_the_verbatim_message_and_never_the_url(bash, app):
    _hold(app)
    proc = _run(bash, app, f"bash {shlex.quote(NOTICE.as_posix())} \"$APP_DIR\"")
    assert proc.returncode == 0 and proc.stdout.strip().splitlines()[-1] == MESSAGE
    posts = _posts(app)
    assert len(posts) == 1 and MESSAGE in posts[0] and "/rollback --release" in posts[0]
    assert URL not in proc.stdout + proc.stderr


def test_notice_survives_a_failed_post_a_missing_url_and_a_broken_file(bash, app):
    _hold(app)
    (app.parent / "stub" / "curl_rc").write_text("22", encoding="utf-8")
    proc = _run(bash, app, f"bash {shlex.quote(NOTICE.as_posix())} \"$APP_DIR\"")
    assert proc.returncode == 0 and proc.stdout.strip().splitlines()[-1] == MESSAGE
    (app / ".env").write_text("OTHER=1\n", encoding="utf-8")
    _hold(app, "{not json")
    proc = _run(bash, app, f"bash {shlex.quote(NOTICE.as_posix())} \"$APP_DIR\"")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "deploy held by rollback (backups/deploy_hold.json unreadable)"
    assert len(_posts(app)) == 1   # only the first run posted
