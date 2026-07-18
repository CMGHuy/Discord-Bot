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
from swingbot.core.jsonio import atomic_write_json, read_json

_LOCK = Lock()


class StateStore:
    def __init__(self, path: str = None):
        self.path = path or os.path.join(config.DATA_DIR, "state.json")
        self._data = self._load()

    def _load(self) -> dict:
        return read_json(self.path, {})

    def _save(self):
        atomic_write_json(self.path, self._data)

    def get_last_trend(self, key: str) -> str | None:
        """`key` is typically `SignalResult.state_key` (ticker|strategy|horizon)."""
        return self._data.get(key, {}).get("trend")

    def set_last_trend(self, key: str, trend: str):
        with _LOCK:
            self._data.setdefault(key, {})["trend"] = trend
            self._save()

    def confirm_or_update(self, key: str, new_value: str, required_confirmations: int = 2) -> bool:
        """
        Call this every scan with the signal's current state_value.
        Returns True only on the scan where a genuinely new value becomes
        confirmed (i.e. this is the moment to fire an alert). Returns
        False otherwise -- either nothing changed, or a change is still
        pending confirmation.
        """
        with _LOCK:
            entry = self._data.setdefault(key, {})
            confirmed = entry.get("trend")

            if new_value == confirmed:
                # Matches the already-confirmed state -- clear any stale pending flip
                if entry.get("pending_value") is not None:
                    entry["pending_value"] = None
                    entry["pending_count"] = 0
                    self._save()
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
                self._save()
                return True

            self._save()
            return False
