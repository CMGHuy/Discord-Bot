# v192 — Wait for a reclaim when a market plan's next open gaps toward its stop, Part 2b: notices, the alert and live integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** bot patch
**Edge:** expectancy — see the index.
**Spec:** [2026-10-24-v192-gap-toward-stop-reclaim-design.md](../specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md)
**Index:** [2026-10-24-v192-gap-toward-stop-reclaim_0-index.md](2026-10-24-v192-gap-toward-stop-reclaim_0-index.md) — Goal, Global Constraints, § Contracts, Review Focus, Parallelisation and the task ledger bind every task below. **Never read a part whole:** `grep -n "^### Task V192-12:" -A 300 <this file>`.

**Scope of this part (V192-11..V192-13):** part 2 split for length; part 2 (`_2-live-path.md`) holds V192-8..V192-10. Here: the manager's notice, log and placeholder wiring and the follower mapping; the alert's market-on-open line; scan-to-fill integration and the live/replay parity of `E`, `a_t`, `X` and the open decision.

**Where commands run, database, clock, complexity:** exactly as in part 2's header — the worktree root `.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim` (prefix every command with `cd E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim &&`); `PlanStore()` tests on the shared `swing-db` after `/replicate-prod-db`; 2026-10-13 is a Tuesday, Berlin = ET + 6 h that week; `python scripts/dev/complexity_gate.py` after every code task.

**What earlier tasks built that this part consumes:** part 1 (`gap_reclaim`, the plan fields, the knobs, waiting builders, `market_next_open`); V192-8/V192-9 (`market_open`, `PlanManager._step_market_open` and its handlers, the test helpers in `tests/planning/test_plan_manager_market_open.py`); V192-10 (`Kind.RECLAIM_ORDER`, the instruction builders).

---

# Phase 6 (continued) — Notices and followers

### Task V192-11: Manager notices, transition log, placeholder discard; follower mapping
**Model:** opus — wires the new events into the re-send queue, the trade-log placeholder and a second channel's preference tables; a miss leaves a stale order unannounced to non-followers or a phantom open trade on the dashboard.

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` — `NOTICE_EVENTS` (`:123`), `_TRANSITION_LOG` (`:138`), a new `PLACEHOLDER_DISCARD_EVENTS` beside them, the discard branch of `_on_event` (`:808-817`)
- Modify: `swingbot/commands/scanning/follow_notify.py` — `NOTIFY_EVENTS`, `EVENT_LABELS`, `_BY_TRANSITION`, `_KIND_BY_EVENT`, `_CLOSED_OTHER_KIND`, `WATCH_DEFAULTS`, `_CANCEL_LABELS`, `COPY` (`:28-208`)
- Modify: `tests/commands/test_follow_notify_policy.py` — the pin in `test_the_six_events_share_one_table` (`:54-59`)
- Create: `tests/planning/test_plan_manager_gap_reclaim_feed.py`, `tests/scanning/test_follow_notify_gap_reclaim.py`

**Interfaces:**
- Consumes: the events and details of V192-8/V192-9; `Kind.RECLAIM_ORDER` (V192-10); `pm.ack_notified`, `pm.Delivery` (existing, `plan_manager.py:262`, `:1745`); the V192-8 test helpers.
- Produces (index § Contracts): `NOTICE_EVENTS |= {"cancelled_open_through_stop", "cancelled_gap_no_reclaim", "gap_reclaim_order"}`; `PLACEHOLDER_DISCARD_EVENTS = frozenset({"cancelled_expired", "cancelled_invalidated", "cancelled_risk_cap", "cancelled_open_through_stop", "cancelled_gap_no_reclaim"})`; `_TRANSITION_LOG` rows for the three; `follow_notify._BY_TRANSITION` rows `cancelled_open_through_stop: "closed_other"`, `cancelled_gap_no_reclaim: "closed_other"`, `gap_reclaim_order: "reclaim_order"`; `_KIND_BY_EVENT["reclaim_order"] = Kind.RECLAIM_ORDER`; `_CLOSED_OTHER_KIND` rows `cancelled_open_through_stop: Kind.INVALIDATED`, `cancelled_gap_no_reclaim: Kind.EXPIRED`.

`"reclaim_order"` becomes the seventh notify event: `_BY_TRANSITION` maps to it, and `mentions_user` reads `FOLLOWING_DEFAULTS` / `WATCH_DEFAULTS` by event, which `NOTIFY_EVENTS` builds — so it joins `NOTIFY_EVENTS`, `EVENT_LABELS`, `WATCH_DEFAULTS` (off for Watch, like `expired`) and `COPY`, which also puts it on `/notify` (`commands/notify.py` enumerates `NOTIFY_EVENTS`). The policy test's pin of the six events moves to seven. `gap_reclaim_order` is a NOTICE: it is queued on `pending_notice` and re-sent until acknowledged; the single slot is overwritten by the session's fill or its `gap_no_reclaim` cancel, so a stale DAY instruction is never re-sent after the close.

- [ ] **Step 1: Write the failing manager tests** — `tests/planning/test_plan_manager_gap_reclaim_feed.py`

```python
"""V192-11: the waiting market plan's open-time events reach the execution feed's
re-send queue, the INFO log and the trade-log placeholder. DB-backed."""
import logging

import pytest

from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning.plan_engine import PlanStatus
from tests.planning.test_plan_manager_market_open import (OPEN, PREMARKET, _Log, _bull, _env,  # noqa: F401
                                                         _et, _flags, _tr)

NEW = {"cancelled_open_through_stop", "cancelled_gap_no_reclaim", "gap_reclaim_order"}


def test_the_new_events_are_feed_notices_and_none_is_follow_only():
    assert NEW <= pm.NOTICE_EVENTS
    assert not NEW & pm.FOLLOW_ONLY_EVENTS


def test_the_placeholder_discard_set():
    assert pm.PLACEHOLDER_DISCARD_EVENTS == frozenset({
        "cancelled_expired", "cancelled_invalidated", "cancelled_risk_cap",
        "cancelled_open_through_stop", "cancelled_gap_no_reclaim"})


def test_the_reclaim_order_is_queued_resent_and_acknowledged():
    store, mgr = _env(_bull(reclaim_level=99.5, reclaim_atr=2.0), [99.0, 99.2])
    first = mgr.poll(OPEN)
    assert _tr(first) == ["gap_reclaim_order"]
    notice = store.get("p1").pending_notice
    assert notice["transition"] == "gap_reclaim_order" and notice["detail"] == first[0].detail
    again = mgr.poll(_et(14, 9, 32))                   # not acked yet: re-sent
    assert [e.detail for e in again if e.transition == "gap_reclaim_order"] == [first[0].detail]
    pm.ack_notified([pm.Delivery("p1", "notice", "gap_reclaim_order")])
    assert store.get("p1").pending_notice is None


def test_the_reclaim_fill_replaces_the_queued_order():
    store, mgr = _env(_bull(reclaim_level=99.5, reclaim_atr=2.0), [99.0, 100.01])
    mgr.poll(OPEN)
    events = mgr.poll(_et(14, 10))
    assert "filled" in _tr(events)
    assert store.get("p1").pending_notice["transition"] == "filled"


def test_the_close_cancel_replaces_the_queued_order_and_drops_the_placeholder():
    log = _Log()
    store, mgr = _env(_bull(reclaim_level=99.5, reclaim_atr=2.0), [99.0, 99.2], trade_log=log)
    mgr.poll(OPEN)
    events = mgr.poll(_et(14, 16, 5))
    assert "cancelled_gap_no_reclaim" in _tr(events)
    assert store.get("p1").pending_notice["transition"] == "cancelled_gap_no_reclaim"
    assert ("discard", "p1") in log.calls


@pytest.mark.parametrize("now, prices", [(OPEN, [98.0]), (PREMARKET, [98.0, 98.0])])
def test_a_through_stop_cancel_is_queued_and_drops_the_placeholder(now, prices):
    log = _Log()
    store, mgr = _env(_bull(), prices, trade_log=log)
    for _ in prices:
        mgr.poll(now)
    plan = store.get("p1")
    assert plan.status == PlanStatus.CANCELLED
    assert plan.pending_notice["transition"] == "cancelled_open_through_stop"
    assert log.calls == [("discard", "p1")]


def test_each_new_event_writes_its_info_line(caplog):
    caplog.set_level(logging.INFO, logger=pm.log.name)
    _store, mgr = _env(_bull(reclaim_level=99.5, reclaim_atr=2.0), [99.0, 99.2])
    mgr.poll(OPEN)
    mgr.poll(_et(14, 16, 5))
    text = caplog.text
    assert "Plan reclaim order at entry: AAPL id=p1 bullish price=100.00" in text
    assert "Plan no reclaim: AAPL id=p1 bullish price=100.00" in text
    caplog.clear()
    _store, mgr = _env(_bull(plan_id="p2"), [98.0])
    mgr.poll(OPEN)
    assert "Plan opened through stop: AAPL id=p2 bullish price=98.00" in caplog.text
```

- [ ] **Step 2: Write the failing follower tests** — `tests/scanning/test_follow_notify_gap_reclaim.py`

```python
"""V192-11: the follow-notify channel's mapping of the waiting market plan's
events: the reclaim order is its own event; the two cancels are closed_other."""
import pytest

from swingbot import config
from swingbot.commands.scanning import follow_notify as fn
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation.kinds import Kind
from tests.planning.test_plan_engine_model import _plan

FOLLOWING = frozenset({"taken"})
WATCH = frozenset({"watch"})


def _waiting(direction="bullish", status="PENDING"):
    levels = (dict(stop_loss=98.5, tp1=103.0) if direction == "bullish"
              else dict(stop_loss=101.5, tp1=97.0, tp2=95.0))
    return _plan(source="confluence", strategy="S/R Confluence", direction=direction,
                 trigger_price=100.0, waits_next_open=True, status=status, **levels)


ORDER = {"entry_price": 100.0, "open_price": 99.0, "reclaim_level": 99.5,
         "order": "buy_stop", "tif": "DAY"}


@pytest.mark.parametrize("transition, event, kind", [
    ("gap_reclaim_order", "reclaim_order", Kind.RECLAIM_ORDER),
    ("cancelled_open_through_stop", "closed_other", Kind.INVALIDATED),
    ("cancelled_gap_no_reclaim", "closed_other", Kind.EXPIRED),
])
def test_mapping_and_kind(transition, event, kind):
    plan_event = PlanEvent("p1", transition, {})
    assert fn.notify_event_for(plan_event) == event
    assert fn.kind_for(plan_event, event) is kind


def test_reclaim_order_is_a_registered_notify_event():
    assert "reclaim_order" in fn.NOTIFY_EVENTS and "reclaim_order" in fn.COPY
    assert fn.NOTIFY_EVENTS.index("reclaim_order") == fn.NOTIFY_EVENTS.index("closed_other") - 1
    assert fn.mentions_user(FOLLOWING, "reclaim_order", {}) is True
    assert fn.mentions_user(WATCH, "reclaim_order", {}) is False
    assert fn.mentions_user(WATCH, "reclaim_order", {"reclaim_order": True}) is True
    assert fn.posts_message("reclaim_order", {1: WATCH}) is True


@pytest.mark.parametrize("direction, order, side", [("bullish", "buy-stop", "long"),
                                                    ("bearish", "sell-stop", "short")])
def test_the_reclaim_order_copy(direction, order, side):
    line = fn.message_line(_waiting(direction), "reclaim_order", "gap_reclaim_order",
                           {**ORDER, "open_price": 99.0 if direction == "bullish" else 101.0})
    opened = "99.00" if direction == "bullish" else "101.00"
    assert line == (f"Paper plan update: AAPL {side} opened at {opened}, toward its stop; it "
                    f"now enters only on a DAY {order} at 100.00 this session.")
    assert not [p for p in fn.FORBIDDEN_PHRASES if p in line.lower()]


@pytest.mark.parametrize("transition, phrase", [
    ("cancelled_open_through_stop", "cancelled: opened at or through its stop."),
    ("cancelled_gap_no_reclaim", "cancelled: opened toward stop, no reclaim."),
])
def test_the_cancel_copy(transition, phrase):
    line = fn.message_line(_waiting(status="CANCELLED"), "closed_other", transition, {})
    assert line == f"Paper plan update: AAPL long {phrase}"


def test_the_cancels_post_only_with_a_following_follower():
    assert fn.posts_message("closed_other", {1: WATCH}) is False
    assert fn.posts_message("closed_other", {1: FOLLOWING}) is True


def test_the_reclaim_order_embed_renders(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", "https://example.test")
    embed = fn.build_notify_embed(_waiting(), "reclaim_order", "gap_reclaim_order", ORDER)
    assert "STOP ORDER AT ENTRY" in embed.title
    assert "DAY buy-stop at 100.00" in embed.description
```

- [ ] **Step 3: Run both to see them fail**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_manager_gap_reclaim_feed.py
python scripts/dev/testrun.py file tests/scanning/test_follow_notify_gap_reclaim.py
```

Expected: FAIL — `AttributeError: PLACEHOLDER_DISCARD_EVENTS`, `pending_notice is None` after the reclaim order, and `notify_event_for` returning `None` for the new transitions.

- [ ] **Step 4: The manager** — `swingbot/core/planning/plan_manager.py`

Replace `NOTICE_EVENTS` with:

```python
NOTICE_EVENTS = frozenset({"filled", "cancelled_expired", "cancelled_invalidated",
                           "cancelled_risk_cap", "closed",
                           # v192: a waiting market plan's open-time messages
                           "cancelled_open_through_stop", "cancelled_gap_no_reclaim",
                           "gap_reclaim_order"})
```

Add to `_TRANSITION_LOG`:

```python
    "cancelled_open_through_stop": ("opened through stop", "live_price"),   # v192
    "cancelled_gap_no_reclaim": ("no reclaim", "entry_price"),             # v192
    "gap_reclaim_order": ("reclaim order at entry", "entry_price"),        # v192
```

Directly after `_TRANSITION_LOG`:

```python
#: Cancels of a plan that never filled: scan_run.py logged a placeholder trade for
#: it at alert time (sized on the trigger), which _on_event deletes (2026-09-11
#: incident). v192 adds the waiting market plan's two open-time cancels.
PLACEHOLDER_DISCARD_EVENTS = frozenset({"cancelled_expired", "cancelled_invalidated",
                                        "cancelled_risk_cap", "cancelled_open_through_stop",
                                        "cancelled_gap_no_reclaim"})
```

In `_on_event`, replace

```python
            elif event.transition in ("cancelled_expired", "cancelled_invalidated",
                                      "cancelled_risk_cap"):
```

with

```python
            elif event.transition in PLACEHOLDER_DISCARD_EVENTS:
```

(same comparison count: `_on_event` stays at cc 15).

- [ ] **Step 5: The follower tables** — `swingbot/commands/scanning/follow_notify.py`

```python
NOTIFY_EVENTS = ("near_stop", "tp1", "tp2", "stopped", "expired", "reclaim_order", "closed_other")
```

`EVENT_LABELS`, insert before `"closed_other"`:

```python
    "reclaim_order": "Opened toward its stop: entry moved to a DAY stop order at the planned entry",
```

`_BY_TRANSITION`, add:

```python
    "cancelled_open_through_stop": "closed_other",      # v192
    "cancelled_gap_no_reclaim": "closed_other",         # v192
    "gap_reclaim_order": "reclaim_order",               # v192
```

`_KIND_BY_EVENT`, add `"reclaim_order": Kind.RECLAIM_ORDER,`; `_CLOSED_OTHER_KIND`, add:

```python
    "cancelled_open_through_stop": Kind.INVALIDATED,
    "cancelled_gap_no_reclaim": Kind.EXPIRED,
```

`WATCH_DEFAULTS`, insert `"reclaim_order": False,` before `"closed_other"`. `_CANCEL_LABELS`, add:

```python
    "cancelled_open_through_stop": "opened at or through its stop",
    "cancelled_gap_no_reclaim": "opened toward stop, no reclaim",
```

Add after `_expired_copy`:

```python
def _reclaim_order_copy(plan, transition: str, detail: dict) -> str:
    order = "buy-stop" if plan.direction == "bullish" else "sell-stop"
    return (f"opened at {ui.fmt_price(detail.get('open_price'))}, toward its stop; it now "
            f"enters only on a DAY {order} at {ui.fmt_price(detail.get('entry_price'))} "
            "this session.")
```

and in `COPY`, before `"closed_other"`: `"reclaim_order": _reclaim_order_copy,`.

- [ ] **Step 6: Move the policy pin** — `tests/commands/test_follow_notify_policy.py`

Rename `test_the_six_events_share_one_table` to `test_the_seven_events_share_one_table` and change its first assertion to:

```python
    assert fn.NOTIFY_EVENTS == ("near_stop", "tp1", "tp2", "stopped", "expired",
                                "reclaim_order", "closed_other")
```

- [ ] **Step 7: Run the tests, the follower and feed suites, and the gate**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_manager_gap_reclaim_feed.py
python scripts/dev/testrun.py file tests/scanning/test_follow_notify_gap_reclaim.py
python scripts/dev/testrun.py file tests/commands/test_follow_notify_policy.py
python scripts/dev/testrun.py file tests/commands/test_follow_notify_copy.py
python scripts/dev/testrun.py file tests/commands/test_slash_notify.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_feed.py
python scripts/dev/testrun.py file tests/planning/test_near_stop_event.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed`; the gate passes (`_on_event` unchanged at 15).

- [ ] **Step 8: Commit (in the worktree)**

```bash
git add swingbot/core/planning/plan_manager.py swingbot/commands/scanning/follow_notify.py tests/commands/test_follow_notify_policy.py tests/planning/test_plan_manager_gap_reclaim_feed.py tests/scanning/test_follow_notify_gap_reclaim.py
git commit -m "feat(v192): open-time events reach the feed queue, the log, the placeholder discard and followers"
```

# Phase 7 — The alert and live integration

### Task V192-12: Alert: market-on-open wording and the X reference line
**Model:** sonnet — one copy helper and three render call sites behind a marker that is absent with the knob off; the feed guards and the flag-off goldens fence it.

**Files:**
- Modify: `swingbot/core/presentation/instructions.py` — new `MARKET_ON_OPEN` and `market_on_open_lines` (after `_cancel_line`, `:250`), the order line of `ticket_for` (`:283-286`)
- Modify: `swingbot/core/scanning/alert_embeds.py` — a field helper, `build_strategy_alert_embed` (`:28`), `build_strategy_simple_embed` (`:45`), `build_embed`'s plan section (`:202-204`)
- Create: `tests/presentation/test_market_on_open_alert.py`

**Interfaces:**
- Consumes: `gap_reclaim.waits_for_open(plan)` (V192-4); `TradePlanV2.reclaim_level` (V192-3); `instructions._REFRAIN`, `_BEYOND` (V192-10).
- Produces (index § Contracts): `instructions.market_on_open_lines(plan) -> list[str]` — `[]` unless the plan waits for its open; else `["Enter at the open (market-on-open)"]`, plus the `X` reference line when `reclaim_level` is set; `instructions.MARKET_ON_OPEN = "Enter at the open (market-on-open)"`; `alert_embeds.MARKET_ON_OPEN_FIELD = "At the open"` and `alert_embeds._market_on_open_fields(plan) -> list[tuple]`.

Where the line lands: the simple-channel ticket (`ticket_for`, which `build_simple_alert` renders for every live v2 plan) leads its lines with it and its order headline reads `BUY AT MARKET ON OPEN ~E` (`SELL SHORT AT MARKET ON OPEN ~E`); the full alert (`build_embed`) and the strategy alert get an "At the open" field; the strategy simple embed gets the lines under its levels. Knob off, no plan waits, every list is empty and every render is unchanged.

- [ ] **Step 1: Write the failing tests** — `tests/presentation/test_market_on_open_alert.py`

```python
"""V192-12: the alert says 'Enter at the open (market-on-open)' and shows X for a
market plan waiting for its next open; every other plan renders as before."""
import pytest

from swingbot import config
from swingbot.core.presentation import instructions as ins
from swingbot.core.presentation import tokens
from swingbot.core.scanning import alert_embeds as ae
from tests.planning.test_plan_engine_model import _plan
from tests.presentation.test_feed_guards import _FORBIDDEN, _allowed, _order_glyph_hits

S = tokens.FEED_SYMBOLS


def _market(direction="bullish", **kw):
    levels = (dict(stop_loss=98.5, tp1=103.0, tp2=105.0) if direction == "bullish"
              else dict(stop_loss=101.5, tp1=97.0, tp2=95.0))
    base = dict(source="confluence", strategy="S/R Confluence", entry_type="market",
                direction=direction, trigger_price=100.0, status="PENDING",
                waits_next_open=True, **levels)
    base.update(kw)
    return _plan(**base)


@pytest.fixture(autouse=True)
def _url(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", "https://example.test")


def test_the_line_is_the_specs_wording():
    assert ins.MARKET_ON_OPEN == "Enter at the open (market-on-open)"


@pytest.mark.parametrize("plan", [
    _market(waits_next_open=None, status="ACTIVE", entry_price=100.0),   # knob off: today's plan
    _market(entry_type="stop_entry", waits_next_open=None),
    _market(status="ACTIVE", entry_price=99.8),                          # already filled
])
def test_no_line_for_a_plan_that_does_not_wait(plan):
    assert ins.market_on_open_lines(plan) == []
    assert ae._market_on_open_fields(plan) == []


def test_a_waiting_plan_without_a_veto_has_the_open_line_only():
    assert ins.market_on_open_lines(_market()) == [ins.MARKET_ON_OPEN]


@pytest.mark.parametrize("direction, level, side, refrain, order", [
    ("bullish", 99.5, "below", "buy", "BUY STOP"),
    ("bearish", 100.5, "above", "short", "SELL STOP"),
])
def test_the_x_reference_line(direction, level, side, refrain, order):
    lines = ins.market_on_open_lines(_market(direction, reclaim_level=level, reclaim_atr=2.0))
    assert lines == [ins.MARKET_ON_OPEN,
                     f"If it opens at or {side} {level:.2f} (toward the stop): don't {refrain} "
                     f"at the open; the bot posts a DAY {order} at 100.00"]


@pytest.mark.parametrize("direction, verb", [("bullish", "BUY AT MARKET"),
                                             ("bearish", "SELL SHORT AT MARKET")])
def test_the_ticket_orders_on_the_open(direction, verb):
    plan = _market(direction, reclaim_level=99.5 if direction == "bullish" else 100.5)
    ticket = ins.ticket_for(plan, logged=True, not_logged_reason=None,
                            money=ins.money_from(54.35, "$"), level=4)
    assert ticket.headline.startswith(f"{S['entry']} {verb} ON OPEN ~100.00 · ")
    assert ticket.lines[:2] == tuple(ins.market_on_open_lines(plan))
    allowed = _allowed(direction)
    for key, after in _order_glyph_hits(ticket):
        assert after.startswith(allowed[key]), (key, after)
    text = "\n".join((ticket.headline, *ticket.lines))
    assert [v for v in _FORBIDDEN[direction] if v in text] == []


def test_a_knob_off_market_ticket_is_unchanged():
    plan = _market(waits_next_open=None, status="ACTIVE", entry_price=100.0)
    ticket = ins.ticket_for(plan, logged=True, not_logged_reason=None,
                            money=ins.money_from(54.35, "$"), level=4)
    assert ticket.headline.startswith(f"{S['entry']} BUY AT MARKET ~100.00 · ")
    assert "ON OPEN" not in ticket.headline
    assert ins.MARKET_ON_OPEN not in ticket.lines


def test_the_field_carries_the_lines():
    plan = _market(reclaim_level=99.5)
    assert ae._market_on_open_fields(plan) == [
        (ae.MARKET_ON_OPEN_FIELD, "\n".join(ins.market_on_open_lines(plan)), False)]
    assert ae._market_on_open_fields(None) == []


def test_the_strategy_alert_and_its_simple_mirror_show_the_line():
    plan = _market(source="strategy", strategy="Fibonacci", reclaim_level=99.5)
    full = ae.build_strategy_alert_embed(plan)
    assert [f.value for f in full.fields if f.name == ae.MARKET_ON_OPEN_FIELD] == [
        "\n".join(ins.market_on_open_lines(plan))]
    simple = ae.build_strategy_simple_embed(plan)
    assert ins.MARKET_ON_OPEN in simple.description


def test_a_strategy_alert_that_does_not_wait_has_no_field():
    plan = _market(source="strategy", strategy="Fibonacci", waits_next_open=None,
                   status="ACTIVE", entry_price=100.0)
    assert ae.MARKET_ON_OPEN_FIELD not in [f.name for f in ae.build_strategy_alert_embed(plan).fields]
    assert ins.MARKET_ON_OPEN not in ae.build_strategy_simple_embed(plan).description
```

- [ ] **Step 2: Run it to see it fail**

```bash
python scripts/dev/testrun.py file tests/presentation/test_market_on_open_alert.py
```

Expected: FAIL — `AttributeError: module ... has no attribute 'MARKET_ON_OPEN'`.

- [ ] **Step 3: The copy** — `swingbot/core/presentation/instructions.py`

Add to the imports: `from swingbot.core.planning.gap_reclaim import waits_for_open` (gap_reclaim imports no presentation module). Move the two V192-10 tables `_REFRAIN` and `_BEYOND` up to just below `_OUTCOME_TONES` (`:59`) so this helper and `_reclaim_order` share them, and add after `_cancel_line`:

```python
#: v192: the alert line of a market plan waiting for its next open (spec wording).
MARKET_ON_OPEN = "Enter at the open (market-on-open)"


def market_on_open_lines(plan) -> list[str]:
    """v192: the alert's market-on-open line, and the X reference line when the
    gap veto is armed; [] for every plan that does not wait for its open."""
    if not waits_for_open(plan):
        return []
    lines = [MARKET_ON_OPEN]
    level = getattr(plan, "reclaim_level", None)
    if level is not None:
        side = _sides(plan.direction)
        lines.append(f"If it opens at or {_BEYOND[plan.direction]} {_price(level)} (toward the "
                     f"stop): don't {_REFRAIN[plan.direction]} at the open; the bot posts a DAY "
                     f"{side['entry_stop']} at {_price(plan.trigger_price)}")
    return lines
```

In `ticket_for`, replace

```python
    if plan.entry_type == "stop_entry":
        order = f"{side['entry_stop']} {_price(plan.trigger_price)}"
    else:
        order = f"{side['entry_market']} ~{_price(plan.trigger_price)}"
    lines = [
```

with

```python
    if plan.entry_type == "stop_entry":
        order = f"{side['entry_stop']} {_price(plan.trigger_price)}"
    elif waits_for_open(plan):
        order = f"{side['entry_market']} ON OPEN ~{_price(plan.trigger_price)}"   # v192
    else:
        order = f"{side['entry_market']} ~{_price(plan.trigger_price)}"
    lines = [
        *market_on_open_lines(plan),
```

- [ ] **Step 4: The alert renders** — `swingbot/core/scanning/alert_embeds.py`

Import beside the presentation imports: `from swingbot.core.presentation.instructions import market_on_open_lines`. Add after `strategy_plan_line`:

```python
#: v192: the full alert's field for a market plan waiting for its next open.
MARKET_ON_OPEN_FIELD = "At the open"


def _market_on_open_fields(plan) -> list:
    lines = market_on_open_lines(plan) if plan is not None else []
    return [(MARKET_ON_OPEN_FIELD, "\n".join(lines), False)] if lines else []
```

In `build_strategy_alert_embed`, directly after the `"Plan (v2)"` field:

```python
    for name, value, inline in _market_on_open_fields(plan):
        embed.add_field(name=name, value=value, inline=inline)
```

In `build_strategy_simple_embed`, build the description as

```python
    description = f"{_strategy_levels(plan)}\n{strategy_plan_line(plan)} · ledger {plan.ledger}"
    description = "\n".join([description, *market_on_open_lines(plan)])
```

and pass `description=description` to `ui.push_embed`. In `build_embed`, after `sections["plan"].extend(_gap_risk_fields(item))`:

```python
    sections["plan"].extend(_market_on_open_fields(plan_v2))
```

- [ ] **Step 5: Run the tests, the alert and feed suites, the goldens and the gate**

```bash
python scripts/dev/testrun.py file tests/presentation/test_market_on_open_alert.py
python scripts/dev/testrun.py file tests/presentation/test_gap_reclaim_instructions.py
python scripts/dev/testrun.py file tests/presentation/test_feed_guards.py
python scripts/dev/testrun.py file tests/presentation/test_instructions.py
python scripts/dev/testrun.py file tests/planning/test_v192_plan_golden.py
python scripts/dev/testrun.py changed
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` (the `changed` run reaches the alert-embed tests, which pin knob-off renders byte for byte); the gate passes (`ticket_for` rises by one branch).

- [ ] **Step 6: Commit (in the worktree)**

```bash
git add swingbot/core/presentation/instructions.py swingbot/core/scanning/alert_embeds.py tests/presentation/test_market_on_open_alert.py
git commit -m "feat(v192): alert reads market-on-open and shows the X reference line for waiting market plans"
```

### Task V192-13: Live integration: scan to fill with the knob on; live/replay parity of E, a_t, X
**Model:** opus — the seam where the live scan, the manager and the replay must agree on one plan's numbers and its open decision; a mismatch silently invalidates the measurement's transfer to live.

**Files:**
- Modify: `swingbot/core/scanning/analyze.py` — a new `_stamp_next_open_live` beside `_stamp_gap_sizing_live` (`:461`), called from `attach_plan_v2` right after `plan.issued_at = ...` (`:543`)
- Modify: `swingbot/core/scanning/strategy_pass.py` — a new `_stamp_issued_for_open`, called in `_emit_signal` directly before `deps.plan_store.add(plan)` (`:296`)
- Create: `tests/scanning/test_v192_scan_to_fill.py`, `tests/scanning/test_v192_live_replay_parity.py`

**Ledger note:** the index ledger names `swingbot/core/scanning/scan_run.py` for this task; the change actually lands in `strategy_pass.py` (where a strategy plan is stored), and `scan_run.py` needs none: its existing alert-time placeholder trade is the stop-entry precedent, which `record_plan_fill` moves onto the fill (V192-8, V192-9) and `discard_plan_placeholder` drops on a cancel (V192-11). No other task touches `strategy_pass.py`.

**Interfaces:**
- Consumes: `gap_reclaim.waits_for_open`, `stamp_next_open`, `atr_at`, `reclaim_level_for`, `reclaim_fill_price`, `tick_for` (V192-4); waiting builders (V192-5); `exit_sim.simulate_exit` dispatching to `market_next_open.next_open_market_exit` (V192-6, V192-7); `PlanManager` open, reclaim and close handlers (V192-8, V192-9); the V192-8 test helpers; `strategy_pass.completed_frame(df, now)` (`strategy_pass.py:31`); `engine.attach_plan_v2` (the `tests/scanning/test_attach_confluence_stop_geometry.py` entry).
- Produces: `analyze._stamp_next_open_live(plan, df, now) -> None`; `strategy_pass._stamp_issued_for_open(plan, now) -> None`.

Two live gaps this task closes, both found against the code:

1. **`a_t` from completed bars.** The live confluence scan hands `build_confluence_plan` the scan frame, whose last row is today's still-forming bar during the session; V192-5's builder stamp would read a partial bar's range. The spec defines `a_t` as Wilder ATR14 "of completed bars through t", and v183's live gap sizing already drops the forming bar the same way (`_stamp_gap_sizing_live`). So `attach_plan_v2` re-derives `a_t` and `X` from `completed_frame(df, now)` before the plan is stored — still once, at creation. Scanned after the close (or before the open) the completed frame is the whole frame and the values equal the replay's at `t` exactly; scanned intraday they come from the bars through the previous session, never from the forming one. Strategy plans are already built on the completed frame (`strategy_pass.build_strategy_plan_at`).
2. **`issued_at` for strategy plans.** The strategy pass stores plans without `issued_at`, so `market_open.deciding_session` would fall back to the session after the bar date — for a pass that runs during session `D` on `D − 1`'s completed bar that is `D` itself, whose open has already passed, and the first regular poll would "decide" at an intraday price. `_emit_signal` stamps `issued_at = now` on a waiting plan, so the deciding open is the first one after the alert. Knob off, no plan waits and nothing is stamped.

- [ ] **Step 1: Write the failing scan-to-fill tests** — `tests/scanning/test_v192_scan_to_fill.py`

```python
"""V192-13: the live scan builds a waiting market plan with a_t and X from
completed bars and the alert time stamped; the manager fills it at the next open
and moves the placeholder trade there. DB-backed for the manager half."""
import datetime as dt
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.planning import gap_reclaim as gr
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.core.scanning import engine, strategy_pass
from tests.fake_feed import FakePriceFeed
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_market_open import _Log, _flags  # noqa: F401

AFTER_CLOSE = dt.datetime(2026, 10, 13, 16, 30, tzinfo=US_MARKET_TZ)
INTRADAY = dt.datetime(2026, 10, 13, 12, 0, tzinfo=US_MARKET_TZ)
OPEN = dt.datetime(2026, 10, 14, 9, 31, tzinfo=US_MARKET_TZ)


@pytest.fixture(autouse=True)
def v2_on(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)


@pytest.fixture
def knobs(monkeypatch):
    def set_(next_open, g):
        monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", next_open)
        monkeypatch.setattr(config, "GAP_RECLAIM_ATR", g)
    return set_


def _frame(n=60):
    """Bars ending Tuesday 2026-10-13, ATR14 real (H - L = 4% of the price)."""
    df = make_ohlcv([100.0] * n, spread=0.02)
    df.index = pd.bdate_range(end="2026-10-13", periods=n)
    return df


def _scenario(direction="bullish"):
    stop, target = (98.5, 103.0) if direction == "bullish" else (101.5, 97.0)
    return SimpleNamespace(direction=direction, entry=100.0, stop_loss=stop, take_profit=target,
                           target_sources=["EMA21"], stop_sources=["Rolling support"])


def _attach(df, now, direction="bullish"):
    item = SimpleNamespace(plan_v2=None)
    engine.attach_plan_v2(item, _scenario(direction), df, "AAPL", "4w", level_map=None,
                          issued_at=now.isoformat(), now=now)
    return item.plan_v2


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_after_the_close_the_scan_builds_a_waiting_plan_from_bar_t(knobs, direction):
    knobs(True, 0.25)
    df = _frame()
    plan = _attach(df, AFTER_CLOSE, direction)
    assert plan.status == PlanStatus.PENDING and plan.entry_price is None
    assert gr.waits_for_open(plan) and plan.issued_at == AFTER_CLOSE.isoformat()
    a_t = gr.atr_at(df, len(df) - 1)
    assert plan.reclaim_atr == a_t
    assert plan.reclaim_level == gr.reclaim_level_for(plan.trigger_price, a_t, 0.25, direction)


def test_intraday_the_forming_bar_never_reaches_a_t(knobs):
    knobs(True, 0.25)
    df = _frame()
    plan = _attach(df, INTRADAY)
    assert plan.reclaim_atr == gr.atr_at(df.iloc[:-1], len(df) - 2)
    moved = df.copy()
    moved.iloc[-1, moved.columns.get_loc("High")] *= 1.3     # the forming bar's range moves
    moved.iloc[-1, moved.columns.get_loc("Low")] *= 0.8
    again = _attach(moved, INTRADAY)
    assert (again.reclaim_atr, again.reclaim_level) == (plan.reclaim_atr, plan.reclaim_level)


def test_next_open_alone_stamps_no_veto(knobs):
    knobs(True, 0.0)
    plan = _attach(_frame(), AFTER_CLOSE)
    assert gr.waits_for_open(plan)
    assert plan.reclaim_atr is None and plan.reclaim_level is None


def test_knob_off_the_scan_plan_is_todays(knobs):
    knobs(False, 0.0)
    plan = _attach(_frame(), INTRADAY)
    assert plan.status == PlanStatus.ACTIVE and plan.entry_price == plan.trigger_price
    assert not {"reclaim_atr", "reclaim_level", "reclaim_session", "waits_next_open"} & set(
        plan_to_dict(plan))


def _run(plan, prices, polls):
    log = _Log()
    store = PlanStore()
    store.add(plan)
    feed = FakePriceFeed()
    feed.set_series(plan.ticker, prices)
    mgr = PlanManager(store, feed.get_price, trade_log=log)
    events = [e for now in polls for e in mgr.poll(now)]
    return store.get(plan.plan_id), events, log


def test_scan_to_fill_at_the_next_open(knobs):
    knobs(True, 0.25)
    plan = _attach(_frame(), AFTER_CLOSE)
    open_price = round(plan.trigger_price - 0.1, 2)            # short of X: the baseline fill
    stored, events, log = _run(plan, [open_price], [OPEN])
    assert "filled" in [e.transition for e in events]
    assert stored.status == PlanStatus.ACTIVE and stored.entry_price == open_price
    assert ("fill", plan.plan_id, open_price) in log.calls


def test_scan_to_reclaim_fill_at_e(knobs):
    knobs(True, 0.25)
    plan = _attach(_frame(), AFTER_CLOSE)
    open_price = round((plan.reclaim_level + plan.stop_loss) / 2, 2)   # at/beyond X, inside the stop
    through = round(plan.trigger_price + gr.tick_for(plan.trigger_price), 2)
    stored, events, log = _run(plan, [open_price, through],
                               [OPEN, OPEN + dt.timedelta(minutes=30)])
    assert [e.transition for e in events][:1] == ["gap_reclaim_order"]
    assert stored.status == PlanStatus.ACTIVE and stored.entry_price == plan.trigger_price
    assert ("fill", plan.plan_id, plan.trigger_price) in log.calls


def test_scan_to_no_reclaim_cancel_drops_the_placeholder(knobs):
    knobs(True, 0.25)
    plan = _attach(_frame(), AFTER_CLOSE)
    open_price = round((plan.reclaim_level + plan.stop_loss) / 2, 2)
    stored, events, log = _run(plan, [open_price, open_price],
                               [OPEN, dt.datetime(2026, 10, 14, 16, 5, tzinfo=US_MARKET_TZ)])
    assert "cancelled_gap_no_reclaim" in [e.transition for e in events]
    assert stored.status == PlanStatus.CANCELLED
    assert ("discard", plan.plan_id) in log.calls


# --- the strategy pass's alert time --------------------------------------------------

NOW = dt.datetime(2026, 10, 13, 14, 0, tzinfo=dt.timezone.utc)


def test_a_waiting_strategy_plan_gets_the_alert_time():
    plan = _plan(status=PlanStatus.PENDING, waits_next_open=True, issued_at=None)
    strategy_pass._stamp_issued_for_open(plan, NOW)
    assert plan.issued_at == NOW.isoformat()


@pytest.mark.parametrize("kw", [dict(status=PlanStatus.ACTIVE, waits_next_open=None),
                                dict(entry_type="stop_entry", waits_next_open=None),
                                dict(status=PlanStatus.PENDING, waits_next_open=True,
                                     issued_at="2026-10-13T12:00:00+00:00")])
def test_every_other_strategy_plan_is_left_alone(kw):
    plan = _plan(**kw)
    before = plan.issued_at
    strategy_pass._stamp_issued_for_open(plan, NOW)
    assert plan.issued_at == before
```

- [ ] **Step 2: Write the failing parity tests** — `tests/scanning/test_v192_live_replay_parity.py`

```python
"""V192-13: live and replay agree on one waiting market plan -- E, a_t and X at
creation, and every outcome of the open decision. The replay is
exit_sim.simulate_exit (market_next_open); live is PlanManager. The one designed
difference: the replay fills a reclaim at E + one tick (the stop order's
slippage), live at E. DB-backed for the live half."""
import datetime as dt
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.planning import gap_reclaim as gr
from swingbot.core.planning.builders import build_confluence_plan
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_engine import PlanStatus
from tests.helpers import make_ohlcv
from tests.planning.test_plan_manager_market_open import (OPEN, _bear, _bull, _env,  # noqa: F401
                                                         _et, _flags, _tr)
from tests.scanning.test_v192_scan_to_fill import AFTER_CLOSE, _attach, _frame, knobs, v2_on  # noqa: F401

SIGNAL = 30


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_e_a_t_and_x_are_the_same_live_and_in_replay(knobs, direction):
    knobs(True, 0.25)
    df = _frame()
    live = _attach(df, AFTER_CLOSE, direction)
    stop, target = (98.5, 103.0) if direction == "bullish" else (101.5, 97.0)
    scenario = SimpleNamespace(direction=direction, entry=100.0, stop_loss=stop,
                               take_profit=target, target_sources=["EMA21"],
                               stop_sources=["Rolling support"])
    replay = build_confluence_plan(scenario, df, ticker="AAPL", horizon_key="4w",
                                   primary_strategy="S/R Confluence")
    assert (live.trigger_price, live.reclaim_atr, live.reclaim_level) == (
        replay.trigger_price, replay.reclaim_atr, replay.reclaim_level)
    assert live.reclaim_atr == gr.atr_at(df, len(df) - 1)


def _bars(next_bar):
    rows = [(100.0, 100.4, 99.6, 100.0)] * 60
    rows[SIGNAL + 1] = next_bar
    df = make_ohlcv(rows)
    df.index = pd.bdate_range(end="2026-12-31", periods=len(rows))
    return df


#: (case, plan maker, plan overrides, bar t+1 (O, H, L, C), live prices after the open)
CASES = [
    ("fill", _bull, {}, (99.8, 100.3, 99.6, 100.0), []),
    ("fill", _bear, {}, (100.2, 100.4, 99.7, 100.0), []),
    ("through_stop", _bull, {}, (98.0, 98.6, 97.8, 98.2), []),
    ("through_stop", _bear, {}, (102.0, 102.2, 101.4, 101.8), []),
    ("risk_cap", _bull, {}, (100.6, 101.0, 100.4, 100.8), []),
    ("gap_target", _bull, {"stop_ceiling_pct": 10.0}, (103.2, 103.6, 102.8, 103.2), []),
    ("gap_target", _bear, {"stop_ceiling_pct": 10.0}, (96.8, 97.2, 96.4, 96.8), []),
    ("reclaim", _bull, {"reclaim_level": 99.5, "reclaim_atr": 2.0},
     (99.0, 100.3, 98.9, 100.2), [100.01]),
    ("reclaim", _bear, {"reclaim_level": 100.5, "reclaim_atr": 2.0},
     (101.0, 101.1, 99.7, 99.8), [99.99]),
    ("no_reclaim", _bull, {"reclaim_level": 99.5, "reclaim_atr": 2.0},
     (99.0, 99.6, 98.9, 99.3), [99.3]),
    ("no_reclaim", _bear, {"reclaim_level": 100.5, "reclaim_atr": 2.0},
     (101.0, 101.1, 100.4, 100.7), [100.7]),
]


def _live(make, overrides, open_price, later):
    store, mgr = _env(make(**overrides), [open_price, *later])
    events = mgr.poll(OPEN)
    if later:
        late = _et(14, 10) if later[0] in (100.01, 99.99) else _et(14, 16, 5)
        events += mgr.poll(late)
    return store.get("p1"), events


@pytest.mark.parametrize("case, make, overrides, bar, later", CASES,
                         ids=[f"{c[0]}-{c[1].__name__}" for c in CASES])
def test_the_open_decision_is_the_same_live_and_in_replay(case, make, overrides, bar, later):
    replay = simulate_exit(_bars(bar), SIGNAL, make(**overrides), scale_out=True)
    live, events = _live(make, overrides, bar[0], later)
    transitions = _tr(events)
    if case == "fill":
        assert replay.entry_price == live.entry_price == bar[0]
        assert live.status == PlanStatus.ACTIVE
    elif case == "through_stop":
        assert replay.outcome == "not_triggered" and replay.cancel_reason == gr.OPEN_THROUGH_STOP
        assert "cancelled_open_through_stop" in transitions
    elif case == "risk_cap":
        assert replay.cancel_reason == gr.RISK_CAP and "cancelled_risk_cap" in transitions
    elif case == "gap_target":
        assert (replay.outcome, replay.r_total, replay.entry_price) == ("scratch", 0.0, bar[0])
        assert replay.legs[0]["reason"] == "gap_target"
        closed = [e for e in events if e.transition == "closed"]
        assert closed and closed[0].detail["leg"]["r"] == 0.0
        assert closed[0].detail["reason"] == "gap_target" and live.entry_price == bar[0]
    elif case == "reclaim":
        plan = make(**overrides)
        assert replay.entry_price == gr.reclaim_fill_price(plan)
        assert live.entry_price == plan.trigger_price
        assert transitions[0] == "gap_reclaim_order" and "filled" in transitions
    else:
        assert replay.cancel_reason == gr.GAP_NO_RECLAIM
        assert live.status == PlanStatus.CANCELLED and "cancelled_gap_no_reclaim" in transitions
```

- [ ] **Step 3: Run both to see them fail**

```bash
python scripts/dev/testrun.py file tests/scanning/test_v192_scan_to_fill.py
python scripts/dev/testrun.py file tests/scanning/test_v192_live_replay_parity.py
```

Expected: FAIL — `AttributeError: module 'swingbot.core.scanning.strategy_pass' has no attribute '_stamp_issued_for_open'`, and `test_intraday_the_forming_bar_never_reaches_a_t` fails (the builder stamp read the forming bar). The parity cases should already pass once the scan-to-fill module imports; any that fail are a real live/replay divergence to fix in V192-6..V192-9, not here.

- [ ] **Step 4: `a_t` from completed bars** — `swingbot/core/scanning/analyze.py`

Add to the imports: `from swingbot.core.planning import gap_reclaim`. After `_stamp_risk_notice_live`:

```python
def _stamp_next_open_live(plan, df, now) -> None:
    """v192: a plan waiting for its next open takes a_t (and X) from COMPLETED bars
    only -- today's forming bar is dropped during the session, as v183's gap sizing
    does -- so live reads what the replay reads at bar t. Still once, at creation.
    Never raises: a frame problem leaves no veto (the plan fills at the open)."""
    if not gap_reclaim.waits_for_open(plan):
        return
    from .strategy_pass import completed_frame
    plan.reclaim_atr = plan.reclaim_level = None
    try:
        frame = completed_frame(df, now or datetime.now(timezone.utc))
        if frame is not None and len(frame):
            gap_reclaim.stamp_next_open(plan, frame, len(frame) - 1)
    except Exception as exc:
        swallowed(log, "scan.analyze.next_open_frame", exc, level=logging.DEBUG)
        plan.reclaim_atr = plan.reclaim_level = None
```

In `attach_plan_v2`, directly after `plan.issued_at = issued_at or datetime.now(timezone.utc).isoformat()`:

```python
        _stamp_next_open_live(plan, df, now)
```

- [ ] **Step 5: The strategy plan's alert time** — `swingbot/core/scanning/strategy_pass.py`

Add `import datetime as dt` and `from swingbot.core.planning import gap_reclaim` to the imports, then after `_open_trade`:

```python
def _stamp_issued_for_open(plan, now) -> None:
    """v192: a strategy plan waiting for its next open records when it was issued,
    so market_open.deciding_session picks the first open after the alert -- never
    the open of the session this pass runs in, already past. Every other plan
    (and a plan that already carries the stamp) is left alone."""
    if gap_reclaim.waits_for_open(plan) and getattr(plan, "issued_at", None) is None:
        plan.issued_at = (now or dt.datetime.now(dt.timezone.utc)).isoformat()
```

In `_emit_signal`, directly before `deps.plan_store.add(plan)`:

```python
    _stamp_issued_for_open(plan, deps.now)
```

- [ ] **Step 6: Run the tests, the scanning neighbours, the goldens and the gate**

```bash
python scripts/dev/testrun.py file tests/scanning/test_v192_scan_to_fill.py
python scripts/dev/testrun.py file tests/scanning/test_v192_live_replay_parity.py
python scripts/dev/testrun.py file tests/scanning/test_attach_confluence_stop_geometry.py
python scripts/dev/testrun.py file tests/planning/test_v192_plan_golden.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_v192_flag_off_golden.py
python scripts/dev/testrun.py changed
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` (the `changed` run reaches the strategy-pass and scan tests, all knob-off); the gate passes (`_stamp_next_open_live` cc 5; `attach_plan_v2` and `_emit_signal` gain no branch).

- [ ] **Step 7: Commit (in the worktree)**

```bash
git add swingbot/core/scanning/analyze.py swingbot/core/scanning/strategy_pass.py tests/scanning/test_v192_scan_to_fill.py tests/scanning/test_v192_live_replay_parity.py
git commit -m "feat(v192): live scan stamps a_t from completed bars and the strategy alert time; scan-to-fill and live/replay parity tests"
```

