"""Point-in-time index membership for survivorship-aware training universes.

A universe built from *today's* S&P 500 list backtests 2010-2023 on the
companies that survived and grew into the index -- a selection made with
hindsight that flatters every long-side result. This module answers the
point-in-time question instead: "was SYMBOL in the index on DATE?", so a
backtest over a `*_pit` universe only counts signals a trader could have
seen while the name was actually a member.

Source: data/universe/sp500_membership.csv, a copy of
`sp500_ticker_start_end.csv` from github.com/fja05680/sp500 (MIT licence,
(c) Farrell J. Aultman), columns `ticker,start_date,end_date`. A ticker may
appear on several rows (it left and re-joined). `end_date` is the first
session the ticker was NOT in the index, so each row is the half-open
interval [start_date, end_date); an empty end_date means still a member.

What it does NOT fix: Yahoo keeps no history for most delisted symbols, so
the membership list names ~830 tickers for 2010-2025 but only the ones Yahoo
still serves can be cached. The fetch script reports that gap explicitly;
it is the residual survivorship bias of free data.

Intervals are plain ISO-string tuples on purpose -- they compare
lexicographically against the backtests' ISO `entry_date` strings and pickle
cheaply into the scenario replay's process pool.
"""
from __future__ import annotations

import csv
import os

from swingbot import config

#: Open-ended membership (empty end_date) sorts after every real ISO date.
OPEN_END = "9999-12-31"

#: `<base>_pit` universe name -> membership CSV under data/universe/.
_MEMBERSHIP_FILES = {"sp500": "sp500_membership.csv"}


def _universe_dir() -> str:
    return os.path.join(config.DATA_DIR, "universe")


def normalize_symbol(raw: str) -> str:
    """Membership-file ticker -> the cache/yfinance spelling (BRK.B -> BRK-B),
    the same rule scripts/data/build_universe.py applies to sp500.json."""
    return raw.strip().upper().replace(".", "-")


def load_intervals(path: str) -> dict[str, list[tuple[str, str]]]:
    """{symbol: [(start, end_exclusive), ...]} sorted by start. Missing file
    -> {} so callers degrade to "no point-in-time mask" rather than crash."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return {}
    out: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        symbol = normalize_symbol(row.get("ticker") or "")
        start = (row.get("start_date") or "").strip()
        if not symbol or not start:
            continue
        end = (row.get("end_date") or "").strip() or OPEN_END
        out.setdefault(symbol, []).append((start, end))
    for spans in out.values():
        spans.sort()
    return out


def is_member(date: str, spans: list[tuple[str, str]] | None) -> bool:
    """True when ISO `date` falls inside any [start, end) span. `spans=None`
    means "no membership data applies" and is always True -- the unmasked
    behaviour every non-PIT universe keeps."""
    if spans is None:
        return True
    day = str(date)[:10]
    return any(start <= day < end for start, end in spans)


def members_between(intervals: dict, start: str, end: str) -> list[str]:
    """Every symbol that was a member at any point in [start, end]."""
    return sorted(sym for sym, spans in intervals.items()
                  if any(s <= end and e > start for s, e in spans))


def membership_file_for(universe: str | None) -> str | None:
    """Path of the membership CSV behind a `<base>_pit` universe name, else
    None. Only the `_pit` suffix opts a run into masking, so every existing
    universe name keeps its exact behaviour."""
    if not universe or not universe.endswith("_pit"):
        return None
    filename = _MEMBERSHIP_FILES.get(universe[: -len("_pit")])
    return os.path.join(_universe_dir(), filename) if filename else None


def membership_map(universe: str | None, symbols) -> dict | None:
    """{symbol: spans} for a `_pit` universe, None for any other. A symbol
    with no row (e.g. a watchlist extra such as SPY) maps to an empty list --
    never a member, so it can never contribute a trade to a PIT run."""
    path = membership_file_for(universe)
    if path is None:
        return None
    intervals = load_intervals(path)
    return {sym: intervals.get(sym, []) for sym in symbols}
