"""Shared import verification for the one-shot JSON-to-Postgres imports."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field


def record_checksum(record: dict) -> str:
    """Return a type-sensitive canonical checksum for one source record."""
    blob = json.dumps(record, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class ImportReport:
    source_count: int = 0
    imported_count: int = 0
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    mismatched: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (self.source_count == self.imported_count and not self.missing
                and not self.extra and not self.mismatched)

    def render(self) -> str:
        lines = [f"  source records : {self.source_count}",
                 f"  imported rows  : {self.imported_count}"]
        for label, ids in (("MISSING (in source, not imported)", self.missing),
                           ("EXTRA (imported, not in source)", self.extra),
                           ("MISMATCH (checksum differs)", self.mismatched)):
            if ids:
                shown = ", ".join(ids[:20])
                more = f" (+{len(ids) - 20} more)" if len(ids) > 20 else ""
                lines.append(f"  {label}: {shown}{more}")
        lines.append("  VERDICT: " + ("OK" if self.ok else "FAILED"))
        return "\n".join(lines)


def _index(rows: list[dict], key: str, label: str) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for row in rows:
        value = str(row.get(key))
        if value in indexed:
            raise ValueError(f"duplicate {key}={value!r} in {label}")
        indexed[value] = row
    return indexed


def compare(source: list[dict], imported: list[dict], key: str,
            ignore_fields: set[str] | frozenset[str] = frozenset()) -> ImportReport:
    """Compare records, optionally ignoring fields absent from legacy JSON."""
    if ignore_fields:
        source = [{name: value for name, value in row.items() if name not in ignore_fields}
                  for row in source]
        imported = [{name: value for name, value in row.items() if name not in ignore_fields}
                    for row in imported]
    src, dst = _index(source, key, "source"), _index(imported, key, "imported")
    return ImportReport(
        source_count=len(src), imported_count=len(dst),
        missing=sorted(set(src) - set(dst)), extra=sorted(set(dst) - set(src)),
        mismatched=sorted(value for value in set(src) & set(dst)
                          if record_checksum(src[value]) != record_checksum(dst[value])),
    )


def run_import(argv, *, load_source, write_one, repo, key: str, name: str) -> int:
    """Run a reusable dry-run/import/verification CLI."""
    parser = argparse.ArgumentParser(description=f"Import {name} into Postgres")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", help="path to the JSON file (default: data/)")
    args = parser.parse_args(argv)
    source = load_source(args.source)
    print(f"[{name}] {len(source)} record(s) in source", flush=True)
    if args.dry_run:
        print(f"[{name}] DRY RUN -- would write {len(source)} row(s); table currently holds {repo.count()}")
        return 0
    for index, record in enumerate(source, 1):
        write_one(repo, record)
        if index % 100 == 0 or index == len(source):
            print(f"[{name}] {index}/{len(source)} written", flush=True)
    report = compare(source, repo.list_all(), key=key)
    print(f"[{name}] verification:")
    print(report.render())
    return 0 if report.ok else 1
