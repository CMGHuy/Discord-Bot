#!/usr/bin/env python3
"""Build data/universe/sp500_pit.json: every symbol that was an S&P 500 member
at any point in a training window, not just today's survivors.

    python scripts/data/build_pit_universe.py                      # 2010-01-01 .. today
    python scripts/data/build_pit_universe.py --start 2018-06-01 --end 2025-12-31

Reads data/universe/sp500_membership.csv (see swingbot/core/marketdata/
pit_membership.py for its source and interval semantics). Name/sector come
from sp500.json where the symbol is still a member; delisted and renamed
symbols get their ticker as name and sector "Unknown".

The `_pit` suffix is what tells run_backtest_range.py / measure_*.py to mask
every signal to the dates the symbol was actually in the index, so this file
is only half the mechanism -- a plain `--universe sp500` run stays the
survivor-only list it always was. Refresh the membership CSV from
github.com/fja05680/sp500 (`sp500_ticker_start_end.csv`), then re-run this.
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot.core.marketdata import pit_membership, universe  # noqa: E402


def build(start: str, end: str, out_dir: str | None = None) -> str:
    out_dir = out_dir or universe.UNIVERSE_DIR
    intervals = pit_membership.load_intervals(os.path.join(out_dir, "sp500_membership.csv"))
    if not intervals:
        raise SystemExit("no membership rows -- is data/universe/sp500_membership.csv present?")
    current = {row["symbol"]: row for row in universe.load("sp500")}
    rows = [current.get(sym) or {"symbol": sym, "name": sym, "sector": "Unknown", "etf": False}
            for sym in pit_membership.members_between(intervals, start, end)]
    out = os.path.join(out_dir, "sp500_pit.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    survivors = sum(1 for r in rows if r["symbol"] in current)
    print(f"wrote {out}: {len(rows)} symbols ever in the S&P 500 {start}..{end} "
          f"({survivors} still members, {len(rows) - survivors} left the index)")
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--start", default="2010-01-01")
    p.add_argument("--end", default=dt.date.today().isoformat())
    a = p.parse_args()
    build(a.start, a.end)
