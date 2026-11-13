#!/usr/bin/env python3
"""Backup manifest helper (v120 section 3). Standard library only: it runs under
the VM host's python3 and on Windows. Subcommands: build, verify, prune, next-name,
prev-sha, count-dump, report-market."""
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
# v221 (v220 spec Section 2): what a stable point needs for /rollback stable-...
ROLLBACK_FIELDS = ("alembic_head", "bot_version", "ui_version", "config_keys_sha256", "features")
PLAN_ID_RE = re.compile(r"\((v\d+)\)")
STABLE_DIR_RE = re.compile(r"^stable-(\d{4}-\d{2}-\d{2})(?:-(\d+))?$")
PRE_V220_NOTE = "era: pre-v220 (no rollback fields: alembic_head, versions, config keys, features)"


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
                   market_files=None, rollback=None) -> dict:
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
    if rollback is not None:
        manifest.update({k: rollback.get(k) for k in ROLLBACK_FIELDS})
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


def config_keys_sha256(config_source: str) -> str:
    """sha256 of the sorted declared config field names, one per line. Names only:
    a value never enters the hash, so adding or removing a key changes it."""
    from rollback_checks import declared_config_keys  # sibling module, stdlib only (v220)
    names = sorted(set(declared_config_keys(config_source)))
    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()


def features_from_log(lines: list[str]) -> list[dict]:
    """`git log --format=%H%x09%s` lines -> [{"plan", "sha", "subject"}], same order."""
    out = []
    for line in lines:
        sha, _, subject = line.rstrip("\r\n").partition("\t")
        if not sha.strip():
            continue
        m = PLAN_ID_RE.search(subject)
        out.append({"plan": m.group(1) if m else None, "sha": sha.strip(), "subject": subject})
    return out


def _stable_key(name: str):
    m = STABLE_DIR_RE.match(name)
    return (m.group(1), int(m.group(2) or 1)) if m else None


def _manifest_git_sha(folder: Path) -> str | None:
    try:
        return json.loads((folder / MANIFEST).read_text(encoding="utf-8")).get("git_sha") or None
    except (OSError, ValueError):
        return None


def previous_stable_sha(stable_dir: Path, exclude: str = "") -> str | None:
    """git_sha of the newest stable point folder holding a manifest, `exclude` skipped."""
    stable_dir = Path(stable_dir)
    if not stable_dir.is_dir():
        return None
    points = sorted((key, p) for p in stable_dir.iterdir()
                    if p.is_dir() and p.name != exclude and (key := _stable_key(p.name)))
    for _, folder in reversed(points):
        sha = _manifest_git_sha(folder)
        if sha:
            return sha
    return None


def manifest_era(manifest: dict) -> str:
    return "v220" if all(k in manifest for k in ROLLBACK_FIELDS) else "pre-v220"


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


def _rollback_inputs(args) -> dict | None:
    given = (args.alembic_head, args.version_json, args.config_source, args.features_log)
    if all(v is None for v in given):
        return None
    versions = _load_json(args.version_json) or {}
    config = Path(args.config_source).read_text(encoding="utf-8") if args.config_source else None
    log = (Path(args.features_log).read_text(encoding="utf-8").splitlines()
           if args.features_log else [])
    return {"alembic_head": args.alembic_head or None,
            "bot_version": versions.get("bot"), "ui_version": versions.get("ui"),
            "config_keys_sha256": config_keys_sha256(config) if config is not None else None,
            "features": features_from_log(log)}


def _cmd_build(args) -> int:
    m = build_manifest(
        Path(args.dir), git_sha=args.git_sha, deploy=_load_json(args.deploy_json),
        restic_id=args.restic_id, row_counts=_load_json(args.row_counts),
        pg_server_version=args.pg_version, vm_epoch=args.vm_epoch,
        market_files=_read_market_files(args.market_files),
        rollback=_rollback_inputs(args))
    print(json.dumps(m, sort_keys=True, indent=2))
    return 0


def _era_note(folder: Path) -> str | None:
    """A stable manifest (it has a restic id) from before v221 gets a note, never a problem."""
    try:
        manifest = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if manifest.get("restic_id") and manifest_era(manifest) == "pre-v220":
        return PRE_V220_NOTE
    return None


def _cmd_verify(args) -> int:
    folder = Path(args.dir)
    problems = verify_folder(folder)
    for p in problems:
        print(p)
    if problems:
        return 1
    note = _era_note(folder)
    if note:
        print(note)
    print("PASS")
    return 0


def _cmd_prev_sha(args) -> int:
    print(previous_stable_sha(Path(args.dir), exclude=args.exclude) or "")
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
    b.add_argument("--alembic-head")
    b.add_argument("--version-json")
    b.add_argument("--config-source")
    b.add_argument("--features-log")
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
    ps = sub.add_parser("prev-sha")
    ps.add_argument("dir")
    ps.add_argument("--exclude", default="")
    return ap


HANDLERS = {"build": _cmd_build, "verify": _cmd_verify,
            "prune": _cmd_prune, "next-name": _cmd_next_name,
            "prev-sha": _cmd_prev_sha,
            "count-dump": _cmd_count_dump, "report-market": _cmd_report_market}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    return HANDLERS[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
