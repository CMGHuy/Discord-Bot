#!/usr/bin/env python3
"""Import data/state.json into the per-key signal-state table."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot import config  # noqa: E402
from swingbot.core.db.repositories.signal_state import SignalStateRepository  # noqa: E402
from swingbot.core.infra.jsonio import read_json  # noqa: E402
from scripts.db.import_common import run_import  # noqa: E402


def load_source(path: str | None) -> list[dict]:
    source = read_json(path or os.path.join(config.DATA_DIR, "state.json"), {})
    return [{"key": key, **value} for key, value in source.items()] if isinstance(source, dict) else []


def write_one(repo, record: dict) -> None:
    repo.put(record["key"], {key: value for key, value in record.items() if key != "key"})


if __name__ == "__main__":
    raise SystemExit(run_import(sys.argv[1:], load_source=load_source, write_one=write_one,
                                repo=SignalStateRepository(), key="key", name="state"))
