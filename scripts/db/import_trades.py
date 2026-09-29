#!/usr/bin/env python3
"""Import data/trades.json into the trades table."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot import config  # noqa: E402
from swingbot.core.db.repositories.trades import TradeRepository  # noqa: E402
from swingbot.core.infra.jsonio import read_json  # noqa: E402
from scripts.db.import_common import run_import  # noqa: E402
from swingbot.core.tracking.performance import _db_record  # noqa: E402


def load_source(path: str | None) -> list[dict]:
    """Return repo-shaped trade records.

    Deliberately the same translator the live dual-write path uses
    (performance.py): it maps the JSON store's `id`/`horizon_key` onto the
    table's `trade_id`/`horizon`. An importer that shaped records differently
    from the live writer would produce a database that passes import and then
    diverges the moment dual-write starts.
    """
    raw = read_json(path or os.path.join(config.DATA_DIR, "trades.json"), [])
    return [_db_record(trade) for trade in raw]


def write_one(repo, record: dict) -> None:
    """Upsert so rerunning an interrupted import converges safely."""
    repo.upsert(record)


if __name__ == "__main__":
    raise SystemExit(run_import(sys.argv[1:], load_source=load_source, write_one=write_one,
                                repo=TradeRepository(), key="trade_id", name="trades"))
