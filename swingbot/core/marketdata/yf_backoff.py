"""v248 § 4: per-ticker yfinance backoff.

A ticker yfinance cannot serve is retried every cycle. After ``MISSES_TO_SKIP``
consecutive misses its yfinance fallback pauses ``FIRST_PAUSE``; each further miss
doubles the pause up to ``MAX_PAUSE``; one success resets it. A held ticker in the
regular session is never paused longer than ``HELD_PRICE_STALE_ALERT_MIN``.

State lives in ``market_cache`` rows of kind ``yf_backoff`` so the bot and the
refresher share it and it survives a restart. It fails open (a busy or down side
pool never stops yfinance); Alpaca is never touched here; only
``MARKETDATA_LAYER == "on"`` touches the store.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from swingbot import config
from swingbot.core.db.repositories.market_shared import market_shared_repo
from swingbot.core.db.side_engine import side_connection
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.market import session

log = logging.getLogger(__name__)

KIND = "yf_backoff"
MISSES_TO_SKIP = 3
FIRST_PAUSE = timedelta(minutes=30)
MAX_PAUSE = timedelta(hours=4)
_HELD_TTL = timedelta(seconds=60)

_held: tuple[datetime, frozenset[str]] | None = None


@dataclass(frozen=True)
class BackoffState:
    misses: int = 0
    skip_until: datetime | None = None
    written_at: datetime | None = None


@dataclass(frozen=True)
class BackoffBatch:
    fetch: list[str]
    skipped: list[str]
    states: dict[str, BackoffState] = field(default_factory=dict)
    known: bool = True


def entry_key(symbol: str) -> str:
    return f"{KIND}:{symbol.upper()}"


def after_miss(state: BackoffState, now: datetime) -> BackoffState:
    misses = state.misses + 1
    if misses < MISSES_TO_SKIP:
        return BackoffState(misses, None, now)
    pause = min(FIRST_PAUSE * (2 ** min(misses - MISSES_TO_SKIP, 4)), MAX_PAUSE)
    return BackoffState(misses, now + pause, now)


def is_skipped(state: BackoffState, now: datetime, *, held_in_session: bool,
               held_cap: timedelta) -> bool:
    until = state.skip_until
    if until is None:
        return False
    if held_in_session and state.written_at is not None:
        until = min(until, state.written_at + held_cap)
    return now < until


def _store_on() -> bool:
    return config.MARKETDATA_LAYER == "on"


def _parse_state(record: dict) -> BackoffState:
    try:
        value = record.get("value") or {}
        until = value.get("skip_until")
        return BackoffState(int(value["misses"]),
                            datetime.fromisoformat(until) if until else None,
                            record.get("fetched_at"))
    except (KeyError, TypeError, ValueError, AttributeError):
        return BackoffState()


def _read_states(tickers: list[str]) -> dict[str, BackoffState] | None:
    try:
        with side_connection() as conn:
            found = market_shared_repo().read_entries([entry_key(t) for t in tickers], conn=conn)
    except Exception as exc:  # noqa: BLE001 - fail open to a direct fetch
        swallowed(log, "marketdata.yf_backoff.read", exc, level=logging.DEBUG)
        return None
    return {t: _parse_state(found[entry_key(t)]) if entry_key(t) in found else BackoffState()
            for t in tickers}


def _write_rows(rows: list[dict]) -> None:
    try:
        with side_connection() as conn:
            market_shared_repo().write_entries(rows, conn=conn)
    except Exception as exc:  # noqa: BLE001 - fail open
        swallowed(log, "marketdata.yf_backoff.write", exc, level=logging.DEBUG)


def _held_for(states: dict[str, BackoffState], now: datetime) -> frozenset[str]:
    in_backoff = any(s.skip_until is not None and s.skip_until > now for s in states.values())
    if in_backoff and session.session_state(now) == session.SESSION_REGULAR:
        return held_symbols(now)
    return frozenset()


def partition(tickers: list[str], now: datetime | None = None) -> BackoffBatch:
    now = now or datetime.now(timezone.utc)
    if not _store_on() or not tickers:
        return BackoffBatch(list(tickers), [], {})
    states = _read_states(list(tickers))
    if states is None:
        return BackoffBatch(list(tickers), [], {}, known=False)
    held = _held_for(states, now)
    cap = timedelta(minutes=int(config.HELD_PRICE_STALE_ALERT_MIN))
    fetch: list[str] = []
    skipped: list[str] = []
    for t in tickers:
        skip = is_skipped(states[t], now, held_in_session=t.upper() in held, held_cap=cap)
        (skipped if skip else fetch).append(t)
    return BackoffBatch(fetch, skipped, states)


def _next_state(prior: BackoffState, hit: bool, now: datetime,
                ticker: str = "") -> BackoffState | None:
    if hit:
        if prior.misses <= 0:
            return None
        if prior.misses >= MISSES_TO_SKIP:
            log.info("yfinance backoff: %s leaves after a fetch", ticker)
        return BackoffState()
    new = after_miss(prior, now)
    if new.misses == MISSES_TO_SKIP:
        log.info("yfinance backoff: %s enters after %d misses, skipped until %s",
                 ticker, new.misses, new.skip_until)
    return new


def _row(ticker: str, state: BackoffState, now: datetime) -> dict:
    return {"key": entry_key(ticker), "kind": KIND, "symbol": ticker.upper(),
            "fetched_at": now, "source": "yfinance",
            "value": {"misses": state.misses,
                      "skip_until": state.skip_until.isoformat() if state.skip_until else None}}


def record(batch: BackoffBatch, got: Iterable[str], now: datetime | None = None) -> None:
    if not _store_on() or not batch.known:
        return
    now = now or datetime.now(timezone.utc)
    got_set = set(got)
    rows = []
    for t in batch.fetch:
        state = _next_state(batch.states.get(t, BackoffState()), t in got_set, now, t)
        if state is not None:
            rows.append(_row(t, state, now))
    if rows:
        _write_rows(rows)


def held_symbols(now: datetime | None = None) -> frozenset[str]:
    global _held
    now = now or datetime.now(timezone.utc)
    if _held is not None and _held[0] <= now < _held[0] + _HELD_TTL:
        return _held[1]
    try:
        from swingbot.core.db.repositories import trades as trades_mod
        rows = trades_mod.trades_repo().open_trades()
    except Exception as exc:  # noqa: BLE001 - keep the last good set, retry next call
        swallowed(log, "marketdata.yf_backoff.held", exc, level=logging.DEBUG)
        return _held[1] if _held is not None else frozenset()
    symbols = frozenset(str(r["ticker"]).upper() for r in rows if r.get("ticker"))
    _held = (now, symbols)
    return symbols


def _reset_for_tests() -> None:
    global _held
    _held = None
