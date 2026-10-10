# v152 part 3b: notify policy tables, D3 `loops.py` wiring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V152-15:" -A 400 docs/superpowers/plans/2026-10-10-v152-discord-notify-taken-cooldown_3b-policy-and-loops.md`.

**Bump:** bot minor · ui patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md`](../specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md) § D1 (event mapping, `/notify` defaults), § D3 (Where, Visible held count, Record)
**Index:** [`2026-10-10-v152-discord-notify-taken-cooldown_0-index.md`](2026-10-10-v152-discord-notify-taken-cooldown_0-index.md): Global Constraints, Decisions fixed by this index (9, 13 bind this file), the task ledger and the full `## Parallelisation` live there and bind every task below.

Part 3 is split in two files only to stay under 1500 lines: [`_3-cooldown-near-stop-policy`](2026-10-10-v152-discord-notify-taken-cooldown_3-cooldown-near-stop-policy.md) holds V152-11 .. V152-13, this file V152-14 and V152-15. Same part, same ledger rows, same contracts.

## Parallelisation

- **V152-14** (`follow_notify.py`, pure) is parallel with V152-11, V152-12, V152-13 and every part-2 task: disjoint files, it consumes only the `near_stop` transition string.
- **V152-15 after V152-12** (consumes `send_then_short(..., apply_cooldown=) -> list`) and V152-11 (`held_note`, `prune`). Part 4's V152-18 edits `loops.py` after it.

# Phase 5 (continued): Notify policy

### Task V152-14: Notify event mapping + mention policy

**Model:** sonnet — a new pure module of lookup tables with a fixed contract from the spec's event table and index decision 9; no I/O, no async.

**Files:**
- Create: `swingbot/commands/scanning/follow_notify.py`
- Create: `tests/commands/test_follow_notify_policy.py`

**Consumes:** `PlanEvent`, `_STOPPED_REASONS` (`plan_manager.py:55`, `:89`, exist); the `near_stop` transition (V152-13 — only the string, so this task does not wait for it); `Kind` members `NEAR_STOP`, `TP1_HIT`, `WIN`, `STOPPED`, `EXPIRED`, `EXITED`, `INVALIDATED`, `RISK_CAP` (`kinds.py:118-134`, exist).
**Produces (ledger):** `NOTIFY_EVENTS`; `EVENT_LABELS: dict[str, str]`; `FOLLOWING_ONLY = frozenset({"closed_other"})`; `_BY_REASON: dict[tuple[str, str], str]`; `_BY_TRANSITION: dict[str, str]`; `notify_event_for(event) -> str | None`; `kind_for(event, notify_event: str) -> Kind`; `WATCH_DEFAULTS: dict[str, bool]`; `mentions_user(kinds: frozenset[str], notify_event: str, prefs: dict) -> bool`; `eligible_mentions(followers: dict[int, frozenset[str]], notify_event: str, prefs_by_user: dict[int, dict]) -> list[int]`; `posts_message(notify_event: str, followers: dict[int, frozenset[str]]) -> bool`. V152-16/17 append to this file; V152-19 reads `NOTIFY_EVENTS`, `EVENT_LABELS`, `WATCH_DEFAULTS`.

**Design.**
- Mapping (spec § D1 Events): `(transition, reason)` first in `_BY_REASON` — `closed`+`win` → `tp1` (no-TP2 plan closed whole at TP1), `closed`+`tp1_runner_tp2` → `tp2`, `closed`+each `_STOPPED_REASONS` → `stopped`; then `_BY_TRANSITION` — `near_stop`, `tp1_partial` → `tp1`, `cancelled_expired` → `expired`, `cancelled_invalidated` / `cancelled_risk_cap` → `closed_other`, and `closed` → `closed_other` as the fallback (time exit, `stall_exit`, `tp1_runner_progress_stall`, any future reason). `filled`, `be_moved`, `stop_moved`, `pyramid_add` and the time notices map to `None`: a stop move is carried by the next message (spec), never its own.
- Kinds: `near_stop` `NEAR_STOP`, `tp1` `TP1_HIT`, `tp2` `WIN`, `stopped` `STOPPED`, `expired` `EXPIRED`; `closed_other` by transition — `closed` `EXITED`, `cancelled_invalidated` `INVALIDATED`, `cancelled_risk_cap` `RISK_CAP`. `MOVE_STOP` and `CANCEL` are imperative labels and appear nowhere in the module (copy rule).
- Mention policy (index decision 9, spec § `/notify`): a user whose kinds include `taken` is **Following** (both rows count as Following) and defaults ON for all six; a Watch-only user defaults ON for `tp1`, `tp2`, `stopped`, OFF for `near_stop`, `expired`, and is **never** mentioned for `closed_other`; `watch_mode="silent"` drops every Watch-only mention; an explicit boolean in the user's prefs overrides the default for either kind (but never lets a Watch-only user into `closed_other` or past `silent`). A preference decides only the mention, never whether the message posts.
- `posts_message`: every event posts (silently when nobody is mentioned, V152-17), except `closed_other`, which posts only with at least one Following follower.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_follow_notify_policy.py`:

```python
"""v152 D1: follow_notify's event mapping and mention policy (pure tables)."""
import ast
import inspect

import pytest

from swingbot.commands.scanning import follow_notify as fn
from swingbot.core.planning.plan_manager import _STOPPED_REASONS, PlanEvent
from swingbot.core.presentation.kinds import Kind

FOLLOWING = frozenset({"taken"})
WATCH = frozenset({"watch"})
BOTH = frozenset({"watch", "taken"})


def _event(transition, reason=None):
    return PlanEvent("p1", transition, {"reason": reason} if reason else {})


@pytest.mark.parametrize("transition, reason, expected, kind", [
    ("near_stop", None, "near_stop", Kind.NEAR_STOP),
    ("tp1_partial", None, "tp1", Kind.TP1_HIT),
    ("closed", "win", "tp1", Kind.TP1_HIT),
    ("closed", "tp1_runner_tp2", "tp2", Kind.WIN),
    ("closed", "loss", "stopped", Kind.STOPPED),
    ("closed", "scratch", "stopped", Kind.STOPPED),
    ("closed", "tp1_runner_be", "stopped", Kind.STOPPED),
    ("closed", "tp1_runner_trail", "stopped", Kind.STOPPED),
    ("cancelled_expired", None, "expired", Kind.EXPIRED),
    ("closed", "time_exit", "closed_other", Kind.EXITED),
    ("closed", "stall_exit", "closed_other", Kind.EXITED),
    ("closed", "tp1_runner_progress_stall", "closed_other", Kind.EXITED),
    ("closed", None, "closed_other", Kind.EXITED),
    ("cancelled_invalidated", None, "closed_other", Kind.INVALIDATED),
    ("cancelled_risk_cap", None, "closed_other", Kind.RISK_CAP),
])
def test_each_transition_picks_its_notify_event_and_kind(transition, reason, expected, kind):
    event = _event(transition, reason)
    assert fn.notify_event_for(event) == expected
    assert fn.kind_for(event, expected) is kind


@pytest.mark.parametrize("transition", ["filled", "be_moved", "stop_moved", "pyramid_add",
                                        "time_exit_due", "time_exit_unresolved"])
def test_other_transitions_are_not_notify_events(transition):
    assert fn.notify_event_for(_event(transition)) is None


def test_every_stopped_reason_is_mapped():
    assert {reason for (t, reason), ev in fn._BY_REASON.items() if ev == "stopped"} == set(
        _STOPPED_REASONS)


def test_the_six_events_share_one_table():
    assert fn.NOTIFY_EVENTS == ("near_stop", "tp1", "tp2", "stopped", "expired", "closed_other")
    assert tuple(fn.EVENT_LABELS) == fn.NOTIFY_EVENTS
    assert tuple(fn.WATCH_DEFAULTS) == fn.NOTIFY_EVENTS
    assert set(fn._BY_TRANSITION.values()) | set(fn._BY_REASON.values()) == set(fn.NOTIFY_EVENTS)
    assert "Following only" in fn.EVENT_LABELS["closed_other"]


def test_imperative_kinds_are_never_used():
    source = inspect.getsource(fn)
    assert "MOVE_STOP" not in source and "Kind.CANCEL" not in source


@pytest.mark.parametrize("event", ["near_stop", "tp1", "tp2", "stopped", "expired", "closed_other"])
def test_following_defaults_on_for_every_event(event):
    assert fn.mentions_user(FOLLOWING, event, {}) is True
    assert fn.mentions_user(BOTH, event, {}) is True


@pytest.mark.parametrize("event, expected", [
    ("near_stop", False), ("tp1", True), ("tp2", True), ("stopped", True),
    ("expired", False), ("closed_other", False),
])
def test_watch_only_defaults(event, expected):
    assert fn.mentions_user(WATCH, event, {}) is expected


def test_an_explicit_toggle_overrides_the_default_for_either_kind():
    assert fn.mentions_user(WATCH, "near_stop", {"near_stop": True}) is True
    assert fn.mentions_user(WATCH, "tp1", {"tp1": False}) is False
    assert fn.mentions_user(FOLLOWING, "stopped", {"stopped": False}) is False


def test_watch_only_is_never_mentioned_for_closed_other_even_when_toggled_on():
    assert fn.mentions_user(WATCH, "closed_other", {"closed_other": True}) is False


def test_silent_watch_mode_drops_watch_only_mentions_but_not_following():
    prefs = {"watch_mode": "silent", "tp1": True}
    assert fn.mentions_user(WATCH, "tp1", prefs) is False
    assert fn.mentions_user(FOLLOWING, "tp1", prefs) is True
    assert fn.mentions_user(BOTH, "tp1", prefs) is True
    assert fn.mentions_user(WATCH, "tp1", {"watch_mode": "mention"}) is True


def test_eligible_mentions_are_sorted_and_use_each_users_prefs():
    followers = {30: WATCH, 10: FOLLOWING, 20: WATCH}
    prefs = {20: {"watch_mode": "silent"}}
    assert fn.eligible_mentions(followers, "tp1", prefs) == [10, 30]
    assert fn.eligible_mentions(followers, "near_stop", prefs) == [10]
    assert fn.eligible_mentions(followers, "closed_other", {}) == [10]
    assert fn.eligible_mentions({}, "tp1", {}) == []


def test_closed_other_posts_only_with_a_following_follower():
    assert fn.posts_message("closed_other", {1: WATCH}) is False
    assert fn.posts_message("closed_other", {}) is False
    assert fn.posts_message("closed_other", {1: WATCH, 2: BOTH}) is True


@pytest.mark.parametrize("event", ["near_stop", "tp1", "tp2", "stopped", "expired"])
def test_every_other_event_posts_with_or_without_followers(event):
    assert fn.posts_message(event, {}) is True
    assert fn.posts_message(event, {1: WATCH}) is True


def test_the_policy_is_tables_not_if_chains():
    tree = ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            assert not (node.orelse and isinstance(node.orelse[0], ast.If)), (
                f"if/elif chain at line {node.lineno}: use a table")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_follow_notify_policy.py`
Expected: FAIL — `ImportError: cannot import name 'follow_notify' from 'swingbot.commands.scanning'`.

- [ ] **Step 3: Write `follow_notify.py`**

Create `swingbot/commands/scanning/follow_notify.py`:

```python
"""v152 D1: the follow-notify channel (DISCORD_CHANNEL_NOTIFY_ID).

Factual paper-plan updates for plans people follow -- near stop, TP1, TP2,
stopped, expired, and closed/cancelled for Following followers only -- each
mentioning the followers who want it. This first part is pure policy: which
PlanEvent is which notify event, which Kind it renders as, and whom it
mentions. The copy table and embed (V152-16) and the claim / send / retry
delivery (V152-17) build on these tables. No if/elif chains: every rule is
a table.
"""
from __future__ import annotations

from swingbot.core.planning.plan_manager import _STOPPED_REASONS, PlanEvent
from swingbot.core.presentation.kinds import Kind

NOTIFY_EVENTS = ("near_stop", "tp1", "tp2", "stopped", "expired", "closed_other")

# What the channel announces, in /notify's words (factual, no imperatives).
EVENT_LABELS = {
    "near_stop": "Near stop: price within 0.25R of the plan's stop (regular session)",
    "tp1": "TP1 reached",
    "tp2": "Closed at TP2",
    "stopped": "Closed at its stop (initial, breakeven or trailing)",
    "expired": "Expired unfilled",
    "closed_other": "Closed or cancelled for any other reason (Following only)",
}

# Posted only when the plan has at least one Following follower.
FOLLOWING_ONLY = frozenset({"closed_other"})

# (transition, reason) first, then transition; "closed" falls back to closed_other.
_BY_REASON: dict[tuple[str, str], str] = {
    ("closed", "win"): "tp1",                 # no-TP2 plan closed whole at TP1
    ("closed", "tp1_runner_tp2"): "tp2",
    **{("closed", reason): "stopped" for reason in sorted(_STOPPED_REASONS)},
}
_BY_TRANSITION: dict[str, str] = {
    "near_stop": "near_stop",
    "tp1_partial": "tp1",
    "cancelled_expired": "expired",
    "cancelled_invalidated": "closed_other",
    "cancelled_risk_cap": "closed_other",
    "closed": "closed_other",
}

_KIND_BY_EVENT = {
    "near_stop": Kind.NEAR_STOP,
    "tp1": Kind.TP1_HIT,
    "tp2": Kind.WIN,
    "stopped": Kind.STOPPED,
    "expired": Kind.EXPIRED,
}
_CLOSED_OTHER_KIND = {
    "closed": Kind.EXITED,
    "cancelled_invalidated": Kind.INVALIDATED,
    "cancelled_risk_cap": Kind.RISK_CAP,
}

FOLLOWING_DEFAULTS: dict[str, bool] = dict.fromkeys(NOTIFY_EVENTS, True)
WATCH_DEFAULTS: dict[str, bool] = {
    "near_stop": False,
    "tp1": True,
    "tp2": True,
    "stopped": True,
    "expired": False,
    "closed_other": False,
}


def notify_event_for(event: PlanEvent) -> str | None:
    """The notify event a PlanEvent announces, or None when it announces none."""
    reason = (event.detail or {}).get("reason")
    return _BY_REASON.get((event.transition, reason)) or _BY_TRANSITION.get(event.transition)


def kind_for(event: PlanEvent, notify_event: str) -> Kind:
    """The registry Kind the message renders as (never MOVE STOP or CANCEL)."""
    if notify_event == "closed_other":
        return _CLOSED_OTHER_KIND[event.transition]
    return _KIND_BY_EVENT[notify_event]


def mentions_user(kinds: frozenset[str], notify_event: str, prefs: dict) -> bool:
    """Whether one follower is mentioned. Following (a 'taken' row) wins over
    Watch; Watch-only is never mentioned for closed_other or in silent mode;
    otherwise an explicit per-event toggle beats the default."""
    following = "taken" in kinds
    if not following and (notify_event in FOLLOWING_ONLY or prefs.get("watch_mode") == "silent"):
        return False
    explicit = prefs.get(notify_event)
    if isinstance(explicit, bool):
        return explicit
    return (FOLLOWING_DEFAULTS if following else WATCH_DEFAULTS)[notify_event]


def eligible_mentions(followers: dict[int, frozenset[str]], notify_event: str,
                      prefs_by_user: dict[int, dict]) -> list[int]:
    """Sorted user ids to mention for one message."""
    return sorted(user_id for user_id, kinds in followers.items()
                  if mentions_user(kinds, notify_event, prefs_by_user.get(user_id, {})))


def posts_message(notify_event: str, followers: dict[int, frozenset[str]]) -> bool:
    """Every event posts, except closed_other without a Following follower."""
    return notify_event not in FOLLOWING_ONLY or any(
        "taken" in kinds for kinds in followers.values())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/commands/test_follow_notify_policy.py`
Expected: PASS.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/commands/scanning/follow_notify.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/follow_notify.py tests/commands/test_follow_notify_policy.py
git commit -m "feat(v152): follow-notify event mapping and mention policy tables"
```

# Phase 6: D3 wiring in `loops.py`

### Task V152-15: D3 `loops.py`: scheduled flag, ops note, nightly prune

**Model:** sonnet — three small edits in the scheduler module with a fixed contract; the care is in leaving every non-scheduled caller and the store-write-halt path untouched, which the tests below pin.

**Files:**
- Modify: `swingbot/commands/scanning/loops.py` (package import :22; `_post_cooldown_note` and `_prune_alert_posts` after `_run_scan_posting_partial` :102-115; `_session_scan_tick` :197-200; `daily_recap` :690-693)
- Create: `tests/commands/test_loops_cooldown.py`

**Consumes:** `send_then_short(..., apply_cooldown: bool = False) -> list` (V152-12); `cooldown.held_note(held) -> str | None`, `cooldown.prune(now=None) -> int` (V152-11); `_ops_channel()` (`loops.py:51`, exists).
**Produces (ledger):** `loops._post_cooldown_note(held: list) -> None` (async); `_session_scan_tick` passes `apply_cooldown=True`; `daily_recap` calls `cooldown.prune` via `to_thread` (through the private helper `_prune_alert_posts`). V152-18 (part 4) edits this file after it and must keep all three.

**Design.**
- `apply_cooldown=True` appears **once** in `loops.py`, on the scheduled `send_then_short` call in `_session_scan_tick` (Global Constraints, Suppression scope). The store-write-halt re-post in `_run_scan_posting_partial` (:114) and the admin-UI scan's `send_then_short` in `config_watcher` (:454) stay as they are; so do `!check` (`commands.py:217`), `commands.py:173` and the outlook post (`outlook.py:83`). A source test pins all of them.
- `_session_scan_tick` is near the complexity limit (about 14 by count; measure in Step 6): it gains **no branch**. The note is one awaited call, `_post_cooldown_note(held)`, which returns at once for an empty list.
- `_post_cooldown_note` (index decision 13): one `channel.send(content=note, silent=True)` on `_ops_channel()` (ops channel, else the alerts channel, never `silence()`-wrapped) inside a `try`; any failure — the note, the channel lookup, the send — is one WARNING and never raises into the scan. `notices.send_guarded` takes an embed, so it is not reused.
- `_prune_alert_posts` runs once a day in `daily_recap`, after the retrospective's own `try`, through `asyncio.to_thread(cooldown.prune)`; a failure is one WARNING (spec § D3 Record: "failure logged"). `daily_recap` gains one call and no branch.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_loops_cooldown.py`:

```python
"""v152 D3 in the scheduler: only the scheduled scan applies the cooldown,
it posts one silent ops line when it held alerts, and daily_recap prunes
alert_posts once a day. The halt re-post, the admin-UI scan, !check and the
outlook post never pass apply_cooldown."""
import asyncio
import datetime as dt
import inspect
import logging
import types

import pytest

from swingbot import config
from swingbot.commands import scanning as scanning_mod
from swingbot.commands.scanning import commands, cooldown, outlook, presence, runstate
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.db import write_failure
from swingbot.core.scanning import engine as scan_engine


class FakeChannel:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord is having a day")
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=1)


def _plan(ticker="AAPL"):
    return types.SimpleNamespace(plan_id="9d4c3b2a-1f0e-4d8c-b7a6-5e4f3a2b1c0d", ticker=ticker,
                                 direction="bullish", horizon_key="4w")


@pytest.fixture(autouse=True)
def _hours(monkeypatch):
    monkeypatch.setattr(config, "ALERT_SYMBOL_COOLDOWN_HOURS", 24.0, raising=False)


def _scan_tick_env(monkeypatch, send_then_short):
    raw = FakeChannel()
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "123", raising=False)
    monkeypatch.setattr(loops_mod, "bot",
                        types.SimpleNamespace(get_channel=lambda _id: raw), raising=False)
    monkeypatch.setattr(runstate, "is_scan_paused", lambda: False, raising=False)
    monkeypatch.setattr(loops_mod, "in_session", lambda: True, raising=False)
    monkeypatch.setattr(runstate, "_write_heartbeat", lambda: None, raising=False)

    async def _noop(*args, **kwargs):
        pass

    async def fake_run_scan(**kwargs):
        return [(types.SimpleNamespace(title="AAPL setup", footer=None), None, None)]

    monkeypatch.setattr(presence, "_check_session_transition", _noop, raising=False)
    monkeypatch.setattr(presence, "_refresh_presence", _noop, raising=False)
    monkeypatch.setattr(presence, "_post_healthcheck", _noop, raising=False)
    monkeypatch.setattr(loops_mod, "_refresh_snapshot_safely", lambda: None, raising=False)
    monkeypatch.setattr(scan_engine, "run_scan", fake_run_scan, raising=False)
    monkeypatch.setattr(loops_mod, "send_then_short", send_then_short)


def test_the_scheduled_tick_applies_the_cooldown_and_posts_its_note(monkeypatch):
    held_plan, calls, notes = _plan(), [], []

    async def fake_send_then_short(channel, alerts, **kwargs):
        calls.append(kwargs)
        return [held_plan]

    async def fake_note(held):
        notes.append(held)

    _scan_tick_env(monkeypatch, fake_send_then_short)
    monkeypatch.setattr(loops_mod, "_post_cooldown_note", fake_note)
    asyncio.run(loops_mod._session_scan_tick())
    assert calls == [{"bot": loops_mod.bot, "require_confirmation": True,
                      "route_by_confidence": True, "apply_cooldown": True}]
    assert notes == [[held_plan]]


def test_the_halt_repost_never_applies_the_cooldown_and_still_raises(monkeypatch):
    seen = []

    async def fake_send(channel, alerts, route_by_confidence=False, **kwargs):
        seen.append(kwargs)
        return []

    async def halted(**kwargs):
        raise write_failure.StoreWriteHalt("plan P2", alerts=["alert-1"])

    monkeypatch.setattr(loops_mod, "_send_alerts", fake_send)
    monkeypatch.setattr(loops_mod.scan_engine, "run_scan", halted)
    with pytest.raises(write_failure.StoreWriteHalt):
        asyncio.run(loops_mod._run_scan_posting_partial("chan", require_confirmation=True))
    assert seen == [{}]


def test_only_the_scheduled_tick_passes_apply_cooldown():
    assert inspect.getsource(loops_mod).count("apply_cooldown=True") == 1
    assert "apply_cooldown=True" in inspect.getsource(loops_mod._session_scan_tick)
    assert "apply_cooldown" not in inspect.getsource(loops_mod._run_scan_posting_partial)
    assert "apply_cooldown" not in inspect.getsource(loops_mod.config_watcher.coro)
    assert "apply_cooldown" not in inspect.getsource(commands)
    assert "apply_cooldown" not in inspect.getsource(outlook)


def test_no_held_alerts_post_no_note(monkeypatch):
    looked_up = []
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: looked_up.append(1))
    asyncio.run(loops_mod._post_cooldown_note([]))
    assert looked_up == []


def test_held_alerts_post_one_silent_line_on_the_ops_channel(monkeypatch):
    chan = FakeChannel()
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: chan)
    held = [_plan(), _plan("MSFT")]
    asyncio.run(loops_mod._post_cooldown_note(held))
    assert chan.sent == [{"content": cooldown.held_note(held), "silent": True}]
    assert chan.sent[0]["content"].startswith("Cooldown held 2 alert(s) this scan: AAPL long 4w")


def test_a_failing_note_warns_and_never_raises(monkeypatch, caplog):
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: FakeChannel(fail=True))
    with caplog.at_level(logging.WARNING):
        asyncio.run(loops_mod._post_cooldown_note([_plan()]))
    assert any("held-alerts note" in r.getMessage() for r in caplog.records)


def test_no_ops_channel_posts_nothing_quietly(monkeypatch, caplog):
    monkeypatch.setattr(loops_mod, "_ops_channel", lambda: None)
    with caplog.at_level(logging.WARNING):
        asyncio.run(loops_mod._post_cooldown_note([_plan()]))
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def _recap_at_trigger(monkeypatch, order, prune):
    now = dt.datetime(2026, 8, 24, 23, 15)        # Monday, at the recap trigger

    class FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=tz)

    async def post():
        order.append("retrospective")

    monkeypatch.setattr(config, "SESSION_END_HOUR", 23)
    monkeypatch.setattr(loops_mod.dt, "datetime", FixedDateTime)
    monkeypatch.setattr(loops_mod.recap, "_post_retrospective", post)
    monkeypatch.setattr(loops_mod, "_recap_fired_date", None)
    monkeypatch.setattr(cooldown, "prune", prune)


def test_daily_recap_prunes_alert_posts_once_after_the_retrospective(monkeypatch):
    order = []

    def prune(now=None):
        order.append("prune")
        return 3

    _recap_at_trigger(monkeypatch, order, prune)
    asyncio.run(scanning_mod.daily_recap.coro())
    monkeypatch.setattr(loops_mod, "_recap_fired_date", None)
    asyncio.run(scanning_mod.daily_recap.coro())          # same day: already fired
    assert order == ["retrospective", "prune"]


def test_a_failing_prune_is_logged_and_never_raises(monkeypatch, caplog):
    order = []

    def prune(now=None):
        raise RuntimeError("database is having a day")

    _recap_at_trigger(monkeypatch, order, prune)
    with caplog.at_level(logging.WARNING):
        asyncio.run(scanning_mod.daily_recap.coro())
    assert order == ["retrospective"]
    assert any("prune alert_posts" in r.getMessage() for r in caplog.records)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_loops_cooldown.py`
Expected: FAIL — `AttributeError: module 'swingbot.commands.scanning.loops' has no attribute '_post_cooldown_note'` (and the scheduled-tick kwargs lack `apply_cooldown`).

- [ ] **Step 3: Import the cooldown module**

In `swingbot/commands/scanning/loops.py`, change

```python
from . import notices, outlook, presence, recap, runstate
```

to

```python
from . import cooldown, notices, outlook, presence, recap, runstate
```

- [ ] **Step 4: Add the two guarded helpers**

Directly after `_run_scan_posting_partial` (which stays byte-for-byte unchanged) and before `@tasks.loop(minutes=config.SCAN_INTERVAL_MINUTES)`, insert:

```python
async def _post_cooldown_note(held: list) -> None:
    """v152 D3: one silent line on the ops channel (else the alerts channel)
    when the scheduled scan held >= 1 alert -- the held count stays visible
    with the digest off. Guarded like notices.send_guarded: any failure is
    one WARNING and never raises into the scan."""
    if not held:
        return
    try:
        note = cooldown.held_note(held)
        channel = _ops_channel()
        if channel is not None:
            await channel.send(content=note, silent=True)
    except Exception:
        log.warning("cooldown: could not post the held-alerts note", exc_info=True)


async def _prune_alert_posts() -> None:
    """v152 D3: the nightly alert_posts trim (keeps max(window, 7 days));
    a failure is logged, never raised."""
    try:
        removed = await asyncio.to_thread(cooldown.prune)
        log.info("daily_recap: pruned %d alert_posts row(s)", removed)
    except Exception:
        log.warning("daily_recap: could not prune alert_posts", exc_info=True)
```

- [ ] **Step 5: Apply the cooldown on the scheduled scan and prune nightly**

In `_session_scan_tick`, replace

```python
    await send_then_short(channel, alerts, bot=bot, require_confirmation=True,
                          route_by_confidence=True)
```

with

```python
    # v152 D3: the only caller that applies the per-symbol cooldown -- the
    # admin-UI scan, !check and the store-write-halt re-post never do.
    held = await send_then_short(channel, alerts, bot=bot, require_confirmation=True,
                                 route_by_confidence=True, apply_cooldown=True)
    await _post_cooldown_note(held)
```

In `daily_recap`, replace the tail

```python
    try:
        await recap._post_retrospective()
    except Exception:
        log.exception("daily_recap: failed to post retrospective")
```

with

```python
    try:
        await recap._post_retrospective()
    except Exception:
        log.exception("daily_recap: failed to post retrospective")
    await _prune_alert_posts()
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/commands/test_loops_cooldown.py`
Expected: PASS.

Run each of these (they drive `_session_scan_tick`, `daily_recap` or the halt path):
- `python scripts/dev/testrun.py file tests/infra/test_silent_alerts_channel.py`
- `python scripts/dev/testrun.py file tests/scanning/test_short_lane_scan.py`
- `python scripts/dev/testrun.py file tests/commands/test_scheduled_jobs.py`
- `python scripts/dev/testrun.py file tests/commands/test_store_write_halt.py`
- `python scripts/dev/testrun.py file tests/scanning/test_heartbeat_outcome.py`
- `python scripts/dev/testrun.py file tests/commands/test_scanning_package.py`

Expected: PASS each. `test_silent_alerts_channel.py::test_the_scan_tick_actually_delivers_a_built_alert` still sees exactly one send: its alert has no plan, so nothing is held and no note posts.

- [ ] **Step 7: Complexity**

Run: `git show HEAD:swingbot/commands/scanning/loops.py > "${TMPDIR:-/tmp}/loops_head.py"`, then `python -m radon cc -s -n C "${TMPDIR:-/tmp}/loops_head.py"` and `python -m radon cc -s -n C swingbot/commands/scanning/loops.py`.
Expected: `_session_scan_tick` and `daily_recap` print the same figure in both runs (or are absent from both — below C); `_post_cooldown_note` and `_prune_alert_posts` absent from the second.

- [ ] **Step 8: Commit**

```bash
git add swingbot/commands/scanning/loops.py tests/commands/test_loops_cooldown.py
git commit -m "feat(v152): cooldown on the scheduled scan only, held-alerts ops note, nightly prune"
```
