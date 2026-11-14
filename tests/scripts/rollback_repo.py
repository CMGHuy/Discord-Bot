"""Temp git repositories for the v220 rollback planner tests (V220-1, V220-1b, V220-2).

Not a test module. `make_repo` commits on `main` in order and points
`refs/remotes/origin/main` at the last commit, so code that reads `origin/main`
sees the whole fixture history.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
from pathlib import Path

_IDENTITY = {
    "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_NOSYSTEM": "1",
}
_BASE = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def git(repo: Path, *args: str, date: str | None = None) -> str:
    env = {**os.environ, **_IDENTITY}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", env=env, check=True)
    return done.stdout.strip()


def make_repo(tmp_path: Path, commits: list[dict]) -> Path:
    """`commits`: dicts with `subject`, optional `files` {relpath: text}, optional `tag`
    (annotated). Commit i is dated 2026-01-01T00:00Z + i hours. Returns the repo path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "config", "tag.gpgsign", "false")
    for index, spec in enumerate(commits):
        date = (_BASE + dt.timedelta(hours=index)).isoformat()
        for rel, text in spec.get("files", {}).items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "--allow-empty", "-m", spec["subject"], date=date)
        if spec.get("tag"):
            git(repo, "tag", "-a", spec["tag"], "-m", spec["tag"], date=date)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def sha_of(repo: Path, rev: str = "HEAD") -> str:
    return git(repo, "rev-parse", rev)


def commit_off_main(repo: Path, subject: str) -> str:
    """A commit object that exists but is not reachable from origin/main."""
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    return git(repo, "commit-tree", tree, "-p", "HEAD", "-m", subject)
