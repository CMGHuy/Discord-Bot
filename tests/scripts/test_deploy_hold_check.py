"""deploy.sh refuses, with exit 0, while a code-only rollback holds deploys
(v220). Runs a temp copy of deploy.sh under bash with `git` stubbed: a held
run must stop before any git call."""
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "deploy.sh"
HOLD = {"sha": "c" * 40, "reason": "v230 broke exits", "at": "2026-11-20T10:00:00Z"}


def test_the_guard_runs_before_the_phase_one_fetch_and_reset():
    src = DEPLOY.read_text(encoding="utf-8")
    guard = src.index("if [ -f backups/deploy_hold.json ]; then")
    assert guard < src.index('if [ "${1:-}" != "--updated" ]; then') < src.index("git fetch origin main")
    block = src[guard:src.index('if [ "${1:-}" != "--updated" ]; then')]
    assert "exit 0" in block and "/rollback --release" in block
    for pinned in ("docker compose up", "env_set.py", ">> backups/deploys.jsonl", "sed -i", "rolling back"):
        assert pinned not in block


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
def app(tmp_path):
    bash = _working_bash(DEPLOY, tmp_path)
    if bash is None:
        pytest.skip("no bash that can see both the repo and the tmp dir")
    (tmp_path / "deploy").mkdir()
    shutil.copy(DEPLOY, tmp_path / "deploy" / "deploy.sh")
    (tmp_path / "backups").mkdir()
    (tmp_path / ".env").write_text("SWING_BOT_IMAGE=x\n", encoding="utf-8", newline="\n")
    return bash, tmp_path


def _run(bash, root):
    stubs = ('git() { echo "git $*" >> "$ROOT/git.log"; return 1; }; '
             'python3() { "$PY" "$@"; }; export -f git python3; ')
    env = {**os.environ, "ROOT": root.as_posix(), "PY": pathlib.Path(sys.executable).as_posix()}
    cmd = stubs + f'bash "{(root / "deploy" / "deploy.sh").as_posix()}"'
    return subprocess.run([bash, "-c", cmd], env=env, capture_output=True, text=True, timeout=60)


def test_a_held_deploy_exits_0_before_any_git_call(app):
    bash, root = app
    (root / "backups" / "deploy_hold.json").write_text(json.dumps(HOLD), encoding="utf-8")
    proc = _run(bash, root)
    assert proc.returncode == 0
    assert f"deploy held by rollback to {'c' * 40} (v230 broke exits, since 2026-11-20T10:00:00Z)" in proc.stdout
    assert not (root / "git.log").exists()


def test_an_unreadable_hold_still_holds(app):
    bash, root = app
    (root / "backups" / "deploy_hold.json").write_text("{broken", encoding="utf-8")
    proc = _run(bash, root)
    assert proc.returncode == 0 and "unreadable" in proc.stdout
    assert not (root / "git.log").exists()


def test_without_a_hold_phase_one_fetches_main(app):
    bash, root = app
    proc = _run(bash, root)
    assert proc.returncode != 0   # the stub git fails, which stops set -e
    assert (root / "git.log").read_text(encoding="utf-8").splitlines()[0] == "git fetch origin main"
