"""Per-ticker memo for indicator calls repeated on one frame (v245 V245-5).

_scan_one builds every horizon from the same frame object, and several
level sources repeat across horizons with equal parameters (Bollinger 20/2,
the 20-bar Donchian channel, the FVG candidates). Inside a ticker_memo()
scope, memo() returns the earlier result for the same key on the same frame
object -- the same computation on the same input, so the same floats.
Outside a scope it just calls fn(), so every other caller (rescenario,
outlook, replay, backtests) behaves exactly as before.

Entries hold a reference to their frame, so an id() is never reused while
its entry lives; the scope ends with the _scan_one call. Exceptions are not
stored. The state is thread-local. Callers only read a shared result.
"""
from __future__ import annotations

import functools
import threading
from contextlib import contextmanager
from typing import Callable, Iterator, TypeVar

T = TypeVar("T")
_state = threading.local()


@contextmanager
def ticker_memo() -> Iterator[None]:
    """A fresh memo for the duration of one ticker's analysis; nests."""
    previous = getattr(_state, "entries", None)
    _state.entries = {}
    try:
        yield
    finally:
        _state.entries = previous


def memo(df, key: tuple, fn: Callable[[], T]) -> T:
    """fn()'s result, shared within the active scope for (df object, key)."""
    entries = getattr(_state, "entries", None)
    if entries is None:
        return fn()
    slot = (id(df), *key)
    hit = entries.get(slot)
    if hit is not None and hit[0] is df:
        return hit[1]
    value = fn()
    entries[slot] = (df, value)
    return value


def with_ticker_memo(fn: Callable[..., T]) -> Callable[..., T]:
    """Decorator: run fn inside its own ticker_memo() scope."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with ticker_memo():
            return fn(*args, **kwargs)
    return wrapper
