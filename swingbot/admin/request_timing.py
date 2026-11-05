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

from flask import Flask, g, request
from sqlalchemy import event

from swingbot import config
from swingbot.core.db import engine as db_engine
from swingbot.core.infra.swallowed import swallowed

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


API_PREFIX = "/api/v1"
_G_KEY = "_v205_request_timing"
_DEFAULT_SLOW_MS = 2000


def server_timing(total_s: float, tally: SqlTally) -> str:
    """The header value; V205-1's timing script parses exactly this."""
    return (f"total;dur={total_s * 1000:.1f}, "
            f'db;dur={tally.db_s * 1000:.1f};desc="{tally.statements} statements"')


def install(app: Flask) -> None:
    """Time every /api/v1 request of ``app``; count its SQL. Called once by app.py."""
    install_sql_counter()
    app.before_request(_begin)
    app.after_request(_finish)
    app.teardown_request(_teardown)


def _begin() -> None:
    if request.path.startswith(API_PREFIX):
        setattr(g, _G_KEY, (time.perf_counter(), start_request()))


def _finish(response):
    state = g.get(_G_KEY)
    if state is None:
        return response
    total_s = time.perf_counter() - state[0]
    tally = current() or SqlTally()
    response.headers["Server-Timing"] = server_timing(total_s, tally)
    _log_if_slow(request.path, total_s, tally)
    return response


def _log_if_slow(path: str, total_s: float, tally: SqlTally) -> None:
    """Read per request, so a saved .env applies on the next request."""
    total_ms = total_s * 1000
    if total_ms > float(getattr(config, "ADMIN_SLOW_REQUEST_MS", _DEFAULT_SLOW_MS)):
        log.warning("slow request %s total=%.0fms db=%.0fms statements=%d",
                    path, total_ms, tally.db_s * 1000, tally.statements)


def _teardown(_exc) -> None:
    state = g.pop(_G_KEY, None)
    if state is None:
        return
    try:
        end_request(state[1])
    except ValueError as exc:
        # A streamed response (the SSE route) can tear down in another
        # context, where the token is foreign: clear the var instead.
        swallowed(log, "ops.request_timing.end_request", exc, level=logging.DEBUG)
        _TALLY.set(None)
