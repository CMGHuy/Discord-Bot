"""Persistent weekly earnings snapshots for the watchlist.

The live earnings cache is intentionally in-memory and short-lived. This
ledger is different: it preserves both the latest announced future date and
dates that have already passed, so a weekly refresh does not erase the
watchlist's earnings context.
"""
from __future__ import annotations

import datetime as dt
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from swingbot import config
from swingbot.core.infra.jsonio import atomic_write_json, read_json
from swingbot.core.market.events import get_earnings_datetimes


def _path() -> str:
    return os.path.join(config.DATA_DIR, "earnings_history.json")


def _iso(value: dt.datetime) -> str:
    return value.isoformat()


def refresh_watchlist_earnings(symbols: list[str], *, now: dt.datetime | None = None) -> dict:
    """Fetch and persist each symbol's next date plus its observed past dates.

    A failed/unavailable provider response leaves a symbol's existing ledger
    entry intact. ETF symbols simply produce no dates through the shared
    resolver, which is the same rule used by the earnings gate.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    previous = read_json(_path(), {})
    entries = previous.get("symbols", {}) if isinstance(previous, dict) else {}
    entries = entries if isinstance(entries, dict) else {}
    next_entries = dict(entries)

    unique = sorted({symbol.upper().strip() for symbol in symbols if symbol.strip()})
    with ThreadPoolExecutor(max_workers=min(10, len(unique) or 1)) as pool:
        futures = {pool.submit(get_earnings_datetimes, symbol, refresh=True): symbol for symbol in unique}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                dates = future.result()
            except Exception:
                continue
            if not dates:
                continue
            past = sorted({_iso(value) for value in dates if value < now})
            upcoming = sorted((_iso(value) for value in dates if value >= now))
            old = entries.get(symbol, {})
            old_past = old.get("past", []) if isinstance(old, dict) else []
            if isinstance(old_past, list):
                past = sorted(set(past).union(value for value in old_past if isinstance(value, str)))
            old_next = old.get("next") if isinstance(old, dict) else None
            if isinstance(old_next, str):
                try:
                    previously_announced = dt.datetime.fromisoformat(old_next)
                    if previously_announced.tzinfo is None:
                        previously_announced = previously_announced.replace(tzinfo=dt.timezone.utc)
                    if previously_announced < now:
                        past = sorted(set(past).union([old_next]))
                except ValueError:
                    pass
            next_entries[symbol] = {"next": upcoming[0] if upcoming else None, "past": past}

    snapshot = {"updated_at": _iso(now), "symbols": next_entries}
    atomic_write_json(_path(), snapshot)
    return snapshot
