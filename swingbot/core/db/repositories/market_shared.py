"""The v171 shared market-data layer's store: cache rows with single-flight leases,
one token bucket and breaker per provider, and hourly fetch counts (spec D1/D6/D9).

Every method takes a required ``conn`` (the side engine's autocommit connection)
and issues exactly one statement, so each call is one round trip under the
layer's statement timeout. Times come from ``clock_timestamp()``, never
``now()``, which is frozen for the length of a transaction.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Iterable, Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import market_cache, market_fetch_counts, provider_budget

#: The flat keys of a cache record that are columns; absent ones read back as None.
_CACHE_FIELDS = ("key", "kind", "symbol", "fetched_at", "source", "lease_holder", "lease_until")
_COUNT_FIELDS = ("hour", "provider", "kind", "asker", "outcome")


def _now():
    return sa.func.clock_timestamp()


def _interval(seconds: float):
    return sa.func.make_interval(0, 0, 0, 0, 0, 0, float(seconds))


class MarketSharedRepository:
    """Spans three tables, so it is not a ``Repository`` subclass; it holds one per table."""

    def __init__(self):
        self.cache = Repository(market_cache, key="key")
        self.budget = Repository(provider_budget, key="provider")
        self.counts = Repository(market_fetch_counts, key="id")

    # -- cache entries and leases -------------------------------------------------

    def read_entries(self, keys: Iterable[str], *, conn: sa.Connection) -> dict[str, dict]:
        """``{key: record}`` for every key that has a row, in one statement."""
        keys = list(keys)
        if not keys:
            return {}
        c = market_cache.c
        param = sa.bindparam("keys", keys, type_=postgresql.ARRAY(sa.Text))
        rows = conn.execute(sa.select(market_cache).where(c.key == sa.any_(param))).all()
        return {row.key: {**dict.fromkeys(_CACHE_FIELDS), **self.cache._record(row)}
                for row in rows}

    def write_entries(self, rows: Sequence[dict], *, conn: sa.Connection) -> None:
        """Upsert cached values; a written value always clears the key's lease."""
        if not rows:
            return
        values = [{**dict.fromkeys(_CACHE_FIELDS), **self.cache._values(r),
                   "lease_holder": None, "lease_until": None} for r in rows]
        ins = pg_insert(market_cache).values(values)
        x = ins.excluded
        conn.execute(ins.on_conflict_do_update(index_elements=[market_cache.c.key], set_={
            "kind": x.kind, "symbol": x.symbol, "fetched_at": x.fetched_at, "source": x.source,
            "doc": x.doc, "lease_holder": None, "lease_until": None, "updated_at": _now()}))

    def try_lease(self, key: str, holder: str, seconds: float, *, kind: str, symbol: str,
                  conn: sa.Connection) -> bool:
        """Claim the key's single-flight lease: free, expired or already ours."""
        c = market_cache.c
        until = _now() + _interval(seconds)
        ins = pg_insert(market_cache).values(key=key, kind=kind, symbol=symbol,
                                             lease_holder=holder, lease_until=until)
        stmt = ins.on_conflict_do_update(
            index_elements=[c.key],
            set_={"lease_holder": ins.excluded.lease_holder, "lease_until": ins.excluded.lease_until},
            where=sa.or_(c.lease_until.is_(None), c.lease_until < _now(), c.lease_holder == holder),
        ).returning(c.key)
        return conn.execute(stmt).first() is not None

    def release_lease(self, key: str, holder: str, *, conn: sa.Connection) -> None:
        """Drop the lease only if ``holder`` still holds it."""
        c = market_cache.c
        conn.execute(sa.update(market_cache)
                     .where(c.key == key, c.lease_holder == holder)
                     .values(lease_holder=None, lease_until=None))

    # -- shared token bucket and breaker ------------------------------------------

    def take_token(self, provider: str, capacity: float, per_minute: float, reserve: float, *,
                   conn: sa.Connection) -> bool:
        """Refill by elapsed time and take one token, only if ``reserve`` remains after."""
        if float(capacity) - 1.0 < float(reserve):
            return False                       # the bucket can never hold enough
        c = provider_budget.c
        elapsed = sa.extract("epoch", _now() - c.stamp)
        refilled = sa.func.least(float(capacity), c.tokens + elapsed * (float(per_minute) / 60.0))
        ins = pg_insert(provider_budget).values(provider=provider, tokens=float(capacity) - 1.0,
                                                stamp=_now())
        stmt = ins.on_conflict_do_update(
            index_elements=[c.provider],
            set_={"tokens": refilled - 1.0, "stamp": _now(), "updated_at": _now()},
            where=(refilled - 1.0 >= float(reserve)),
        ).returning(c.tokens)
        return conn.execute(stmt).first() is not None

    def breaker_state(self, provider: str, *, conn: sa.Connection) -> tuple[int, datetime | None]:
        """``(consecutive failures, open until)``; ``(0, None)`` with no row."""
        c = provider_budget.c
        row = conn.execute(sa.select(c.breaker_failures, c.breaker_open_until)
                           .where(c.provider == provider)).first()
        return (0, None) if row is None else (int(row[0]), row[1])

    def breaker_record(self, provider: str, ok: bool, failures_to_open: int,
                       cooldown_s: float, *, conn: sa.Connection) -> None:
        """Success resets the count (never shortens an open window); the n-th failure opens."""
        c = provider_budget.c
        open_until = _now() + _interval(cooldown_s)
        opens_now = (not ok) and 1 >= int(failures_to_open)
        ins = pg_insert(provider_budget).values(
            provider=provider, tokens=0.0,
            stamp=_now() - sa.text("interval '1 hour'"),   # a breaker-created row refills to full
            breaker_failures=0 if ok else 1,
            breaker_open_until=open_until if opens_now else None)
        if ok:
            updates = {"breaker_failures": 0}
        else:
            updates = {"breaker_failures": c.breaker_failures + 1,
                       "breaker_open_until": sa.case(
                           (c.breaker_failures + 1 >= int(failures_to_open), open_until),
                           else_=c.breaker_open_until)}
        conn.execute(ins.on_conflict_do_update(index_elements=[c.provider],
                                               set_={**updates, "updated_at": _now()}))

    # -- hourly counts --------------------------------------------------------------

    def add_counts(self, rows: Iterable[tuple], *, conn: sa.Connection) -> None:
        """Add ``(hour, provider, kind, asker, outcome, n)`` rows to the hourly counters."""
        totals: Counter = Counter()
        for row in rows:
            totals[tuple(row[:5])] += int(row[5])
        if not totals:
            return
        values = [{**dict(zip(_COUNT_FIELDS, k)), "n": n, "doc": {}} for k, n in totals.items()]
        ins = pg_insert(market_fetch_counts).values(values)
        conn.execute(ins.on_conflict_do_update(
            constraint="market_fetch_counts_key_uq",
            set_={"n": market_fetch_counts.c.n + ins.excluded.n, "updated_at": _now()}))

    def count_rows(self, since: datetime, until: datetime, *, conn: sa.Connection) -> list[dict]:
        """Counter rows with ``since <= hour < until``, in a stable order."""
        c = market_fetch_counts.c
        cols = [c[name] for name in (*_COUNT_FIELDS, "n")]
        stmt = (sa.select(*cols).where(c.hour >= since, c.hour < until)
                .order_by(*cols[:5]))
        return [dict(row._mapping) for row in conn.execute(stmt).all()]


_repo: MarketSharedRepository | None = None


def market_shared_repo() -> MarketSharedRepository:
    global _repo
    if _repo is None:
        _repo = MarketSharedRepository()
    return _repo
