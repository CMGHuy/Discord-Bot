"""Per-trade lessons journal: one entry per closed trade, auto-populated
with MFE/MAE/exit-efficiency and a templated lesson (Task A20), auto-tagged
(Task A21), and optionally hand-annotated with a free-text note. This IS
the data source for the retrospective (A27), the weekly digest (A25), and
the admin/Discord Journal browsers in Plans B/C -- none of them re-derive
a lesson, they only render what's already here."""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from swingbot import config
from swingbot.core.analytics import metrics
from swingbot.core.analytics.mfe_mae import compute_mfe_mae
from swingbot.core.jsonio import atomic_write_json, read_json

_LOCK = threading.Lock()


class JournalStore:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(config.DATA_DIR, "journal.json")

    def _load(self) -> list[dict]:
        return read_json(self.path, [])

    def _save(self, entries: list[dict]) -> None:
        atomic_write_json(self.path, entries)

    def add(self, entry: dict) -> dict:
        """Insert (or replace, if `entry["trade_id"]` already exists) one
        journal entry, stamping `created_at` fresh every time -- a
        re-add (e.g. the backfill script re-run, or a future re-journal
        after a correction) always reflects "when this record was last
        written", not "when it was first written"."""
        with _LOCK:
            entries = self._load()
            stamped = dict(entry, created_at=datetime.now(timezone.utc).isoformat())
            entries = [e for e in entries if e.get("trade_id") != entry.get("trade_id")]
            entries.append(stamped)
            self._save(entries)
            return stamped

    def get(self, trade_id: str) -> dict | None:
        return next((e for e in self._load() if e.get("trade_id") == trade_id), None)

    def entries(self, *, strategy: str | None = None, tag: str | None = None,
                outcome: str | None = None, since: str | None = None,
                has_note: bool | None = None) -> list[dict]:
        """Every matching entry, newest first (by `closed_at`, falling back
        to `created_at` for an entry that somehow lacks it). All filters
        are AND-combined; omit a filter (leave it None) to not apply it."""
        rows = self._load()
        if strategy is not None:
            rows = [e for e in rows if e.get("strategy") == strategy]
        if tag is not None:
            rows = [e for e in rows if tag in (e.get("tags") or [])]
        if outcome is not None:
            rows = [e for e in rows if e.get("outcome") == outcome]
        if since is not None:
            rows = [e for e in rows if (e.get("closed_at") or "") >= since]
        if has_note is not None:
            rows = [e for e in rows if bool((e.get("note") or "").strip()) == has_note]
        rows.sort(key=lambda e: e.get("closed_at") or e.get("created_at") or "", reverse=True)
        return rows

    def set_note(self, trade_id: str, note: str) -> bool:
        """Attach/replace a free-text note on an existing entry. False (no
        exception) when `trade_id` isn't journaled -- most likely a trade
        that hasn't closed yet, or predates the journal existing at all."""
        with _LOCK:
            entries = self._load()
            for e in entries:
                if e.get("trade_id") == trade_id:
                    e["note"] = note
                    self._save(entries)
                    return True
            return False


def _resolve_outcome(trade: dict) -> str:
    """status is the coarse open/win/loss/closed vocabulary TradeLog has
    always used; a v2-manager close additionally carries a specific
    close_reason ("scratch"/"timeout"/...) inside the generic "closed"
    status (see plan-engine-v2 Task 70's status mapping: only "win"/
    "loss"/"closed" ever land in the field, with the real nuance in the
    leg reason or close_reason). Prefer that finer-grained reason when
    status itself is the generic "closed" bucket."""
    status = trade.get("status")
    if status in ("win", "loss"):
        return status
    legs = trade.get("legs") or []
    candidates = []
    if legs:
        candidates.append(legs[-1].get("reason", ""))
    candidates.append((trade.get("close_reason") or ""))
    for reason in candidates:
        reason = reason.lower()
        if "scratch" in reason:
            return "scratch"
        if "timeout" in reason:
            return "timeout"
    return status or "closed"


def _holding_days(trade: dict) -> float | None:
    opened, closed = trade.get("opened_at"), trade.get("closed_at")
    if not opened or not closed:
        return None
    try:
        from datetime import datetime
        return round((datetime.fromisoformat(closed) - datetime.fromisoformat(opened)).total_seconds() / 86400, 2)
    except ValueError:
        return None


def _auto_lesson(outcome: str, mfe_r: float | None, mae_r: float | None,
                  exit_efficiency: float | None, r_realized: float | None) -> str:
    if outcome == "loss" and mae_r is not None and mfe_r is not None and mae_r <= 0.3 and mfe_r >= 1.0:
        return (f"Trade went {mfe_r:.1f}R in favor before stopping out — exit management, "
                f"not entry, cost this one.")
    if outcome == "win" and exit_efficiency is not None and exit_efficiency >= 0.8:
        return f"Clean capture: banked {exit_efficiency:.0%} of the available move."
    if outcome == "loss" and mae_r is not None and mfe_r is not None and mae_r >= 1.0 and mfe_r < 0.2:
        return "Entry was wrong from the first bar — review the trigger, not the exit."
    if outcome in ("scratch", "timeout"):
        return "No follow-through within the horizon — count it as rent, not error."
    if r_realized is None:
        return f"Outcome {outcome}."
    return f"Outcome {outcome} at {r_realized:+.2f}R."


def build_entry(trade: dict, df) -> dict:
    """Assemble one auto-populated journal entry for a just-closed trade.
    `df` is the ticker's cached daily bars (or None -- every MFE/MAE field
    degrades to None rather than raising when it's unavailable, per the
    Global Constraint on graceful degradation)."""
    m = compute_mfe_mae(trade, df) if df is not None else None
    mfe_r = m["mfe_r"] if m else None
    mae_r = m["mae_r"] if m else None
    exit_efficiency = m["exit_efficiency"] if m else None
    r_realized = metrics.r_multiple(trade)
    outcome = _resolve_outcome(trade)

    return {
        "trade_id": trade.get("id"),
        "ticker": trade.get("ticker"),
        "strategy": trade.get("strategy"),
        "horizon_key": trade.get("horizon_key"),
        "direction": trade.get("direction"),
        "tier": trade.get("tier"),
        "badge": trade.get("badge"),
        "quality_score": trade.get("quality_score"),
        "outcome": outcome,
        "r_realized": r_realized,
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "exit_efficiency": exit_efficiency,
        "holding_days": _holding_days(trade),
        "tags": [],  # Task A21 fills this in via tags_for()
        "auto_lesson": _auto_lesson(outcome, mfe_r, mae_r, exit_efficiency, r_realized),
        "note": "",
        "opened_at": trade.get("opened_at"),
        "closed_at": trade.get("closed_at"),
    }
