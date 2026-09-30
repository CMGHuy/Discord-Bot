"""Versioned copies of .env for point-in-time rollback (v116 Phase 0).

Every path that changes .env -- the admin settings save, deploy/deploy.sh and
scripts/ops/env_set.py -- leaves a copy at ``backups/env/<UTC ts>.env`` beside
the .env when its content changed, so scripts/ops/rollback_to.sh can put back
the .env that was live at any second of the last 30 days.

Stdlib only: the VM host runs it as ``python3 -m swingbot.core.infra.env_snapshot``
with no requirements installed. Copied, never rewritten: .env is a single-file
bind mount (known-traps.md, "Editing production .env with sed -i").
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import logging
import os
import shutil
import sys

log = logging.getLogger(__name__)

#: Fixed width with microseconds, so lexical order is time order and two
#: saves in one second never overwrite each other.
STAMP_FORMAT = "%Y-%m-%dT%H-%M-%S-%fZ"
SUFFIX = ".env"


def snapshot_dir(env_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(env_path)), "backups", "env")


def stamp_of(name: str) -> dt.datetime | None:
    if not name.endswith(SUFFIX):
        return None
    try:
        parsed = dt.datetime.strptime(name[:-len(SUFFIX)], STAMP_FORMAT)
    except ValueError:
        return None
    return parsed.replace(tzinfo=dt.timezone.utc)


def snapshot_names(directory: str) -> list[str]:
    try:
        names = os.listdir(directory)
    except FileNotFoundError:
        return []
    return sorted(name for name in names if stamp_of(name) is not None)


def _digest(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def take_snapshot(env_path: str, *, now: dt.datetime | None = None) -> str | None:
    """Copy ``env_path`` if it differs from the newest copy; return the new path."""
    if not os.path.isfile(env_path):
        return None
    directory = snapshot_dir(env_path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    names = snapshot_names(directory)
    if names and _digest(os.path.join(directory, names[-1])) == _digest(env_path):
        return None
    stamp = (now or dt.datetime.now(dt.timezone.utc)).strftime(STAMP_FORMAT)
    target = os.path.join(directory, stamp + SUFFIX)
    shutil.copyfile(env_path, target)
    os.chmod(target, 0o600)
    return target


def snapshot_quietly(env_path: str) -> None:
    """take_snapshot for callers that must not fail: a save beats its history."""
    try:
        path = take_snapshot(env_path)
    except OSError:
        log.warning("could not snapshot %s", env_path, exc_info=True)
        return
    if path:
        log.info("snapshotted .env to %s", path)


def prune(directory: str, keep_days: int = 30, now: dt.datetime | None = None) -> list[str]:
    """Delete versions older than the window, except the newest of them:
    that one was live when the window opened, and a rollback to the window's
    first second needs it."""
    cutoff = (now or dt.datetime.now(dt.timezone.utc)) - dt.timedelta(days=keep_days)
    old = [name for name in snapshot_names(directory) if stamp_of(name) < cutoff]
    doomed = [os.path.join(directory, name) for name in old[:-1]]
    for path in doomed:
        os.remove(path)
    return doomed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="env_snapshot")
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("env_path")
    pruner = sub.add_parser("prune")
    pruner.add_argument("directory")
    pruner.add_argument("days", type=int)
    args = parser.parse_args(argv)
    if args.command == "snapshot":
        print(take_snapshot(args.env_path) or "unchanged")
        return 0
    for path in prune(args.directory, args.days):
        print(f"pruned {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
