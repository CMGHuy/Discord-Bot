"""Shared import verification for the one-shot JSON-to-Postgres imports."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field


def _fold_negative_zero(value):
    """Replace ``-0.0`` with ``0.0``, recursively."""
    if isinstance(value, float) and value == 0.0:
        return 0.0
    if isinstance(value, dict):
        return {key: _fold_negative_zero(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_fold_negative_zero(item) for item in value]
    return value


def record_checksum(record: dict) -> str:
    """Return a type-sensitive canonical checksum for one source record.

    Non-finite floats are folded to None first: the write path narrows NaN to
    null at the codec boundary, so a source NaN and a stored null are the same
    record and parity must not report them as a mismatch. Negative zero is
    folded to zero for the same reason: JSONB stores a numeric, so a source
    ``-0.0`` (a scratch exit's R) comes back ``0.0``; they compare equal and
    no consumer divides by them.
    """
    from swingbot.core.db.codec import sanitise_non_finite
    blob = json.dumps(_fold_negative_zero(sanitise_non_finite(record)),
                      sort_keys=True, default=str, separators=(",", ":"))
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


def parity(store: str, source_path: str | None = None) -> ImportReport:
    """Authoritative per-store parity (lazy: parity_report imports this module)."""
    from scripts.db.parity_report import parity as _parity
    return _parity(store, source_path)


def run_import(argv, *, load_source, write_one, repo, key: str, name: str, prune=None) -> int:
    """Run a reusable dry-run/import/verification CLI.

    ``prune(repo, source)``, when given, runs after the writes and removes rows
    the source no longer holds. Only for stores where the source is the whole
    truth (an upsert alone never deletes, so a renamed key lingers).
    """
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
    if prune is not None:
        print(f"[{name}] pruned {prune(repo, source)} row(s) absent from source", flush=True)
    # One verifier. The ad-hoc comparison this replaced had neither the
    # per-store from_repo_shape translation nor ignore_fields, so it reported
    # watchlist FAILED on all 77 rows while authoritative parity reported OK,
    # and passed stores whose shape it never translated.
    report = parity(name, args.source)
    print(f"[{name}] verification:")
    print(report.render())
    return 0 if report.ok else 1
