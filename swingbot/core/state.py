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

    def was_refused(self, key: str, value: str) -> bool:
        """True if `value` was already surfaced once and refused downstream
        (see revert_confirmation). Lets the caller send the "refused" alert
        once per setup instead of every time the debounce re-fires."""
        return self._data.get(key, {}).get("refused_value") == value

    def clear_refusal(self, key: str):
        """Drop the `refused_value` marker once a setup gets through. Kept
        separate from confirm_or_update because only the caller knows
        whether the alert it just built actually shipped."""
        with _LOCK:
            entry = self._data.get(key)
            if entry and entry.pop("refused_value", None) is not None:
                self._save()

    def revert_confirmation(self, key: str, value: str, previous: str | None):
        """Hand back a confirmation that confirm_or_update() granted but the
        caller went on to refuse (V8: the gatekeeper blocks in the alert
        loop, long after the debounce has already committed).

        Without this, a refused setup is spent: `trend` holds `value`, so
        every later scan takes confirm_or_update's `new_value == confirmed`
        branch and returns False forever. The setup can then never come
        back -- not when the blocking condition clears, not when its score
        improves, not after the close. Restoring `previous` puts it back
        `required_confirmations` scans away from firing again.

        `refused_value` records what was refused so the caller can suppress
        the repeat notification while still letting the setup re-qualify.
        It is deliberately NOT consulted by confirm_or_update: this reopens
        the setup, it does not re-arm the alert."""
        with _LOCK:
            entry = self._data.setdefault(key, {})
            if entry.get("trend") != value:
                # Something else moved this key on after the confirmation we
                # are undoing -- leave it alone rather than clobber it.
                return
            if previous is None:
                entry.pop("trend", None)
            else:
                entry["trend"] = previous
            entry["pending_value"] = None
            entry["pending_count"] = 0
            entry["refused_value"] = value
            self._save()
