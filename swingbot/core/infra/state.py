"""
Tiny JSON-file persistence for signal state per ticker+strategy+horizon.

Two jobs:
  1. Don't re-alert every scan while a signal is still the same as last
     confirmed (only fire on a genuine change).
  2. Debounce: when scanning intraday, the underlying daily candle is
     still forming, so a signal can flip back and forth as the price
     moves before the candle closes. A change only gets "confirmed" (and
     triggers an alert) after it's seen the same way on N consecutive
     scans -- filtering out noise from a single volatile tick.
"""
import os
from threading import Lock

from swingbot import config
from swingbot.core.infra.jsonio import atomic_write_json, read_json

_LOCK = Lock()


class StateStore:
    def __init__(self, path: str = None):
        self.path = path or os.path.join(config.DATA_DIR, "state.json")
        from swingbot.core.db import stages
        self._data = {} if stages.reads_db("state") else self._load()

    def _load(self) -> dict:
        return read_json(self.path, {})

    def _save(self):
        atomic_write_json(self.path, self._data)

    def _read(self, key: str) -> dict:
        from swingbot.core.db import stages
        if stages.reads_db("state"):
            from swingbot.core.db.repositories.signal_state import signal_state_repo
            return signal_state_repo().entry(key)
        return self._data.setdefault(key, {})

    def _write(self, key: str, entry: dict) -> None:
        from swingbot.core.db import stages
        if stages.writes_json("state"):
            self._data[key] = entry
            self._save()
        if stages.writes_db("state"):
            from swingbot.core.db.repositories.signal_state import signal_state_repo
            signal_state_repo().put(key, entry)

    def confirm_or_update(self, key: str, new_value: str, required_confirmations: int = 2) -> bool:
        """
        Call this every scan with the signal's current state_value.
        Returns True only on the scan where a genuinely new value becomes
        confirmed (i.e. this is the moment to fire an alert). Returns
        False otherwise -- either nothing changed, or a change is still
        pending confirmation.
        """
        with _LOCK:
            entry = dict(self._read(key))
            confirmed = entry.get("trend")

            if new_value == confirmed:
                # Matches the already-confirmed state -- clear any stale pending flip
                if entry.get("pending_value") is not None:
                    entry["pending_value"] = None
                    entry["pending_count"] = 0
                    self._write(key, entry)
                return False

            if entry.get("pending_value") == new_value:
                entry["pending_count"] = entry.get("pending_count", 0) + 1
            else:
                entry["pending_value"] = new_value
                entry["pending_count"] = 1

            if entry["pending_count"] >= required_confirmations:
                entry["trend"] = new_value
                entry["pending_value"] = None
                entry["pending_count"] = 0
                self._write(key, entry)
                return True

            self._write(key, entry)
            return False
