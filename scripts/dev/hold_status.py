"""SessionStart HOLD line (v220): is a code-only rollback holding deploys?

`--line` prints the line from the cache only, never touching the network (the
hook must not block a session start). `--refresh [--if-stale]` asks the VM
through scripts/ops/ssh-hetzner.sh (a read-only `cat`) and rewrites the cache;
the hook starts it detached. Errors are cached, never raised.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "logs" / "deploy_hold_cache.json"
SSH = REPO / "scripts" / "ops" / "ssh-hetzner.sh"
REMOTE_CMD = "cat /opt/swing-bot/backups/deploy_hold.json 2>/dev/null || echo NO_HOLD"
REFRESH_AFTER = timedelta(minutes=30)
STAMP = "%Y-%m-%dT%H:%M:%SZ"


def hold_line(cache: dict | None) -> str | None:
    hold = (cache or {}).get("hold")
    if not isinstance(hold, dict):
        return None
    return (f"HOLD     : deploy held by rollback to {str(hold.get('sha', '?'))[:12]} "
            f"({hold.get('reason', '?')}, since {hold.get('at', '?')}) -- release with /rollback --release "
            f"(checked {cache.get('checked_at', '?')})")


def is_stale(cache: dict | None, now: datetime) -> bool:
    try:
        checked = datetime.strptime((cache or {})["checked_at"], STAMP).replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        return True
    return now - checked > REFRESH_AFTER


def _read_vm(run, ssh: Path) -> tuple[dict | None, str | None]:
    if not ssh.exists():
        return None, f"{ssh.name} missing"
    try:
        proc = run(["bash", str(ssh), REMOTE_CMD], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"ssh failed: {type(exc).__name__}"
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return None, f"ssh exit {proc.returncode}"
    if out.endswith("NO_HOLD"):
        return None, None
    try:
        hold = json.loads(out)
    except ValueError:
        return None, "unreadable hold file"
    return (hold, None) if isinstance(hold, dict) else (None, "unreadable hold file")


def refresh(cache_path: Path, *, run=subprocess.run, ssh: Path = SSH) -> dict:
    hold, error = _read_vm(run, ssh)
    cache = {"checked_at": datetime.now(timezone.utc).strftime(STAMP), "hold": hold, "error": error}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, sort_keys=True), encoding="utf-8")
    tmp.replace(cache_path)
    return cache


def _load(cache_path: Path) -> dict | None:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def main(argv: list[str] | None = None, *, run=subprocess.run) -> int:
    parser = argparse.ArgumentParser(description="v220 deploy-hold status for the SessionStart hook")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--line", action="store_true")
    mode.add_argument("--refresh", action="store_true")
    parser.add_argument("--if-stale", action="store_true")
    parser.add_argument("--cache", type=Path, default=CACHE)
    args = parser.parse_args(argv)
    cache = _load(args.cache)
    if args.line:
        line = hold_line(cache)
        if line:
            print(line)
        return 0
    if args.if_stale and not is_stale(cache, datetime.now(timezone.utc)):
        return 0
    refresh(args.cache, run=run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
