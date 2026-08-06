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
from datetime import datetime, timedelta, timezone
from threading import Lock

from swingbot import config
from swingbot.core.jsonio import atomic_write_json, read_json

_LOCK = Lock()


def _utcnow() -> datetime:
    """Isolated so tests can pin the clock instead of reaching for the real
    one. A real-clock dependency buried in the debounce is exactly the trap
    that let test_flag_on_polls_open_plans drift into failure once the wall
    clock moved past a hardcoded date."""
    return datetime.now(timezone.utc)


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

            # Re-entry cooldown (see release_for_reentry): the setup's last
            # plan has closed and the lockout was dropped, but re-alerting
            # the same ticker/strategy/horizon/direction immediately after a
            # stop-out is how one bad level turns into a run of losses.
            # Nothing accumulates toward confirmation while this is in force.
            cooling = entry.get("cooldown_until")
            if cooling:
                if _utcnow() < datetime.fromisoformat(cooling):
                    return False
                # Expired -- drop the marker so this check costs nothing from
                # here on, and let the scan below start accumulating.
                entry.pop("cooldown_until", None)
                self._save()

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

    def release_for_reentry(self, key: str, cooldown_days: float = 0.0) -> bool:
        """Drop the confirmed stamp so a still-valid setup can alert again
        once the plan it produced has closed. Returns True if something was
        actually released.

        Why this exists. confirm_or_update() returns True only on the scan
        where a value BECOMES confirmed; every later scan with the same value
        takes the `new_value == confirmed` branch and returns False. That is
        correct while a plan is live -- it stops the same setup re-alerting
        every 5 minutes -- but nothing ever cleared `trend` when the plan
        reached a terminal state, so the setup was spent permanently. A
        ticker/strategy/horizon/direction that alerted once could never alert
        again while its target stayed in the same bucket, no matter how many
        times the level held.

        revert_confirmation() already fixes exactly this shape for the
        gatekeeper's refusals, and its own docstring names the case it does
        NOT cover: "not when the blocking condition clears, not when its
        score improves, *not after the close*." This is that last one.

        It also reconciles live with the backtest those thresholds were tuned
        against: backtest_scenarios.replay_scenarios re-emits the same
        ticker/horizon/direction after `cooldown_bars` (5), while live
        implemented an infinite lockout -- strictly more restrictive than the
        configuration whose win rate was measured. `cooldown_days` is the
        live analogue and defaults to that same 5.

        Releasing is not a quality concession: the setup must clear every
        filter again from scratch -- confidence level, min strategies, the
        gate, the target floor -- and re-serve the full
        SIGNAL_CONFIRMATION_SCANS debounce before it can post.
        """
        with _LOCK:
            entry = self._data.get(key)
            if not entry or entry.get("trend") is None:
                return False
            entry.pop("trend", None)
            entry["pending_value"] = None
            entry["pending_count"] = 0
            if cooldown_days > 0:
                entry["cooldown_until"] = (
                    _utcnow() + timedelta(days=cooldown_days)).isoformat()
            else:
                entry.pop("cooldown_until", None)
            self._save()
            return True

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
