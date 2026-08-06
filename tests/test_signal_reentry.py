"""Guards for the signal re-entry release (plan v8 live fix, 2026-08-06).

The bug: StateStore.confirm_or_update() stamps `trend` on the scan where a
value becomes confirmed, and every later scan with the same value returns
False. Nothing cleared that stamp when the plan it produced closed, so a
ticker/strategy/horizon/direction that alerted once could never alert again
while its target stayed in the same bucket -- the live bot went from 12 plans
one day to 0 the next with the same setups still valid.

These tests pin the refusals as hard as the happy path: the cooldown must
actually block, a release must not fire for a plan that is still open, and the
state_key the manager rebuilds must keep matching the one the scanner writes.
No real clock -- state._utcnow is monkeypatched everywhere it matters.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swingbot.core import state as state_mod
from swingbot.core.levels import ScenarioSignal
from swingbot.core.plan_engine import PlanStatus
from swingbot.core.plan_manager import PlanManager
from swingbot.core.state import StateStore

T0 = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "_utcnow", lambda: T0)
    return StateStore(path=str(tmp_path / "state.json"))


def _confirm(store, key="T|RSI|4w|bullish", value="100", scans=2):
    """Drive a value through the debounce until it confirms."""
    fired = [store.confirm_or_update(key, value, required_confirmations=scans)
             for _ in range(scans)]
    return fired


# --- StateStore.release_for_reentry ----------------------------------------

def test_confirmed_signal_is_locked_out_without_release(store):
    """The bug itself, pinned: without a release the setup is spent forever."""
    assert _confirm(store)[-1] is True
    for _ in range(50):
        assert store.confirm_or_update("T|RSI|4w|bullish", "100",
                                       required_confirmations=2) is False


def test_release_lets_the_same_setup_confirm_again(store):
    _confirm(store)
    assert store.release_for_reentry("T|RSI|4w|bullish", cooldown_days=0) is True
    # Full debounce served again -- the release is not a shortcut past it.
    assert store.confirm_or_update("T|RSI|4w|bullish", "100",
                                   required_confirmations=2) is False
    assert store.confirm_or_update("T|RSI|4w|bullish", "100",
                                   required_confirmations=2) is True


def test_release_is_a_noop_when_nothing_was_confirmed(store):
    assert store.release_for_reentry("T|RSI|4w|bullish", cooldown_days=0) is False
    assert store.release_for_reentry("never|seen|before|bullish") is False


def test_cooldown_blocks_reconfirmation_until_it_expires(store, monkeypatch):
    _confirm(store)
    store.release_for_reentry("T|RSI|4w|bullish", cooldown_days=5)

    # Still inside the window: no accumulation at all, however many scans run.
    monkeypatch.setattr(state_mod, "_utcnow", lambda: T0 + timedelta(days=4.9))
    for _ in range(10):
        assert store.confirm_or_update("T|RSI|4w|bullish", "100",
                                       required_confirmations=2) is False

    # Past it: the normal debounce resumes from scratch.
    monkeypatch.setattr(state_mod, "_utcnow", lambda: T0 + timedelta(days=5.1))
    assert store.confirm_or_update("T|RSI|4w|bullish", "100",
                                   required_confirmations=2) is False
    assert store.confirm_or_update("T|RSI|4w|bullish", "100",
                                   required_confirmations=2) is True


def test_expired_cooldown_marker_is_cleared_from_disk(store, monkeypatch):
    _confirm(store)
    store.release_for_reentry("T|RSI|4w|bullish", cooldown_days=1)
    monkeypatch.setattr(state_mod, "_utcnow", lambda: T0 + timedelta(days=2))
    store.confirm_or_update("T|RSI|4w|bullish", "100", required_confirmations=2)
    reloaded = StateStore(path=store.path)
    assert "cooldown_until" not in reloaded._data["T|RSI|4w|bullish"]


def test_release_survives_a_reload(store):
    _confirm(store)
    store.release_for_reentry("T|RSI|4w|bullish", cooldown_days=0)
    assert StateStore(path=store.path)._data["T|RSI|4w|bullish"].get("trend") is None


# --- PlanManager wiring -----------------------------------------------------

class _Plan:
    """Minimal stand-in carrying only what the release path reads."""
    def __init__(self, status):
        self.plan_id = "p1"
        self.ticker = "IBM"
        self.strategy = "FVG (bullish)"
        self.horizon_key = "7m"
        self.direction = "bullish"
        self.status = status


def _manager(released, **kw):
    return PlanManager(store=None, price_fn=lambda t: 1.0,
                       signal_release_fn=released.append, **kw)


@pytest.mark.parametrize("status", [PlanStatus.CLOSED, PlanStatus.CANCELLED])
def test_terminal_status_releases_the_signal(status):
    released = []
    _manager(released)._release_signal_if_terminal(_Plan(status))
    assert released == ["IBM|FVG (bullish)|7m|bullish"]


@pytest.mark.parametrize("status", [PlanStatus.PENDING, PlanStatus.ACTIVE,
                                    PlanStatus.PARTIAL])
def test_open_plan_never_releases(status):
    """An open plan must keep its lockout -- otherwise the same setup
    re-alerts every scan while the position is still running."""
    released = []
    _manager(released)._release_signal_if_terminal(_Plan(status))
    assert released == []


def test_no_release_fn_is_inert():
    """Backtest/replay harnesses drive this manager too and must not touch
    live scan state."""
    mgr = PlanManager(store=None, price_fn=lambda t: 1.0)
    mgr._release_signal_if_terminal(_Plan(PlanStatus.CLOSED))  # must not raise


def test_release_failure_never_breaks_the_manager():
    def boom(_key):
        raise RuntimeError("state store unavailable")
    mgr = PlanManager(store=None, price_fn=lambda t: 1.0, signal_release_fn=boom)
    mgr._release_signal_if_terminal(_Plan(PlanStatus.CLOSED))  # swallowed


def test_manager_key_matches_the_key_the_scanner_writes():
    """Drift guard. The manager rebuilds the state_key from plan fields; the
    scanner writes it from ScenarioSignal. If the format moves on one side
    only, releases silently stop matching and setups are spent forever again
    -- the exact bug this fix exists to close, but invisible."""
    plan = _Plan(PlanStatus.CLOSED)
    signal = ScenarioSignal(
        ticker=plan.ticker, horizon_key=plan.horizon_key, horizon_label="7 months",
        trend=plan.direction, close=100.0, scenario=None, strategy=plan.strategy)

    released = []
    _manager(released)._release_signal_if_terminal(plan)

    assert released == [signal.state_key]


def test_end_to_end_close_then_realert(store, monkeypatch):
    """The whole point, in one test: alert -> plan closes -> cooldown -> the
    same setup can alert again."""
    key = "IBM|FVG (bullish)|7m|bullish"
    assert _confirm(store, key=key, value="3671")[-1] is True
    assert store.confirm_or_update(key, "3671", required_confirmations=2) is False

    plan = _Plan(PlanStatus.CLOSED)
    mgr = PlanManager(store=None, price_fn=lambda t: 1.0,
                      signal_release_fn=lambda k: store.release_for_reentry(k, 5))
    mgr._release_signal_if_terminal(plan)

    monkeypatch.setattr(state_mod, "_utcnow", lambda: T0 + timedelta(days=6))
    assert store.confirm_or_update(key, "3671", required_confirmations=2) is False
    assert store.confirm_or_update(key, "3671", required_confirmations=2) is True
