"""Earnings calendar provider (Finnhub, TTL-cached).

The task said to wrap llm-advisor's market_context under the
one-implementation rule. Capability check 2026-07-29: `swingbot/core/advisor`
does not exist — llm-advisor v5 is planned but unimplemented (see G219) — so
that wrap is dead code and is not written.

There IS a second earnings lookup in the repo: `core/events.py`'s
get_next_earnings_date(), which asks yfinance per ticker with no cache. That
one serves the live bot's holding-window check. This module deliberately does
not call it by default: the gate evaluates per candidate inside the scan
loop, and an uncached per-ticker network call there would be a hidden cost.
Pass fallback_to_events=True to opt in. If the two ever need to become one,
that is a deliberate task — not something to paper over here.
"""
from __future__ import annotations

import datetime as dt

from swingbot import config
from swingbot.core.macro.httpcache import fetch_json


def days_to_earnings(ticker: str, now: dt.date | None = None,
                     fallback_to_events: bool = False) -> int | None:
    now = now or dt.date.today()
    key = (getattr(config, "FINNHUB_API_KEY", "") or "").strip()
    if key:
        params = {"symbol": ticker, "token": key,
                  "from": (now - dt.timedelta(days=30)).isoformat(),
                  "to": (now + dt.timedelta(days=30)).isoformat()}
        data = fetch_json("https://finnhub.io/api/v1/calendar/earnings",
                          params=params, ttl_s=6 * 3600)
        if data:
            dates = sorted(e["date"] for e in data.get("earningsCalendar", [])
                           if e.get("date"))
            future = [d for d in dates if d >= now.isoformat()]
            if future:
                return (dt.date.fromisoformat(future[0]) - now).days
        return None
    if fallback_to_events:
        from swingbot.core import events as events_mod
        nxt = events_mod.get_next_earnings_date(ticker)
        if nxt is not None:
            return (nxt - now).days
    return None


def earnings_within(ticker: str, days: int, now: dt.date | None = None,
                    fallback_to_events: bool = False) -> bool | None:
    d = days_to_earnings(ticker, now=now, fallback_to_events=fallback_to_events)
    return None if d is None else d <= days    # None = unknown, never a silent False
