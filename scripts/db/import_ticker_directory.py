#!/usr/bin/env python3
"""Import data/ticker_directory.json into the ticker_directory table."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot import config  # noqa: E402
from swingbot.core.db.repositories.ticker_directory import TickerDirectoryRepository  # noqa: E402
from swingbot.core.infra.jsonio import read_json  # noqa: E402
from scripts.db import part3_sources  # noqa: E402
from scripts.db.import_common import run_import  # noqa: E402


def load_source(path: str | None) -> list[dict]:
    raw = read_json(path or os.path.join(config.DATA_DIR, "ticker_directory.json"), {})
    return part3_sources.ticker_rows(raw)


def write_one(repo, record: dict, conn=None) -> None:
    """Upsert so rerunning an interrupted import converges safely."""
    repo.upsert(record, conn=conn)


def main(argv=None) -> int:
    # ~10k rows: one transaction (a commit per row takes minutes), with run_import's
    # progress line every 100 rows and at the end.
    return run_import(sys.argv[1:] if argv is None else argv, load_source=load_source,
                      write_one=write_one, repo=TickerDirectoryRepository(), key="symbol",
                      name="ticker_directory", one_transaction=True)


if __name__ == "__main__":
    raise SystemExit(main())
