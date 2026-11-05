"""v205 L1-c: open the core read memo for one admin GET view.

`swingbot.core.infra.read_memo` loads each store once per scope; outside a
scope every store call is today's direct call. The admin opens a scope only
here, only on the GET views plan v205 lists (V205-9), and never on a write
route: tests/admin_perf/test_read_scope_routes.py enumerates the url map.

Place it under ``@require_auth``: that wrapper's ``functools.wraps`` copies
``READ_SCOPE_ATTR`` outward to the function Flask registers."""
from __future__ import annotations

import functools

from swingbot.core.infra import read_memo

READ_SCOPE_ATTR = "__read_scope__"


def read_scope(view):
    """Run ``view`` inside one read-memo scope; the scope resets in its own ``finally``."""

    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        with read_memo.scope():
            return view(*args, **kwargs)

    setattr(wrapper, READ_SCOPE_ATTR, True)
    return wrapper
