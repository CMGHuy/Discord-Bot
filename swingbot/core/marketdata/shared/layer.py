"""The v171 shared market-data layer: one cache, cross-process single-flight (D1/D2/D6).

``get`` (mode ``on``) serves each symbol by the first situation that holds: a
cached value no older than the asker's window is a ``hit``; a stale or missing
value with no live foreign lease is leased by this call and fetched in one
batched ``fetch`` with every other such symbol (``fetched``, ``failed`` when the
reply has no value); a live lease held by another call is polled every 100 ms
until a fresh value lands (``shared-wait``); a vanished or expired foreign lease
is taken and fetched; past the deadline tiers 1-2 fetch for themselves and tiers
3-5 get the last cached value of any age (``shared-wait``) or nothing; a
``budget.BudgetDeferred`` from ``fetch`` serves the last cached value of any age
(``budget-deferred``); any other ``fetch`` error releases this call's leases and
propagates (``failed``); spot metals ride in the same batch but are never keyed,
leased or written.

Fail open: any cache read, lease or write error or timeout is warned (once a
minute per operation and error class) and the remaining symbols are fetched
directly. Mode ``off`` is a plain pass-through; mode ``count`` is the same call
plus a count per symbol. No side connection is held while ``fetch`` runs or
while sleeping.

This module takes no budget tokens; provider calls inside ``fetch`` do.
"""
from __future__ import annotations

import itertools
import os
import socket
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Optional

from swingbot import config
from swingbot.core.db.repositories.market_shared import market_shared_repo
from swingbot.core.db.side_engine import side_connection
from swingbot.core.marketdata.shared import counters
from swingbot.core.marketdata.shared.budget import BudgetDeferred
from swingbot.core.marketdata.shared.kinds import (
    Asker, DataKind, Entry, cache_key, resolve_asker)
from swingbot.core.marketdata.spot_metals import is_spot_metal

#: Process prefix of every lease holder; each ``get``/``lease`` call appends ``#n``.
HOLDER_ID = f"{socket.gethostname()}:{os.getpid()}"

_POLL_S = 0.1
_DEFAULT_DEADLINE_S = 30.0
_monotonic = time.monotonic
_sleep = time.sleep
_calls = itertools.count()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def identity(value: Any) -> Any:
    return value


def _next_holder() -> str:
    return f"{HOLDER_ID}#{next(_calls)}"


@dataclass
class _Call:
    kind: DataKind
    fetch: Callable
    asker: Asker
    provider: str
    params: str
    window: Optional[float]
    deadline: float
    encode: Callable
    decode: Callable
    holder: str
    started: datetime

    def key(self, symbol: str) -> str:
        return cache_key(self.kind, symbol, self.params)

    def count(self, outcome: str, n: int = 1) -> None:
        counters.count(self.provider, self.kind, self.asker, outcome, n)


# -- public API -----------------------------------------------------------------


def get(kind: DataKind, symbols, fetch: Callable, *, asker: Asker, provider: str,
        params: str = "", max_age_s: Optional[float] = None,
        deadline_s: float = _DEFAULT_DEADLINE_S, encode: Callable = identity,
        decode: Callable = identity) -> dict[str, Entry]:
    """``{symbol: Entry}`` keyed exactly as passed; a symbol with no value is absent."""
    asker = resolve_asker(asker)
    window = max_age_s if max_age_s is not None else asker.window_s(kind)
    call = _Call(kind, fetch, asker, provider, params, window, _monotonic() + deadline_s,
                 encode, decode, _next_holder(), _now())
    unique = list(dict.fromkeys(symbols))
    mode = config.MARKETDATA_LAYER
    try:
        if mode == "on":
            return _get_on(call, unique)
        return _passthrough(call, unique, counted=(mode == "count"))
    finally:
        counters.flush()


@contextmanager
def lease(kind: DataKind, symbol: str, *, asker: Asker, deadline_s: float = _DEFAULT_DEADLINE_S,
          params: str = "") -> Iterator[bool]:
    """Single-flight for bar writers: True = write, False = another holder finished or failed open."""
    if config.MARKETDATA_LAYER != "on" or is_spot_metal(symbol):
        yield True
        return
    holder = _next_holder()
    key = cache_key(kind, symbol, params)
    held = _acquire(kind, symbol, key, holder, resolve_asker(asker), _monotonic() + deadline_s)
    try:
        yield held
    finally:
        if held:
            _release_keys(holder, [key])


def last_cached(kind: DataKind, symbols, params: str = "") -> dict[str, Entry]:
    """The stored (undecoded) value of any age per symbol; mode ``on`` only, fail open ``{}``."""
    if config.MARKETDATA_LAYER != "on":
        return {}
    keys = {s: cache_key(kind, s, params) for s in dict.fromkeys(symbols)}
    rows = _read_keys(list(dict.fromkeys(keys.values())))
    if not rows:
        return {}
    return {s: _row_entry(rows[k], rows[k].get("value"), "", "hit")
            for s, k in keys.items() if _has_fetched(rows.get(k))}


# -- modes off / count ------------------------------------------------------------


def _passthrough(call: _Call, symbols: list[str], *, counted: bool) -> dict[str, Entry]:
    try:
        reply = call.fetch(symbols) or {}
    except Exception:
        if counted and symbols:
            call.count("failed", len(symbols))
        raise
    now = _now()
    out = {s: Entry(reply[s], now, call.provider, "fetched")
           for s in symbols if reply.get(s) is not None}
    if counted:
        _count_split(call, len(out), len(symbols) - len(out))
    return out


def _count_split(call: _Call, fetched: int, failed: int) -> None:
    if fetched:
        call.count("fetched", fetched)
    if failed:
        call.count("failed", failed)


# -- mode on ------------------------------------------------------------------------


def _get_on(call: _Call, symbols: list[str]) -> dict[str, Entry]:
    spot = [s for s in symbols if is_spot_metal(s)]
    groups: dict[str, list[str]] = {}
    for s in symbols:
        if not is_spot_metal(s):
            groups.setdefault(call.key(s), []).append(s)
    reps = [members[0] for members in groups.values()]
    rows = _read(call, list(groups))
    if rows is None:
        got = _fetch_and_store(call, reps, spot, set(), {})
    else:
        got = _serve(call, reps, spot, rows)
    return _expand(call, got, groups)


def _serve(call: _Call, reps: list[str], spot: list[str], rows: dict) -> dict[str, Entry]:
    out: dict[str, Entry] = {}
    waiting, need = [], []
    for s in reps:
        row = rows.get(call.key(s))
        if _is_fresh(row, call):
            out[s] = _entry(row, call, "hit")
            call.count("hit")
        elif _lease_live(row, call):
            waiting.append(s)
        else:
            need.append(s)
    owned, lost, leased = _claim(call, need)
    out.update(_fetch_and_store(call, owned, spot, leased, rows))
    out.update(_wait(call, waiting + lost, rows))
    return out


def _expand(call: _Call, got: dict[str, Entry], groups: dict[str, list[str]]) -> dict[str, Entry]:
    """Copy each representative's entry to every caller symbol sharing its cache key."""
    out = dict(got)
    for members in groups.values():
        if members[0] in got:
            out.update(dict.fromkeys(members[1:], got[members[0]]))
    return out


def _claim(call: _Call, symbols: list[str]) -> tuple[list[str], list[str], set[str]]:
    """``(owned, lost, leased keys)``; a lease error fails open: every symbol owned, unleased."""
    owned: list[str] = []
    lost: list[str] = []
    leased: set[str] = set()
    if not symbols:
        return owned, lost, leased
    try:
        with side_connection() as conn:
            repo = market_shared_repo()
            for s in symbols:
                key = call.key(s)
                if repo.try_lease(key, call.holder, float(config.MARKETDATA_LEASE_SECONDS),
                                  kind=call.kind.value, symbol=s.upper(), conn=conn):
                    owned.append(s)
                    leased.add(key)
                else:
                    lost.append(s)
    except Exception as exc:  # noqa: BLE001 - fail open to a direct fetch
        counters.warn_fail_open("lease", exc)
        return list(symbols), [], leased
    return owned, lost, leased


def _fetch_and_store(call: _Call, symbols: list[str], spot: list[str], leased: set[str],
                     stale: dict) -> dict[str, Entry]:
    batch = list(symbols) + list(spot)
    if not batch:
        return {}
    try:
        reply = call.fetch(batch) or {}
    except BudgetDeferred:
        _release_keys(call.holder, leased)
        return _deferred(call, batch, stale)
    except Exception:
        _release_keys(call.holder, leased)
        call.count("failed", len(batch))
        raise
    now = _now()
    out = {s: Entry(reply[s], now, call.provider, "fetched")
           for s in batch if reply.get(s) is not None}
    _count_split(call, len(out), len(batch) - len(out))
    rows = [_cache_row(call, s, out[s], now) for s in symbols if s in out]
    _write(rows)
    _release_keys(call.holder, leased - {r["key"] for r in rows})
    return out


def _deferred(call: _Call, batch: list[str], stale: dict) -> dict[str, Entry]:
    call.count("budget-deferred", len(batch))
    out = {}
    for s in batch:
        row = stale.get(call.key(s))
        if _has_value(row):
            out[s] = _entry(row, call, "budget-deferred")
    return out


def _cache_row(call: _Call, symbol: str, entry: Entry, now: datetime) -> dict:
    return {"key": call.key(symbol), "kind": call.kind.value, "symbol": symbol.upper(),
            "fetched_at": now, "source": call.provider, "value": call.encode(entry.value)}


def _wait(call: _Call, symbols: list[str], rows: dict) -> dict[str, Entry]:
    pending = {call.key(s): s for s in symbols}
    last = {k: rows.get(k) for k in pending}
    out: dict[str, Entry] = {}
    while pending and _monotonic() < call.deadline:
        _sleep(_POLL_S)
        fresh = _read(call, list(pending))
        if fresh is None:
            break
        last.update(fresh)
        retry = _poll_round(call, pending, fresh, out)
        if retry:
            owned, lost, leased = _claim(call, retry)
            out.update(_fetch_and_store(call, owned, [], leased, last))
            pending.update({call.key(s): s for s in lost})
    if pending:
        out.update(_after_deadline(call, list(pending.values()), last))
    return out


def _poll_round(call: _Call, pending: dict[str, str], rows: dict,
                out: dict[str, Entry]) -> list[str]:
    """Move fresh rows to ``out``; pop and return symbols whose foreign lease is gone."""
    retry = []
    for key, s in list(pending.items()):
        row = rows.get(key)
        if _is_fresh(row, call) or _landed(row, call):
            out[s] = _entry(row, call, "shared-wait")
            call.count("shared-wait")
            del pending[key]
        elif not _lease_live(row, call):
            retry.append(s)
            del pending[key]
    return retry


def _after_deadline(call: _Call, symbols: list[str], last: dict) -> dict[str, Entry]:
    if call.asker.priority <= 2:
        return _fetch_and_store(call, symbols, [], set(), last)
    out = {}
    for s in symbols:
        row = last.get(call.key(s))
        if _has_value(row):
            out[s] = _entry(row, call, "shared-wait")
            call.count("shared-wait")
        else:
            call.count("failed")
    return out


# -- bar-writer lease ---------------------------------------------------------------


def _acquire(kind: DataKind, symbol: str, key: str, holder: str, asker: Asker,
             deadline: float) -> bool:
    try:
        if _try_lease(kind, symbol, key, holder):
            return True
        while _monotonic() < deadline:
            _sleep(_POLL_S)
            row = _read_one(key)
            if row is None or row.get("lease_until") is None:
                return False                 # the holder finished: re-read, do not refetch
            if row["lease_until"] <= _now() and _try_lease(kind, symbol, key, holder):
                return True
        return asker.priority <= 2
    except Exception as exc:  # noqa: BLE001 - fail open
        counters.warn_fail_open("lease", exc)
        return False


def _try_lease(kind: DataKind, symbol: str, key: str, holder: str) -> bool:
    with side_connection() as conn:
        return market_shared_repo().try_lease(
            key, holder, float(config.MARKETDATA_LEASE_SECONDS),
            kind=kind.value, symbol=symbol.upper(), conn=conn)


def _read_one(key: str) -> Optional[dict]:
    with side_connection() as conn:
        return market_shared_repo().read_entries([key], conn=conn).get(key)


# -- Postgres touches, each its own short connection, all fail open ------------------


def _read(call: _Call, keys: list[str]) -> Optional[dict]:
    """``{key: row}``, or None when the read failed open."""
    if not keys:
        return {}
    try:
        with side_connection() as conn:
            return market_shared_repo().read_entries(keys, conn=conn)
    except Exception as exc:  # noqa: BLE001 - fail open to a direct fetch
        counters.warn_fail_open("cache read", exc)
        return None


def _read_keys(keys: list[str]) -> dict:
    try:
        with side_connection() as conn:
            return market_shared_repo().read_entries(keys, conn=conn)
    except Exception as exc:  # noqa: BLE001 - fail open
        counters.warn_fail_open("cache read", exc)
        return {}


def _write(rows: list[dict]) -> None:
    if not rows:
        return
    try:
        with side_connection() as conn:
            market_shared_repo().write_entries(rows, conn=conn)
    except Exception as exc:  # noqa: BLE001 - write-back is best effort
        counters.warn_fail_open("cache write", exc)


def _release_keys(holder: str, keys) -> None:
    keys = list(keys)
    if not keys:
        return
    try:
        with side_connection() as conn:
            repo = market_shared_repo()
            for key in keys:
                repo.release_lease(key, holder, conn=conn)
    except Exception as exc:  # noqa: BLE001 - an unreleased lease expires on its own
        counters.warn_fail_open("lease release", exc)


# -- row predicates ------------------------------------------------------------------


def _has_fetched(row: Optional[dict]) -> bool:
    return bool(row) and row.get("fetched_at") is not None


def _has_value(row: Optional[dict]) -> bool:
    return _has_fetched(row) and "value" in row


def _is_fresh(row: Optional[dict], call: _Call) -> bool:
    """Has a value and is within the window; None = any age, 0 = never served from cache."""
    if not _has_value(row):
        return False
    if call.window is None:
        return True
    age = (_now() - row["fetched_at"]).total_seconds()
    return call.window > 0 and age <= call.window


def _landed(row: Optional[dict], call: _Call) -> bool:
    """A value written after this call started: as fresh as one it would fetch itself."""
    return _has_value(row) and row["fetched_at"] >= call.started


def _lease_live(row: Optional[dict], call: _Call) -> bool:
    if not row or row.get("lease_until") is None:
        return False
    return row["lease_until"] > _now() and row.get("lease_holder") != call.holder


def _entry(row: dict, call: _Call, outcome: str) -> Entry:
    return _row_entry(row, call.decode(row["value"]), call.provider, outcome)


def _row_entry(row: dict, value: Any, provider: str, outcome: str) -> Entry:
    return Entry(value, row["fetched_at"], row.get("source") or provider, outcome)
