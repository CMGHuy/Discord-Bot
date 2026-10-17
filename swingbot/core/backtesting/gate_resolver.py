"""v147: the nightly resolver for live `gate_rejections` rows.

Selects pending rows whose walk window has closed, loads daily bars from the
live `market_data/` cache through `data_store.load_normalized` -- never a
`get_daily_data_batch` cold fetch (known-traps § two OHLCV caches) -- runs
`gate_counterfactual.simulate_blocked` and writes the outcome once.

Bars stop at the last NYSE session strictly before `today`, so a bar still
forming when the resolver runs is never read. A due row the simulator still
calls `pending` (the cache is short or missing) is re-checked once per session,
up to GRACE_SESSIONS times, then `no-data`. A resolved row is never resolved
again: the repository only updates rows whose `cf_status` is still `pending`.
Runs off the event loop (`loops.gate_counterfactual_resolve`, `asyncio.to_thread`).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import logging
from collections import Counter

import pandas as pd

from swingbot.core.backtesting import gate_counterfactual as gc
from swingbot.core.market.session import nyse_calendar
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.plan_types import plan_from_dict

log = logging.getLogger(__name__)

RESOLVE_BATCH_CAP = 200
GRACE_SESSIONS = 5
PENDING_SCAN_CAP = 5000
_CANDIDATE_FIELDS = tuple(f.name for f in dataclasses.fields(gc.BlockedCandidate))
_UNREAD = gc.CounterfactualResult("pending", None, None, None, None, None, False, None)


def due_bars(horizon: str, expiry_bars: int | None) -> int:
    """Sessions after the signal bar before a row can resolve: pending window + horizon hold.
    With no plan the pending window is unknown, so 0 -- a lower bound, never late."""
    return int(expiry_bars or 0) + int(HORIZONS[horizon]["max_holding_days"])


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _load_daily(ticker: str):
    from swingbot.core.marketdata import data_store
    return data_store.load_normalized(ticker, "daily")


def _default_repo():
    from swingbot.core.db.repositories.gate_rejections import gate_rejections_repo
    return gate_rejections_repo()


def _last_session_before(today: str) -> dt.date:
    calendar = nyse_calendar()
    day = dt.date.fromisoformat(today) - dt.timedelta(days=1)
    while day > calendar.first and not calendar.is_session(day):
        day -= dt.timedelta(days=1)
    return day


def _elapsed(row: dict, last_session: dt.date) -> int:
    signal = dt.date.fromisoformat(row["signal_date"])
    return nyse_calendar().sessions_between(signal, last_session) or 0


def _need(plan: dict | None, horizon: str) -> int:
    """Bars the walk reads after the signal: the plan's own window, else the lower bound."""
    if plan:
        return gc.bars_needed(plan_from_dict(plan))
    return due_bars(horizon, None)


def _due(rows: list, last_session: dt.date, limit: int) -> list[tuple[dict, int]]:
    """Up to `limit` (row, elapsed) pairs whose window has closed and not checked this session."""
    checked_on = last_session.isoformat()
    due = []
    for row in rows:
        elapsed = _elapsed(row, last_session)
        if elapsed >= _need(row.get("plan"), row["horizon"]) and row.get("pending_checked_on") != checked_on:
            due.append((row, elapsed))
        if len(due) >= limit:
            break
    return due


def _closes(bars) -> dict:
    index = pd.DatetimeIndex(bars.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    return dict(zip(index.strftime("%Y-%m-%d"), bars["Close"].astype(float)))


def _signal_close(row: dict, bars) -> float | None:
    """The stored close; for an intraday write, the close implied by its completed basis bar."""
    if row.get("signal_close") is not None:
        return float(row["signal_close"])
    basis_date, basis_close = row.get("basis_date"), row.get("basis_close")
    if bars is None or not basis_date or not basis_close:
        return None
    closes = _closes(bars)
    if basis_date not in closes or row["signal_date"] not in closes:
        return None
    return closes[row["signal_date"]] * float(basis_close) / closes[basis_date]


def _candidate(row: dict, bars) -> gc.BlockedCandidate:
    fields = {name: row.get(name) for name in _CANDIDATE_FIELDS}
    fields["signal_close"] = _signal_close(row, bars)
    return gc.BlockedCandidate(**fields)


def _simulate(row: dict, bars, last_session: dt.date) -> gc.CounterfactualResult:
    if bars is None or len(bars) == 0:
        return _UNREAD                    # a missing cache file waits like a short one
    return gc.simulate_blocked(_candidate(row, bars), bars, last_session=last_session.isoformat())


def _outcome(result: gc.CounterfactualResult) -> dict:
    return {"cf_r": result.cf_r, "win": result.win, "exit_index": result.exit_index,
            "last_bar_date": result.last_bar_date, "bars_sha256": result.bars_sha256,
            "reanchored": result.reanchored, "cf_plan": result.plan}


def _hold_or_expire(row: dict, result, elapsed: int, last_session: dt.date, repo) -> str | None:
    """A due row the simulator still calls pending: count one grace session, or give up."""
    if elapsed < _need(result.plan, row["horizon"]):
        return None                       # the rebuilt plan's own window is still open
    checks = int(row.get("pending_checks") or 0) + 1
    if checks > GRACE_SESSIONS:
        done = repo.resolve(row["id"], cf_status="no-data", resolved_at=_utc_now(),
                            outcome={**_outcome(result), "pending_checks": checks})
        return "no-data" if done else None
    repo.resolve(row["id"], cf_status="pending", resolved_at=None,
                 outcome={"pending_checks": checks, "pending_checked_on": last_session.isoformat()})
    return "pending"


def _resolve_row(row: dict, elapsed: int, last_session: dt.date, repo, load_bars) -> str | None:
    result = _simulate(row, load_bars(row["ticker"]), last_session)
    if result.cf_status == "pending":
        return _hold_or_expire(row, result, elapsed, last_session, repo)
    done = repo.resolve(row["id"], cf_status=result.cf_status, resolved_at=_utc_now(),
                        outcome=_outcome(result))
    return result.cf_status if done else None


def _safe_resolve(row: dict, elapsed: int, last_session: dt.date, repo, load_bars) -> str | None:
    try:
        return _resolve_row(row, elapsed, last_session, repo, load_bars)
    except Exception:   # noqa: BLE001 -- one bad row never costs the night's batch
        log.warning("gate resolver: row %s (%s %s) failed -- left pending", row.get("id"),
                    row.get("ticker"), row.get("signal_date"), exc_info=True)
        return "error"


def resolve_due(today: str, *, limit: int = RESOLVE_BATCH_CAP, repo=None,
                load_bars=None) -> dict[str, int]:
    """Resolve up to `limit` due pending rows as of `today` (ISO date, the ET session date).

    Returns counts per resulting cf_status ("pending" = a grace session counted,
    "error" = the row raised and stays pending). Rows not yet due are untouched."""
    repo = repo if repo is not None else _default_repo()
    load_bars = load_bars if load_bars is not None else _load_daily
    last_session = _last_session_before(today)
    counts: Counter = Counter()
    for row, elapsed in _due(repo.pending(limit=PENDING_SCAN_CAP), last_session, limit):
        status = _safe_resolve(row, elapsed, last_session, repo, load_bars)
        if status is not None:
            counts[status] += 1
    return dict(counts)
