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


### Task V189-14: Deletes end their linked plans and say so

**Model:** opus — every delete path (TradeLog, admin API, Discord) moves into one locked transaction with the plan rows, multi-plan lock order matters, and the confirmation copy makes a claim about the balance that a test must hold.

**Spec:** D4 A7 (`clear_open` and legacy-id `delete_trade` end the linked plan in the same transaction, reason `trade_deleted`; PENDING → cancelled with `cancelled_trade_deleted`, ACTIVE/PARTIAL → closed, no P&L settled; the confirmation names every ACTIVE/PARTIAL position ended, says monitoring and stop/TP alerts stop, and that banked TP1 dollars go with the trade); § Testing A7 (`clear_open` cancels its plans); Corrections 7 (the notice is test-pinned for both cases); index clarification 2 (the notice travels in the plan's `pending_notice` slot, re-emitted by `PlanManager.resend_notices`). Lock order: index § Global Constraints (plan → trade, multi-plan in `plan_id` order, no `threading.Lock` held while waiting on a row).

**Files:**
- Modify: `swingbot/core/tracking/plan_links.py` (V189-12's module: add `TRADE_DELETED_REASON`, `describe_ended`, `_names`, `_cancel_line`)
- Modify: `swingbot/core/tracking/performance.py` (`delete_trade` and `clear_open` near `:1558-1571`; new `TradeLog._delete_open_with_plan`; module helpers `_end_plan_for_delete`, `_plan_lock_order` beside V189-12's `_close_linked_plan_safely`)
- Modify: `swingbot/admin/api_v1/trade_commands.py` (`delete_trade` `:240-263`, `clear_open` `:267-270`; imports)
- Modify: `swingbot/commands/trades.py` (`handle_trades_clear` `:193-197`, `handle_trade_delete` `:362-367`; imports `:9-22`)
- Modify: `tests/commands/parity_cases/trades.py` (`_FakeLog.clear_open` / `delete_trade` return `DeleteResult`; two new cases)
- Modify: `tests/tracking/test_tradelog_db_bulk.py` (`FakeTradesRepo.get_for_update`; three return-type assertions)
- Modify: `tests/admin/test_api_v1_trade_commands.py` (two `clear-open` JSON equalities at `:226` and `:245`)
- Create: `tests/tracking/test_delete_ends_linked_plans.py`
- Create: `tests/admin/test_delete_ends_plans_api.py`

The last two modified test files are not in the ledger row: the return types change (`bool`/`int` → `DeleteResult`) and the clear-open JSON gains two keys, so their equality assertions must follow. No other task touches them.

**Interfaces:**
- Consumes (V189-12, `swingbot/core/tracking/plan_links.py`): `EndedPlan(plan_id, ticker, status_before, status_after)`, `DeleteResult(removed, ended=())` with `__bool__` = `removed > 0`, `end_linked_plan(plan_id, reason, *, conn, notice=False) -> EndedPlan | None` (with `notice=True` it writes `pending_notice`: `cancelled_trade_deleted` with `{"reason", "live_price": None}` on a cancel, `closed` with `{"reason"}` on a close). V189-11: `TradeLog._open_trade_by_id(trade_id, *, conn=None)` (row-locked read on `conn`; None unless open). V189-5: `transaction(..., lock_timeout_ms=)`, `LockTimeout`, `ADMIN_LOCK_TIMEOUT_MS`. V189-13: the vocabulary that renders both notices. Existing: `PlanManager(store, price_fn).resend_notices(now=None)` (`plan_manager.py:489`), `PlanStatus` (`plan_types.py`), `trades_repo()` (`db/repositories/trades.py`), `error(code, message, status)` (`admin/api_v1`).
- Produces:
  ```python
  # swingbot/core/tracking/plan_links.py
  TRADE_DELETED_REASON = "trade_deleted"
  def describe_ended(result: DeleteResult) -> str      # "" when nothing ended
  # swingbot/core/tracking/performance.py
  TradeLog.delete_trade(self, trade_id: str) -> DeleteResult     # any status, as today; ends its plan
  TradeLog.clear_open(self) -> DeleteResult                      # open rows only, as today; ends their plans
  ```
  Admin JSON: `DELETE /api/v1/trades/<id>` → 200 `{"deleted": id, "ended": [{"plan_id", "ticker", "status_before", "status_after"}, ...], "notice": str}`; `POST /api/v1/trades/clear-open` → 200 `{"removed": n, "ended": [...], "notice": str}`; a `LockTimeout` on either → 409 `conflict`, nothing changed. Discord replies append `describe_ended(result)` on its own line when it is not empty. `clear_history` / `clear_all` keep returning `int` (V189-15 owns `clear_history`).

**Decisions written down:**
- **One transaction per call, on the admin lock timeout** (both callers are admin or Discord paths). `delete_trade` reads the trade unlocked to learn its `plan_id`, then in one transaction locks and ends the plan, then deletes the trade row. `clear_open` reads the open trades unlocked, sorts them by `(plan_id is None, plan_id, id)` so plan rows lock in `plan_id` order, and for each: ends the plan, re-reads the trade under its row lock with `_open_trade_by_id(conn=)`, deletes it only if it is still open. A trade the bot closed between the read and the lock is kept (its plan was already terminal, since closes commit with their plan, so `end_linked_plan` wrote nothing). A trade opened after the read is not touched: only rows the call saw are deleted, so no plan is left behind without its trade.
- `_LOCK` (the process-local `threading.Lock`) is no longer taken by these two methods: they would hold it while waiting on a row lock.
- **No P&L, no balance write, no placeholder call.** The trade row being deleted *is* the PENDING plan's placeholder, so `discard_plan_placeholder` is not called. Balance = `base_balance + Σ realized_pnl_amount` (`account._sum_realized_pnl`); an open PARTIAL carries no `realized_pnl_amount` (TP1 is a leg until the close settles), so its banked TP1 never reached the balance. The copy says exactly that, and `test_deleting_a_partial_leaves_the_balance_where_it_was` pins it. **If that test fails, stop and report**: the copy's claim would be false.
- **The notice** is the plan's `pending_notice`, written by `end_linked_plan(..., notice=True)` inside the delete transaction (clarification 2). The bot's next `resend_notices` emits it and V189-13's vocabulary renders it. No `_queue_notify` record: its consumer drops plan records.
- **Copy.** `describe_ended` names the ACTIVE/PARTIAL ends first (a held position loses its alerts), then the cancels. Each name reads ``AAPL (`p1`, was PARTIAL)``. Exact text is fixed by the tests in Step 1.
- A `LockTimeout` (the bot holds a plan row past 5 s) rolls everything back. Admin answers 409 `conflict`, Discord an error reply; both say nothing was deleted.
- The admin `delete_trade` still refuses plan-shaped ids (422); only what a trade-id delete does to its plan changes. The frontend's `ClearResult` keeps reading `removed`; showing `notice` in the UI is not in this plan.

- [ ] **Step 1: Write the failing TradeLog tests**

Create `tests/tracking/test_delete_ends_linked_plans.py`:

```python
"""v189 D4 A7: deleting a trade ends its linked v2 plan in the same
transaction -- a PENDING plan is cancelled (cancelled_trade_deleted), an
ACTIVE/PARTIAL one is closed with no P&L -- and the plan's pending_notice
carries the follow / feed notice. A plan is never left stepping with no trade."""
import pytest

from swingbot.core.db.repositories import trades as trades_repo_module
from swingbot.core.planning import account as account_module
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.tracking import plan_links
from swingbot.core.tracking.performance import TradeLog
from swingbot.core.tracking.plan_links import DeleteResult, EndedPlan, describe_ended
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_active import _active
from tests.store_seed import seed_store

_TP1 = {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}


@pytest.fixture
def tlog(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)
    seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0,
                           "sizing_mode": "risk_pct", "balance_history": []})
    return TradeLog()


def _partial(**kw):
    plan = _active(**kw)
    plan.legs_realized.append(dict(_TP1))
    record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial", at="t1")
    return plan


_BUILD = {"PENDING": lambda **kw: _plan(entry_type="stop_entry", **kw),
          "ACTIVE": _active, "PARTIAL": _partial}
_ENDS = {"PENDING": "CANCELLED", "ACTIVE": "CLOSED", "PARTIAL": "CLOSED"}


def _log(tl, ticker, plan_id=None) -> str:
    return tl.log_trade(ticker=ticker, strategy="RSI", horizon_key="2w", direction="bullish",
                        confidence_level=3, confidence_label="Medium", entry=100.0,
                        stop_loss=95.0, take_profit=110.0, plan_id=plan_id)


def _open(tl, status, plan_id="p1", ticker="AAPL") -> str:
    """A plan in `status` and its open trade row; returns the trade id."""
    PlanStore().add(_BUILD[status](plan_id=plan_id, ticker=ticker))
    tid = _log(tl, ticker, plan_id)
    if status == "PARTIAL":
        tl.append_leg_by_plan(plan_id, dict(_TP1))
    return tid


def _resent():
    events = PlanManager(PlanStore(), lambda ticker: None).resend_notices()
    return [(e.plan_id, e.transition, e.detail) for e in events]


@pytest.mark.parametrize("status", list(_BUILD))
def test_delete_trade_ends_its_plan_by_status(tlog, status):
    tid = _open(tlog, status)
    result = tlog.delete_trade(tid)
    assert result == DeleteResult(1, (EndedPlan("p1", "AAPL", status, _ENDS[status]),))
    plan = PlanStore().get("p1")
    assert plan.status == _ENDS[status]
    assert plan.status_history[-1]["reason"] == "trade_deleted" == plan_links.TRADE_DELETED_REASON
    assert tlog.get_trade_by_id(tid) is None
    assert account_module.get_balance_history() == []


def test_a_pending_delete_queues_the_cancel_notice_and_resend_emits_it(tlog):
    tlog.delete_trade(_open(tlog, "PENDING"))
    assert _resent() == [
        ("p1", "cancelled_trade_deleted", {"reason": "trade_deleted", "live_price": None})]


@pytest.mark.parametrize("status", ["ACTIVE", "PARTIAL"])
def test_a_position_delete_queues_a_closed_notice_and_resend_emits_it(tlog, status):
    tlog.delete_trade(_open(tlog, status))
    assert _resent() == [("p1", "closed", {"reason": "trade_deleted"})]


def test_deleting_a_partial_leaves_the_balance_where_it_was(tlog):
    """The copy says banked TP1 dollars never reached the balance: an open
    PARTIAL has no realized_pnl_amount until its close settles."""
    tid = _open(tlog, "PARTIAL")
    before = account_module.load_account_config()["balance"]
    tlog.delete_trade(tid)
    assert account_module.load_account_config()["balance"] == before


def test_deleting_a_closed_trade_leaves_its_terminal_plan_alone(tlog):
    plan = _active()
    record_transition(plan, PlanStatus.CLOSED, reason="loss", at="t2")
    PlanStore().add(plan)
    tid = _log(tlog, "AAPL", "p1")
    history = PlanStore().get("p1").status_history
    assert tlog.delete_trade(tid) == DeleteResult(1)
    assert PlanStore().get("p1").status_history == history
    assert PlanStore().get("p1").pending_notice is None


def test_deleting_a_legacy_trade_ends_nothing(tlog):
    assert tlog.delete_trade(_log(tlog, "MSFT")) == DeleteResult(1)


def test_deleting_an_unknown_trade_is_falsy(tlog):
    result = tlog.delete_trade("nope")
    assert not result and result == DeleteResult(0)


def test_a_failed_row_delete_rolls_the_plan_back(tlog, monkeypatch):
    tid = _open(tlog, "ACTIVE")

    def boom(self, key, *, conn=None):
        raise RuntimeError("trade row delete failed")

    monkeypatch.setattr(trades_repo_module.TradeRepository, "delete", boom)
    with pytest.raises(RuntimeError):
        tlog.delete_trade(tid)
    assert PlanStore().get("p1").status == "ACTIVE"
    assert PlanStore().get("p1").pending_notice is None


def test_clear_open_ends_every_plan_in_plan_id_order(tlog, monkeypatch):
    _open(tlog, "PARTIAL", plan_id="p3", ticker="NVDA")
    _open(tlog, "PENDING", plan_id="p1", ticker="AAPL")
    _open(tlog, "ACTIVE", plan_id="p2", ticker="MSFT")
    _log(tlog, "AMD")
    locked = []
    real_end = plan_links.end_linked_plan

    def spy(plan_id, reason, *, conn, notice=False):
        locked.append(plan_id)
        return real_end(plan_id, reason, conn=conn, notice=notice)

    monkeypatch.setattr(plan_links, "end_linked_plan", spy)
    result = tlog.clear_open()
    assert locked == ["p1", "p2", "p3"]
    assert result.removed == 4
    assert [(e.plan_id, e.status_after) for e in result.ended] == [
        ("p1", "CANCELLED"), ("p2", "CLOSED"), ("p3", "CLOSED")]
    assert [PlanStore().get(p).status for p in ("p1", "p2", "p3")] == [
        "CANCELLED", "CLOSED", "CLOSED"]
    assert tlog.get_trades(status="open", limit=None) == []


def test_clear_open_keeps_closed_history(tlog):
    _open(tlog, "ACTIVE")
    closed = _log(tlog, "MSFT")
    assert tlog.close_trade_manual(closed, exit_price=108.0)
    result = tlog.clear_open()
    assert result.removed == 1
    assert tlog.get_trade_by_id(closed) is not None


def test_clear_open_on_an_empty_book(tlog):
    result = tlog.clear_open()
    assert result == DeleteResult(0) and describe_ended(result) == ""


def test_describe_ended_names_positions_then_cancels():
    result = DeleteResult(3, (
        EndedPlan("p1", "AAPL", "PENDING", "CANCELLED"),
        EndedPlan("p2", "MSFT", "ACTIVE", "CLOSED"),
        EndedPlan("p3", "NVDA", "PARTIAL", "CLOSED"),
    ))
    assert describe_ended(result) == (
        "Ended 2 open position(s): MSFT (`p2`, was ACTIVE), NVDA (`p3`, was PARTIAL). "
        "The bot no longer monitors them and sends no more stop or take-profit alerts "
        "for them. Any TP1 dollars they banked are deleted with the trade and never "
        "reach the balance.\n"
        "Cancelled 1 unfilled plan(s): AAPL (`p1`, was PENDING). Its order never filled.")


def test_describe_ended_with_only_cancels_or_nothing():
    two = DeleteResult(2, (EndedPlan("p1", "AAPL", "PENDING", "CANCELLED"),
                           EndedPlan("p2", "MSFT", "PENDING", "CANCELLED")))
    assert describe_ended(two) == (
        "Cancelled 2 unfilled plan(s): AAPL (`p1`, was PENDING), MSFT (`p2`, was PENDING). "
        "Their orders never filled.")
    assert describe_ended(DeleteResult(2)) == ""
```

- [ ] **Step 2: Write the failing admin tests**

Create `tests/admin/test_delete_ends_plans_api.py`:

```python
"""v189 A7 over HTTP: a trade-id delete and clear-open end the linked plans
and report them; a lock timeout is a 409 and nothing changes."""
import pytest

from tests.admin.api_v1_contract import assert_error
from tests.admin.test_api_v1_trades import _plan, _trade
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}
_PLAN_ID = "55555555-5555-4555-8555-555555555555"
_TRADE_ID = "bbbbbbbbbbbbbbbb"
_TP1 = {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}


@pytest.fixture
def seed(admin_app):
    def _seed(plans=(), trades=()):
        seed_store("plans", list(plans))
        seed_store("trades", list(trades))
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture(autouse=True)
def _no_live_quote(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.data.get_current_price", lambda *a, **k: None)


def _stored(plan_id):
    from swingbot.core.planning.plan_store import PlanStore
    return PlanStore().get(plan_id)


def test_deleting_a_partial_trade_closes_its_plan_and_says_so(seed, logged_in):
    seed(plans=[{**_plan(_PLAN_ID, status="PARTIAL"), "legs_realized": [dict(_TP1)]}],
         trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    r = logged_in.delete(f"/api/v1/trades/{_TRADE_ID}")
    assert r.status_code == 200
    body = r.get_json()
    assert body["deleted"] == _TRADE_ID
    assert body["ended"] == [{"plan_id": _PLAN_ID, "ticker": "AAPL",
                              "status_before": "PARTIAL", "status_after": "CLOSED"}]
    assert f"AAPL (`{_PLAN_ID}`, was PARTIAL)" in body["notice"]
    assert "no more stop or take-profit alerts" in body["notice"]
    assert "TP1 dollars" in body["notice"]
    plan = _stored(_PLAN_ID)
    assert plan.status == "CLOSED"
    assert plan.pending_notice["detail"] == {"reason": "trade_deleted"}


def test_deleting_a_pending_placeholder_cancels_its_plan(seed, logged_in):
    seed(plans=[_plan(_PLAN_ID, status="PENDING")], trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    body = logged_in.delete(f"/api/v1/trades/{_TRADE_ID}").get_json()
    assert [e["status_after"] for e in body["ended"]] == ["CANCELLED"]
    assert _stored(_PLAN_ID).pending_notice["transition"] == "cancelled_trade_deleted"


def test_deleting_a_legacy_trade_reports_nothing_ended(seed, logged_in):
    seed(trades=[_trade(_TRADE_ID, plan_id=None, status="win")])
    body = logged_in.delete(f"/api/v1/trades/{_TRADE_ID}").get_json()
    assert body == {"deleted": _TRADE_ID, "ended": [], "notice": ""}


def test_clear_open_ends_the_plans_and_reports_them(seed, logged_in):
    seed(plans=[_plan(_PLAN_ID, status="ACTIVE")],
         trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID),
                 _trade("cccccccccccccccc", plan_id=None, status="win")])
    body = logged_in.post("/api/v1/trades/clear-open").get_json()
    assert body["removed"] == 1
    assert [(e["plan_id"], e["status_after"]) for e in body["ended"]] == [(_PLAN_ID, "CLOSED")]
    assert body["notice"].startswith("Ended 1 open position(s): AAPL")
    assert _stored(_PLAN_ID).status == "CLOSED"


@pytest.mark.parametrize("method, path, attr", [
    ("delete", f"/api/v1/trades/{_TRADE_ID}", "delete_trade"),
    ("post", "/api/v1/trades/clear-open", "clear_open"),
])
def test_a_lock_timeout_is_a_409(seed, logged_in, monkeypatch, method, path, attr):
    from swingbot.core.db.engine import LockTimeout
    from swingbot.core.tracking.performance import TradeLog

    def locked(self, *args):
        raise LockTimeout("plan row held by the bot")

    seed(plans=[_plan(_PLAN_ID, status="ACTIVE")], trades=[_trade(_TRADE_ID, plan_id=_PLAN_ID)])
    monkeypatch.setattr(TradeLog, attr, locked)
    assert_error(getattr(logged_in, method)(path), "conflict", 409)
    assert _stored(_PLAN_ID).status == "ACTIVE"
```

- [ ] **Step 3: Run both new files to verify they fail**

Run: `python scripts/dev/testrun.py file tests/tracking/test_delete_ends_linked_plans.py`
Expected: FAIL — `ImportError: cannot import name 'describe_ended' from 'swingbot.core.tracking.plan_links'`.

Run: `python scripts/dev/testrun.py file tests/admin/test_delete_ends_plans_api.py`
Expected: FAIL — `KeyError: 'ended'`, plans still `PARTIAL` / `PENDING` / `ACTIVE`, and the 409 cases get a 500.

- [ ] **Step 4: Update the three existing test files to the new return shapes**

`tests/tracking/test_tradelog_db_bulk.py`:

(a) Add to `FakeTradesRepo`, after `delete`:

```python
    def get_for_update(self, key, *, conn):
        row = self.rows.get(key)
        return dict(row) if row is not None else None
```

(b) `test_delete_trade_removes_db_only_row`: `assert log.delete_trade("T1") is True` becomes `assert log.delete_trade("T1").removed == 1`; `assert log.delete_trade("T1") is False` becomes `assert not log.delete_trade("T1")`.

(c) `test_clear_open_deletes_open_db_rows_only`: `assert log.clear_open().removed == 2`. `test_clear_on_empty_db_returns_zero`: `assert log.clear_open().removed == 0`. (`clear_history` and `clear_all` keep `int`.)

`tests/admin/test_api_v1_trade_commands.py`: `test_clear_open_leaves_closed_history` (`:226`) compares to `{"removed": 1, "ended": [], "notice": ""}`; `test_clear_open_on_an_empty_store_is_not_an_error` (`:245`) to `{"removed": 0, "ended": [], "notice": ""}`.

`tests/commands/parity_cases/trades.py`: add `from swingbot.core.tracking.plan_links import DeleteResult, EndedPlan` to the imports; in `_FakeLog`:

```python
    def clear_open(self):
        return DeleteResult(sum(1 for t in self.trades if t["status"] == "open"))

    def delete_trade(self, trade_id):
        return DeleteResult(int(self.get_trade_by_id(trade_id) is not None))
```

Below `_FakeLog`:

```python
_ENDED = (EndedPlan("p-aapl-0001", "AAPL", "PARTIAL", "CLOSED"),
          EndedPlan("p-msft-0002", "MSFT", "PENDING", "CANCELLED"))


class _EndingLog(_FakeLog):
    """A log whose deletes end linked plans (v189 A7): the reply names them."""

    def clear_open(self):
        return DeleteResult(2, _ENDED)

    def delete_trade(self, trade_id):
        return DeleteResult(1, _ENDED[:1])


def _ending_stub(monkeypatch):
    _stub()(monkeypatch)
    monkeypatch.setattr(trades_mod, "trade_log", _EndingLog(ALL_TRADES))
```

And two cases in `CASES`, after `trade_delete_missing`:

```python
    ParityCase("trades_clear_ends_plans", trades_mod.handle_trades_clear, stub=_ending_stub),
    ParityCase("trade_delete_ends_plan", trades_mod.handle_trade_delete, args=("T0001",),
               stub=_ending_stub),
```

- [ ] **Step 5: `plan_links.py` — the reason and the confirmation copy**

In `swingbot/core/tracking/plan_links.py`, below `TRADE_DELETED_EVENT`:

```python
#: the transition reason a delete writes on the plan it ends.
TRADE_DELETED_REASON = "trade_deleted"
```

At the end of the module add `_names(ended) -> str` (comma-joined ``f"{e.ticker} (`{e.plan_id}`, was {e.status_before})"``), `_cancel_line(cancelled: list[EndedPlan]) -> str` (`"Cancelled {n} unfilled plan(s): {names}. "` + `"Its order never filled."` for one, `"Their orders never filled."` for more) and:

```python
def describe_ended(result: DeleteResult) -> str:
    """The confirmation lines for the plans a delete ended ("" when none).
    Held positions first: they lose their monitoring and alerts. An open
    PARTIAL's TP1 leg is not in the balance until the close settles, so the
    deleted trade takes it along."""
    closed = [e for e in result.ended if e.status_after == PlanStatus.CLOSED]
    cancelled = [e for e in result.ended if e.status_after == PlanStatus.CANCELLED]
    lines = []
    if closed:
        lines.append(
            f"Ended {len(closed)} open position(s): {_names(closed)}. "
            "The bot no longer monitors them and sends no more stop or take-profit alerts "
            "for them. Any TP1 dollars they banked are deleted with the trade and never "
            "reach the balance.")
    if cancelled:
        lines.append(_cancel_line(cancelled))
    return "\n".join(lines)
```

- [ ] **Step 6: `performance.py` — `delete_trade` and `clear_open` in one transaction with their plans**

Beside V189-12's `_close_linked_plan_safely`, add:

```python
def _end_plan_for_delete(trade: dict, *, conn):
    """End the v2 plan behind a trade that is being deleted (v189 A7), in the
    delete's transaction, and queue its notice. None for a legacy trade or a
    plan that is already terminal."""
    plan_id = trade.get("plan_id")
    if not plan_id:
        return None
    from swingbot.core.tracking import plan_links
    return plan_links.end_linked_plan(plan_id, plan_links.TRADE_DELETED_REASON,
                                      conn=conn, notice=True)


def _plan_lock_order(trade: dict) -> tuple:
    """Plan rows lock in plan_id order (index lock-order rule); legacy rows last."""
    plan_id = trade.get("plan_id")
    return (plan_id is None, plan_id or "", trade["id"])
```

(`plan_links.end_linked_plan` is looked up on the module at call time, so the order test's spy reaches it.)

Replace `delete_trade` and `clear_open` (`:1558-1571`):

```python
    def delete_trade(self, trade_id: str) -> "DeleteResult":
        """Remove one trade record by id, any status. v189 A7: its linked plan
        ends in the same transaction -- PENDING cancels, ACTIVE/PARTIAL close
        with no P&L -- with its feed / follow notice queued. Falsy when nothing
        was deleted. LockTimeout propagates and nothing changes."""
        from swingbot.core.db.engine import ADMIN_LOCK_TIMEOUT_MS, transaction
        from swingbot.core.db.repositories.trades import trades_repo
        from swingbot.core.tracking.plan_links import DeleteResult
        trade = next((t for t in self._all() if t["id"] == trade_id), None)
        if trade is None:
            return DeleteResult(0)
        with transaction(lock_timeout_ms=ADMIN_LOCK_TIMEOUT_MS) as tx:
            ended = _end_plan_for_delete(trade, conn=tx)
            removed = int(trades_repo().delete(trade_id, conn=tx))
        return DeleteResult(removed, (ended,) if ended else ())

    def clear_open(self) -> "DeleteResult":
        """Delete every open trade this call reads, leaving closed history
        untouched, and end each one's linked plan in the same transaction
        (v189 A7). Plan rows lock in plan_id order, each trade row after its
        plan; a trade closed meanwhile is kept. LockTimeout propagates and
        nothing changes."""
        from swingbot.core.db.engine import ADMIN_LOCK_TIMEOUT_MS, transaction
        from swingbot.core.tracking.plan_links import DeleteResult
        doomed = sorted((t for t in self._all() if t["status"] == "open"), key=_plan_lock_order)
        if not doomed:
            return DeleteResult(0)
        with transaction(lock_timeout_ms=ADMIN_LOCK_TIMEOUT_MS) as tx:
            outcomes = [self._delete_open_with_plan(t, conn=tx) for t in doomed]
        return DeleteResult(sum(removed for removed, _ in outcomes),
                            tuple(ended for _, ended in outcomes if ended))

    def _delete_open_with_plan(self, trade: dict, *, conn) -> tuple:
        """(rows removed, EndedPlan | None) for one open trade inside `conn`:
        the plan first, then the trade row under its lock, deleted only if
        it is still open."""
        from swingbot.core.db.repositories.trades import trades_repo
        ended = _end_plan_for_delete(trade, conn=conn)
        if self._open_trade_by_id(trade["id"], conn=conn) is None:
            return 0, ended
        return int(trades_repo().delete(trade["id"], conn=conn)), ended
```

For the string annotations, add `from typing import TYPE_CHECKING` (if absent) and `if TYPE_CHECKING: from swingbot.core.tracking.plan_links import DeleteResult` near the top of `performance.py`. At runtime `plan_links` stays a lazy import: it imports `TradeLog` lazily from this module.

- [ ] **Step 7: Admin endpoints report what ended**

In `swingbot/admin/api_v1/trade_commands.py` add `from dataclasses import asdict` to the stdlib imports and `from swingbot.core.tracking.plan_links import describe_ended` beside V189-11's `performance` import (`LockTimeout` is already imported by V189-11). Above `delete_trade` add:

```python
_DELETE_LOCKED = ("A plan behind this delete is being updated by the bot; "
                  "nothing was deleted. Try again in a moment.")


def _ended_body(result) -> dict:
    """The A7 part of a delete response: every plan ended, and the copy."""
    return {"ended": [asdict(e) for e in result.ended], "notice": describe_ended(result)}
```

Replace the tail of `delete_trade` (from `if not TradeLog().delete_trade(trade_id):`) with:

```python
    try:
        result = TradeLog().delete_trade(trade_id)
    except LockTimeout:
        return error("conflict", _DELETE_LOCKED, 409)
    if not result:
        return error("not_found", f"No trade with id {trade_id!r}", 404)
    return jsonify({"deleted": trade_id, **_ended_body(result)})
```

Replace `clear_open`'s body with:

```python
    try:
        result = TradeLog().clear_open()
    except LockTimeout:
        return error("conflict", _DELETE_LOCKED, 409)
    return jsonify({"removed": result.removed, **_ended_body(result)})
```

Add one paragraph to `delete_trade`'s docstring: a trade-id delete of a plan-linked trade ends that plan (PENDING cancelled, ACTIVE/PARTIAL closed, no P&L) and the response lists it under `ended`, with the confirmation in `notice`.

- [ ] **Step 8: Discord replies name what ended**

In `swingbot/commands/trades.py` add to the imports:

```python
from swingbot.core.db.engine import LockTimeout
from swingbot.core.tracking.plan_links import describe_ended
```

Above `handle_trades_clear`:

```python
_DELETE_LOCKED = ("A plan behind this is being updated by the bot right now; "
                  "nothing was deleted. Try again in a moment.")


def _with_ended(text: str, result) -> str:
    """`text`, then the A7 lines naming every plan the delete ended."""
    notice = describe_ended(result)
    return f"{text}\n{notice}" if notice else text
```

Replace the two handlers:

```python
async def handle_trades_clear(reply) -> None:
    """Clear all currently OPEN/active trades and end their linked plans.
    Closed trade history is kept."""
    try:
        result = trade_log.clear_open()
    except LockTimeout:
        await reply.send_error(_DELETE_LOCKED)
        return
    await reply.send(_with_ended(
        f"Cleared {result.removed} open trade(s). Closed win/loss history was not touched.",
        result))


async def handle_trade_delete(reply, trade_id: str) -> None:
    try:
        result = trade_log.delete_trade(trade_id)
    except LockTimeout:
        await reply.send_error(_DELETE_LOCKED)
        return
    if not result:
        await reply.send_error(f"No trade found with id `{trade_id}`.")
        return
    await reply.send(_with_ended(f"Deleted trade `{trade_id}`.", result))
```

The prefix and slash bodies stay one `handle_*` call each (`tests/commands/test_slash_parity.py`); v187's admin decorators are not touched.

- [ ] **Step 9: Run the new and the updated tests**

Run: `python scripts/dev/testrun.py file tests/tracking/test_delete_ends_linked_plans.py`
Expected: PASS (16 tests).

Run: `python scripts/dev/testrun.py file tests/admin/test_delete_ends_plans_api.py`
Expected: PASS (6 tests).

Run each (all must PASS):
`python scripts/dev/testrun.py file tests/tracking/test_tradelog_db_bulk.py`
`python scripts/dev/testrun.py file tests/tracking/test_tradelog_db.py`
`python scripts/dev/testrun.py file tests/tracking/test_plan_links.py`
`python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_commands.py`
`python scripts/dev/testrun.py file tests/commands/test_reply_parity.py`
`python scripts/dev/testrun.py file tests/commands/test_slash_parity.py`
`python scripts/dev/testrun.py file tests/commands/test_state_command_gates.py`
`python scripts/dev/testrun.py file tests/presentation/test_trade_deleted_cancel_vocab.py`

Run: `python scripts/dev/testrun.py changed`
Expected: 0 failed, 0 xfailed.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`describe_ended` about 5, `clear_open` about 4, `delete_trade` 3, `_delete_open_with_plan` 2, each handler 3).

- [ ] **Step 10: Commit**

Two scoped commits (core, then the two surfaces):

```bash
git add swingbot/core/tracking/plan_links.py swingbot/core/tracking/performance.py tests/tracking/test_delete_ends_linked_plans.py tests/tracking/test_tradelog_db_bulk.py
git commit -m "fix(tracking): deleting a trade ends its linked plan in the same transaction and queues its notice (v189 V189-14)"
git add swingbot/admin/api_v1/trade_commands.py swingbot/commands/trades.py tests/admin/test_delete_ends_plans_api.py tests/admin/test_api_v1_trade_commands.py tests/commands/parity_cases/trades.py
git commit -m "feat(admin,discord): delete and clear-open name every plan they end (v189 V189-14)"
```

(Both are edited and Step 9 is green before the first commit.)
