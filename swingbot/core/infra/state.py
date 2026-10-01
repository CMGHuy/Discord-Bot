"""
Tiny Postgres-backed persistence for signal state per ticker+strategy+horizon.

Two jobs:
  1. Don't re-alert every scan while a signal is still the same as last
     confirmed (only fire on a genuine change).
  2. Debounce: when scanning intraday, the underlying daily candle is
     still forming, so a signal can flip back and forth as the price
     moves before the candle closes. A change only gets "confirmed" (and
     triggers an alert) after it's seen the same way on N consecutive
     scans -- filtering out noise from a single volatile tick.
"""
from threading import Lock

_LOCK = Lock()


class StateStore:
    def _read(self, key: str) -> dict:
        from swingbot.core.db.repositories.signal_state import signal_state_repo
        return signal_state_repo().entry(key)

    def _write(self, key: str, entry: dict) -> None:
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

    def confirmed_value(self, key: str) -> str | None:
        """The last confirmed state_value for `key`, or None if none yet."""
        with _LOCK:
            return self._read(key).get("trend")

    def revoke_confirmation(self, key: str, value: str, previous: str | None) -> None:
        """Undo a confirmation whose alert was never posted (its plan was
        rejected at build): restore `previous`, so the same value has to
        re-confirm -- and can alert -- on a later scan. A no-op if `value`
        is no longer the confirmed state."""
        with _LOCK:
            entry = dict(self._read(key))
            if entry.get("trend") != value:
                return
            entry["trend"] = previous
            self._write(key, entry)
