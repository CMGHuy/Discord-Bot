#!/usr/bin/env python3
"""Import data/starred_plans.json into Postgres."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from swingbot import config  # noqa: E402
from swingbot.core.db.repositories.starred import StarredRepository  # noqa: E402
from swingbot.core.infra.jsonio import read_json  # noqa: E402
from scripts.db.import_common import run_import  # noqa: E402


def load_source(path: str | None) -> list[dict]:
    return [{"plan_id": value} for value in read_json(path or os.path.join(config.DATA_DIR, "starred_plans.json"), [])]


def write_one(repo, record: dict) -> None:
    repo.star(record["plan_id"])


if __name__ == "__main__":
    raise SystemExit(run_import(sys.argv[1:], load_source=load_source, write_one=write_one,
                                repo=StarredRepository(), key="plan_id", name="starred_plans"))
