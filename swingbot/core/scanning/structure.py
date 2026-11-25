"""v245: the exact prefix cache for the live scan's analysis phase.

A cached value is a frozen, pure function of ``frame.iloc[:m]``, stored under
``(ticker, unit, prefix_fingerprint(frame, m))``; the tail and the live price
are recomputed every scan (spec § Exact prefix caching). Only the two live
call sites pass a cache. Every config change clears it (``apply_config_change``
on SIGHUP/config_watcher; the settings generation in ``cache_for_mode``).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Callable

from swingbot import config
from swingbot.core.infra import store_generation

log = logging.getLogger(__name__)

DEFAULT_MAX_ENTRIES = 256
_MISSING = object()


def prefix_fingerprint(frame, m: int) -> tuple:
    """Identity of ``frame.iloc[:m]`` (index Decision 5): ``m``, the first row's
    date and close (trim start, split restatement), the last prefix row's date
    and OHLCV (revised bar or volume). ``m == 0`` is the empty prefix."""
    if m <= 0:
        return (0,)
    row = frame.iloc[m - 1]
    volume = float(row["Volume"]) if "Volume" in frame.columns else None
    return (m, str(frame.index[0]), float(frame["Close"].iloc[0]), str(frame.index[m - 1]),
            float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]), volume)


class StructureCache:
    """Bounded, lock-guarded LRU. ``None`` is never stored: a ``None`` get is a miss."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES):
        self._lock = threading.Lock()
        self._entries: OrderedDict = OrderedDict()
        self._max = max(int(max_entries), 0)
        self._generation = store_generation.generation("settings")
        self._hits = self._misses = self._evictions = 0
        self.prefix_build_s = 0.0

    @property
    def max_entries(self) -> int:
        return self._max

    def get(self, key):
        with self._lock:
            value = self._entries.get(key, _MISSING)
            if value is _MISSING:
                self._misses += 1
                return None
            self._entries.move_to_end(key)
            self._hits += 1
            return value

    def put(self, key, value) -> None:
        if value is None:
            return
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            self._evict_locked()

    def get_or_build(self, key: tuple, build: Callable[[], object], *, ticker: str = ""):
        """Cached value, or ``build()`` stored; a failing build warns, stores nothing, returns None."""
        value = self.get(key)
        if value is not None:
            return value
        started = time.perf_counter()
        try:
            value = build()
        except Exception as exc:
            log.warning("analysis cache: building %s failed for %s; computing uncached this scan: %s",
                        key[1] if len(key) > 1 else key, ticker, exc)
            return None
        finally:
            self._add_build_time(time.perf_counter() - started)
        self.put(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def resize(self, max_entries: int) -> None:
        with self._lock:
            self._max = max(int(max_entries), 0)
            self._evict_locked()

    def sync_config(self, generation: int, max_entries: int) -> None:
        """Clear when the settings generation moved since the last sync;
        resize when the cap changed."""
        with self._lock:
            if generation != self._generation:
                self._generation = generation
                self._entries.clear()
        if int(max_entries) != self._max:
            self.resize(max_entries)

    def stats(self) -> dict:
        with self._lock:
            return {"cache_hits": self._hits, "cache_misses": self._misses,
                    "cache_evictions": self._evictions, "cache_entries": len(self._entries)}

    def reset_counters(self) -> None:
        with self._lock:
            self._hits = self._misses = self._evictions = 0
            self.prefix_build_s = 0.0

    def _add_build_time(self, seconds: float) -> None:
        with self._lock:
            self.prefix_build_s += seconds

    def _evict_locked(self) -> None:
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)
            self._evictions += 1


STRUCTURE_CACHE = StructureCache(getattr(config, "STRUCTURE_CACHE_MAX", DEFAULT_MAX_ENTRIES))


def analysis_cache_mode() -> str:
    """``ANALYSIS_CACHE`` as config parsed it: off | shadow | on."""
    return getattr(config, "ANALYSIS_CACHE", "off")


def cache_for_mode(mode: str) -> StructureCache | None:
    """The live cache for ``shadow``/``on``, synced to the current config;
    ``None`` for ``off``. Called once per scan, never per ticker."""
    if mode not in ("shadow", "on"):
        return None
    STRUCTURE_CACHE.sync_config(store_generation.generation("settings"),
                                getattr(config, "STRUCTURE_CACHE_MAX", DEFAULT_MAX_ENTRIES))
    return STRUCTURE_CACHE


def apply_config_change(changed: dict) -> None:
    """Reload hook: any changed setting clears the whole cache (no hand-kept
    field list); a changed ``STRUCTURE_CACHE_MAX`` also resizes it."""
    if not changed:
        return
    if "STRUCTURE_CACHE_MAX" in changed:
        STRUCTURE_CACHE.resize(config.STRUCTURE_CACHE_MAX)
    STRUCTURE_CACHE.clear()
    log.info("analysis cache cleared: %d setting(s) changed", len(changed))
