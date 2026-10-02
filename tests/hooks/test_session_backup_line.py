"""SessionStart hook prints one BACKUP line so an overdue off-VM copy is visible."""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "session-cursor.ps1"
PWSH = shutil.which("pwsh")

pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh not on PATH")


def _iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(backups: Path) -> tuple[int, str]:
    env = dict(os.environ, SWINGBOT_BACKUPS_DIR=str(backups))
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-File", str(HOOK)],
        capture_output=True, text=True, env=env, cwd=ROOT, timeout=120,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("BACKUP")]
    assert len(lines) == 1, proc.stdout + proc.stderr
    return proc.returncode, lines[0]


def _good_pull(backups: Path, age: timedelta) -> None:
    backups.mkdir(parents=True, exist_ok=True)
    (backups / "pulls" / "20261001T000000Z").mkdir(parents=True, exist_ok=True)
    (backups / "LAST_GOOD_PULL").write_text(
        f"{_iso(-age)} pulls/20261001T000000Z 1790000000\n", encoding="utf-8")


def test_recent_pull_shows_age_and_newest_stable(tmp_path):
    _good_pull(tmp_path, timedelta(days=2, hours=3))
    for name in ("stable-2026-09-01", "stable-2026-10-01", "stable-2026-10-05.partial"):
        (tmp_path / "stable" / name).mkdir(parents=True)
    code, line = _run(tmp_path)
    assert code == 0
    assert "2d ago" in line and "stable-2026-10-01" in line
    assert " | newest stable stable-2026-10-01" in line
    assert line.isascii(), line
    assert "WARNING" not in line and ".partial" not in line


def test_nine_day_old_pull_warns(tmp_path):
    _good_pull(tmp_path, timedelta(days=9, hours=1))
    _, line = _run(tmp_path)
    assert "WARNING" in line and "9d" in line and "/backup-pull" in line


def test_missing_file_says_no_good_pull_yet(tmp_path):
    _, line = _run(tmp_path)
    assert "no good pull yet" in line


def test_garbage_file_warns_and_exits_zero(tmp_path):
    (tmp_path / "LAST_GOOD_PULL").write_text("garbage\n", encoding="utf-8")
    code, line = _run(tmp_path)
    assert code == 0 and "WARNING" in line


def test_future_timestamp_never_negative_or_crashes(tmp_path):
    _good_pull(tmp_path, -timedelta(days=3))
    code, line = _run(tmp_path)
    assert code == 0 and "-" not in line.split("ago")[0].split("pull")[-1]
    assert "0d ago" in line


def test_seven_days_23_hours_is_still_fine(tmp_path):
    _good_pull(tmp_path, timedelta(days=7, hours=23))
    _, line = _run(tmp_path)
    assert "WARNING" not in line and "7d ago" in line


def test_eight_days_warns(tmp_path):
    _good_pull(tmp_path, timedelta(days=8))
    _, line = _run(tmp_path)
    assert "WARNING" in line and "8d" in line


def test_missing_pull_folder_is_not_called_good(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "LAST_GOOD_PULL").write_text(
        f"{_iso(-timedelta(days=1))} pulls/20261001T000000Z 1790000000\n", encoding="utf-8")
    _, line = _run(tmp_path)
    assert "WARNING last good pull folder is missing -- run /backup-pull" in line
    assert "ago" not in line


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def test_worktree_session_reads_the_main_trees_backups(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git not on PATH")
    main = tmp_path / "main"
    main.mkdir()
    try:
        _git(main, "init", "-q")
        _git(main, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
             "--allow-empty", "-m", "init")
        wt = tmp_path / "wt"
        _git(main, "worktree", "add", "-q", str(wt), "-b", "side")
    except (subprocess.CalledProcessError, OSError):
        pytest.skip("git worktree unavailable")
    hook_dir = wt / ".claude" / "hooks"
    hook_dir.mkdir(parents=True)
    shutil.copy(HOOK, hook_dir / "session-cursor.ps1")
    _good_pull(main / "backups", timedelta(days=1, hours=2))
    env = {k: v for k, v in os.environ.items() if k != "SWINGBOT_BACKUPS_DIR"}
    proc = subprocess.run([PWSH, "-NoProfile", "-File", str(hook_dir / "session-cursor.ps1")],
                          capture_output=True, text=True, env=env, cwd=wt, timeout=120)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("BACKUP")]
    assert len(lines) == 1, proc.stdout + proc.stderr
    assert "1d ago" in lines[0] and "WARNING" not in lines[0], lines[0]
