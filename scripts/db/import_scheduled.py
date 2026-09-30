#!/usr/bin/env python3
"""Import data/scheduled_jobs.json into the scheduled_jobs table."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot import config  # noqa: E402
from swingbot.core.db.repositories.scheduled import ScheduledJobRepository  # noqa: E402
from swingbot.core.infra.jsonio import read_json  # noqa: E402
from scripts.db import part3_sources  # noqa: E402
from scripts.db.import_common import run_import  # noqa: E402


def load_source(path: str | None) -> list[dict]:
    raw = read_json(path or os.path.join(config.DATA_DIR, "scheduled_jobs.json"), {})
    return part3_sources.scheduled_rows(raw)


def write_one(repo, record: dict) -> None:
    repo.mark(record["job"], record["fired_on"])


def main(argv=None) -> int:
    return run_import(sys.argv[1:] if argv is None else argv, load_source=load_source,
                      write_one=write_one, repo=ScheduledJobRepository(), key="job",
                      name="scheduled_jobs")


if __name__ == "__main__":
    raise SystemExit(main())
