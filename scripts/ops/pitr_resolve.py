#!/usr/bin/env python3
"""Resolve what rollback_to.sh restores for one target second (v116 Phase 0).

Reads backups/deploys.jsonl, the backups/env/ versions, `restic snapshots
--json` and `pgbackrest info --output=json`. Prints REFUSE lines (exit 2), or
shell assignments for `eval` (exit 0). Stdlib only: it runs on the VM host
while the containers are stopped.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import sys
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from swingbot.core.infra import env_snapshot  # noqa: E402  (stdlib-only)

UTC = dt.timezone.utc


def parse_ts(text: str) -> dt.datetime:
    """`...Z`, `YYYY-MM-DD HH:MM:SS`, `+00:00`, and restic's nanoseconds. Naive is UTC."""
    raw = text.strip().replace(" ", "T")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    head, dot, tail = raw.partition(".")
    if dot:
        digits = "".join(ch for ch in tail if ch.isdigit())
        raw = f"{head}.{digits[:6]}{tail[len(digits):]}"
    parsed = dt.datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _json_line(line: str) -> dict | None:
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    return row if isinstance(row, dict) and row.get("ts") else None


def load_deploys(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as handle:
        rows = [row for row in map(_json_line, handle) if row is not None]
    return sorted(({**row, "_at": parse_ts(row["ts"])} for row in rows), key=lambda r: r["_at"])


def env_versions(directory: str) -> list[tuple[dt.datetime, str]]:
    return [(env_snapshot.stamp_of(name), os.path.join(directory, name))
            for name in env_snapshot.snapshot_names(directory)]


def restic_snapshots(text: str) -> list[tuple[dt.datetime, str]]:
    rows = json.loads(text or "[]") or []
    return sorted((parse_ts(row["time"]), row.get("short_id") or row["id"][:8])
                  for row in rows if row.get("time"))


def pgbackrest_oldest(text: str) -> dt.datetime | None:
    stanzas = json.loads(text or "[]") or []
    stops = [backup["timestamp"]["stop"] for stanza in stanzas
             for backup in stanza.get("backup", [])]
    return dt.datetime.fromtimestamp(min(stops), UTC) if stops else None


def last_at_or_before(items: list[tuple], target: dt.datetime):
    eligible = [item for item in items if item[0] <= target]
    return eligible[-1] if eligible else None


@dataclass
class Resolution:
    target: dt.datetime
    deploy: dict | None = None
    env_file: str | None = None
    restic: tuple | None = None
    refusals: list[str] = field(default_factory=list)


def _refusals(target, now, pg_oldest, found: dict) -> list[str]:
    out = []
    if target > now:
        out.append(f"target {target.isoformat()} is in the future (now {now.isoformat()})")
    if pg_oldest is None:
        out.append("pgBackRest has no completed backup, so nothing is restorable")
    elif target < pg_oldest:
        out.append(f"target is older than the oldest restorable point {pg_oldest.isoformat()}")
    out.extend(f"no {label} at or before the target" for label, item in found.items() if item is None)
    return out


def resolve(target, now, deploys, envs, snapshots, pg_oldest) -> Resolution:
    deploy = last_at_or_before([(row["_at"], row) for row in deploys], target)
    env = last_at_or_before(envs, target)
    snap = last_at_or_before(snapshots, target)
    found = {"deploy record": deploy, ".env version": env, "market_data snapshot": snap}
    return Resolution(target=target, deploy=deploy[1] if deploy else None,
                      env_file=env[1] if env else None, restic=snap,
                      refusals=_refusals(target, now, pg_oldest, found))


def shell_lines(res: Resolution) -> list[str]:
    pairs = {
        "target_pg": res.target.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S+00"),
        "git_sha": res.deploy["git_sha"],
        "bot_image": res.deploy["bot_image"],
        "db_image": res.deploy["db_image"],
        "env_file": res.env_file,
        "restic_id": res.restic[1],
        "restic_time": res.restic[0].isoformat(),
    }
    return [f"{key}={shlex.quote(str(value))}" for key, value in pairs.items()]


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", required=True)
    parser.add_argument("--now")
    parser.add_argument("--deploys", default="backups/deploys.jsonl")
    parser.add_argument("--env-dir", default="backups/env")
    parser.add_argument("--restic-json", required=True)
    parser.add_argument("--pgbackrest-json", required=True)
    args = parser.parse_args(argv)
    now = parse_ts(args.now) if args.now else dt.datetime.now(UTC)
    res = resolve(parse_ts(args.target).astimezone(UTC), now, load_deploys(args.deploys),
                  env_versions(args.env_dir), restic_snapshots(_read(args.restic_json)),
                  pgbackrest_oldest(_read(args.pgbackrest_json)))
    if res.refusals:
        print("\n".join(f"REFUSE: {line}" for line in res.refusals))
        return 2
    print("\n".join(shell_lines(res)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
