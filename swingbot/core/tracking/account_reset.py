"""v189 A6: clearing history is an archived full reset.

Order (spec D4 A6):
  1. refuse while the kill switch is tripped, unless forced (it is never cleared here);
  2. one transaction (ADMIN lock timeout) that locks plans, trades and
     account_balance_history IN EXCLUSIVE MODE (plan -> trade -> account),
     collects every closed trade, terminal plan, balance point and the terminal
     plans' star/follower/notification rows, writes them to
     data/archives/account-reset-<UTC>.json (the reset stops if that write
     fails), deletes them, and reseeds one history point at the base balance,
     so the drawdown peak, the throttle and the kill-switch drawdown trigger
     all restart from the base balance;
  3. after commit, the snapshot refresh.
Open trades, live plans and journal entries are never touched. The archive is
the rollback: scripts/ops/restore_account_reset.py.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa

from swingbot import config
from swingbot.core.db.codec import normalise
from swingbot.core.db.engine import ADMIN_LOCK_TIMEOUT_MS, transaction
from swingbot.core.db.repositories.account import account_repo
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.repositories.plans import plans_repo
from swingbot.core.db.repositories.trades import trades_repo
from swingbot.core.db.schema import plan_followers, plan_notifications, plans, starred_plans
from swingbot.core.edge import throttle
from swingbot.core.planning import account as account_module
from swingbot.core.tracking.performance import _refresh_snapshot_safely, run_after_commit

log = logging.getLogger(__name__)

RESET_REASON = "account_reset"
ARCHIVE_VERSION = 1
CHILD_TABLES = {"starred_plans": starred_plans, "plan_followers": plan_followers,
                "plan_notifications": plan_notifications}
BOOK_LOCK = sa.text(
    "LOCK TABLE plans, trades, account_balance_history IN EXCLUSIVE MODE")
REFUSED_TEXT = (
    "Reset refused: the kill switch is tripped. Release it first, or force the reset "
    "(`force=true` on the endpoint, `!trades clear history force` or "
    "`/trades-clear-history force:True`); the kill switch stays on either way.")


class ResetRefused(Exception):
    """The kill switch is tripped and the caller did not force the reset."""


class ArchiveFailed(Exception):
    """The archive could not be written; nothing was deleted. The message is
    the user-facing text."""


@dataclass(frozen=True)
class ResetResult:
    removed_trades: int
    removed_plans: int
    archive_path: str
    throttle_multiplier: float
    throttle_paused: bool
    kill_on: bool
    base_balance: float
    reset_at: str


def archive_dir() -> Path:
    """Where reset archives live: the persistent data volume (read at call time)."""
    return Path(config.DATA_DIR) / "archives"


def _utc(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    return now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _child_rows(table: sa.Table, plan_ids: list[str], *, conn) -> list[dict]:
    if not plan_ids:
        return []
    return Repository(table, key="plan_id").list_all(
        conn=conn, where=table.c.plan_id.in_(plan_ids), order_by=table.c.plan_id)


def collect_archive(*, conn, reset_at: str | None = None) -> dict:
    """Every row the reset deletes, as repository records, JSON-safe."""
    cfg = account_module.load_account_config(conn=conn)
    repo = plans_repo()
    terminal = repo.list_all(conn=conn, where=plans.c.status.in_(repo.TERMINAL_STATUSES),
                             order_by=plans.c.plan_id)
    plan_ids = [plan["plan_id"] for plan in terminal]
    payload = {
        "version": ARCHIVE_VERSION,
        "reset_at": reset_at or _utc(None).isoformat(),
        "base_balance": float(cfg["base_balance"]),
        "trades": trades_repo().closed_trades(conn=conn),
        "plans": terminal,
        "account_balance_history": account_repo().history(conn=conn),
    }
    for name, table in CHILD_TABLES.items():
        payload[name] = _child_rows(table, plan_ids, conn=conn)
    return normalise(payload)


def _failed_text(path: Path, exc: Exception) -> str:
    return (f"Reset aborted: the archive {path.name} could not be written ({exc}). "
            "Nothing was deleted.")


VERIFIED_KEYS = ("trades", "plans", "account_balance_history", *CHILD_TABLES)


def _verify_archive(path: Path, payload: dict) -> None:
    """Re-read the archive from disk: it is the only rollback, so a short or
    unreadable file must stop the reset (ValueError -> ArchiveFailed)."""
    with path.open(encoding="utf-8") as handle:
        stored = json.load(handle)
    for key in VERIFIED_KEYS:
        if len(stored.get(key, ())) != len(payload[key]):
            raise ValueError(f"read-back check failed: {key} row count differs")


def _write_archive(path: Path, payload: dict) -> None:
    """Exclusive-create the archive (an existing one is never overwritten)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("x", encoding="utf-8")
    except OSError as exc:
        raise ArchiveFailed(_failed_text(path, exc)) from exc
    try:
        with handle:
            json.dump(payload, handle, indent=1, sort_keys=True, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        _verify_archive(path, payload)
    except (OSError, TypeError, ValueError) as exc:
        path.unlink(missing_ok=True)
        raise ArchiveFailed(_failed_text(path, exc)) from exc


def _reseed(base: float, reset_at: str, archive_name: str, *, conn) -> None:
    account_repo().append_history({"ts": reset_at, "balance": base, "pnl_amount": 0.0,
                                   "reason": RESET_REASON, "archive": archive_name}, conn=conn)
    cfg = account_module.load_account_config(conn=conn)
    account_module.save_account_config({**cfg, "balance": base, "balance_history": []},
                                       conn=conn)


def _reset_in_tx(path: Path, reset_at: str) -> tuple[int, int, float]:
    """Lock, archive, delete, reseed in one transaction; a failure after the
    archive was written removes the file, so every archive is a reset that
    happened. Returns (removed trades, removed plans, base balance)."""
    written = False
    try:
        with transaction(lock_timeout_ms=ADMIN_LOCK_TIMEOUT_MS) as conn:
            conn.execute(BOOK_LOCK)
            payload = collect_archive(conn=conn, reset_at=reset_at)
            _write_archive(path, payload)
            written = True
            removed_plans = plans_repo().delete_terminal(conn=conn)
            removed_trades = trades_repo().clear(status="closed", conn=conn)
            account_repo().clear_history(conn=conn)
            _reseed(payload["base_balance"], reset_at, path.name, conn=conn)
    except Exception:
        if written:
            path.unlink(missing_ok=True)
        raise
    return removed_trades, removed_plans, payload["base_balance"]


def reset_closed_history(*, force: bool = False, now: datetime | None = None) -> ResetResult:
    """The archived full reset (spec D4 A6). Raises ResetRefused while the kill
    switch is tripped unless `force`, ArchiveFailed when the archive cannot be
    written (nothing deleted), LockTimeout when the book stays locked > 5s."""
    if throttle.kill_state().get("on") and not force:
        log.info("account reset refused: kill switch tripped (force overrides)")
        raise ResetRefused(REFUSED_TEXT)
    moment = _utc(now)
    path = archive_dir() / f"account-reset-{moment:%Y%m%dT%H%M%SZ}.json"
    removed_trades, removed_plans, base = _reset_in_tx(path, moment.isoformat())
    run_after_commit([_refresh_snapshot_safely])
    points = [balance for _, balance in account_module.get_balance_history_points()]
    multiplier, paused = throttle.current_throttle(points)
    kill_on = bool(throttle.kill_state().get("on"))
    log.info("account reset: removed %d closed trade(s) and %d terminal plan(s); archive %s%s",
             removed_trades, removed_plans, path, " (forced; kill switch left on)" if kill_on else "")
    return ResetResult(removed_trades=removed_trades, removed_plans=removed_plans,
                       archive_path=str(path), throttle_multiplier=multiplier,
                       throttle_paused=paused, kill_on=kill_on, base_balance=base,
                       reset_at=moment.isoformat())


def describe_reset(result: ResetResult) -> str:
    """The confirmation every surface shows (spec D4 A6)."""
    throttle_state = "paused" if result.throttle_paused else "not paused"
    kill = ("on -- the reset never releases it; release it by hand" if result.kill_on
            else "off")
    return "\n".join((
        f"Account reset: removed {result.removed_trades} closed trade(s) and "
        f"{result.removed_plans} finished plan(s). Realized P&L and the drawdown history "
        f"restart from the base balance {result.base_balance:,.2f}.",
        f"Archive: {Path(result.archive_path).name}",
        f"Throttle: {result.throttle_multiplier:.2f}x, {throttle_state}. The drawdown peak "
        "restarts at the base balance, so any throttle is lifted.",
        f"Kill switch: {kill}.",
        "New trades are sized off the base balance. Open trades and live plans were not touched.",
    ))
