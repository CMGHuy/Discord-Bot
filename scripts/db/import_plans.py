#!/usr/bin/env python3
"""Import data/plans.json into the normalized plans table."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot import config  # noqa: E402
from swingbot.core.db.repositories.plans import PlanRepository  # noqa: E402
from swingbot.core.infra.jsonio import read_json  # noqa: E402
from scripts.db.import_common import run_import  # noqa: E402


def load_source(path: str | None) -> list[dict]:
    rows = read_json(path or os.path.join(config.DATA_DIR, "plans.json"), [])
    return list(rows.values()) if isinstance(rows, dict) else rows


def write_one(repo, record: dict) -> None:
    repo.upsert(record)


if __name__ == "__main__":
    raise SystemExit(run_import(sys.argv[1:], load_source=load_source, write_one=write_one,
                                repo=PlanRepository(), key="plan_id", name="plans"))
