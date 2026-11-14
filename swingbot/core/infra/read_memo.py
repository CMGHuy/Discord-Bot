"""Load each store once per admin read request (v205 L1-c).

A leaf module: it imports nothing from ``swingbot`` (or flask), so core stores
can read through it without a core -> admin import.

The memo is **opt-in**. Nothing is memoised unless a caller has entered
``scope()``; the admin's GET views do so through ``@read_scope``
(``swingbot/admin/api_v1/read_scope.py``). Outside a scope -- the bot, the
refresher, scripts, every write -- ``records()``/``mapping()`` return the
loader's own result, exactly today's direct call.

Inside a scope the first call per key stores the loader's result and every call
returns **shallow copies** of it (a new list or dict of new top-level dicts), so
each caller owns its records' top level as it owns the fresh dicts a store's
``_all()`` builds. Nested values are shared within the scope; no read path may
write into them (V205-8's frozen-memo test). A store call that passes ``conn``
(a transaction) never reads through here.

A **backing** (v218) may serve each scope's first load of a key:
``set_backing(fn)`` makes ``_stored`` call ``fn(key, loader)`` instead of
``loader()``. The admin app installs ``store_snapshot.read`` there (a
cross-request snapshot of raw records); this module still copies per caller
and still imports nothing from ``swingbot``. With no backing (the bot, the
refresher, scripts) behaviour is exactly the above.

The memo lives in a ``contextvars.ContextVar``: each gunicorn thread has its own
context, and ``scope()`` resets its token in ``finally``, so no memo outlives
its request or crosses to another thread.
"""
from __future__ import annotations

import contextlib
import contextvars
from typing import Callable, Iterator

TRADE_ROWS = "trade_rows"   # account._sum_realized_pnl: normalised trades rows
TRADES = "trades"           # TradeLog._all: trades in TradeLog's JSON shape
PLANS = "plans"             # PlanStore._all: plan_id -> plan record
NOTED_IDS = "noted_ids"     # admin trades._noted_ids: journal entries that carry a note

_MEMO: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "swingbot_read_memo", default=None)

_BACKING: Callable[[str, Callable[[], object]], object] | None = None


def set_backing(fn: Callable[[str, Callable[[], object]], object] | None) -> None:
    """Route each scope's first load of a key through ``fn(key, loader)``; None = load directly."""
    global _BACKING
    _BACKING = fn


@contextlib.contextmanager
def scope() -> Iterator[None]:
    """Memoise store reads until the block exits; a nested scope reuses the outer memo."""
    if _MEMO.get() is not None:
        yield
        return
    token = _MEMO.set({})
    try:
        yield
    finally:
        _MEMO.reset(token)


def active() -> bool:
    """True inside ``scope()``."""
    return _MEMO.get() is not None


def _stored(key: str, loader: Callable[[], object]) -> object | None:
    """The memoised value for ``key`` (loading it once), or None outside a scope."""
    memo = _MEMO.get()
    if memo is None:
        return None
    if key not in memo:
        backing = _BACKING
        # A raising loader (or backing) stores nothing.
        memo[key] = loader() if backing is None else backing(key, loader)
    return memo[key]


def records(key: str, loader: Callable[[], list[dict]]) -> list[dict]:
    """``loader()`` outside a scope; inside, per-call shallow copies of the memoised records."""
    if not active():
        return loader()
    return [dict(record) for record in _stored(key, loader)]


def mapping(key: str, loader: Callable[[], dict[str, dict]]) -> dict[str, dict]:
    """``loader()`` outside a scope; inside, a per-call copy with each value copied."""
    if not active():
        return loader()
    return {name: dict(record) for name, record in _stored(key, loader).items()}


def peek(key: str) -> object | None:
    """Test seam: the stored value for ``key``, or None (never loads)."""
    memo = _MEMO.get()
    return None if memo is None else memo.get(key)
