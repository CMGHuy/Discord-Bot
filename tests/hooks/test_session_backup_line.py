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
    (backups / "LAST_GOOD_PULL").write_text(
        f"{_iso(-age)} pulls/20261001T000000Z 1790000000\n", encoding="utf-8")


def test_recent_pull_shows_age_and_newest_stable(tmp_path):
    _good_pull(tmp_path, timedelta(days=2, hours=3))
    for name in ("stable-2026-09-01", "stable-2026-10-01", "stable-2026-10-05.partial"):
        (tmp_path / "stable" / name).mkdir(parents=True)
    code, line = _run(tmp_path)
    assert code == 0
    assert "2d ago" in line and "stable-2026-10-01" in line
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
