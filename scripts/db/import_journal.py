#!/usr/bin/env python3
"""Import data/journal.json into the PostgreSQL journal table."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot import config  # noqa: E402
from swingbot.core.db.repositories.journal import JournalRepository  # noqa: E402
from swingbot.core.infra.jsonio import read_json  # noqa: E402
from scripts.db.import_common import run_import  # noqa: E402


def load_source(path: str | None) -> list[dict]:
    rows = read_json(path or os.path.join(config.DATA_DIR, "journal.json"), [])
    return rows if isinstance(rows, list) else []


def write_one(repo, record: dict) -> None:
    repo.upsert(record)


if __name__ == "__main__":
    raise SystemExit(run_import(sys.argv[1:], load_source=load_source, write_one=write_one,
                                repo=JournalRepository(), key="trade_id", name="journal"))
