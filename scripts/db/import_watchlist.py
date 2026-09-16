#!/usr/bin/env python3
"""Import the flat legacy watchlist into PostgreSQL."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot import config  # noqa: E402
from swingbot.core.db.repositories.watchlist import WatchlistRepository  # noqa: E402
from swingbot.core.infra.jsonio import read_json  # noqa: E402
from scripts.db.import_common import run_import  # noqa: E402


def load_source(path: str | None) -> list[dict]:
    tickers = read_json(path or os.path.join(config.DATA_DIR, "watchlist.json"), [])
    stamped = dt.datetime.now(dt.timezone.utc).isoformat()
    # The JSON representation never retained an add date; import time is the
    # only honest value and parity explicitly ignores this generated field.
    return [{"ticker": ticker, "added_at": stamped} for ticker in tickers]


def write_one(repo, record: dict) -> None:
    repo.upsert(record)


if __name__ == "__main__":
    raise SystemExit(run_import(sys.argv[1:], load_source=load_source, write_one=write_one,
                                repo=WatchlistRepository(), key="ticker", name="watchlist"))
