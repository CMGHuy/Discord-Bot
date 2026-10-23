# v189 — Book integrity and partial-trade truth: Implementation Plan, part 4b of 7 — the delete vocabulary and deletes that end their plans

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier. **Never read this part whole**: `grep -n "^### Task V189-14:" -A 500 <this file>`.

**Spec:** [2026-10-23-v189-book-integrity-partial-truth-design.md](../specs/2026-10-23-v189-book-integrity-partial-truth-design.md) — D4 A7; `## Corrections from the code brief` 7 wins over the A7 bullet's delivery wording.
**Index:** [2026-10-23-v189-book-integrity-partial-truth_0-index.md](2026-10-23-v189-book-integrity-partial-truth_0-index.md) — `## Global Constraints`, `## Spec clarifications` 2 (the notice travels in the plan's `pending_notice` slot), `## Contracts` § Vocabulary and § Plan links, `## Parallelisation`, the task ledger.
**Part 4a:** [2026-10-23-v189-book-integrity-partial-truth_4-book-fixes.md](2026-10-23-v189-book-integrity-partial-truth_4-book-fixes.md) holds V189-11 and V189-12 and the list of contracts this part consumes from parts 1-2 and v187. From part 4a this part uses `plan_links.end_linked_plan(plan_id, reason, *, conn, notice=False)`, `EndedPlan`, `DeleteResult`, `TRADE_DELETED_EVENT` (V189-12).
**Worktree:** `.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth`. Every path below is relative to it; every command runs from it.

v187's vocabulary rows for `cancelled_limit` / `cancelled_gap_through_stop` are the pattern V189-13 copies, site for site (v187 plan, part 2, V187-10..V187-12). Before editing a table, read it as merged: `git grep -n "cancelled_gap_through_stop" -- swingbot`.

# Phase D — Book fixes (continued)

### Task V189-13: The cancelled_trade_deleted event across the vocabulary

**Model:** sonnet — table rows and two small builders across six presentation/policy modules, copying v187's pattern for its two limit cancels, with one test file pinning every site.

**Spec:** D4 A7 ("`cancelled_trade_deleted` is added to v187's `PENDING_CANCEL_EVENTS`"; the ACTIVE/PARTIAL case is closed with no P&L settled); index § Contracts / Vocabulary; index clarification 2 (the ACTIVE/PARTIAL notice is a `closed` event with `{"reason": "trade_deleted"}` and no exit price).

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (`PENDING_CANCEL_EVENTS`, `_TRANSITION_LOG` — v187's literals near `:122-150`)
- Modify: `swingbot/core/presentation/instructions.py` (`_CANCEL_LEADS`, `_CANCEL_WHY`, `_BUILDERS` — v187's tables near `:542-583`; `_closed` `:433-445`)
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` (`PLAN_EVENT_KINDS` `:302-309`; a field builder after v187's `_gap_through_stop_fields`; `_EVENT_FIELDS` `:413-421`)
- Modify: `swingbot/core/scanning/execution_embeds.py` (`_EVENT_KINDS` `:27-34`; `_event_style` `:106-115`)
- Modify: `swingbot/core/planning/session_expiry.py` (module docstring `:1-16`; constants `:26-35`; v187's per-transition message table above `in_session_message`)
- Modify: `swingbot/commands/scanning/follow_notify.py` (`_BY_TRANSITION` `:50-57`; `_CLOSED_OTHER_KIND` `:65-69`; `kind_for` `:89-93`; `_CANCEL_LABELS` `:139-142`; `_other_copy` `:187-195`; `build_notify_embed` `:221-232`)
- Create: `tests/presentation/test_trade_deleted_cancel_vocab.py`

**Interfaces:**
- Consumes: v187's `PENDING_CANCEL_EVENTS`, derived `NOTICE_EVENTS`, `instructions._CANCEL_WHY` (transition → `fn(detail) -> str`), and `session_expiry`'s per-transition message table (named `_LIMIT_MESSAGES` in v187's plan). The tests build `PlanEvent`s by hand, so V189-12 need not be merged first (the two may run in parallel; this task does not import `plan_links`).
- Produces (index § Contracts / Vocabulary, exactly):

  | Site | `cancelled_trade_deleted` |
  |---|---|
  | `plan_manager.PENDING_CANCEL_EVENTS` | member (so also in `NOTICE_EVENTS`) |
  | `plan_manager._TRANSITION_LOG` | `("trade deleted", "live_price")` |
  | `instructions._CANCEL_LEADS` | `""` |
  | `instructions._CANCEL_WHY` | `The trade record was deleted before the order filled. Nothing was opened and the plan is no longer monitored.` |
  | `instructions._BUILDERS` | `_cancelled` |
  | `lifecycle_embeds.PLAN_EVENT_KINDS`, `execution_embeds._EVENT_KINDS` | `Kind.CANCEL` |
  | `lifecycle_embeds._EVENT_FIELDS` | `_trade_deleted_fields` |
  | `session_expiry._IN_SESSION_CODES` | `TRADE_DELETED = "trade_deleted"` |
  | `follow_notify._BY_TRANSITION` | `"closed_other"` |
  | `follow_notify._CLOSED_OTHER_KIND` | `Kind.INVALIDATED` |
  | `follow_notify._CANCEL_LABELS` | `"trade record deleted before fill"` |

  And for a `closed` event whose `detail["reason"] == "trade_deleted"`: `instructions._closed` returns verb `EXITED`, headline `NO LONGER MONITORED · trade record deleted`, tone `inert`; `execution_embeds._event_style` returns `(Kind.INVALIDATED, None, None)`; `follow_notify.kind_for` returns `Kind.INVALIDATED`, the copy reads `is no longer monitored: its trade record was deleted.`, and `build_notify_embed` passes no R.

**Decisions written down:**
- Glyph: none (`""`), like the risk-cap and limit cancels; `FEED_SYMBOLS` is pinned.
- The closed-by-delete notice is not a result: nothing was exited and the trade (with any banked TP1) is gone, so it carries no exit price, no R, no result block and no R stripe. It renders as `Kind.INVALIDATED` (RESULT family, grey, the "withdrawn" mark) in both the feed and the follow channel. The feed's text still names the direction's exit verb, so a reader holding the position at a broker knows how to get out (the feed guard `test_every_close_and_time_exit_names_the_exit_verb` holds for every `EXITED`).
- `lifecycle_embeds._closed_fields` / `CLOSE_REASON_STYLES` are not touched: `closed` is a `NOTICE_EVENTS` member, so `notify_plan_events` renders it through `build_instruction_embed`, never through the history-only `build_plan_event_embed`.
- `session_expiry` gets the code and a message so its tables stay complete, though no outlook annotation reaches a delete today (`_annotate_outlook` runs inside the plan manager's step, and a delete ends the plan in `plan_links`).
- `follow_notify` stays tables and plain `if`s (`test_the_policy_is_tables_not_if_chains`), and no comment in it contains the text `Kind.CANCEL` (`test_imperative_kinds_are_never_used` greps the source).

- [ ] **Step 1: Write the failing test**

Create `tests/presentation/test_trade_deleted_cancel_vocab.py`:

```python
"""v189 A7: the delete vocabulary.

`cancelled_trade_deleted` (a PENDING plan whose placeholder trade was deleted)
joins every table a pending cancel lives in, as v187's two limit cancels did.
A `closed` event with reason `trade_deleted` (an ACTIVE/PARTIAL plan whose
trade was deleted) has no exit price: the feed and the follow channel say the
position is no longer monitored -- no exit, no R, no result block.
"""
import pytest

from swingbot.commands.scanning import follow_notify as fn
from swingbot.core.planning import plan_manager
from swingbot.core.planning import session_expiry as se
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import instructions as ins
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import execution_embeds, lifecycle_embeds
from swingbot.core.scanning.embeds import build_plan_event_embed
from tests.planning.test_plan_engine_model import _plan

EVENT = "cancelled_trade_deleted"
CANCEL_DETAIL = {"reason": "trade_deleted", "live_price": None}
CLOSE_DETAIL = {"reason": "trade_deleted"}
DIRECTIONS = ("bullish", "bearish")
WHY = ("The trade record was deleted before the order filled. Nothing was opened and "
       "the plan is no longer monitored.")


def _levels(direction):
    sign = 1 if direction == "bullish" else -1
    return dict(direction=direction, trigger_price=100.0, stop_loss=100.0 - 5 * sign,
                tp1=100.0 + 10 * sign, tp2=100.0 + 20 * sign)


def _cancelled(direction="bullish"):
    plan = _plan(entry_type="stop_entry", **_levels(direction))
    record_transition(plan, PlanStatus.CANCELLED, reason="trade_deleted",
                      at="2026-10-23T15:00:00+00:00")
    return plan


def _closed_partial(direction="bullish"):
    sign = 1 if direction == "bullish" else -1
    plan = _plan(entry_type="stop_entry", entry_price=100.0, **_levels(direction))
    record_transition(plan, PlanStatus.ACTIVE, reason="stop_entry_fill", at="t0")
    plan.legs_realized.append({"fraction": 0.5, "exit_price": 100.0 + 10 * sign,
                               "r": 2.0, "reason": "tp1"})
    record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial", at="t1")
    record_transition(plan, PlanStatus.CLOSED, reason="trade_deleted", at="t2")
    return plan


def _texts(instruction):
    return [instruction.headline, *instruction.lines, *instruction.warnings]


# --- cancelled_trade_deleted -----------------------------------------------------

def test_it_is_a_pending_cancel_and_a_notice():
    assert EVENT in plan_manager.PENDING_CANCEL_EVENTS
    assert EVENT in plan_manager.NOTICE_EVENTS
    assert plan_manager._TRANSITION_LOG[EVENT] == ("trade deleted", "live_price")


@pytest.mark.parametrize("direction, order", [("bullish", "BUY STOP"), ("bearish", "SELL STOP")])
def test_the_feed_words_the_cancel(direction, order):
    instruction = ins.instruction_for(_cancelled(direction), PlanEvent("p1", EVENT, CANCEL_DETAIL))
    assert (instruction.verb, instruction.tone) == (ins.CANCEL, "inert")
    assert instruction.headline == f"CANCEL {order} 100.00"
    assert instruction.lines == (WHY,)
    assert ins._CANCEL_LEADS[EVENT] == ""
    assert ins._BUILDERS[EVENT] is ins._cancelled


def test_both_embed_tables_render_it_as_cancel():
    assert lifecycle_embeds.PLAN_EVENT_KINDS[EVENT] is Kind.CANCEL
    assert execution_embeds._EVENT_KINDS[EVENT] is Kind.CANCEL
    assert execution_embeds._event_style(_cancelled(), PlanEvent("p1", EVENT, CANCEL_DETAIL),
                                         None) == (Kind.CANCEL, None, None)


def test_the_history_embed_says_why():
    embed = build_plan_event_embed(_cancelled(), PlanEvent("p1", EVENT, CANCEL_DETAIL))
    assert embed.title == "🚫 ▲ LONG AAPL · CANCEL"
    why = next(f.value for f in embed.fields if f.name == "Why")
    assert why == ("The trade record was deleted before the 100.00 order filled. "
                   "Never opened; no position, no P&L.")


def test_the_outlook_code_and_message():
    assert se.TRADE_DELETED == "trade_deleted"
    assert se.code_for(EVENT) == se.TRADE_DELETED
    assert se.in_session_message(_cancelled(), EVENT, CANCEL_DETAIL) == (
        "The trade record was deleted before the order filled; nothing opened")


def test_the_follow_channel_posts_it_as_a_factual_cancel():
    event = PlanEvent("p1", EVENT, CANCEL_DETAIL)
    assert fn.notify_event_for(event) == "closed_other"
    assert fn.kind_for(event, "closed_other") is Kind.INVALIDATED
    line = fn.message_line(_cancelled(), "closed_other", EVENT, CANCEL_DETAIL)
    assert line == "Paper plan update: AAPL long cancelled: trade record deleted before fill."
    assert not [p for p in fn.FORBIDDEN_PHRASES if p in line.lower()]


def test_every_pending_cancel_event_has_every_row():
    cancels = plan_manager.PENDING_CANCEL_EVENTS
    assert cancels <= set(ins._BUILDERS) and cancels <= set(ins._CANCEL_LEADS)
    assert cancels <= set(lifecycle_embeds.PLAN_EVENT_KINDS)
    assert cancels <= set(lifecycle_embeds._EVENT_FIELDS)
    assert cancels <= set(execution_embeds._EVENT_KINDS)
    assert all(fn.notify_event_for(PlanEvent("p1", t, {})) is not None for t in cancels)


# --- closed with reason trade_deleted ------------------------------------------------

@pytest.mark.parametrize("direction, exit_verb", [("bullish", "SELL AT MARKET"),
                                                  ("bearish", "BUY TO COVER AT MARKET")])
def test_the_feed_says_no_longer_monitored_with_no_exit(direction, exit_verb):
    instruction = ins.instruction_for(_closed_partial(direction),
                                      PlanEvent("p1", "closed", CLOSE_DETAIL))
    assert (instruction.verb, instruction.tone) == (ins.EXITED, "inert")
    assert instruction.headline == "NO LONGER MONITORED · trade record deleted"
    text = "\n".join(_texts(instruction))
    assert exit_verb in text
    assert "@" not in text and "n/a" not in text


def test_the_feed_embed_is_a_grey_withdrawn_result_with_no_r(monkeypatch):
    plan = _closed_partial()
    event = PlanEvent("p1", "closed", CLOSE_DETAIL)
    monkeypatch.setattr(execution_embeds, "_event_money", lambda plan_: None)
    instruction = ins.instruction_for(plan, event)
    assert execution_embeds._event_style(plan, event, instruction) == (Kind.INVALIDATED, None, None)
    embed = execution_embeds.build_instruction_embed(plan, event)
    assert "INVALIDATED" in embed.title
    assert "NO LONGER MONITORED" in embed.description


def test_the_follow_channel_says_no_longer_monitored():
    plan = _closed_partial()
    event = PlanEvent("p1", "closed", CLOSE_DETAIL)
    assert fn.notify_event_for(event) == "closed_other"
    assert fn.kind_for(event, "closed_other") is Kind.INVALIDATED
    line = fn.message_line(plan, "closed_other", "closed", CLOSE_DETAIL)
    assert line == "Paper plan update: AAPL long is no longer monitored: its trade record was deleted."
    embed = fn.build_notify_embed(plan, "closed_other", "closed", CLOSE_DETAIL)
    assert "INVALIDATED" in embed.title
    assert embed.push_text == line


@pytest.mark.parametrize("reason", ["time_exit", "loss"])
def test_an_ordinary_close_is_unchanged(reason):
    plan = _closed_partial()
    event = PlanEvent("p1", "closed", {"reason": reason, "exit_price": 104.0})
    assert fn.kind_for(event, "closed_other") is Kind.EXITED
    kind, block, r = execution_embeds._event_style(plan, event, ins.instruction_for(plan, event))
    assert kind is Kind.EXITED and block is not None and r is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/presentation/test_trade_deleted_cancel_vocab.py`
Expected: FAIL — `cancelled_trade_deleted` is in none of the tables (`KeyError` / `AssertionError`), `session_expiry` has no `TRADE_DELETED`, and the closed-by-delete instruction reads `EXITED @ n/a · trade_deleted`.

- [ ] **Step 3: `plan_manager.py` — the event set and the log line**

In `swingbot/core/planning/plan_manager.py`, add the member to v187's `PENDING_CANCEL_EVENTS` literal (keep v187's members exactly):

```python
PENDING_CANCEL_EVENTS = frozenset({
    "cancelled_expired", "cancelled_invalidated", "cancelled_risk_cap",
    "cancelled_limit", "cancelled_gap_through_stop",
    "cancelled_trade_deleted",     # v189 A7: queued by tracking/plan_links, not by a step
})
```

and one row to `_TRANSITION_LOG`, after v187's `"cancelled_gap_through_stop"` row:

```python
    "cancelled_trade_deleted": ("trade deleted", "live_price"),
```

`NOTICE_EVENTS` is derived from `PENDING_CANCEL_EVENTS` (v187), so it needs no edit; confirm with `git grep -n "NOTICE_EVENTS =" -- swingbot/core/planning/plan_manager.py`.

- [ ] **Step 4: `instructions.py` — the cancel wording and the no-exit close**

In `swingbot/core/presentation/instructions.py`:

(a) Add `"cancelled_trade_deleted": ""` to `_CANCEL_LEADS`, and above v187's `_CANCEL_WHY` add:

```python
def _trade_deleted_why(detail: dict) -> str:
    return ("The trade record was deleted before the order filled. Nothing was opened "
            "and the plan is no longer monitored.")
```

then add `"cancelled_trade_deleted": _trade_deleted_why,` to `_CANCEL_WHY`, and `"cancelled_trade_deleted": _cancelled,` to `_BUILDERS` after v187's two limit rows.

(b) Above `_closed` (`:433`) add:

```python
#: v189 A7: closes with no exit behind them. The bot stopped monitoring the
#: position because its trade record was deleted; nothing was exited.
_NO_EXIT_REASONS = frozenset({"trade_deleted"})


def _no_exit_close(side: dict, common: dict) -> Instruction:
    return Instruction(
        verb=EXITED, headline="NO LONGER MONITORED · trade record deleted",
        lines=("The paper trade record was deleted, so the bot stopped monitoring this "
               "position: no more stop or target alerts.",
               "Nothing was exited by the bot. If you hold it at your broker, its orders "
               f"are yours to manage; to close it: {side['exit']}."),
        tone="inert", **common)
```

and make it the first statement of `_closed`:

```python
def _closed(plan, detail: dict, side: dict, common: dict,
            money: Money | None = None) -> Instruction:
    if detail.get("reason") in _NO_EXIT_REASONS:
        return _no_exit_close(side, common)
    exit_price = detail.get("exit_price")
    ...the rest of the body unchanged...
```

No glyph literal is written (`test_feed_guards.py::test_instructions_py_writes_no_glyph_literal`); the `·` separator is the one the close headline already uses.

- [ ] **Step 5: `lifecycle_embeds.py` and `execution_embeds.py`**

(a) `swingbot/core/scanning/lifecycle_embeds.py`: add `"cancelled_trade_deleted": Kind.CANCEL,   # v189 A7` to `PLAN_EVENT_KINDS` after v187's two rows; after v187's `_gap_through_stop_fields` add:

```python
def _trade_deleted_fields(embed, plan, d) -> None:
    """v189 A7: a PENDING plan whose placeholder trade record was deleted."""
    embed.description = plan_levels_block(plan, plan.trigger_price)
    embed.add_field(name="Why", value=(
        f"The trade record was deleted before the {plan.trigger_price:.2f} order filled. "
        "Never opened; no position, no P&L."), inline=False)
```

and add `"cancelled_trade_deleted": _trade_deleted_fields,` to `_EVENT_FIELDS`.

(b) `swingbot/core/scanning/execution_embeds.py`: add `"cancelled_trade_deleted": Kind.CANCEL,   # v189 A7` to `_EVENT_KINDS`; above `_event_style` add:

```python
#: v189 A7: a close with no exit behind it (the trade record was deleted) is
#: shown as a withdrawn plan -- no result block, no R stripe.
_NO_EXIT_CLOSE_KINDS = {"trade_deleted": Kind.INVALIDATED}
```

and make the `closed` branch of `_event_style` start with the lookup:

```python
    if event.transition == "closed":
        no_exit = _NO_EXIT_CLOSE_KINDS.get(event.detail.get("reason"))
        if no_exit is not None:
            return no_exit, None, None
        exit_price = event.detail.get("exit_price")
        ...the rest of the branch unchanged...
```

- [ ] **Step 6: `session_expiry.py`**

In `swingbot/core/planning/session_expiry.py`, append one sentence to the module docstring's first paragraph: `v189 adds cancelled_trade_deleted: the placeholder trade was deleted (a human act, at any time), worded here so the tables stay complete.` Add the constant after v187's two:

```python
TRADE_DELETED = "trade_deleted"            # v189 A7
```

add `"cancelled_trade_deleted": TRADE_DELETED` to `_IN_SESSION_CODES`, and above v187's per-transition message table add

```python
def _trade_deleted_message(plan, detail: dict) -> str:
    return "The trade record was deleted before the order filled; nothing opened"
```

with `"cancelled_trade_deleted": _trade_deleted_message,` as a new row of that table (v187 named it `_LIMIT_MESSAGES`; keep the name).

- [ ] **Step 7: `follow_notify.py`**

In `swingbot/commands/scanning/follow_notify.py`:

(a) Add rows after v187's: `"cancelled_trade_deleted": "closed_other",` to `_BY_TRANSITION`; `"cancelled_trade_deleted": Kind.INVALIDATED,` to `_CLOSED_OTHER_KIND`; `"cancelled_trade_deleted": "trade record deleted before fill",` to `_CANCEL_LABELS`.

(b) Below `_CLOSED_OTHER_KIND` add:

```python
# v189 A7: closes with no exit behind them -- the trade record was deleted.
# Factual copy and the withdrawn-plan kind; never an R.
_NO_EXIT_CLOSES = {"trade_deleted": "is no longer monitored: its trade record was deleted."}
_CLOSED_OTHER_KIND_BY_REASON = {"trade_deleted": Kind.INVALIDATED}
```

(c) Replace `kind_for`:

```python
def kind_for(event: PlanEvent, notify_event: str) -> Kind:
    """The registry Kind the message renders as (never MOVE STOP or an imperative cancel)."""
    if notify_event == "closed_other":
        reason = (event.detail or {}).get("reason")
        return _CLOSED_OTHER_KIND_BY_REASON.get(reason) or _CLOSED_OTHER_KIND[event.transition]
    return _KIND_BY_EVENT[notify_event]
```

(d) In `_other_copy`, after the `if transition != "closed":` block and before `reason = detail.get("reason") or "other exit"`, add:

```python
    no_exit = _NO_EXIT_CLOSES.get(detail.get("reason"))
    if no_exit is not None:
        return no_exit
```

(e) Above `build_notify_embed` add

```python
def _close_r(plan, transition: str, detail: dict) -> float | None:
    """The stripe R of a close; None for anything else and for a close with
    no exit behind it."""
    if transition != "closed" or detail.get("reason") in _NO_EXIT_CLOSES:
        return None
    return instructions.total_r(plan, detail.get("exit_price"))
```

and in `build_notify_embed` replace the `close_r = ...` line with `close_r = _close_r(plan, transition, detail)`.

- [ ] **Step 8: Run the tests**

Run: `python scripts/dev/testrun.py file tests/presentation/test_trade_deleted_cancel_vocab.py`
Expected: PASS (14 tests).

Run each (all must PASS unchanged; v187's coverage tests now include the new member):
`python scripts/dev/testrun.py file tests/presentation/test_instructions.py`
`python scripts/dev/testrun.py file tests/presentation/test_feed_guards.py`
`python scripts/dev/testrun.py file tests/presentation/test_feed_symbols.py`
`python scripts/dev/testrun.py file tests/presentation/test_instructions_limit_cancels.py`
`python scripts/dev/testrun.py file tests/scanning/test_lifecycle_embeds_limit_cancels.py`
`python scripts/dev/testrun.py file tests/scanning/test_execution_embeds.py`
`python scripts/dev/testrun.py file tests/commands/test_follow_notify_policy.py`
`python scripts/dev/testrun.py file tests/commands/test_follow_notify_copy.py`
`python scripts/dev/testrun.py file tests/commands/test_follow_notify_limit_cancels.py`
`python scripts/dev/testrun.py file tests/planning/test_session_expiry.py`

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed, 0 xfailed.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`_closed` +1, `_event_style` +1, `kind_for` +1, `_other_copy` +1; all far below 15).

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/planning/plan_manager.py swingbot/core/presentation/instructions.py swingbot/core/scanning/lifecycle_embeds.py swingbot/core/scanning/execution_embeds.py swingbot/core/planning/session_expiry.py swingbot/commands/scanning/follow_notify.py tests/presentation/test_trade_deleted_cancel_vocab.py
git commit -m "feat(feed): cancelled_trade_deleted across the vocabulary; a close by delete says no longer monitored (v189 V189-13)"
```

