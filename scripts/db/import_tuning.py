#!/usr/bin/env python3
"""Import data/tuning_results/*.json and data/tuning_proposals/*.json."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot import config  # noqa: E402
from swingbot.core.db.repositories.tuning import ProposalRepository, TuningRepository  # noqa: E402
from scripts.db import part3_sources  # noqa: E402
from scripts.db.import_common import run_import  # noqa: E402


def load_results(path: str | None) -> list[dict]:
    """Result files hold the payload only, so `created_at` is stamped from the file mtime."""
    directory = path or os.path.join(config.DATA_DIR, "tuning_results")
    rows = part3_sources.tuning_result_rows(directory)
    for row in rows:
        row["created_at"] = part3_sources.file_mtime_iso(
            os.path.join(directory, f"{row['job_id']}.json"))
    return rows


def load_proposals(path: str | None) -> list[dict]:
    return part3_sources.proposal_rows(path or os.path.join(config.DATA_DIR, "tuning_proposals"))


def write_one(repo, record: dict) -> None:
    repo.upsert(record)


def _stores() -> tuple:
    return ((load_results, TuningRepository(), "job_id", "tuning", "tuning_results"),
            (load_proposals, ProposalRepository(), "filename", "tuning_proposals",
             "tuning_proposals"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import tuning results and proposals")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", help="data directory holding tuning_results/ and "
                                          "tuning_proposals/ (default: data/)")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    base = args.source or config.DATA_DIR
    flags = ["--dry-run"] if args.dry_run else []
    failed = 0
    for load, repo, key, name, subdir in _stores():
        failed += bool(run_import([*flags, "--source", os.path.join(base, subdir)],
                                  load_source=load, write_one=write_one, repo=repo,
                                  key=key, name=name))
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
