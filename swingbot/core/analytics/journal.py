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
