"""v201: the refresher's quote and FX steps.

``quote_step`` is the one place admin market quotes are fetched: one batched
tier-5 call (``data.refresh_quote_batch``) for the symbol set plus the queued
keys, with the yfinance fallback capped per cycle and skipped while a scan
runs, then the index tape. Every symbol is marked in flight before the fetch
and cleared after it -- with an error text when no quote came back -- so the
SPA's spinners always stop. The first marks of a cycle raise one ``market``
NOTIFY (the partner wants the spinner for refreshes the refresher started on
its own); ``loop.run_cycle`` raises the second once values have landed.

``fx_step`` resolves quote-currency codes for every symbol it sees (and, on a
full cycle, every ticker ever traded) and refreshes the pair frames.
``fx_snap_step`` (v205) writes the day's FX rate rows from 08:00 Berlin.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import sqlalchemy as sa

from swingbot import config
from swingbot.core.db import engine, notify
from swingbot.core.db.repositories.market_refresh import quote_currency_repo, refresh_mark_repo
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata import data, fx, fx_snap
from swingbot.core.marketdata.shared import admin_refresh, tape
from swingbot.core.marketdata.shared.kinds import Asker

if TYPE_CHECKING:
    from swingbot.refresher.loop import CycleContext

log = logging.getLogger(__name__)

NO_QUOTE = "no quote"
NO_QUOTE_DURING_SCAN = "no quote (yfinance fallback skipped during a scan)"


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _keys(symbols) -> list[str]:
    return [admin_refresh.quote_mark_key(s) for s in symbols]


def _announce_marks(ctx: "CycleContext") -> None:
    """One ``market`` NOTIFY per cycle, right after its first marks are set."""
    if ctx.marks_announced:
        return
    ctx.marks_announced = True
    try:
        notify.publish("market")
    except Exception as exc:  # noqa: BLE001 - a missed NOTIFY never stops a refresh
        swallowed(log, "ops.refresher.notify_marks", exc, level=logging.WARNING)


def _miss_reason(ctx: "CycleContext") -> str:
    return NO_QUOTE_DURING_SCAN if ctx.scan_running else NO_QUOTE


def _mark(ctx: "CycleContext", keys: list[str]):
    marks = refresh_mark_repo()
    marks.mark(keys, timeout_s=float(config.ADMIN_REFRESH_MARK_TIMEOUT_S), now=ctx.now)
    _announce_marks(ctx)
    ctx.report.changed = True
    return marks


def _settle(ctx: "CycleContext", marks, ok: list[str], missed: list[str]) -> None:
    marks.clear(_keys(ok), now=ctx.now)
    marks.clear(_keys(missed), error=_miss_reason(ctx), now=ctx.now)


def quote_step(ctx: "CycleContext") -> None:
    wanted = list(dict.fromkeys([*ctx.symbols.quotes, *(s.upper() for s in ctx.queued_quotes)]))
    if wanted:
        _refresh_quotes(ctx, wanted)
    if ctx.symbols.index and not ctx.scan_running:
        _refresh_index(ctx, list(ctx.symbols.index))


def _refresh_quotes(ctx: "CycleContext", wanted: list[str]) -> None:
    keys = _keys(wanted)
    marks = _mark(ctx, keys)
    limit = 0 if ctx.scan_running else int(config.ADMIN_REFRESH_YF_FALLBACK_CAP)
    try:
        got = data.refresh_quote_batch(wanted, yf_limit=limit)
    except Exception as exc:
        marks.clear(keys, error=_describe(exc), now=ctx.now)
        raise                                   # loop records it; last values stay cached
    ok = [s for s in wanted if s in got]
    missed = [s for s in wanted if s not in got]
    _settle(ctx, marks, ok, missed)
    ctx.report.quotes_ok, ctx.report.quotes_missed = tuple(ok), tuple(missed)
    ctx.report.fallback_used = sum(1 for q in got.values()
                                   if str(getattr(q, "source", "")).startswith("yfinance"))


def _refresh_index(ctx: "CycleContext", syms: list[str]) -> None:
    """The index tape is a yfinance call: never run while a scan runs."""
    keys = _keys(syms)
    marks = _mark(ctx, keys)
    try:
        got = tape.refresh_tape(syms, asker=Asker.ADMIN_REFRESH, max_age_s=0) or {}
    except Exception as exc:
        marks.clear(keys, error=_describe(exc), now=ctx.now)
        raise
    _settle(ctx, marks, [s for s in syms if s in got], [s for s in syms if s not in got])


def _traded_tickers() -> list[str]:
    """Every ticker ever traded: closed trades' amounts are converted too, and
    their tickers are in no symbol set. Unreadable reads as none."""
    try:
        with engine.get_engine().connect() as conn:
            rows = conn.execute(sa.text("SELECT DISTINCT ticker FROM trades")).scalars()
            return [str(t).upper() for t in rows if t]
    except Exception as exc:  # noqa: BLE001
        swallowed(log, "ops.refresher.traded_tickers", exc, level=logging.DEBUG)
        return []


def fx_step(ctx: "CycleContext") -> None:
    full = bool(ctx.symbols.quotes)
    symbols = [*ctx.symbols.quotes, *(s.upper() for s in ctx.queued_quotes)]
    if full:
        symbols += _traded_tickers()
    symbols = list(dict.fromkeys(symbols))
    if not symbols:
        return
    fx.refresh_quote_codes(symbols, now=ctx.now)
    if full:
        rows = quote_currency_repo().get_many(symbols)
        fx.refresh_pair_frames({row["code"] for row in rows.values() if row.get("code")})


def fx_snap_step(ctx: "CycleContext") -> None:
    """v205: from 08:00 Berlin, the day's fx_daily_rates rows (insert-if-absent).

    Runs every cycle, after `fx_step` and even when it returned early. A failure
    is swallowed and stays out of `report.error`, because a missed snap does not
    make quotes stale and the next cycle writes the same row. Before
    `alembic upgrade head` creates the table, each cycle logs one warning."""
    try:
        fx_snap.snap(ctx.now)
    except Exception as exc:  # noqa: BLE001 - a missed snap never fails the cycle
        swallowed(log, "ops.refresher.fx_snap", exc, "fx snap failed: %s", exc,
                  level=logging.WARNING)
