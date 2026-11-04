"""Per-request SQL tally for the admin (v205 L1-d).

``start_request()`` puts a fresh ``SqlTally`` in a contextvar; the cursor
listeners add each statement's count and duration to it while it is set and
do nothing otherwise. A contextvar, not a global: gunicorn runs one worker
with 16 threads, and each request thread sees only its own tally.

The listener reaches an engine only through ``engine.add_engine_hook``, which
only this module calls (``install_sql_counter``), and only the admin app
imports it. The bot's and the refresher's engines never carry it.
"""
from __future__ import annotations

import contextvars
import logging
import time
from dataclasses import dataclass

from sqlalchemy import event

from swingbot.core.db import engine as db_engine

log = logging.getLogger(__name__)

_T0_KEY = "v205_statement_t0"


@dataclass
class SqlTally:
    statements: int = 0
    db_s: float = 0.0


_TALLY: contextvars.ContextVar[SqlTally | None] = contextvars.ContextVar("v205_sql_tally", default=None)


def start_request() -> contextvars.Token:
    return _TALLY.set(SqlTally())


def end_request(token: contextvars.Token) -> SqlTally:
    """The finished tally; the contextvar is back to what it was before."""
    tally = _TALLY.get() or SqlTally()
    _TALLY.reset(token)
    return tally


def current() -> SqlTally | None:
    return _TALLY.get()


def _before(conn, cursor, statement, parameters, context, executemany) -> None:
    if _TALLY.get() is not None:
        conn.info[_T0_KEY] = time.perf_counter()


def _after(conn, cursor, statement, parameters, context, executemany) -> None:
    started = conn.info.pop(_T0_KEY, None)
    tally = _TALLY.get()
    if tally is None or started is None:
        return
    tally.statements += 1
    tally.db_s += time.perf_counter() - started


def _attach(target) -> None:
    """Install both cursor listeners on ``target`` once."""
    if event.contains(target, "before_cursor_execute", _before):
        return
    event.listen(target, "before_cursor_execute", _before)
    event.listen(target, "after_cursor_execute", _after)


def install_sql_counter() -> None:
    """Count statements on every engine the admin process creates."""
    db_engine.add_engine_hook(_attach)
