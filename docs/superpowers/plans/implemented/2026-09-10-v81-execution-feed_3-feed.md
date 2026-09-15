# v81 — Execution Feed, part 3: ticket, routing, verification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Index:** `2026-09-10-v81-execution-feed_0-index.md` — its Global Constraints
apply to every task here.

---

### Task F5: The order ticket — renderer, `build_simple_alert`, scan decision

**Files:**
- Create: `swingbot/core/scanning/execution_embeds.py`
- Modify: `swingbot/core/scanning/analyze.py` — two `ScanItem` fields (class at
  line 69) and `paper_trade_decision()` directly after the class
- Modify: `swingbot/core/scanning/scan_run.py:682` and its `from .` imports
- Modify: `swingbot/core/scanning/alert_embeds.py:224` (`build_simple_alert`) and its imports
- Create: `tests/scanning/test_paper_trade_decision.py`
- Create: `tests/scanning/test_execution_embeds.py`
- Modify: `tests/scanning/test_simple_alerts.py` (v2-plan shape tests only; the
  `_send_alerts` routing tests are untouched)

**Interfaces:**
- Consumes: `instructions.Instruction`, `ticket_for`, `instruction_for`,
  `block_warnings` (F2); existing `plan_table._sizing_snapshot(entry, plan)`,
  `presentation.apply_chrome`, `accent_for_level`, `accent_for_outcome`,
  `accent_blocked`, `direction_glyph`.
- Produces:
  - `ScanItem.paper_logged: bool = False`, `ScanItem.not_logged_reason: str | None = None`
  - `analyze.paper_trade_decision(item, already_open: bool) -> tuple[bool, str | None]`
  - `execution_embeds.render(instruction) -> discord.Embed`
  - `execution_embeds.build_ticket_embed(item, plan) -> discord.Embed`
  - `execution_embeds.build_instruction_embed(plan, event) -> discord.Embed` (F6 consumes)
  - `build_simple_alert(item)` returns the ticket for an item with a v2 plan
    under `PLAN_ENGINE_V2 == "on"`, else `_legacy_simple_alert(item)`, the
    pre-v81 body unchanged.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_paper_trade_decision.py`:

```python
"""v81: the one decision the order ticket's PLACE / DO NOT PLACE mirrors --
whether scan_run logs a paper trade for an item, and why not."""
from swingbot.core.scanning.analyze import ScanItem, paper_trade_decision
from swingbot.core.scanning.embeds import RequirementCheck


def _item(*passed):
    requirements = [RequirementCheck(key=f"k{i}", label=f"Gate {i}", passed=ok,
                                     detail=f"detail {i}")
                    for i, ok in enumerate(passed)]
    return ScanItem(result=None, plan=None, conf=None, requirements=requirements)


def test_a_clean_item_is_logged():
    assert paper_trade_decision(_item(True, True), already_open=False) == (True, None)


def test_no_requirements_counts_as_met():
    assert paper_trade_decision(_item(), already_open=False) == (True, None)


def test_already_open_is_the_reason_even_with_failed_gates():
    assert paper_trade_decision(_item(False), already_open=True) == (False, "already open")


def test_unmet_requirements_are_listed():
    assert paper_trade_decision(_item(True, False, False), already_open=False) == (
        False, "unmet: Gate 1: detail 1; Gate 2: detail 2")


def test_it_agrees_with_the_gate_it_replaced():
    for passed in [(), (True,), (False,), (True, False)]:
        for already_open in (False, True):
            item = _item(*passed)
            logged, _ = paper_trade_decision(item, already_open)
            assert logged == (item.all_requirements_met and not already_open)


def test_scan_items_default_to_not_logged():
    item = _item()
    assert (item.paper_logged, item.not_logged_reason) == (False, None)
```

Create `tests/scanning/test_execution_embeds.py`:

```python
"""v81: execution_embeds renders an Instruction through the shared kit."""
import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import tokens
from swingbot.core.presentation.instructions import Instruction
from swingbot.core.scanning import execution_embeds
from tests.scanning.test_embeds_v3 import make_item, make_plan_v2


@pytest.fixture(autouse=True)
def _unsized(monkeypatch):
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: None)


def _instruction(**kw):
    base = dict(verb="MOVE STOP", ticker="NVDA", direction="bullish",
                headline="MOVE STOP → 107.30 now",
                lines=("trail; +0.6R since the last ping",), plan_id="plan-123456789")
    base.update(kw)
    return Instruction(**base)


def test_render_puts_direction_ticker_and_verb_in_the_title():
    assert execution_embeds.render(_instruction()).title == "▲ LONG NVDA — MOVE STOP"
    assert execution_embeds.render(_instruction(direction="bearish")).title == \
        "▼ SHORT NVDA — MOVE STOP"


def test_render_orders_warnings_then_headline_then_lines():
    embed = execution_embeds.render(_instruction(warnings=("⚠ over portfolio heat cap",)))
    assert embed.description.splitlines() == [
        "⚠ over portfolio heat cap",
        "**MOVE STOP → 107.30 now**",
        "trail; +0.6R since the last ping",
    ]


@pytest.mark.parametrize("tone,level,expected", [
    ("level", 5, tokens.ACCENT_RAMP[5]),
    ("inert", None, tokens.ACCENT_BLOCKED),
    ("good", None, tokens.ACCENT_RAMP[5]),
    ("bad", None, tokens.ACCENT_RAMP[1]),
    ("neutral", None, tokens.ACCENT_RAMP[3]),
])
def test_render_maps_each_tone_to_a_shared_accent(tone, level, expected):
    assert execution_embeds.render(_instruction(tone=tone, level=level)).color.value == expected


def test_render_applies_the_shared_chrome():
    embed = execution_embeds.render(_instruction())
    assert "plan plan-123" in embed.footer.text
    assert embed.timestamp is not None


def test_build_ticket_embed_carries_the_blocks_and_the_scan_decision():
    item = make_item(plan_v2=make_plan_v2(entry_type="stop_entry", trigger_price=101.0))
    item.paper_logged = True
    item.heat_blocked = {"allowed": False, "open_heat": 6.2, "cap": 6.0}
    embed = execution_embeds.build_ticket_embed(item, item.plan_v2)
    assert embed.title == "▲ LONG NVDA — PLACE"
    assert embed.description.startswith("⚠ over portfolio heat cap")
    assert "**BUY STOP 101.00 · size n/a**" in embed.description
    assert embed.color.value == tokens.ACCENT_RAMP[item.conf.level]


def test_build_instruction_embed_renders_a_plan_event():
    plan = make_plan_v2(entry_type="stop_entry")
    embed = execution_embeds.build_instruction_embed(
        plan, PlanEvent(plan.plan_id, "cancelled_expired", {"bars_waited": 6}))
    assert embed.title == "▲ LONG NVDA — CANCEL"
    assert "**CANCEL BUY STOP 100.00**" in embed.description
```

In `tests/scanning/test_simple_alerts.py`, add to the imports:

```python
from swingbot.core.scanning import execution_embeds
```

and, directly after the imports block, add:

```python
@pytest.fixture
def unsized(monkeypatch):
    """Ticket tests must not read the real data/account.json."""
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: None)
```

Replace `test_simple_alert_shows_trail_when_v2_plan_has_no_hard_tp2` (the whole
function) with:

```python
def test_a_v2_ticket_shows_the_trail_when_there_is_no_hard_tp2(monkeypatch, unsized):
    """v81: a v2 scale-out runner is managed to a trailing stop, and the order
    ticket says so on its RUNNER line."""
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2())
    item.plan_v2.tp2 = None
    item.paper_logged = True
    assert "RUNNER 50% → trail 2×ATR" in build_simple_alert(item).description
```

Replace `test_simple_alert_carries_no_chart_or_image_reference` (the whole
function) with:

```python
def test_simple_alert_carries_no_chart_or_image_reference(monkeypatch, unsized):
    """The whole point of the simple channel: no render, no attachment."""
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    embed = build_simple_alert(make_item(plan_v2=make_plan_v2()))
    assert "attachment://" not in embed.description
    assert ".png" not in embed.description
    assert embed.image.url is None
```

Replace the parametrize decorator above
`test_simple_alert_prices_follow_the_same_cutover_as_the_full_embed`:

```python
@pytest.mark.parametrize("flag,expected_entry,expected_tp1,expected_tp2", [
    ("off", "100.00", "110.00", "115.00"),   # legacy scenario numbers
    ("on", "100.00", "110.00", "120.00"),    # v2 plan numbers (tp2=120.0)
])
```

with:

```python
@pytest.mark.parametrize("flag,expected_entry,expected_tp1,expected_tp2", [
    ("off", "100.00", "110.00", "115.00"),   # legacy scenario numbers
    # "on" is the v81 order ticket: test_the_v2_ticket_quotes_the_plans_own_levels
])
```

Directly after that function's last line
(`    assert f"TP2 **{expected_tp2}**" in embed.description`), add:

```python
def test_the_v2_ticket_quotes_the_plans_own_levels(monkeypatch, unsized):
    """With PLAN_ENGINE_V2 on, the ticket and the plan manager read one plan:
    its stop, TP1 and TP2 -- never the legacy scenario's."""
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2())
    item.paper_logged = True
    text = build_simple_alert(item).description
    assert "**BUY AT MARKET ~100.00 · size n/a**" in text
    assert "SELL STOP 95.00" in text
    assert "TP1 SELL LIMIT 110.00 · 50%" in text
    assert "TP2 120.00" in text
    assert "115.00" not in text                      # the legacy scenario's target2


def test_shadow_mode_keeps_the_legacy_mirror(monkeypatch, unsized):
    """Shadow mode never persists the plan, so nothing would ever ping about
    it: no ticket, the pre-v81 mirror."""
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    embed = build_simple_alert(make_item(plan_v2=make_plan_v2()))
    assert "Entry **100.00**" in embed.description


def test_an_unlogged_v2_alert_says_do_not_place(monkeypatch, unsized):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2())
    item.not_logged_reason = "already open"
    embed = build_simple_alert(item)
    assert embed.title.endswith("— DO NOT PLACE")
    assert "**DO NOT PLACE — already open**" in embed.description
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_paper_trade_decision.py`
Expected: FAIL — `ImportError: cannot import name 'paper_trade_decision'`.

Run: `python scripts/dev/testrun.py file tests/scanning/test_execution_embeds.py`
Expected: FAIL — `ImportError: cannot import name 'execution_embeds'`.

- [ ] **Step 3: Add the scan decision**

In `swingbot/core/scanning/analyze.py`, add the last two fields of `ScanItem`,
directly after `intraday: bool | None = None ...`:

```python
    # v81: whether scan_run logged a paper trade for this item -- the order
    # ticket's PLACE / DO NOT PLACE -- and why not when it didn't.
    paper_logged: bool = False
    not_logged_reason: str | None = None
```

Directly after the `ScanItem` class (after its `all_requirements_met` property), add:

```python
def paper_trade_decision(item: "ScanItem", already_open: bool) -> tuple[bool, str | None]:
    """v81: whether scan_run logs a paper trade for this item, and why not.
    Exactly `item.all_requirements_met and not already_open`, plus the reason
    the order ticket prints when it says DO NOT PLACE."""
    if already_open:
        return False, "already open"
    unmet = [f"{r.label}: {r.detail}" for r in item.requirements if not r.passed]
    if unmet:
        return False, "unmet: " + "; ".join(unmet)
    return True, None
```

In `swingbot/core/scanning/scan_run.py`, add to its `from .` imports:

```python
from .analyze import paper_trade_decision
```

and replace the line:

```python
        if item.all_requirements_met and not already_open:
```

with:

```python
        # v81: the same decision the order ticket's PLACE / DO NOT PLACE mirrors.
        item.paper_logged, item.not_logged_reason = paper_trade_decision(item, already_open)
        if item.paper_logged:
```

- [ ] **Step 4: Write the renderer**

Create `swingbot/core/scanning/execution_embeds.py`:

```python
"""v81: the execution feed's only Discord-aware piece.

Everything a message SAYS is decided in core/presentation/instructions.py;
this module decides only how it looks, through the shared presentation kit.
It sets no colour of its own -- tests/presentation/test_no_adhoc_color.py
walks the AST, which is also why no function here carries a colour type
annotation.
"""
import discord

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.presentation.instructions import (Instruction, block_warnings,
                                                     instruction_for, ticket_for)

from .plan_table import _sizing_snapshot

_OUTCOME_FOR_TONE = {"good": "win", "bad": "loss", "neutral": "scratch"}


def _accent(instruction: Instruction):
    if instruction.tone == "level":
        return ui.accent_for_level(instruction.level)
    if instruction.tone == "inert":
        return ui.accent_blocked()
    return ui.accent_for_outcome(_OUTCOME_FOR_TONE.get(instruction.tone, "scratch"))


def render(instruction: Instruction) -> discord.Embed:
    """Title: direction, ticker, verb. Description: warnings, the bold
    headline, then the order lines, one per line."""
    side = "LONG" if instruction.direction == "bullish" else "SHORT"
    embed = discord.Embed(title=f"{ui.direction_glyph(instruction.direction)} {side} "
                                f"{instruction.ticker} — {instruction.verb}")
    embed.description = "\n".join([*instruction.warnings, f"**{instruction.headline}**",
                                   *instruction.lines])
    ui.apply_chrome(embed, accent=_accent(instruction), plan_id=instruction.plan_id)
    return embed


def _entry(plan) -> float:
    return plan.entry_price if plan.entry_price is not None else plan.trigger_price


def build_ticket_embed(item, plan) -> discord.Embed:
    """The order ticket for a scan item carrying a live v2 plan."""
    return render(ticket_for(
        plan,
        logged=item.paper_logged,
        not_logged_reason=item.not_logged_reason,
        sizing=_sizing_snapshot(_entry(plan), plan),
        currency=config.CURRENCY_SYMBOL,
        warnings=block_warnings(heat=getattr(item, "heat_blocked", None),
                                cluster=getattr(item, "cluster_blocked", None),
                                kill=getattr(item, "kill_switch_blocked", None)),
        level=item.conf.level,
    ))


def build_instruction_embed(plan, event) -> discord.Embed:
    """The execution-feed message for one plan_manager PlanEvent."""
    return render(instruction_for(plan, event, sizing=_sizing_snapshot(_entry(plan), plan)))
```

- [ ] **Step 5: Route `build_simple_alert`**

In `swingbot/core/scanning/alert_embeds.py`, after
`from .plan_table import (_v2_plan, plan_numbers_for_display, leg_rows)`, add:

```python
from .execution_embeds import build_ticket_embed
```

Rename `def build_simple_alert(item) -> discord.Embed:` to
`def _legacy_simple_alert(item) -> discord.Embed:` — its docstring and body stay
exactly as they are — and insert directly above it:

```python
def build_simple_alert(item) -> discord.Embed:
    """The DISCORD_CHANNEL_TRADES_SIMPLE_ID message for a new alert.

    v81: that channel is the execution feed. An item carrying a v2 plan under
    PLAN_ENGINE_V2 "on" -- the only mode that persists the plan the manager
    then pings about -- gets its order ticket. Anything else keeps the pre-v81
    chartless mirror, _legacy_simple_alert, unchanged."""
    plan_v2 = _v2_plan(item)
    if plan_v2 is not None and config.PLAN_ENGINE_V2 == "on":
        return build_ticket_embed(item, plan_v2)
    return _legacy_simple_alert(item)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run each; expected PASS for all:

```
python scripts/dev/testrun.py file tests/scanning/test_paper_trade_decision.py
python scripts/dev/testrun.py file tests/scanning/test_execution_embeds.py
python scripts/dev/testrun.py file tests/scanning/test_simple_alerts.py
python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py
python scripts/dev/testrun.py file tests/presentation/test_no_adhoc_color.py
```

`test_engine_v2_plans.py` drives the real `_sync_run_scan`, so it proves the
`scan_run` edit keeps the paper-trade gate on both branches.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/scanning/execution_embeds.py swingbot/core/scanning/alert_embeds.py swingbot/core/scanning/analyze.py swingbot/core/scanning/scan_run.py tests/scanning/test_paper_trade_decision.py tests/scanning/test_execution_embeds.py tests/scanning/test_simple_alerts.py
git commit -m "feat(v81): order ticket on the simple-alerts channel"
```

---

### Task F6: Execution-feed routing and `trade_monitor` acknowledgement

**Files:**
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` — `import time`; replace
  `notify_plan_events` (lines 342-363) and add three helpers above it
- Modify: `swingbot/commands/scanning/loops.py` — `trade_monitor` (lines
  531-533 and 572-584) and two helpers above `@tasks.loop(seconds=60)`
- Create: `tests/scanning/test_execution_feed_routing.py`
- Modify: `tests/test_trade_monitor_task.py`

**Interfaces:**
- Consumes: `plan_manager.Delivery`, `STOP_EVENTS`, `NOTICE_EVENTS`,
  `ack_notified`, `run_notice_sweep` (F3, F4); `execution_embeds.build_instruction_embed` (F5);
  existing `silent_channel.silence`, `build_plan_event_embed`.
- Produces: `notify_plan_events(bot, events) -> list[Delivery]` — posts each
  stop or notice event to `DISCORD_CHANNEL_TRADES_SIMPLE_ID` (notifying) and a
  silent copy to `DISCORD_CHANNEL_TRADES_HISTORY_ID`; if the feed is unset or
  raises, the history copy notifies instead; any other transition keeps the
  pre-v81 embed, history only, not delivered. Fills no longer post to
  `DISCORD_CHANNEL_TRADES_ID`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_execution_feed_routing.py`:

```python
"""v81: notify_plan_events routes every instruction to the execution feed,
which pings, with a silent copy in trades-history -- and reports what it
delivered so plan_manager stops re-sending it.

No pytest-asyncio in this repo -- coroutines run under asyncio.run()."""
import asyncio
import types

import pytest

from swingbot import config
from swingbot.core.planning.plan_manager import Delivery, PlanEvent
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.scanning import execution_embeds, lifecycle_embeds
from swingbot.core.scanning.lifecycle_embeds import notify_plan_events
from tests.planning.test_plan_engine_model import _plan


class FakeChannel:
    def __init__(self):
        self.sent = []
        self.fail = False

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord is having a day")
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=1)


@pytest.fixture
def wired(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: None)
    monkeypatch.setattr(lifecycle_embeds, "_last_warned", {})
    channels = {"111": FakeChannel(), "222": FakeChannel(), "333": FakeChannel()}
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "111")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "222")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "333")
    bot = types.SimpleNamespace(get_channel=lambda channel_id: channels.get(str(channel_id)))
    PlanStore().add(_plan(status="ACTIVE", entry_price=100.0, stop_loss=95.0,
                          tp1=110.0, working_stop=100.0))
    return bot, channels["111"], channels["222"], channels["333"]


def _post(bot, *events):
    return asyncio.run(notify_plan_events(bot, list(events)))


BE = PlanEvent("p1", "be_moved", {"working_stop": 100.0})


def test_the_feed_pings_and_history_gets_a_silent_copy(wired):
    bot, feed, history, _ = wired
    deliveries = _post(bot, BE)
    assert "silent" not in feed.sent[0]
    assert history.sent[0]["silent"] is True
    assert feed.sent[0]["embed"].title == history.sent[0]["embed"].title
    assert deliveries == [Delivery("p1", "stop", 100.0)]


def test_an_unset_feed_hands_the_ping_to_history(wired, monkeypatch):
    bot, feed, history, _ = wired
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "")
    deliveries = _post(bot, BE)
    assert feed.sent == []
    assert "silent" not in history.sent[0]
    assert deliveries == [Delivery("p1", "stop", 100.0)]


def test_a_failing_feed_hands_the_ping_to_history(wired):
    bot, feed, history, _ = wired
    feed.fail = True
    deliveries = _post(bot, BE)
    assert "silent" not in history.sent[0]
    assert deliveries == [Delivery("p1", "stop", 100.0)]


def test_an_event_that_reached_no_channel_is_not_delivered(wired):
    bot, feed, history, _ = wired
    feed.fail = history.fail = True
    assert _post(bot, BE) == []


def test_one_broken_event_does_not_drop_the_rest(wired):
    bot, feed, _, _ = wired
    broken = PlanEvent("p1", "stop_moved", {})         # no detail keys: raises while rendering
    assert _post(bot, broken, BE) == [Delivery("p1", "stop", 100.0)]
    assert len(feed.sent) == 1


def test_fills_no_longer_reach_the_alerts_channel(wired):
    bot, feed, _, trades = wired
    deliveries = _post(bot, PlanEvent("p1", "filled", {"entry_price": 100.0}))
    assert trades.sent == []
    assert feed.sent[0]["embed"].title.endswith("— FILLED")
    assert deliveries == [Delivery("p1", "notice", "filled")]


def test_a_stop_moved_delivery_records_the_new_stop(wired):
    bot, _, _, _ = wired
    event = PlanEvent("p1", "stop_moved", {"old": 95.0, "new": 100.0, "r_moved": 1.0,
                                           "effective": "now"})
    assert _post(bot, event) == [Delivery("p1", "stop", 100.0)]


def test_a_close_delivery_names_the_notice(wired):
    bot, _, _, _ = wired
    event = PlanEvent("p1", "closed", {"reason": "loss", "exit_price": 94.5,
                                       "session": "regular", "notified_stop": 95.0,
                                       "bot_stop": 95.0})
    assert _post(bot, event) == [Delivery("p1", "notice", "closed")]


def test_pyramid_add_keeps_its_old_embed_in_history_only(wired):
    bot, feed, history, _ = wired
    assert _post(bot, PlanEvent("p1", "pyramid_add", {})) == []
    assert feed.sent == []
    assert len(history.sent) == 1
```

In `tests/test_trade_monitor_task.py`, replace
`test_trade_monitor_skips_cleanly_when_there_are_no_open_trades` (the whole
function) with:

```python
def test_trade_monitor_skips_pricing_but_still_sweeps_notices_with_no_open_trades(monkeypatch):
    """No open trade costs no price work -- but v81: that is exactly the state
    right after the last position closes, whose EXIT may still be undelivered,
    so the notice sweep still runs."""
    monkeypatch.setattr(scan_engine, "is_scan_running", lambda: False)
    monkeypatch.setattr(loops.trade_log, "get_trades",
                        lambda status=None, limit=None: [])

    calls = {"tick": 0, "sweep": 0}
    monkeypatch.setattr("swingbot.core.planning.plan_manager.run_manager_tick",
                        lambda: calls.__setitem__("tick", calls["tick"] + 1) or [])
    monkeypatch.setattr("swingbot.core.planning.plan_manager.run_notice_sweep",
                        lambda: calls.__setitem__("sweep", calls["sweep"] + 1) or [])

    _run(scanning_mod.trade_monitor.coro())

    assert calls["tick"] == 0
    assert calls["sweep"] == 1


def test_trade_monitor_acknowledges_what_the_feed_delivered(monkeypatch):
    from swingbot.core.planning.plan_manager import Delivery

    monkeypatch.setattr(scan_engine, "is_scan_running", lambda: False)
    monkeypatch.setattr(loops.trade_log, "get_trades",
                        lambda status=None, limit=None: [{"ticker": "AAPL", "id": "t1",
                                                          "status": "open"}])
    monkeypatch.setattr(loops, "get_current_price", lambda t: 100.0)
    monkeypatch.setattr(loops.trade_log, "close_if_live_price_hit", lambda ticker, live: [])
    monkeypatch.setattr(loops.trade_log, "check_near_tp_timeout", lambda ticker, live: [])
    event = PlanEvent("p1", "be_moved", {"working_stop": 100.0})
    monkeypatch.setattr("swingbot.core.planning.plan_manager.run_manager_tick", lambda: [event])

    delivered = [Delivery("p1", "stop", 100.0)]

    async def fake_notify(bot, events):
        assert events == [event]
        return delivered

    acked = []
    monkeypatch.setattr("swingbot.core.scanning.embeds.notify_plan_events", fake_notify)
    monkeypatch.setattr("swingbot.core.planning.plan_manager.ack_notified", acked.append)

    _run(scanning_mod.trade_monitor.coro())

    assert acked == [delivered]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_execution_feed_routing.py`
Expected: FAIL — `AttributeError: ... has no attribute '_last_warned'`.

Run: `python scripts/dev/testrun.py file tests/test_trade_monitor_task.py`
Expected: FAIL — the sweep count is 0 and nothing is acknowledged.

- [ ] **Step 3: Rewrite `notify_plan_events`**

In `swingbot/core/scanning/lifecycle_embeds.py`, add `import time` after
`import os`. Replace the whole `async def notify_plan_events(bot, events):`
function with:

```python
_WARN_EVERY_SECONDS = 15 * 60
_last_warned: dict[str, float] = {}


def _warn_throttled(plan_id: str, message: str, *args) -> None:
    """At most one warning per plan per 15 minutes: an undelivered instruction
    is re-sent every 60s tick, so an outage would otherwise flood the log."""
    now = time.monotonic()
    if now - _last_warned.get(plan_id, float("-inf")) < _WARN_EVERY_SECONDS:
        return
    _last_warned[plan_id] = now
    log.warning(message, *args)


def _resolve_channel(bot, channel_id):
    if not channel_id:
        return None
    try:
        return bot.get_channel(int(channel_id))
    except (TypeError, ValueError):
        return None


def _delivery(plan, event):
    from swingbot.core.planning.plan_manager import Delivery
    if event.transition == "stop_moved":
        return Delivery(plan.plan_id, "stop", event.detail["new"])
    if event.transition in ("be_moved", "tp1_partial"):
        return Delivery(plan.plan_id, "stop", event.detail["working_stop"])
    return Delivery(plan.plan_id, "notice", event.transition)


async def notify_plan_events(bot, events) -> list:
    """v81 execution feed. Each stop or notice event posts to the simple-alerts
    channel, which notifies, and a silent copy to trades-history. When the
    feed is unset or its send raises, the history copy keeps its notification
    instead -- the hand-back rule _send_alerts uses -- so every instruction
    pings once. Fills no longer post to DISCORD_CHANNEL_TRADES_ID.

    Any other transition (pyramid_add) keeps the pre-v81 status embed, history
    channel only, and is not delivered.

    Returns the Delivery list trade_monitor passes to
    plan_manager.ack_notified. An event that reached no notifying channel is
    left out, so the manager re-sends it next tick."""
    from swingbot.core.infra.silent_channel import silence
    from swingbot.core.planning.plan_manager import NOTICE_EVENTS, STOP_EVENTS
    from swingbot.core.planning.plan_store import PlanStore
    from .execution_embeds import build_instruction_embed

    store = PlanStore()
    feed = _resolve_channel(bot, config.DISCORD_CHANNEL_TRADES_SIMPLE_ID)
    history = _resolve_channel(bot, config.DISCORD_CHANNEL_TRADES_HISTORY_ID)
    deliveries = []
    for event in events:
        try:
            plan = store.get(event.plan_id)
            if plan is None:
                continue
            if event.transition not in STOP_EVENTS | NOTICE_EVENTS:
                if history is not None:
                    await history.send(embed=build_plan_event_embed(plan, event))
                continue
            embed = build_instruction_embed(plan, event)
            pinged = False
            if feed is not None:
                try:
                    await feed.send(embed=embed)
                    pinged = True
                except Exception as exc:
                    _warn_throttled(plan.plan_id, "execution feed: %s for plan %s failed on "
                                    "the feed channel (%s); history will notify instead",
                                    event.transition, plan.plan_id, exc)
            if history is not None:
                try:
                    await (silence(history) if pinged else history).send(embed=embed)
                    pinged = True
                except Exception as exc:
                    _warn_throttled(plan.plan_id, "execution feed: history copy of %s for "
                                    "plan %s failed: %s", event.transition, plan.plan_id, exc)
            if pinged:
                deliveries.append(_delivery(plan, event))
                log.info("execution feed: delivered %s for plan %s",
                         event.transition, plan.plan_id)
            else:
                _warn_throttled(plan.plan_id, "execution feed: %s for plan %s reached no "
                                "channel; it will be re-sent", event.transition, plan.plan_id)
        except Exception as exc:
            _warn_throttled(event.plan_id, "execution feed: could not post %s for plan %s: %s",
                            event.transition, event.plan_id, exc)
    return deliveries
```

- [ ] **Step 4: Wire `trade_monitor`**

In `swingbot/commands/scanning/loops.py`, directly above
`@tasks.loop(seconds=60)` / `async def trade_monitor():`, add:

```python
async def _post_plan_events(plan_events) -> None:
    """Post plan events to the execution feed, then record what was delivered
    (v81). A failed acknowledgement only means a duplicate next tick."""
    from swingbot.core.planning import plan_manager
    from swingbot.core.scanning.embeds import notify_plan_events
    try:
        deliveries = await notify_plan_events(bot, plan_events)
    except Exception as exc:
        log.warning("trade_monitor: failed to post plan events: %s", exc)
        return
    if not deliveries:
        return
    try:
        await asyncio.to_thread(plan_manager.ack_notified, deliveries)
    except Exception as exc:
        log.warning("trade_monitor: could not record feed deliveries "
                    "(they will be re-sent): %s", exc)


async def _resend_plan_notices() -> None:
    """v81: re-send undelivered notices when there is no open trade to tick for."""
    from swingbot.core.planning import plan_manager
    try:
        events = await asyncio.to_thread(plan_manager.run_notice_sweep)
    except Exception as exc:
        log.warning("trade_monitor: notice sweep failed: %s", exc)
        return
    if events:
        await _post_plan_events(events)
```

Inside `trade_monitor`, replace:

```python
    open_trades = trade_log.get_trades(status="open", limit=200)
    if not open_trades:
        return
```

with:

```python
    open_trades = trade_log.get_trades(status="open", limit=200)
    if not open_trades:
        # v81: nothing to price, but the EXIT of a position that just closed
        # may still be undelivered -- this is exactly when that happens.
        await _resend_plan_notices()
        return
```

and replace:

```python
    if plan_events:
        from swingbot.core.scanning.embeds import notify_plan_events
        try:
            await notify_plan_events(bot, plan_events)   # Task 72
        except Exception as exc:
            log.warning("trade_monitor: failed to post plan events: %s", exc)
```

with:

```python
    if plan_events:
        await _post_plan_events(plan_events)   # Task 72; v81 acknowledges deliveries
```

- [ ] **Step 5: Run the tests to verify they pass**

Run each; expected PASS for all:

```
python scripts/dev/testrun.py file tests/scanning/test_execution_feed_routing.py
python scripts/dev/testrun.py file tests/test_trade_monitor_task.py
python scripts/dev/testrun.py file tests/scanning/test_transition_embeds.py
python scripts/dev/testrun.py file tests/commands/test_scanning_package.py
```

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/lifecycle_embeds.py swingbot/commands/scanning/loops.py tests/scanning/test_execution_feed_routing.py tests/test_trade_monitor_task.py
git commit -m "feat(v81): route plan events to the execution feed and acknowledge deliveries"
```

---

### Task F7: Surface agreement, v67 note, preview script

**Files:**
- Modify: `tests/presentation/test_surface_agreement.py` (append one test)
- Modify: `docs/superpowers/plans/2026-08-29-v67-json-to-postgres_2b-trading-state-plans.md` (Task P2-07)
- Create: `scripts/dev/preview_execution_feed.py`

**Interfaces:**
- Consumes: `plan_manager.resting_stop`, `stop_move_event` (F3);
  `instructions.instruction_for`, `ticket_for`, `block_warnings` (F2).
- Produces: `python scripts/dev/preview_execution_feed.py` — prints every
  instruction for fixture plans; no Discord, no network, no data dir.

- [ ] **Step 1: Add the surface-agreement test**

Append to `tests/presentation/test_surface_agreement.py`:

```python
def test_execution_feed_stop_agrees(view):
    """v81: the execution feed is a fifth surface. Its stop for this legacy
    partial (no working_stop) is the runner floor, never the risk stop."""
    from swingbot.core.planning.plan_manager import resting_stop, stop_move_event
    from swingbot.core.presentation.instructions import instruction_for

    plan = Attr(PLAN)
    assert resting_stop(plan) == pytest.approx(view.stop)
    event = stop_move_event(plan, "2026-09-10", 0.25)
    assert event is not None
    headline = instruction_for(plan, event).headline
    assert f"{view.stop:.2f}" in headline and "90.00" not in headline
```

Run: `python scripts/dev/testrun.py file tests/presentation/test_surface_agreement.py`
Expected: PASS.

- [ ] **Step 2: Record the ledger in v67's P2-07**

In `docs/superpowers/plans/2026-08-29-v67-json-to-postgres_2b-trading-state-plans.md`,
replace the line:

```markdown
### Task P2-07: The plans repository and importer
```

with:

```markdown
### Task P2-07: The plans repository and importer

> **v81 (2026-09-10):** `TradePlanV2` gained `notified_stop` and
> `pending_notice`, the execution feed's delivery ledger. Both live inside
> `doc`; no column is added. The round-trip test below carries both, so an
> importer that drops keys it does not know fails it.
```

and in that task's `test_the_full_plan_dict_round_trips`, replace:

```python
    rec = _p("P1", legs=[{"fraction": 0.5, "r": 1.0}], take_profit=110.0,
             confidence={"level": 4, "score": 71})
```

with:

```python
    rec = _p("P1", legs=[{"fraction": 0.5, "r": 1.0}], take_profit=110.0,
             confidence={"level": 4, "score": 71},
             notified_stop=101.5,
             pending_notice={"transition": "closed",
                             "detail": {"reason": "loss", "exit_price": 94.5},
                             "at": "2026-09-10T15:00:00+00:00"})
```

- [ ] **Step 3: Write the preview script**

Create `scripts/dev/preview_execution_feed.py`:

```python
"""v81: print every execution-feed instruction for fixture plans, so the
wording can be read end to end before merge. No Discord, no network, no data
dir: sizing is a fixed snapshot and every plan is built in memory.

    python scripts/dev/preview_execution_feed.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from swingbot.core.planning.plan_manager import PlanEvent  # noqa: E402
from swingbot.core.planning.plan_types import TradePlanV2  # noqa: E402
from swingbot.core.presentation.instructions import (  # noqa: E402
    block_warnings, instruction_for, ticket_for)

SIZING = {"shares": 2439.02, "risk_amount": 10000.0}


def plan(**kw) -> TradePlanV2:
    base = dict(plan_id="preview1", ticker="AAPL", created_at="2026-09-10",
                source="strategy", strategy="RSI Pullback", horizon_key="1m",
                direction="bullish", entry_type="stop_entry", trigger_price=102.50,
                entry_price=None, expiry_bars=5, stop_loss=98.40, tp1=106.00,
                tp1_fraction=0.5, tp2=110.00, breakeven_trigger_fraction=0.5,
                trail_atr_mult=3.0, quality_score=70, quality_breakdown=[],
                badge="VALIDATED", badge_stats={}, status="PENDING")
    base.update(kw)
    return TradePlanV2(**base)


def show(title, instruction) -> None:
    print(f"=== {title}")
    print(f"[{instruction.verb}] {instruction.ticker} "
          f"({instruction.direction}, tone={instruction.tone})")
    for line in (*instruction.warnings, instruction.headline, *instruction.lines):
        print(f"  {line}")
    print()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    long_pending = plan()
    short_pending = plan(direction="bearish", trigger_price=97.50, stop_loss=101.60,
                         tp1=94.00, tp2=None)
    active = plan(status="ACTIVE", entry_price=102.61)
    partial = plan(status="PARTIAL", entry_price=102.61, working_stop=104.87,
                   legs_realized=[{"fraction": 0.5, "exit_price": 106.0, "r": 0.81,
                                   "reason": "tp1"}])
    trail_closed = plan(status="CLOSED", entry_price=102.61, working_stop=107.30,
                        legs_realized=[{"fraction": 0.5, "exit_price": 106.0, "r": 0.81,
                                        "reason": "tp1"},
                                       {"fraction": 0.5, "exit_price": 107.30, "r": 1.11,
                                        "reason": "tp1_runner_trail"}])

    show("ticket: long stop entry", ticket_for(
        long_pending, logged=True, not_logged_reason=None, sizing=SIZING,
        currency="$", level=5))
    show("ticket: short stop entry, unsized", ticket_for(
        short_pending, logged=True, not_logged_reason=None, sizing=None, level=4))
    show("ticket: market entry", ticket_for(
        plan(entry_type="market"), logged=True, not_logged_reason=None,
        sizing=SIZING, currency="$", level=4))
    show("ticket: over heat cap, kill switch on", ticket_for(
        long_pending, logged=True, not_logged_reason=None, sizing=SIZING,
        currency="$", level=5,
        warnings=block_warnings(heat={"open_heat": 6.2, "cap": 6.0}, cluster=None,
                                kill={"reason": "3 consecutive losses"})))
    show("ticket: not logged", ticket_for(
        long_pending, logged=False, not_logged_reason="already open", sizing=SIZING))

    events = [
        ("filled", active,
         PlanEvent("preview1", "filled", {"entry_price": 102.61})),
        ("break-even armed today", active,
         PlanEvent("preview1", "be_moved", {"working_stop": 102.61})),
        ("TP1 banked", partial,
         PlanEvent("preview1", "tp1_partial", {"fraction": 0.5, "exit_price": 106.0,
                                               "r": 0.81, "working_stop": 104.87})),
        ("trail moved", partial,
         PlanEvent("preview1", "stop_moved", {"old": 104.87, "new": 107.30,
                                              "r_moved": 0.58, "effective": "now"})),
        ("expired", long_pending,
         PlanEvent("preview1", "cancelled_expired", {"bars_waited": 6})),
        ("invalidated, short", short_pending,
         PlanEvent("preview1", "cancelled_invalidated", {"live_price": 101.70})),
        ("trail exit while the reader's stop lagged", trail_closed,
         PlanEvent("preview1", "closed", {"reason": "tp1_runner_trail", "exit_price": 107.30,
                                          "session": "regular", "notified_stop": 106.90,
                                          "bot_stop": 107.30})),
        ("stopped out after hours", plan(status="CLOSED", entry_price=102.61),
         PlanEvent("preview1", "closed", {"reason": "loss", "exit_price": 97.80,
                                          "session": "extended", "notified_stop": 98.40,
                                          "bot_stop": 98.40})),
    ]
    for title, event_plan, event in events:
        show(title, instruction_for(event_plan, event, sizing=SIZING))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the preview and hand it to the human partner**

Run: `python scripts/dev/preview_execution_feed.py`
Expected: 13 `===` blocks, beginning:

```
=== ticket: long stop entry
[PLACE] AAPL (bullish, tone=level)
  BUY STOP 102.50 · 2,439 sh (risk $10,000)
  SELL STOP 98.40
  TP1 SELL LIMIT 106.00 · 1,219 sh (50%)
```

Paste the complete output to the human partner and **wait for them to read it**
(spec, "Verification"). A wording change they ask for goes into
`instructions.py` and its test before F8; re-run this script after it.

- [ ] **Step 5: Commit**

```bash
git add tests/presentation/test_surface_agreement.py docs/superpowers/plans/2026-08-29-v67-json-to-postgres_2b-trading-state-plans.md scripts/dev/preview_execution_feed.py
git commit -m "test(v81): feed stop agrees with plan_view; v67 ledger note; preview script"
```

---

### Task F8: Full-suite verification, release, close-out

**Files:**
- Modify: `VERSION.json`, `swingbot/admin/version_history.json`
- Move: the four `2026-09-10-v81-execution-feed_*.md` plan files and the spec into `implemented/`

- [ ] **Step 1: Confirm exits were not touched**

Run: `git diff --stat main -- swingbot/core/planning/lifecycle.py swingbot/core/planning/exit_sim.py`
Expected: no output.

- [ ] **Step 2: Run the full suite once**

Dispatch the `test-runner` subagent (or run `python scripts/dev/testrun.py full`)
over the whole branch. Expect `0 failed`, `0 xfailed`. **If not green, fix
forward from the failures it names** — they are this plan's regressions, and
this task is not done until the run is green.

- [ ] **Step 3: Merge**

Use `superpowers:finishing-a-development-branch` to merge
`2026-09-10-v81-execution-feed` into `main`. Do not run the suite again after a
conflict-free merge; a merge that resolved conflicts gets one full run.

- [ ] **Step 4: Release**

On `main`:

1. Read `VERSION.json` — not a header, not memory.
2. `bot`: minor bump (`A.B.C` → `A.(B+1).0`). `ui`: patch bump (`X.Y.Z` → `X.Y.(Z+1)`).
3. Set `bot_updated` and `ui_updated` to now, format `YYYY-MM-DD HH-MM-SS`.
4. Run: `python scripts/dev/build_version_matrix.py`

```bash
git add VERSION.json swingbot/admin/version_history.json
git commit -m "chore(v81): bump bot minor and ui patch, regenerate version history"
```

- [ ] **Step 5: Deploy, then check the first live pings**

Deploy only with the human partner's go-ahead, per `docs/deploy/DEPLOY_HETZNER.md`.
After deploy, during the next regular session:

Run: `bash scripts/ops/ssh-hetzner.sh "grep -h 'execution feed' /opt/swing-bot/logs/*.log | tail -40"`

Expected: one `delivered stop_moved` per open plan whose resting stop already
differed from its stop by the threshold (the deploy catch-up), then quiet
until a stop moves. Compare the count against the admin Plans page's PARTIAL
plans plus ACTIVE plans with a moved stop, and one delivered stop against that
plan's working stop there. Any `reached no channel` line means a channel ID is
wrong — fix `.env` on production and mirror it back into the repo.

- [ ] **Step 6: Close out**

```bash
git mv docs/superpowers/plans/2026-09-10-v81-execution-feed_0-index.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-10-v81-execution-feed_1-foundation.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-10-v81-execution-feed_2-manager.md docs/superpowers/plans/implemented/
git mv docs/superpowers/plans/2026-09-10-v81-execution-feed_3-feed.md docs/superpowers/plans/implemented/
git mv docs/superpowers/specs/2026-09-10-v81-execution-feed-design.md docs/superpowers/specs/implemented/
git grep -n "2026-09-10-v81-execution-feed" -- docs swingbot tests scripts .claude
```

Re-point every path the `git grep` prints at the `implemented/` location. Tick
the index's Progress block, adding one line per task that was cut or deferred,
then stage the moves plus exactly the files you re-pointed — never a whole
tree, which would sweep in unrelated work:

```bash
git add docs/superpowers/plans/implemented docs/superpowers/specs/implemented
git add <each file the git grep above listed>
git commit -m "docs(v81): close out the execution feed plan"
```
