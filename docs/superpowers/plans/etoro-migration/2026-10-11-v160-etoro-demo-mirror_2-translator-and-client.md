# v160 eToro demo mirror: plan events become demo-account trades. Part 2: translator and client (EM6–EM7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task EM6" -A 500 <this file>`.

**Spec:** `docs/superpowers/specs/etoro-migration/2026-10-11-v160-etoro-demo-mirror-design.md` (§ Components, § Event mapping, § eToro API facts, § Testing)
**Index:** `docs/superpowers/plans/etoro-migration/2026-10-11-v160-etoro-demo-mirror_0-index.md`. Its `## Global Constraints`, `## Parallelisation` and `## Task ledger` apply to every task below and win over anything here.

**Conventions for every task in this part**

- `WT` is the worktree root: `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-11-v160-etoro-demo-mirror` (created in EM1). Every path below is relative to `WT`. Never `cd`: use `git -C "$WT" ...`, and run tests as `python "$WT/scripts/dev/testrun.py" file <test path relative to WT>`.
- `swingbot/core/broker/__init__.py`, `swingbot/core/broker/guard.py` and `tests/broker/__init__.py` exist already (v159 ER7). No task here creates or edits them.
- v159's AST scan (`tests/broker/test_guard.py::test_no_module_in_the_repo_touches_etoro_without_the_guard`) treats every **string constant**, docstrings included, that contains `etoro.com` as eToro code. `mirror.py` must not contain that substring anywhere (it does not call `assert_demo` and must not need to); `etoro_client.py` contains it and calls `guard.assert_demo("demo")`.
- Every new function stays below cyclomatic complexity 15: `python -m radon cc -s -n C <files>` prints nothing for the files a task created.
- The suite makes no network call to eToro: client tests inject a fake session.

# Phase 2 (continued) — the pure translator (EM6)

### Task EM6: `mirror.py`: the event translator

**Model:** opus — the dedupe, no-mid-lifecycle-adoption and no-widen rules decide whether a (demo) position is opened twice or a stop is loosened; a subtle miss here is money-shaped, so the top tier writes it.

Spec § Event mapping, § Sizing and order checks ("Stops only tighten"), § Testing (`test_mirror.py`). `mirror.py` is **pure**: no I/O, no clock, no config, no network. It reads one `PlanEvent`, the `TradePlanV2` it belongs to and a `SentState` (what `broker_orders` says was already queued or sent for that plan, built by the executor from `repo.for_plan(plan_id)` through `sent_state_from_rows`) and returns the `BrokerAction`s to queue. It does **not** size, quote, check eligibility or pick the settlement type: the executor (EM8) does all of that at send time. Its one side effect is a WARNING log line when the no-widen guard drops a stop move (Global Constraints, logging contract).

Rules this task pins, in the order `actions_for` applies them:

1. `plan.ledger != "main"` → `[]` for every transition.
2. `filled` → one `open` action, `event_key "filled"`, `stop_rate = round_rate(plan.stop_loss)`, `tp_rate = take_profit(plan)`; dropped when `("open", "filled")` is already in `sent.keys` (a resent `filled`, or a `filled` whose first open was rejected or skipped: a plan is opened at most once, ever).
3. Any other transition when `sent.has_open` is false → `[]` (never adopted mid-lifecycle; a plan whose open was rejected or skipped never gets closes or stop moves).
4. `closed` (every reason) → `close_all`, `event_key "closed"`.
5. `tp1_partial` → `close_units` (`event_key "tp1_partial"`, `fraction = plan.tp1_fraction`), then the stop move of rule 6. The executor computes `round_down(open units × fraction)` and records `fraction_closed`.
6. `be_moved`, `stop_moved` (and the second half of `tp1_partial`) → `move_stop` to `stop_target(event, plan)`, `event_key f"{target:.4f}"`. Dropped **silently** when that key is already in `sent.keys` (same target sent before); otherwise dropped **with a WARNING** when `checks.check_stop_move(plan.direction, sent.last_stop, target)` returns `"stop_widen"`.
7. Every other transition (`cancelled_*`, `pyramid_add`, `time_exit_due`, `time_exit_unresolved`, anything new) → `[]`.

Every action whose `(action, event_key)` is already in `sent.keys` is dropped before it is returned. The repository's unique index (EM2) is the second, authoritative dedupe; this one keeps resent events from even reaching the insert.

**Files:**
- Create: `swingbot/core/broker/mirror.py`
- Create: `tests/broker/test_mirror.py`

**Interfaces:**
- Consumes:
  - `swingbot.core.broker.checks.check_stop_move(direction: str, last_stop: float | None, new_stop: float | None) -> str | None` (EM4): `"stop_widen"` when `new_stop` is `None`, or is lower than or equal to `last_stop` for `bullish`, or higher than or equal to it for `bearish`; `None` otherwise (including `last_stop is None`).
  - `swingbot.core.planning.plan_manager.PlanEvent(plan_id: str, transition: str, detail: dict)` (`plan_manager.py:55`).
  - `swingbot.core.planning.plan_types.TradePlanV2` fields `plan_id`, `ticker`, `direction` (`"bullish"`/`"bearish"`), `stop_loss`, `working_stop` (`None` = use `stop_loss`, `plan_types.py:46`), `tp1`, `tp1_fraction`, `tp2` (`float | None`), `ledger` (`"main"`/`"weak"`, `plan_types.py:67`).
  - Event detail shapes (`plan_manager.py`): `be_moved` `{"working_stop", "live_price"}`; `tp1_partial` the leg dict plus `"working_stop"` (added at `:433`); `stop_moved` `{"old", "new", "r_moved", "effective"}` (no `working_stop` key, so the target falls back to `plan.working_stop`, which equals `new`).
  - Test helper `tests.planning.test_plan_engine_model._plan(**kw) -> TradePlanV2`; `PlanStatus` from `swingbot.core.planning.plan_engine`.
- Produces (consumed by EM8, EM10):
  - `ACTION_OPEN = "open"`, `ACTION_CLOSE_UNITS = "close_units"`, `ACTION_CLOSE_ALL = "close_all"`, `ACTION_MOVE_STOP = "move_stop"`.
  - `@dataclass(frozen=True) BrokerAction(plan_id: str, action: str, event_key: str, ticker: str, direction: str, stop_rate: float | None = None, tp_rate: float | None = None, fraction: float | None = None)`.
  - `@dataclass(frozen=True) SentState(has_open: bool = False, last_stop: float | None = None, keys: frozenset = frozenset())`; `keys` holds `(action, event_key)` tuples.
  - `round_rate(rate: float) -> float` (2 decimals at or above 1.00 in absolute value, 4 below; non-finite passes through unchanged).
  - `stop_target(event: PlanEvent, plan: TradePlanV2) -> float`.
  - `take_profit(plan: TradePlanV2) -> float | None`.
  - `sent_state_from_rows(rows: list[dict]) -> SentState` over flat repository records (`action`, `event_key`, `seq`, `status`, `stop_sent`): `keys` from **every** row whatever its status; `has_open` true when an `open` row has a status other than `rejected`/`skipped`; `last_stop` is the `stop_sent` of the highest-`seq` `open`/`move_stop` row whose status is not `rejected`/`skipped` and whose `stop_sent` is not `None`.
  - `actions_for(event: PlanEvent, plan: TradePlanV2, sent: SentState) -> list[BrokerAction]`.

- [ ] **Step 1: Confirm EM4's contract is on the branch**

Run: `git -C "$WT" grep -n "def check_stop_move" -- swingbot/core/broker/checks.py`
Expected: one hit. If there is none, EM4 is not on the branch yet: stop and report `BLOCKED: EM6 needs EM4 (checks.check_stop_move)`.

- [ ] **Step 2: Write the failing tests**

Create `tests/broker/test_mirror.py`:

```python
"""v160 EM6: the pure PlanEvent -> BrokerAction translator (spec § Event mapping)."""
import ast
import logging
import math
from pathlib import Path

import pytest

from swingbot.core.broker.mirror import (
    ACTION_CLOSE_ALL, ACTION_CLOSE_UNITS, ACTION_MOVE_STOP, ACTION_OPEN,
    BrokerAction, SentState, actions_for, round_rate, sent_state_from_rows,
    stop_target, take_profit,
)
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanEvent
from tests.planning.test_plan_engine_model import _plan

ROOT = Path(__file__).resolve().parents[2]
MIRROR_LOGGER = "swingbot.core.broker.mirror"

# A plan with a live, filled open row whose stop was sent at 95.0.
OPEN_SENT = SentState(has_open=True, last_stop=95.0,
                      keys=frozenset({(ACTION_OPEN, "filled")}))


def _active(**kw):
    base = dict(entry_price=100.0, status=PlanStatus.ACTIVE)
    base.update(kw)
    return _plan(**base)


def _row(action, event_key, seq, status, **doc):
    return {"plan_id": "p1", "action": action, "event_key": event_key,
            "seq": seq, "status": status, **doc}


# --- filled -> open --------------------------------------------------------

def test_filled_bullish_opens_with_the_plan_stop_and_tp2():
    event = PlanEvent("p1", "filled", {"entry_price": 100.0, "live_price": 100.2})
    assert actions_for(event, _active(), SentState()) == [
        BrokerAction("p1", ACTION_OPEN, "filled", "AAPL", "bullish",
                     stop_rate=95.0, tp_rate=105.0)]


def test_filled_bearish_opens_with_the_plan_direction():
    plan = _active(direction="bearish", stop_loss=105.0, tp1=98.0, tp2=95.0)
    [action] = actions_for(PlanEvent("p1", "filled", {}), plan, SentState())
    assert (action.action, action.direction, action.stop_rate, action.tp_rate) == (
        ACTION_OPEN, "bearish", 105.0, 95.0)


def test_filled_rounds_the_stop_to_rate_precision_and_never_changes_the_plan():
    plan = _active(stop_loss=95.12345, tp2=None, tp1_fraction=0.5)
    [action] = actions_for(PlanEvent("p1", "filled", {}), plan, SentState())
    assert action.stop_rate == 95.12
    assert action.tp_rate is None
    assert plan.stop_loss == 95.12345


def test_resent_filled_is_deduplicated():
    assert actions_for(PlanEvent("p1", "filled", {}), _active(), OPEN_SENT) == []


def test_filled_after_a_rejected_open_never_reopens():
    sent = sent_state_from_rows([_row(ACTION_OPEN, "filled", 1, "rejected", stop_sent=95.0)])
    assert actions_for(PlanEvent("p1", "filled", {}), _active(), sent) == []


# --- ledger and no-adoption guards ----------------------------------------

@pytest.mark.parametrize("transition",
                         ["filled", "tp1_partial", "be_moved", "stop_moved", "closed"])
def test_weak_ledger_maps_to_nothing(transition):
    plan = _active(ledger="weak", working_stop=100.0)
    event = PlanEvent("p1", transition, {"working_stop": 100.0, "reason": "loss"})
    assert actions_for(event, plan, OPEN_SENT) == []


@pytest.mark.parametrize("transition", ["tp1_partial", "be_moved", "stop_moved", "closed"])
def test_no_open_row_maps_to_nothing(transition):
    plan = _active(working_stop=100.0)
    event = PlanEvent("p1", transition, {"working_stop": 100.0, "reason": "loss"})
    assert actions_for(event, plan, SentState()) == []


@pytest.mark.parametrize("dead", ["rejected", "skipped"])
def test_a_dead_open_row_counts_as_no_open(dead):
    sent = sent_state_from_rows([_row(ACTION_OPEN, "filled", 1, dead, stop_sent=95.0)])
    assert sent.has_open is False
    event = PlanEvent("p1", "closed", {"reason": "loss", "exit_price": 94.5})
    assert actions_for(event, _active(status=PlanStatus.CLOSED), sent) == []


# --- closed -> close_all ---------------------------------------------------

@pytest.mark.parametrize("reason", ["loss", "scratch", "stall_exit", "tp1_runner_be",
                                    "tp1_runner_trail", "time", "structure"])
def test_closed_maps_to_close_all_for_every_reason(reason):
    event = PlanEvent("p1", "closed", {"reason": reason, "exit_price": 94.5})
    assert actions_for(event, _active(status=PlanStatus.CLOSED), OPEN_SENT) == [
        BrokerAction("p1", ACTION_CLOSE_ALL, "closed", "AAPL", "bullish")]


def test_resent_closed_is_deduplicated():
    sent = SentState(has_open=True, last_stop=95.0,
                     keys=frozenset({(ACTION_OPEN, "filled"), (ACTION_CLOSE_ALL, "closed")}))
    event = PlanEvent("p1", "closed", {"reason": "loss", "exit_price": 94.5})
    assert actions_for(event, _active(status=PlanStatus.CLOSED), sent) == []


# --- tp1_partial, be_moved, stop_moved -------------------------------------

def test_tp1_partial_closes_the_fraction_then_moves_the_stop():
    plan = _active(status=PlanStatus.PARTIAL, working_stop=100.0)
    event = PlanEvent("p1", "tp1_partial", {"fraction": 0.5, "exit_price": 102.0, "r": 0.4,
                                            "reason": "tp1", "working_stop": 100.0})
    assert actions_for(event, plan, OPEN_SENT) == [
        BrokerAction("p1", ACTION_CLOSE_UNITS, "tp1_partial", "AAPL", "bullish", fraction=0.5),
        BrokerAction("p1", ACTION_MOVE_STOP, "100.0000", "AAPL", "bullish", stop_rate=100.0)]


def test_tp1_partial_still_closes_when_its_stop_move_would_widen():
    sent = SentState(has_open=True, last_stop=101.0, keys=frozenset({(ACTION_OPEN, "filled")}))
    plan = _active(status=PlanStatus.PARTIAL, working_stop=100.0)
    event = PlanEvent("p1", "tp1_partial", {"fraction": 0.5, "working_stop": 100.0})
    assert actions_for(event, plan, sent) == [
        BrokerAction("p1", ACTION_CLOSE_UNITS, "tp1_partial", "AAPL", "bullish", fraction=0.5)]


def test_be_moved_moves_the_stop_to_the_event_working_stop():
    event = PlanEvent("p1", "be_moved", {"working_stop": 100.0, "live_price": 101.5})
    assert actions_for(event, _active(working_stop=100.0), OPEN_SENT) == [
        BrokerAction("p1", ACTION_MOVE_STOP, "100.0000", "AAPL", "bullish", stop_rate=100.0)]


def test_stop_moved_falls_back_to_the_plan_working_stop():
    sent = SentState(has_open=True, last_stop=100.0, keys=frozenset({(ACTION_OPEN, "filled")}))
    event = PlanEvent("p1", "stop_moved", {"old": 100.0, "new": 101.0, "r_moved": 0.2,
                                           "effective": "now"})
    assert actions_for(event, _active(working_stop=101.0), sent) == [
        BrokerAction("p1", ACTION_MOVE_STOP, "101.0000", "AAPL", "bullish", stop_rate=101.0)]


@pytest.mark.parametrize("transition", ["cancelled_expired", "cancelled_invalidated",
                                        "cancelled_risk_cap", "pyramid_add", "time_exit_due",
                                        "time_exit_unresolved", "something_new"])
def test_other_transitions_map_to_nothing(transition):
    assert actions_for(PlanEvent("p1", transition, {}), _active(), OPEN_SENT) == []


# --- stop target: three branches -------------------------------------------

def test_stop_target_prefers_the_event_working_stop():
    event = PlanEvent("p1", "be_moved", {"working_stop": 100.004})
    assert stop_target(event, _active(working_stop=99.0)) == 100.0


def test_stop_target_falls_back_to_plan_working_stop():
    assert stop_target(PlanEvent("p1", "stop_moved", {"new": 99.5}),
                       _active(working_stop=99.5)) == 99.5


def test_stop_target_falls_back_to_stop_loss_when_working_stop_is_none():
    assert stop_target(PlanEvent("p1", "stop_moved", {}), _active(working_stop=None)) == 95.0


# --- no-widen guard ----------------------------------------------------------

@pytest.mark.parametrize("direction,last,target", [
    ("bullish", 100.0, 99.0), ("bullish", 100.0, 100.0),
    ("bearish", 100.0, 101.0), ("bearish", 100.0, 100.0)])
def test_no_widen_guard_drops_and_warns(direction, last, target, caplog):
    sent = SentState(has_open=True, last_stop=last, keys=frozenset({(ACTION_OPEN, "filled")}))
    plan = _active(direction=direction, working_stop=target)
    with caplog.at_level(logging.WARNING, logger=MIRROR_LOGGER):
        assert actions_for(PlanEvent("p1", "stop_moved", {}), plan, sent) == []
    assert "etoro mirror skipped (stop_widen): AAPL p1" in caplog.text


@pytest.mark.parametrize("direction,last,target", [
    ("bullish", 100.0, 101.0), ("bearish", 100.0, 99.0)])
def test_a_tightening_stop_move_passes(direction, last, target):
    sent = SentState(has_open=True, last_stop=last, keys=frozenset({(ACTION_OPEN, "filled")}))
    plan = _active(direction=direction, working_stop=target)
    [action] = actions_for(PlanEvent("p1", "stop_moved", {}), plan, sent)
    assert (action.action, action.stop_rate, action.direction) == (ACTION_MOVE_STOP, target, direction)


def test_an_already_sent_stop_target_is_dropped_without_a_warning(caplog):
    sent = SentState(has_open=True, last_stop=100.0,
                     keys=frozenset({(ACTION_OPEN, "filled"), (ACTION_MOVE_STOP, "100.0000")}))
    with caplog.at_level(logging.WARNING, logger=MIRROR_LOGGER):
        assert actions_for(PlanEvent("p1", "be_moved", {"working_stop": 100.0}),
                           _active(working_stop=100.0), sent) == []
    assert "stop_widen" not in caplog.text


# --- take-profit rule ----------------------------------------------------------

def test_take_profit_is_tp2_when_set():
    assert take_profit(_active(tp2=105.004)) == 105.0


def test_take_profit_is_tp1_when_tp1_closes_everything():
    assert take_profit(_active(tp2=None, tp1=102.0, tp1_fraction=1.0)) == 102.0


def test_take_profit_is_none_for_a_runner():
    assert take_profit(_active(tp2=None, tp1_fraction=0.5)) is None


# --- rate precision ------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [(123.456, 123.46), (1.0, 1.0),
                                          (0.987654, 0.9877), (0.123456, 0.1235)])
def test_round_rate(raw, expected):
    assert round_rate(raw) == expected


def test_round_rate_passes_non_finite_values_through():
    assert math.isnan(round_rate(float("nan")))
    assert round_rate(float("inf")) == float("inf")


# --- SentState from repository rows -----------------------------------------

def test_sent_state_reads_the_open_and_the_last_live_stop():
    rows = [_row(ACTION_OPEN, "filled", 1, "filled", stop_sent=95.0),
            _row(ACTION_MOVE_STOP, "100.0000", 2, "filled", stop_sent=100.0),
            _row(ACTION_MOVE_STOP, "101.0000", 3, "rejected", stop_sent=101.0),
            _row(ACTION_CLOSE_UNITS, "tp1_partial", 4, "queued")]
    sent = sent_state_from_rows(rows)
    assert sent.has_open is True
    assert sent.last_stop == 100.0
    assert sent.keys == frozenset({(ACTION_OPEN, "filled"), (ACTION_MOVE_STOP, "100.0000"),
                                   (ACTION_MOVE_STOP, "101.0000"),
                                   (ACTION_CLOSE_UNITS, "tp1_partial")})


def test_a_queued_open_already_counts_as_open():
    sent = sent_state_from_rows([_row(ACTION_OPEN, "filled", 1, "queued", stop_sent=95.0)])
    assert (sent.has_open, sent.last_stop) == (True, 95.0)


def test_sent_state_of_no_rows_is_empty():
    assert sent_state_from_rows([]) == SentState()


# --- purity ------------------------------------------------------------------

FORBIDDEN_IMPORTS = ("requests", "time", "datetime", "swingbot.config",
                     "swingbot.core.db", "swingbot.core.broker.etoro_client",
                     "swingbot.core.broker.executor")


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_mirror_is_pure_and_never_names_the_broker_host():
    text = (ROOT / "swingbot/core/broker/mirror.py").read_text(encoding="utf-8")
    names = _imported_names(ast.parse(text))
    hits = sorted(name for name in names for bad in FORBIDDEN_IMPORTS
                  if name == bad or name.startswith(bad + "."))
    assert hits == []
    assert "etoro.com" not in text.lower()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_mirror.py`
Expected: FAIL, collection error `ModuleNotFoundError: No module named 'swingbot.core.broker.mirror'`.

- [ ] **Step 4: Write the implementation**

Create `swingbot/core/broker/mirror.py`:

```python
"""Pure PlanEvent -> BrokerAction translator for the demo mirror (v160).

No I/O, no clock, no config, no network. It reads one plan event, the plan
it belongs to and a SentState (what the broker_orders rows say was already
queued or sent for that plan) and returns the actions to queue. Sizing,
quotes, eligibility and every order check happen later, in the executor.

Rules (spec § Event mapping): only main-ledger plans; `filled` opens once,
ever; nothing else acts on a plan without a live open row (no adoption
mid-lifecycle); stops only tighten (checks.check_stop_move), and a widening
move is dropped with a WARNING. Every action whose (action, event_key) is
already in SentState.keys is dropped: poll() re-emits unacknowledged
`filled`/`closed` notices with no resend marker.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from swingbot.core.broker import checks

if TYPE_CHECKING:
    from swingbot.core.planning.plan_manager import PlanEvent
    from swingbot.core.planning.plan_types import TradePlanV2

log = logging.getLogger(__name__)

ACTION_OPEN = "open"
ACTION_CLOSE_UNITS = "close_units"
ACTION_CLOSE_ALL = "close_all"
ACTION_MOVE_STOP = "move_stop"

MAIN_LEDGER = "main"
_DEAD_STATUSES = frozenset({"rejected", "skipped"})
_STOP_ACTIONS = frozenset({ACTION_OPEN, ACTION_MOVE_STOP})


@dataclass(frozen=True)
class BrokerAction:
    plan_id: str
    action: str
    event_key: str
    ticker: str
    direction: str
    stop_rate: float | None = None
    tp_rate: float | None = None
    fraction: float | None = None


@dataclass(frozen=True)
class SentState:
    has_open: bool = False
    last_stop: float | None = None
    keys: frozenset = frozenset()   # {(action, event_key)} over every row of the plan


def round_rate(rate: float) -> float:
    """No rate precision is published: 2 decimals at or above 1.00, 4 below
    (US tick sizes). Non-finite values pass through for the checks to reject."""
    rate = float(rate)
    if not math.isfinite(rate):
        return rate
    return round(rate, 2) if abs(rate) >= 1.0 else round(rate, 4)


def stop_target(event: PlanEvent, plan: TradePlanV2) -> float:
    """Event detail `working_stop`, else plan.working_stop, else stop_loss."""
    raw = (event.detail or {}).get("working_stop")
    if raw is None:
        raw = plan.working_stop
    if raw is None:
        raw = plan.stop_loss
    return round_rate(raw)


def take_profit(plan: TradePlanV2) -> float | None:
    """tp2 when set; tp1 when TP1 closes the whole position; else none (the
    runner leaves on the bot's trail or time rules as MoveStop/CloseAll)."""
    if plan.tp2 is not None:
        return round_rate(plan.tp2)
    if float(plan.tp1_fraction) >= 1.0:
        return round_rate(plan.tp1)
    return None


def _live(row: dict) -> bool:
    return row.get("status") not in _DEAD_STATUSES


def _last_stop(rows: list[dict]) -> float | None:
    stops = [row for row in rows
             if row.get("action") in _STOP_ACTIONS and _live(row)
             and row.get("stop_sent") is not None]
    if not stops:
        return None
    return float(max(stops, key=lambda row: row.get("seq") or 0)["stop_sent"])


def sent_state_from_rows(rows: list[dict]) -> SentState:
    """SentState from one plan's broker_orders records (flat dicts)."""
    rows = list(rows or [])
    return SentState(
        has_open=any(row.get("action") == ACTION_OPEN and _live(row) for row in rows),
        last_stop=_last_stop(rows),
        keys=frozenset((row.get("action"), row.get("event_key")) for row in rows),
    )


def _action(plan: TradePlanV2, action: str, event_key: str, **extra) -> BrokerAction:
    return BrokerAction(plan.plan_id, action, event_key, plan.ticker, plan.direction, **extra)


def _open(event: PlanEvent, plan: TradePlanV2, sent: SentState) -> list[BrokerAction]:
    return [_action(plan, ACTION_OPEN, "filled",
                    stop_rate=round_rate(plan.stop_loss), tp_rate=take_profit(plan))]


def _close_all(event: PlanEvent, plan: TradePlanV2, sent: SentState) -> list[BrokerAction]:
    return [_action(plan, ACTION_CLOSE_ALL, "closed")]


def _move_stop(event: PlanEvent, plan: TradePlanV2, sent: SentState) -> list[BrokerAction]:
    target = stop_target(event, plan)
    key = f"{target:.4f}"
    if (ACTION_MOVE_STOP, key) in sent.keys:
        return []
    reason = checks.check_stop_move(plan.direction, sent.last_stop, target)
    if reason is not None:
        log.warning("etoro mirror skipped (%s): %s %s target %s, last stop sent %s",
                    reason, plan.ticker, plan.plan_id, target, sent.last_stop)
        return []
    return [_action(plan, ACTION_MOVE_STOP, key, stop_rate=target)]


def _tp1_partial(event: PlanEvent, plan: TradePlanV2, sent: SentState) -> list[BrokerAction]:
    close = _action(plan, ACTION_CLOSE_UNITS, "tp1_partial", fraction=float(plan.tp1_fraction))
    return [close, *_move_stop(event, plan, sent)]


_FOLLOWERS = {
    "closed": _close_all,
    "tp1_partial": _tp1_partial,
    "be_moved": _move_stop,
    "stop_moved": _move_stop,
}


def actions_for(event: PlanEvent, plan: TradePlanV2, sent: SentState) -> list[BrokerAction]:
    """The broker actions one plan event asks for, already deduplicated."""
    if getattr(plan, "ledger", MAIN_LEDGER) != MAIN_LEDGER:
        return []
    if event.transition == "filled":
        builder = _open
    elif sent.has_open:
        builder = _FOLLOWERS.get(event.transition)
    else:
        builder = None
    if builder is None:
        return []
    return [action for action in builder(event, plan, sent)
            if (action.action, action.event_key) not in sent.keys]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_mirror.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py`
Expected: PASS. `mirror.py` is in `ALLOWED_BROKER_MODULES` (EM1) and does not touch eToro, so v159's AST scan ignores it. If the scan lists `swingbot/core/broker/mirror.py`, a string in it names the broker host: remove that string, never add a guard call or an `EXEMPT` entry.

- [ ] **Step 6: Complexity check**

Run: `python -m radon cc -s -n C "$WT/swingbot/core/broker/mirror.py"`
Expected: no output (every function below C; `actions_for` is about B 6).

- [ ] **Step 7: Commit**

```bash
git -C "$WT" add swingbot/core/broker/mirror.py tests/broker/test_mirror.py
git -C "$WT" commit -m "feat(v160): EM6 mirror.py -- pure PlanEvent to BrokerAction translator with dedupe and no-widen guard"
```

# Phase 3 — the demo-only client (EM7)

### Task EM7: `etoro_client.py`: demo-only REST client and token bucket

**Model:** sonnet — a thin, fully specified HTTP wrapper (paths, headers, timeout, bucket all fixed by the index) with fake-transport tests; no design choice left open.

Spec § Components (`etoro_client.py`), § eToro API facts, § Testing (`test_client.py`, `test_demo_only_paths.py`); index § Global Constraints (the route table, headers, demo only). The client knows nothing about plans, rows or outcomes: it sends one request and returns a `ClientResult`. It never sleeps, never retries and never raises on an HTTP or transport failure (the executor, EM8, owns every retry rule). It raises only when `guard.assert_demo` raises, at construction.

Design points pinned here:

- `API_BASE` and the eight path constants are the **only** URL strings in the module. Path parameters are filled with `str.format(position_id=int(...))`; query strings go through `params=`, never string concatenation.
- Headers on every request: `x-user-key` = `config.ETORO_USER_KEY`, `x-api-key` = `config.ETORO_API_KEY` (read at call time, so a SIGHUP key change applies to the next request), `x-request-id`, `Accept: application/json`. Never `Authorization`. Order and stop calls take the caller's `request_id` (the executor's uuid5, so eToro's idempotency stops a second order on a resend); read calls get a fresh `uuid4`.
- Every request passes `timeout=REQUEST_TIMEOUT_S` (10).
- `TokenBucket` is a sliding window: at most `capacity` takes per `window_s`. `try_take()` returns `False` when full and **never sleeps**; it holds a `threading.Lock` because the hook runs it in `asyncio.to_thread` and a timed-out tick's thread can still be running when the next starts. Only `open_order` and `close_position` take a token (eToro's shared 20-per-60 s order pool); an empty bucket returns `ClientResult(0, deferred=True)` without touching the session.
- A `requests.RequestException` (timeout, connection error) returns `ClientResult(0, error="<ExceptionName>: <message>")`. A non-JSON body falls back to the response text (or `None` when empty). `Retry-After` is parsed as seconds (`float`, finite, non-negative), else `None`.

**Files:**
- Create: `swingbot/core/broker/etoro_client.py`
- Create: `tests/broker/test_client.py`
- Create: `tests/broker/test_demo_only_paths.py`

**Interfaces:**
- Consumes:
  - `swingbot.core.broker.guard.assert_demo(account: str) -> None` and `guard.RealAccountBlocked(RuntimeError)` (v159 ER7).
  - `config.ETORO_USER_KEY`, `config.ETORO_API_KEY` (existing `Field`s, `swingbot/config.py:128`/`:134`).
  - `requests` (pinned in `requirements.txt` by EM1, `requests==2.34.2` on 2026-10-11).
  - `tests/broker/test_guard.py::ALLOWED_BROKER_MODULES` contains `"etoro_client.py"` (EM1).
- Produces (consumed by EM8, EM9, EM13, EM14):
  - `API_BASE = "https://public-api.etoro.com"`; `OPEN_PATH`, `CLOSE_PATH`, `POSITION_PATH`, `LOOKUP_PATH`, `ELIGIBILITY_PATH`, `RATES_PATH`, `PORTFOLIO_PATH`, `HISTORY_PATH` (exact strings in Step 4).
  - `REQUEST_TIMEOUT_S = 10`, `ORDER_BUCKET_CAPACITY = 15`, `ORDER_BUCKET_WINDOW_S = 60.0`.
  - `@dataclass(frozen=True) ClientResult(status_code: int, body: object = None, retry_after: float | None = None, deferred: bool = False, error: str = "")` with property `ok -> bool` (`200 <= status_code < 300`).
  - `class TokenBucket(capacity: int = 15, window_s: float = 60.0, clock=time.monotonic)` with `try_take() -> bool`.
  - `class EtoroClient(*, session=None, bucket: TokenBucket | None = None)`; `session` is any object with `request(method, url, *, headers, json, params, timeout)` returning an object with `status_code`, `headers`, `text`, `json()` (default `requests.Session()`). Methods, each `-> ClientResult`: `open_order(body: dict, request_id: str)`, `close_position(position_id: int, instrument_id: int, units: float | None, request_id: str)` (body `{"InstrumentID": int, "UnitsToDeduct": float | None}`; `None` closes the whole position), `update_stop(position_id: int, stop_rate: float, request_id: str)` (body `{"stopLossRate": float}`), `lookup(reference_id: str)` (`params={"referenceId": ...}`), `eligibility(symbol: str)` (body `{"symbols": [symbol]}`), `rates(instrument_id: int)` (`params={"instrumentIds": "<id>"}`), `portfolio()`, `history(min_date: str, page: int = 1, page_size: int = 200)` (`params={"minDate", "page", "pageSize"}`).
  - `tests/broker/test_demo_only_paths.py::real_account_routes(root: Path) -> list[str]` (`"<rel path>: <string>"` per offending route string under `swingbot/core/broker/` and `scripts/ops/etoro_*.py`).

- [ ] **Step 1: Confirm the gate, the pin and the allow-list**

Run: `git -C "$WT" grep -n "def assert_demo" -- swingbot/core/broker/guard.py`
Expected: one hit (v159 ER7). None means v159 is not merged: stop with `BLOCKED: v159 ER7/ER8 not on main`.

Run: `git -C "$WT" grep -n "^requests==" -- requirements.txt`
Expected: one hit (EM1). None means EM1 is not on the branch: stop with `BLOCKED: EM7 needs EM1 (requests pin)`.

Run: `git -C "$WT" grep -n "etoro_client.py" -- tests/broker/test_guard.py`
Expected: one hit inside `ALLOWED_BROKER_MODULES` (EM1).

- [ ] **Step 2: Write the failing client tests**

Create `tests/broker/test_client.py`:

```python
"""v160 EM7: the demo-only eToro REST client (fake transport, no network)."""
import time
from pathlib import Path

import pytest
import requests

from swingbot import config
from swingbot.core.broker import etoro_client, guard
from swingbot.core.broker.etoro_client import (
    API_BASE, CLOSE_PATH, ELIGIBILITY_PATH, HISTORY_PATH, LOOKUP_PATH, OPEN_PATH,
    ORDER_BUCKET_CAPACITY, ORDER_BUCKET_WINDOW_S, PORTFOLIO_PATH, POSITION_PATH,
    RATES_PATH, REQUEST_TIMEOUT_S, ClientResult, EtoroClient, TokenBucket,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    """Records every request; replies from a script, else 200 {}."""

    def __init__(self, replies=None):
        self.calls = []
        self.replies = list(replies or [])

    def request(self, method, url, *, headers, json, params, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers),
                           "json": json, "params": params, "timeout": timeout})
        reply = self.replies.pop(0) if self.replies else FakeResponse(200, {})
        if isinstance(reply, Exception):
            raise reply
        return reply


class ManualClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setattr(config, "ETORO_USER_KEY", "user-1", raising=False)
    monkeypatch.setattr(config, "ETORO_API_KEY", "api-1", raising=False)


@pytest.fixture
def no_sleep(monkeypatch):
    def _fail(*_args, **_kwargs):
        raise AssertionError("the eToro client must never sleep")
    monkeypatch.setattr(time, "sleep", _fail)


def _client(session=None, bucket=None):
    return EtoroClient(session=session or FakeSession(), bucket=bucket)


# --- construction and the demo guard ---------------------------------------

def test_constructor_calls_assert_demo_with_demo(monkeypatch):
    seen = []
    monkeypatch.setattr(guard, "assert_demo", seen.append)
    _client()
    assert seen == ["demo"]


def test_constructor_propagates_a_real_account_block(monkeypatch):
    def _blocked(account):
        raise guard.RealAccountBlocked(account)
    monkeypatch.setattr(guard, "assert_demo", _blocked)
    with pytest.raises(guard.RealAccountBlocked):
        _client()


def test_default_session_is_a_requests_session():
    client = EtoroClient()
    assert isinstance(client._session, requests.Session)
    assert isinstance(client._bucket, TokenBucket)


# --- headers, timeout, routes ---------------------------------------------

def test_headers_are_read_from_config_on_every_request(keys, monkeypatch):
    session = FakeSession()
    client = _client(session)
    client.portfolio()
    monkeypatch.setattr(config, "ETORO_USER_KEY", "user-2")
    monkeypatch.setattr(config, "ETORO_API_KEY", "api-2")
    client.portfolio()
    first, second = (call["headers"] for call in session.calls)
    assert (first["x-user-key"], first["x-api-key"]) == ("user-1", "api-1")
    assert (second["x-user-key"], second["x-api-key"]) == ("user-2", "api-2")
    for headers in (first, second):
        assert "Authorization" not in headers and "authorization" not in headers
        assert headers["x-request-id"]
    assert first["x-request-id"] != second["x-request-id"]


def test_open_order_posts_the_body_with_the_caller_request_id_and_timeout(keys):
    session = FakeSession([FakeResponse(202, {"orderId": 7, "referenceId": "rid-1"})])
    body = {"action": "open", "transaction": "buy", "symbol": "AAPL", "units": 1.0}
    result = _client(session).open_order(body, "rid-1")
    [call] = session.calls
    assert (call["method"], call["url"]) == ("POST", API_BASE + OPEN_PATH)
    assert call["json"] == body
    assert call["headers"]["x-request-id"] == "rid-1"
    assert call["timeout"] == REQUEST_TIMEOUT_S == 10
    assert result == ClientResult(202, {"orderId": 7, "referenceId": "rid-1"})
    assert result.ok


@pytest.mark.parametrize("units,expected", [(2.5, 2.5), (None, None)])
def test_close_position_fills_the_path_and_body(keys, units, expected):
    session = FakeSession()
    _client(session).close_position(4242, 1001, units, "rid-close")
    [call] = session.calls
    assert call["method"] == "POST"
    assert call["url"] == API_BASE + CLOSE_PATH.format(position_id=4242)
    assert call["url"].endswith("/demo/market-close-orders/positions/4242")
    assert call["json"] == {"InstrumentID": 1001, "UnitsToDeduct": expected}
    assert call["headers"]["x-request-id"] == "rid-close"


def test_update_stop_patches_the_position(keys):
    session = FakeSession([FakeResponse(202, {"operationId": "op"})])
    result = _client(session).update_stop(4242, 101.5, "rid-stop")
    [call] = session.calls
    assert (call["method"], call["url"]) == ("PATCH", API_BASE + POSITION_PATH.format(position_id=4242))
    assert call["json"] == {"stopLossRate": 101.5}
    assert call["headers"]["x-request-id"] == "rid-stop"
    assert result.status_code == 202


def test_read_routes_use_params_and_bodies(keys):
    session = FakeSession()
    client = _client(session)
    client.lookup("rid-1")
    client.eligibility("AAPL")
    client.rates(1001)
    client.portfolio()
    client.history("2026-10-01", page=2, page_size=50)
    lookup, elig, rates, portfolio, history = session.calls
    assert (lookup["method"], lookup["url"], lookup["params"]) == (
        "GET", API_BASE + LOOKUP_PATH, {"referenceId": "rid-1"})
    assert (elig["method"], elig["url"], elig["json"]) == (
        "POST", API_BASE + ELIGIBILITY_PATH, {"symbols": ["AAPL"]})
    assert (rates["method"], rates["url"], rates["params"]) == (
        "GET", API_BASE + RATES_PATH, {"instrumentIds": "1001"})
    assert (portfolio["method"], portfolio["url"]) == ("GET", API_BASE + PORTFOLIO_PATH)
    assert (history["method"], history["url"], history["params"]) == (
        "GET", API_BASE + HISTORY_PATH, {"minDate": "2026-10-01", "page": 2, "pageSize": 50})
    assert all(call["timeout"] == REQUEST_TIMEOUT_S for call in session.calls)


# --- results ----------------------------------------------------------------

def test_429_carries_retry_after_seconds(keys):
    session = FakeSession([FakeResponse(429, {"error": "slow down"}, {"Retry-After": "12"})])
    result = _client(session).open_order({}, "rid")
    assert (result.status_code, result.retry_after, result.ok) == (429, 12.0, False)


@pytest.mark.parametrize("raw", ["soon", "-3", "nan", ""])
def test_unusable_retry_after_is_none(keys, raw):
    session = FakeSession([FakeResponse(429, {}, {"Retry-After": raw})])
    assert _client(session).open_order({}, "rid").retry_after is None


def test_a_transport_error_becomes_a_result_never_an_exception(keys):
    session = FakeSession([requests.Timeout("read timed out")])
    result = _client(session).lookup("rid")
    assert result.status_code == 0 and not result.ok and not result.deferred
    assert result.error.startswith("Timeout: ")


def test_a_non_json_body_falls_back_to_text(keys):
    session = FakeSession([FakeResponse(500, None, text="gateway down"),
                           FakeResponse(204, None, text="")])
    client = _client(session)
    assert client.portfolio().body == "gateway down"
    assert client.portfolio().body is None


# --- the order bucket ------------------------------------------------------

def test_default_bucket_is_15_per_60_seconds():
    assert (ORDER_BUCKET_CAPACITY, ORDER_BUCKET_WINDOW_S) == (15, 60.0)
    bucket = TokenBucket()
    assert (bucket.capacity, bucket.window_s) == (15, 60.0)


def test_an_empty_bucket_defers_order_calls_without_sleeping(keys, no_sleep):
    clock = ManualClock()
    session = FakeSession()
    client = _client(session, TokenBucket(capacity=2, window_s=60.0, clock=clock))
    assert client.open_order({}, "a").status_code == 200
    assert client.close_position(1, 2, None, "b").status_code == 200
    deferred = client.open_order({}, "c")
    assert deferred == ClientResult(0, deferred=True)
    assert client.close_position(1, 2, 1.0, "d").deferred is True
    assert len(session.calls) == 2


def test_stop_moves_and_reads_never_take_an_order_token(keys, no_sleep):
    session = FakeSession()
    client = _client(session, TokenBucket(capacity=1, clock=ManualClock()))
    assert client.open_order({}, "a").ok
    assert client.update_stop(1, 99.0, "b").ok
    assert client.lookup("a").ok
    assert client.eligibility("AAPL").ok
    assert client.open_order({}, "c").deferred is True
    assert len(session.calls) == 4


def test_the_bucket_refills_after_the_window(no_sleep):
    clock = ManualClock()
    bucket = TokenBucket(capacity=2, window_s=60.0, clock=clock)
    assert bucket.try_take() and bucket.try_take()
    assert bucket.try_take() is False
    clock.advance(59.9)
    assert bucket.try_take() is False
    clock.advance(0.1)
    assert bucket.try_take() is True
    assert bucket.try_take() is True
    assert bucket.try_take() is False


def test_the_module_never_imports_a_sleep():
    source = Path(etoro_client.__file__).read_text(encoding="utf-8")
    assert "sleep" not in source
```

- [ ] **Step 3: Write the failing demo-only path test**

Create `tests/broker/test_demo_only_paths.py`:

```python
"""v160 EM7: no real-account route string anywhere in the broker code.

Every string constant (f-string pieces and docstrings included) that looks
like an eToro route (`/api/v<N>/` or `/trading/`) must be a demo route: it
names a `/demo/` segment and no `real` segment. The market-data rates route
has no account and no `/trading/` segment, so it passes. Scope: every module
under swingbot/core/broker/ and the eToro ops scripts.
"""
import ast
import inspect
import re
from pathlib import Path

from swingbot.core.broker import etoro_client

ROOT = Path(__file__).resolve().parents[2]
_REAL_SEGMENT_RE = re.compile(r"(^|/)real(/|$|\?)", re.IGNORECASE)


def _is_route(text: str) -> bool:
    return "/api/v" in text or "/trading/" in text


def _is_real_route(text: str) -> bool:
    if _REAL_SEGMENT_RE.search(text):
        return True
    return "/trading/" in text and "/demo/" not in text


def _scanned(root: Path) -> list[Path]:
    broker = sorted((root / "swingbot" / "core" / "broker").rglob("*.py"))
    scripts = sorted((root / "scripts" / "ops").glob("etoro_*.py"))
    return [path for path in broker + scripts if "__pycache__" not in path.parts]


def real_account_routes(root: Path) -> list[str]:
    bad = []
    for path in _scanned(root):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and _is_route(node.value) and _is_real_route(node.value)):
                bad.append(f"{rel}: {node.value}")
    return bad


def test_no_real_account_route_in_the_broker_code():
    assert real_account_routes(ROOT) == []


def test_the_scan_sees_the_client():
    scanned = {path.relative_to(ROOT).as_posix() for path in _scanned(ROOT)}
    assert "swingbot/core/broker/etoro_client.py" in scanned


def _module(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_the_scan_flags_planted_real_routes(tmp_path):
    _module(tmp_path, "swingbot/core/broker/bad.py",
            'A = "/api/v3/trading/execution/orders"\n'
            'B = "/api/v1/trading/execution/real/orders"\n')
    _module(tmp_path, "scripts/ops/etoro_bad.py",
            'C = f"/api/v2/trading/real/positions/{1}"\n')
    _module(tmp_path, "swingbot/core/broker/good.py",
            'D = "/api/v3/trading/execution/demo/orders"\n'
            'E = "/api/v2/market-data/rates"\n'
            'SETTLEMENT = "real"\n')
    _module(tmp_path, "scripts/ops/other.py", 'F = "/api/v1/trading/real/x"\n')
    assert sorted(real_account_routes(tmp_path)) == [
        "scripts/ops/etoro_bad.py: /api/v2/trading/real/positions/",
        "swingbot/core/broker/bad.py: /api/v1/trading/execution/real/orders",
        "swingbot/core/broker/bad.py: /api/v3/trading/execution/orders",
    ]


def test_every_client_path_is_a_demo_route_or_market_data():
    paths = [etoro_client.OPEN_PATH, etoro_client.CLOSE_PATH, etoro_client.POSITION_PATH,
             etoro_client.LOOKUP_PATH, etoro_client.ELIGIBILITY_PATH,
             etoro_client.PORTFOLIO_PATH, etoro_client.HISTORY_PATH]
    assert all("/demo/" in path for path in paths)
    assert etoro_client.RATES_PATH == "/api/v2/market-data/rates"
    assert etoro_client.API_BASE == "https://public-api.etoro.com"


def test_the_client_takes_no_account_argument():
    assert "account" not in inspect.signature(etoro_client.EtoroClient).parameters
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_client.py`
Expected: FAIL, collection error `ModuleNotFoundError: No module named 'swingbot.core.broker.etoro_client'`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_demo_only_paths.py`
Expected: FAIL, the same collection error.

- [ ] **Step 5: Write the implementation**

Create `swingbot/core/broker/etoro_client.py`:

```python
"""Thin, demo-only REST client for the eToro Public API (v160).

One request in, one ClientResult out. Every request carries a hard 10 s
timeout, the x-user-key / x-api-key headers read from config at call time
(never an Authorization header) and an x-request-id: the caller's id for
orders and stop moves (eToro's idempotency stops a resent order), a fresh
uuid4 for reads.

Open and close orders share eToro's 20-per-60 s order pool. A sliding
15-per-60 s TokenBucket sits over it: when it is empty the call returns
ClientResult(deferred=True) at once. Nothing here waits, retries or raises
on an HTTP or transport failure; the executor owns every retry rule.

Only demo route paths are written in this module
(tests/broker/test_demo_only_paths.py). The constructor calls
guard.assert_demo("demo"); there is no account parameter.
"""
from __future__ import annotations

import collections
import math
import threading
import time
import uuid
from dataclasses import dataclass

import requests

from swingbot import config
from swingbot.core.broker import guard

API_BASE = "https://public-api.etoro.com"
OPEN_PATH = "/api/v3/trading/execution/demo/orders"
CLOSE_PATH = "/api/v1/trading/execution/demo/market-close-orders/positions/{position_id}"
POSITION_PATH = "/api/v2/trading/demo/positions/{position_id}"
LOOKUP_PATH = "/api/v2/trading/info/demo/orders:lookup"
ELIGIBILITY_PATH = "/api/v2/trading/info/demo/eligibility"
RATES_PATH = "/api/v2/market-data/rates"
PORTFOLIO_PATH = "/api/v1/trading/info/demo/portfolio"
HISTORY_PATH = "/api/v1/trading/info/trade/demo/history"

REQUEST_TIMEOUT_S = 10
ORDER_BUCKET_CAPACITY = 15
ORDER_BUCKET_WINDOW_S = 60.0


@dataclass(frozen=True)
class ClientResult:
    status_code: int                 # 0 = not sent (deferred) or transport error
    body: object = None
    retry_after: float | None = None
    deferred: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class TokenBucket:
    """Sliding window of at most `capacity` takes per `window_s`. Never waits."""

    def __init__(self, capacity: int = ORDER_BUCKET_CAPACITY,
                 window_s: float = ORDER_BUCKET_WINDOW_S, clock=time.monotonic):
        self.capacity = int(capacity)
        self.window_s = float(window_s)
        self._clock = clock
        self._taken: collections.deque = collections.deque()
        self._lock = threading.Lock()

    def try_take(self) -> bool:
        with self._lock:
            now = self._clock()
            while self._taken and now - self._taken[0] >= self.window_s:
                self._taken.popleft()
            if len(self._taken) >= self.capacity:
                return False
            self._taken.append(now)
            return True


def _headers(request_id: str) -> dict:
    return {
        "x-user-key": str(config.ETORO_USER_KEY or ""),
        "x-api-key": str(config.ETORO_API_KEY or ""),
        "x-request-id": str(request_id),
        "Accept": "application/json",
    }


def _read_id() -> str:
    return str(uuid.uuid4())


def _retry_after(headers) -> float | None:
    raw = (headers or {}).get("Retry-After")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _body(response) -> object:
    try:
        return response.json()
    except ValueError:
        return response.text or None


class EtoroClient:
    """Demo-account routes only. Construction refuses unless assert_demo passes."""

    def __init__(self, *, session=None, bucket: TokenBucket | None = None):
        guard.assert_demo("demo")
        self._session = session if session is not None else requests.Session()
        self._bucket = bucket if bucket is not None else TokenBucket()

    # --- order pool (bucketed) ---------------------------------------------
    def open_order(self, body: dict, request_id: str) -> ClientResult:
        return self._order("POST", OPEN_PATH, request_id, json=body)

    def close_position(self, position_id: int, instrument_id: int,
                       units: float | None, request_id: str) -> ClientResult:
        payload = {"InstrumentID": int(instrument_id),
                   "UnitsToDeduct": None if units is None else float(units)}
        path = CLOSE_PATH.format(position_id=int(position_id))
        return self._order("POST", path, request_id, json=payload)

    # --- default pool ------------------------------------------------------
    def update_stop(self, position_id: int, stop_rate: float, request_id: str) -> ClientResult:
        path = POSITION_PATH.format(position_id=int(position_id))
        return self._send("PATCH", path, request_id, json={"stopLossRate": float(stop_rate)})

    def lookup(self, reference_id: str) -> ClientResult:
        return self._send("GET", LOOKUP_PATH, _read_id(), params={"referenceId": reference_id})

    def eligibility(self, symbol: str) -> ClientResult:
        return self._send("POST", ELIGIBILITY_PATH, _read_id(), json={"symbols": [symbol]})

    def rates(self, instrument_id: int) -> ClientResult:
        return self._send("GET", RATES_PATH, _read_id(),
                          params={"instrumentIds": str(int(instrument_id))})

    def portfolio(self) -> ClientResult:
        return self._send("GET", PORTFOLIO_PATH, _read_id())

    def history(self, min_date: str, page: int = 1, page_size: int = 200) -> ClientResult:
        params = {"minDate": min_date, "page": int(page), "pageSize": int(page_size)}
        return self._send("GET", HISTORY_PATH, _read_id(), params=params)

    # --- transport ---------------------------------------------------------
    def _order(self, method: str, path: str, request_id: str, **kwargs) -> ClientResult:
        if not self._bucket.try_take():
            return ClientResult(0, deferred=True)
        return self._send(method, path, request_id, **kwargs)

    def _send(self, method: str, path: str, request_id: str, *,
              json: dict | None = None, params: dict | None = None) -> ClientResult:
        try:
            response = self._session.request(
                method, API_BASE + path, headers=_headers(request_id),
                json=json, params=params, timeout=REQUEST_TIMEOUT_S)
        except requests.RequestException as exc:
            return ClientResult(0, error=f"{type(exc).__name__}: {exc}")
        return ClientResult(int(response.status_code), _body(response),
                            _retry_after(getattr(response, "headers", None)))
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_client.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_demo_only_paths.py`
Expected: PASS.

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py`
Expected: PASS, including v159's `test_no_module_in_the_repo_touches_etoro_without_the_guard`: `etoro_client.py` names the broker host and reads both keys, and passes because it calls `guard.assert_demo("demo")`. If the scan lists the client, the call is missing or misspelt; never add it to `EXEMPT`.

- [ ] **Step 7: Complexity check**

Run: `python -m radon cc -s -n C "$WT/swingbot/core/broker/etoro_client.py"`
Expected: no output (the largest function, `TokenBucket.try_take`, is about A 4).

- [ ] **Step 8: Commit**

```bash
git -C "$WT" add swingbot/core/broker/etoro_client.py tests/broker/test_client.py tests/broker/test_demo_only_paths.py
git -C "$WT" commit -m "feat(v160): EM7 etoro_client.py -- demo-only REST client, 10 s timeout, non-sleeping 15/60 s order bucket"
```
