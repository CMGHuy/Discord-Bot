"""Pulled env files hold live tokens (v120 §2): git must never stage them."""
import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("path", [
    "backups/pulls/2026-10-01T18-04Z/env",
    "backups/stable/stable-2026-10-01/env",
    "backups/market_data/daily/AAPL.csv",
    "backups/LAST_GOOD_PULL",
])
def test_git_ignores_every_backup_path(path):
    r = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=REPO)
    assert r.returncode == 0, f"{path} is not git-ignored"


def test_search_tools_skip_backups():
    lines = (REPO / ".ignore").read_text(encoding="utf-8").splitlines()
    assert "backups/" in lines
