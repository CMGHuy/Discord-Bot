"""v172: one live equity sample every 5 minutes, written from trade_monitor.

The trade monitor already prices the open book every 60 seconds. After this
tick's closes have landed (per-ticker hits and the plan-manager tick),
`record_sample` re-reads every trade, values the account through the one
equity definition (`swingbot.core.tracking.equity.snapshot_at`) at the
prices this tick fetched, and writes one `equity_samples` row
(`source="live"`, `kind="point"`).

Rules (spec v172 § 2, Corrections 3 and 6):
- regular US session only (`is_regular_session`): the monitor itself runs
  around the clock;
- at most one row per `SAMPLE_INTERVAL`: the first tick at least 5 minutes
  after the last written live row, seeded from the table after a restart;
- no market-data call of its own; an unpriced or unsized position is
  counted in `skipped_n`, never priced at 0;
- never raises: a failure is logged once per process per exception type
  (later ones at DEBUG) and the sample skipped. A missed sample is a gap,
  never an invented value.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from swingbot.core.infra.swallowed import swallowed
from swingbot.core.db.repositories.equity_samples import (EquitySampleRepository,
                                                          equity_samples_repo)
from swingbot.core.market.session import is_regular_session
from swingbot.core.tracking import equity

log = logging.getLogger(__name__)

SAMPLE_INTERVAL = timedelta(minutes=5)

# Process-local, like loops._recap_fired_date: the table is the durable record.
_state: dict = {"last_at": None, "seeded": False}
_warned: set[str] = set()


def reset_state() -> None:
    """Test hook: forget the throttle and the exception types already warned about."""
    _state.update(last_at=None, seeded=False)
    _warned.clear()


def load_trades() -> list[dict]:
    """Every trade, read now: the monitor's own list is stale after its closes."""
    from swingbot.core.tracking.performance import TradeLog
    return TradeLog().get_trades(status=None, limit=None, sort_by="opened_at") or []


def _priced(live_prices: dict | None) -> dict[str, float]:
    """Only real prints: a missing, zero or negative price leaves the position unpriced."""
    return {ticker: price for ticker, price in (live_prices or {}).items()
            if price is not None and price > 0}


def _last_written(repo: EquitySampleRepository) -> datetime | None:
    if not _state["seeded"]:
        _state["last_at"] = repo.latest_at("live")
        _state["seeded"] = True
    return _state["last_at"]


def _due(now: datetime, repo: EquitySampleRepository) -> bool:
    last = _last_written(repo)
    return last is None or now - last >= SAMPLE_INTERVAL


def _row(snapshot: equity.EquitySnapshot, now: datetime) -> dict:
    return {"at": now, "realized_balance": snapshot.realized_balance,
            "unrealized_pnl": snapshot.unrealized_pnl, "equity": snapshot.equity,
            "open_n": snapshot.open_n, "skipped_n": snapshot.skipped_n,
            "source": "live", "kind": "point", "backfill_run": None}


def _record(live_prices: dict, now: datetime, repo: EquitySampleRepository) -> bool:
    if not is_regular_session(now) or not _due(now, repo):
        return False
    snapshot = equity.snapshot_at(load_trades(), equity.load_plans_by_id(),
                                  _priced(live_prices), now, equity.starting_balance())
    repo.insert_sample(_row(snapshot, now))
    _state["last_at"] = now
    return True


def _first_of_kind(exc: Exception) -> bool:
    """True once per process per exception type (that one is logged at WARNING)."""
    kind = type(exc).__name__
    first = kind not in _warned
    _warned.add(kind)
    return first


def record_sample(live_prices: dict[str, float], *, now: datetime | None = None,
                  repo: EquitySampleRepository | None = None) -> bool:
    """Write one live sample when due; True when a row was written. Never raises."""
    try:
        moment = now or datetime.now(timezone.utc)
        return _record(live_prices, moment, repo or equity_samples_repo())
    except Exception as exc:  # noqa: BLE001 -- recording must never break the monitor
        first = _first_of_kind(exc)
        swallowed(log, "ops.equity_record_sample", exc,
                  "equity sample skipped (%s%s): %s", type(exc).__name__,
                  "; repeats of this error logged at DEBUG" if first else "", exc,
                  level=logging.WARNING if first else logging.DEBUG, exc_info=first)
        return False
