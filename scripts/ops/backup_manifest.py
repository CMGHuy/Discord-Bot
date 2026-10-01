#!/usr/bin/env python3
"""Backup manifest helper (v120 section 3). Standard library only: it runs under
the VM host's python3 and on Windows. Subcommands: build, verify, prune, next-name, count-dump, report-market."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFEST = "manifest.json"
CHUNK = 1 << 20


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _folder_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and p.name != MANIFEST)


def build_manifest(folder: Path, *, git_sha=None, deploy=None, restic_id=None,
                   row_counts=None, pg_server_version=None, vm_epoch=None,
                   market_files=None) -> dict:
    folder = Path(folder)
    deploy = deploy or {}
    manifest = {
        "schema": 1,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "vm_epoch": vm_epoch,
        "git_sha": git_sha,
        "bot_image": deploy.get("bot_image"),
        "db_image": deploy.get("db_image"),
        "restic_id": restic_id,
        "row_counts": row_counts,
        "pg_server_version": pg_server_version,
        "files": {p.name: {"sha256": _sha256(p), "bytes": p.stat().st_size}
                  for p in _folder_files(folder)},
        "market_files": market_files,
    }
    (folder / MANIFEST).write_text(json.dumps(manifest, sort_keys=True, indent=2),
                                   encoding="utf-8")
    return manifest


def _gzip_problem(path: Path) -> str | None:
    try:
        with gzip.open(path, "rb") as fh:
            while fh.read(CHUNK):
                pass
    except (OSError, EOFError) as exc:
        return f"gzip read failed: {path.name}: {exc}"
    return None


def _file_problems(folder: Path, name: str, meta: dict) -> list[str]:
    path = folder / name
    if not path.is_file():
        return [f"missing file: {name}"]
    problems = []
    if path.stat().st_size != meta.get("bytes"):
        problems.append(f"size mismatch: {name}")
    if _sha256(path) != meta.get("sha256"):
        problems.append(f"sha256 mismatch: {name}")
    return problems


def verify_folder(folder: Path) -> list[str]:
    folder = Path(folder)
    mpath = folder / MANIFEST
    if not mpath.is_file():
        return [f"missing manifest: {mpath}"]
    try:
        listed = json.loads(mpath.read_text(encoding="utf-8")).get("files", {})
    except (OSError, ValueError) as exc:
        return [f"unreadable manifest: {exc}"]
    problems: list[str] = []
    for name, meta in listed.items():
        problems += _file_problems(folder, name, meta)
    for p in _folder_files(folder):
        if p.name not in listed:
            problems.append(f"unlisted file: {p.name}")
    for p in _folder_files(folder):
        if p.name.endswith(".gz") and p.name in listed:
            gz = _gzip_problem(p)
            if gz:
                problems.append(gz)
    return problems


def _good_and_failed(pulls: Path) -> tuple[list[Path], list[Path]]:
    dirs = sorted(p for p in pulls.iterdir() if p.is_dir())
    failed = [p for p in dirs if p.name.endswith(".FAILED")]
    good = [p for p in dirs if not p.name.endswith(".FAILED")]
    return good, failed


def prune_pulls(backups: Path, keep: int = 10) -> list[Path]:
    if keep < 1:
        raise ValueError(f"keep must be at least 1, got {keep}")
    backups = Path(backups).resolve()
    pulls = (backups / "pulls").resolve()
    if pulls.parent != backups:
        raise ValueError(f"{pulls} resolves outside {backups}")
    if not pulls.is_dir():
        return []
    good, failed = _good_and_failed(pulls)
    doomed = good[:-keep]
    if good:
        newest = good[-1].name
        doomed += [p for p in failed if p.name[: -len(".FAILED")] < newest]
    removed = []
    for p in doomed:
        if p.resolve().parent == pulls:
            shutil.rmtree(p)
            removed.append(p)
    return removed


def next_stable_name(date: str, existing: set[str]) -> str:
    base = f"stable-{date}"
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else None


def _read_market_files(path):
    if not path:
        return None
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        size, _, name = line.partition("\t")
        if name:
            out[name] = int(size)
    return out


def _cmd_build(args) -> int:
    m = build_manifest(
        Path(args.dir), git_sha=args.git_sha, deploy=_load_json(args.deploy_json),
        restic_id=args.restic_id, row_counts=_load_json(args.row_counts),
        pg_server_version=args.pg_version, vm_epoch=args.vm_epoch,
        market_files=_read_market_files(args.market_files))
    print(json.dumps(m, sort_keys=True, indent=2))
    return 0


def _cmd_verify(args) -> int:
    problems = verify_folder(Path(args.dir))
    for p in problems:
        print(p)
    if problems:
        return 1
    print("PASS")
    return 0


COPY_RE = re.compile(r"^COPY (.+?) \(.*\) FROM stdin;$")


def count_dump(path) -> dict:
    """Rows per table in a plain pg_dump (.sql.gz): COPY block lines up to the
    terminator. Counts come from the dump itself, so they cannot drift from it."""
    counts: dict = {}
    table = None
    with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if table is None:
                m = COPY_RE.match(line)
                if m:
                    table = m.group(1).replace('"', "")
                    counts[table] = 0
            elif line == "\\.":
                table = None
            else:
                counts[table] += 1
    return counts


def _cmd_count_dump(args) -> int:
    print(json.dumps(count_dump(args.dump), sort_keys=True))
    return 0


def _local_sizes(root: Path) -> dict:
    if not root.is_dir():
        return {}
    return {p.relative_to(root).as_posix(): p.stat().st_size
            for p in root.rglob("*") if p.is_file()}


def market_report(vm_files: dict, root: Path) -> tuple[list[str], int]:
    """Compare the local market_data mirror with the VM's file list (report only,
    nothing is deleted or fetched). Returns (lines, count of files only local)."""
    local = _local_sizes(Path(root))
    only_local = sorted(set(local) - set(vm_files))
    absent = sorted(set(vm_files) - set(local))
    differs = sorted(n for n in set(vm_files) & set(local) if local[n] != vm_files[n])
    lines = [f"missing on VM: {n}" for n in only_local]
    lines += [f"absent locally: {n}" for n in absent]
    lines += [f"size differs: {n}" for n in differs]
    return lines, len(only_local)


def _cmd_report_market(args) -> int:
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    lines, missing = market_report(manifest.get("market_files") or {}, Path(args.root))
    for ln in lines:
        print(ln)
    print(f"MISSING_COUNT={missing}")
    return 0


def _cmd_prune(args) -> int:
    if args.keep < 1:
        _parser().error("--keep must be at least 1")
    for p in prune_pulls(Path(args.backups), keep=args.keep):
        print(f"removed {p}")
    return 0


def _cmd_next_name(args) -> int:
    lines = Path(args.existing).read_text(encoding="utf-8").splitlines()
    print(next_stable_name(args.date, {ln.strip() for ln in lines if ln.strip()}))
    return 0


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("dir")
    b.add_argument("--git-sha")
    b.add_argument("--deploy-json")
    b.add_argument("--restic-id")
    b.add_argument("--row-counts")
    b.add_argument("--pg-version")
    b.add_argument("--vm-epoch", type=int)
    b.add_argument("--market-files")
    v = sub.add_parser("verify")
    v.add_argument("dir")
    p = sub.add_parser("prune")
    p.add_argument("backups")
    p.add_argument("--keep", type=int, default=10)
    c = sub.add_parser("count-dump")
    c.add_argument("dump")
    r = sub.add_parser("report-market")
    r.add_argument("manifest")
    r.add_argument("root")
    n = sub.add_parser("next-name")
    n.add_argument("date")
    n.add_argument("--existing", required=True)
    return ap


HANDLERS = {"build": _cmd_build, "verify": _cmd_verify,
            "prune": _cmd_prune, "next-name": _cmd_next_name,
            "count-dump": _cmd_count_dump, "report-market": _cmd_report_market}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    return HANDLERS[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
