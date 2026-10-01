#!/usr/bin/env python3
"""Set one KEY=value in the VM's .env IN PLACE, then snapshot it (v116).

In place means the same inode. .env is a single-file bind mount; a rename
(sed -i, most editors) leaves the running containers reading the old file
(docs/claude/known-traps.md). Stdlib only: it runs on the VM host.

    python3 scripts/ops/env_set.py DB_STORES 'flags:dual,heartbeat:dual'
    python3 scripts/ops/env_set.py --get DB_STORES

Then restart and verify inside the containers -- this script only edits.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from swingbot.core.infra import env_snapshot  # noqa: E402  (stdlib-only)


def _pattern(key: str) -> re.Pattern:
    return re.compile(rf"^[ \t]*{re.escape(key)}[ \t]*=[^\r\n]*", re.M)


def set_value(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    pattern = _pattern(key)
    if pattern.search(text):
        return pattern.sub(lambda _match: line, text)
    eol = "\r\n" if "\r\n" in text else "\n"
    separator = "" if not text or text.endswith("\n") else eol
    return f"{text}{separator}{line}{eol}"


def get_value(text: str, key: str) -> str | None:
    matches = _pattern(key).findall(text)
    if not matches:
        return None
    value = matches[-1].split("=", 1)[1].strip()
    return value.strip("'\"")


def write_in_place(path: str, text: str) -> None:
    with open(path, "r+", encoding="utf-8", newline="") as handle:
        handle.seek(0)
        handle.write(text)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())


def _snapshot_or_warn(path: str, when: str) -> None:
    if not env_snapshot.snapshot_quietly(path):
        print(f"env_set: WARNING .env snapshot FAILED ({when} the edit); no version "
              f"was saved -- check that {env_snapshot.snapshot_dir(path)} is writable "
              "by this user", file=sys.stderr)


def _notify_settings() -> None:
    """Best-effort NOTIFY through the db container (the host has no psql), so a
    live admin refreshes; a missed one costs one stale screen."""
    subprocess.run(["docker", "compose", "exec", "-T", "db", "psql", "-U", "swingbot",
                    "-d", "swingbot", "-c", "NOTIFY settings"],
                   cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, check=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", default=os.path.join(ROOT, ".env"))
    parser.add_argument("--get", metavar="KEY")
    parser.add_argument("key", nargs="?")
    parser.add_argument("value", nargs="?")
    args = parser.parse_args(argv)
    with open(args.env, encoding="utf-8", newline="") as handle:
        text = handle.read()
    if args.get:
        print(get_value(text, args.get) or "")
        return 0
    if args.key is None or args.value is None:
        parser.error("pass KEY VALUE, or --get KEY")
    _snapshot_or_warn(args.env, "before")
    inode = os.stat(args.env).st_ino
    write_in_place(args.env, set_value(text, args.key, args.value))
    if os.stat(args.env).st_ino != inode:
        print("env_set: .env changed inode; restart the containers", file=sys.stderr)
        return 1
    _snapshot_or_warn(args.env, "after")
    _notify_settings()
    print(f"env_set: {args.key} updated in place in {args.env}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
