"""Single-flight cache in front of the tape's two batch fetches (v132).

`/market/tape` is refetched by every open tab, and each call used to make two
yfinance downloads behind the process-wide download lock. Under load the
requests queued on that lock until the admin process ran out of file handles
(2026-10-05). Here any number of concurrent callers cost one download per TTL:
the first caller with a missing symbol fetches, the rest wait for it and then
serve whatever the cache holds.

Display-only. Trading decisions never read this.
"""
from __future__ import annotations

import threading
import time

#: Daily bars feed only the previous close, which changes once a day.
DAILY_TTL_SECONDS = 300.0
#: Matches data._BATCH_PRICE_CACHE_TTL_SECONDS.
PRICE_TTL_SECONDS = 15.0


class SingleFlightCache:
    """Per-symbol TTL cache with at most one fetch in flight."""

    def __init__(self, ttl: float, wait: float = 10.0, clock=time.monotonic):
        self._ttl = ttl
        self._wait = wait
        self._clock = clock
        self._entries: dict = {}
        self._cond = threading.Condition()
        self._fetching = False

    def get(self, symbols: list, fetch) -> dict:
        """`{symbol: value}` for every symbol the cache can answer.

        A failed or empty fetch caches nothing, so an expired entry keeps
        being served (stale beats blank) and a never-seen symbol is absent.
        """
        missing = self._claim(symbols)
        if missing:
            self._lead(missing, fetch)
        with self._cond:
            return {s: self._entries[s][0] for s in symbols if s in self._entries}

    def clear(self) -> None:
        with self._cond:
            self._entries.clear()

    def _claim(self, symbols: list) -> list:
        """The symbols this caller must fetch -- empty when all are fresh or
        another caller's fetch was waited on instead."""
        with self._cond:
            missing = self._missing(symbols)
            if not missing:
                return []
            if self._fetching:
                self._cond.wait(timeout=self._wait)
                return []
            self._fetching = True
            return missing

    def _missing(self, symbols: list) -> list:
        now = self._clock()
        return [s for s in symbols
                if s not in self._entries or now - self._entries[s][1] >= self._ttl]

    def _lead(self, missing: list, fetch) -> None:
        got: dict = {}
        try:
            got = fetch(missing) or {}
        except Exception:  # a dead feed degrades to stale rows, never a 500
            got = {}
        finally:
            with self._cond:
                now = self._clock()
                for symbol, value in got.items():
                    self._entries[symbol] = (value, now)
                self._fetching = False
                self._cond.notify_all()


_prices = SingleFlightCache(PRICE_TTL_SECONDS)
_daily = SingleFlightCache(DAILY_TTL_SECONDS)


def prices(symbols: list) -> dict:
    from swingbot.core.marketdata import data as market_data
    return _prices.get(symbols, lambda missing: market_data.get_current_price_batch(missing))


def daily_frames(symbols: list) -> dict:
    from swingbot.core.marketdata import data as market_data
    return _daily.get(symbols, lambda missing: market_data.get_daily_data_batch(missing))


def reset() -> None:
    """Tests only: drop every cached entry."""
    _prices.clear()
    _daily.clear()
