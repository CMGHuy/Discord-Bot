# v110 — Part 2: pushed builders

Header, goal, global constraints, resolved spec gaps, parallelisation and conventions live in [`_0-index`](2026-09-28-v110-discord-notification-identity_0-index.md). Every task below implicitly includes its Global Constraints. Phase A (V110-1..V110-3) is in [`_1-registry`](2026-09-28-v110-discord-notification-identity_1-registry.md).

# Phase B — Pushed builders

### Task V110-4: Full alert, legacy simple mirror, strategy signal and its new simple mirror

Load the `alert-surface` skill first. Fields still go through the `sections[...]` accumulator. This task changes only the title, stripe, footer, headline and one intraday glyph.

**Files:**
- Modify: `swingbot/core/scanning/alert_embeds.py`:
  - `build_strategy_alert_embed`
  - `build_embed`
  - `_legacy_simple_alert`
  - new `strategy_plan_line`, `_strategy_levels`, `build_strategy_simple_embed` and `_alert_detail`
- Test: `tests/scanning/test_strategy_embeds.py` (new), `tests/scanning/test_embeds_v3.py`, `tests/scanning/test_simple_alerts.py`, `tests/test_stats_commands.py`

**Interfaces:**
- Consumes:
  - V110-1: `Kind.SETUP_ALERT`, `STRATEGY_SIGNAL` and `SETUP_SIMPLE`, plus `kinds.side_word`, `kinds.plan_badge_text`, `kinds.SETUP_RAMP` and `kinds.SETUP_BLOCKED`.
  - V110-2: `ui.levels_block`.
  - V110-3: `ui.push_embed` and `ui.apply_chrome(kind=…)`.
- Produces:
  - `alert_embeds.strategy_plan_line(plan) -> str`, consumed by V110-6.
  - `alert_embeds.build_strategy_simple_embed(plan) -> PushEmbed`, consumed by V110-8.
  - `build_embed` / `build_simple_alert` / `build_strategy_alert_embed` now return `PushEmbed`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_strategy_embeds.py`:

```python
"""v110: the strategy signal and its simple-channel mirror are NEW SETUP embeds."""
from types import SimpleNamespace

import discord

from swingbot.core.presentation import ansi, kinds, tokens
from swingbot.core.scanning.alert_embeds import (build_strategy_alert_embed,
                                                 build_strategy_simple_embed,
                                                 strategy_plan_line)


def _plan(**kw):
    base = dict(plan_id="0123456789ab", ticker="AAPL", strategy="Fibonacci",
                direction="bullish", horizon_key="4w", trigger_price=100.0, stop_loss=94.0,
                tp1=110.0, tp2=None, badge="WEAK", ledger="weak", confidence_level=4)
    base.update(kw)
    return SimpleNamespace(**base)


def test_strategy_signal_title_push_line_stripe_and_footer():
    embed = build_strategy_alert_embed(_plan())
    assert embed.title == "🆕 ▲ LONG AAPL · STRATEGY · Fibonacci"
    assert embed.push_text == "🆕 NEW SETUP · ▲ LONG AAPL · STRATEGY · Fibonacci"
    assert embed.color.value == kinds.SETUP_RAMP[4]
    assert embed.footer.text == f"{tokens.DISCLAIMER} · plan 01234567"


def test_strategy_signal_leads_with_the_levels_block():
    embed = build_strategy_alert_embed(_plan())
    assert embed.description.startswith("```ansi\n")
    plain = ansi._ESCAPE_RE.sub("", embed.description)
    assert "entry 100.00" in plain and "stop  94.00" in plain and "TP1   110.00" in plain


def test_strategy_plan_line_names_the_side_and_has_no_check_mark():
    line = strategy_plan_line(_plan(badge="VALIDATED"))
    assert line == "Fibonacci · 4w · LONG · VALIDATED"
    assert "bullish" not in line and "✅" not in line
    assert strategy_plan_line(_plan()).endswith("⚠️ WEAK")


def test_strategy_simple_mirror_is_an_embed_with_the_same_identity():
    embed = build_strategy_simple_embed(_plan())
    assert isinstance(embed, discord.Embed)
    assert embed.title == build_strategy_alert_embed(_plan()).title
    assert embed.push_text.startswith("🆕 NEW SETUP · ▲ LONG AAPL")
    assert embed.description.startswith("```ansi\n")
    assert "ledger weak" in embed.description
    assert not embed.fields


def test_a_plan_without_a_confidence_level_takes_the_bottom_of_the_ramp():
    plan = _plan()
    del plan.confidence_level
    assert build_strategy_alert_embed(plan).color.value == kinds.SETUP_RAMP[1]
```

In `tests/scanning/test_embeds_v3.py`, add `from swingbot.core.presentation import kinds, tokens` to the imports. Then make these changes:
- In `test_a_blocked_alert_takes_the_inert_accent_not_red`, change the assert to `assert _build(make_item(all_ok=False)).color.value == kinds.SETUP_BLOCKED` and delete the function-local `from swingbot.core.presentation import tokens` import.
- In `test_weak_plan_v2_uses_its_confidence_level_colour` and `test_validated_plan_uses_the_confidence_level_colour_without_badge`, replace `0x9ACD32` with `kinds.SETUP_RAMP[4]`.
- In `test_no_v2_plan_falls_back_to_the_shared_confidence_accent_and_plain_title`, replace `ui.accent_for_level(item.conf.level).value` with `kinds.SETUP_RAMP[item.conf.level]`.

Then append:

```python
def test_full_alert_title_push_line_and_footer_come_from_the_registry(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    embed = _build(make_item(plan_v2=make_plan_v2(plan_id="12345678-abcd")))
    assert embed.title == "🆕 ▲ LONG NVDA · ALERT · Lv4 ⭐"
    assert embed.push_text == "🆕 NEW SETUP · ▲ LONG NVDA · ALERT · Lv4 ⭐"
    assert embed.color.value == kinds.SETUP_RAMP[4]
    assert embed.footer.text == f"{tokens.DISCLAIMER} · plan 12345678"


def test_a_blocked_alert_says_review_instead_of_the_star():
    assert _build(make_item(all_ok=False)).title == "🆕 ▲ LONG NVDA · ALERT · Lv4 ⚠️ review"


def test_full_alert_never_uses_the_retired_circles():
    for trend in ("bullish", "bearish"):
        item = make_item()
        item.result.trend = trend
        title = _build(item).title
        assert "🟢" not in title and "🔴" not in title


def test_a_short_alert_leads_with_the_red_side_line():
    item = make_item()
    item.result.trend = "bearish"
    embed = _build(item)
    assert embed.title.startswith("🆕 ▼ SHORT NVDA")
    assert ansi.paint("▼ SHORT", "red") in embed.description


def test_intraday_confirmation_uses_a_plain_check_not_the_outcome_mark():
    item = make_item()
    item.intraday = True
    field = next(f for f in _build(item).fields if f.name == "⏱ Intraday timing")
    assert field.value.startswith("✔ confirms") and "✅" not in field.value
```

In `tests/scanning/test_simple_alerts.py`, add `from swingbot.core.presentation import kinds` to the imports. Replace `tokens.ACCENT_RAMP[item.conf.level]` (in the bearish test) and `tokens.ACCENT_RAMP[make_item().conf.level]` (in the bullish test) with `kinds.SETUP_RAMP[item.conf.level]` and `kinds.SETUP_RAMP[make_item().conf.level]`. Then append, before the `# _send_alerts mirroring` banner:

```python
def test_legacy_simple_mirror_is_a_new_setup_push(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "off")
    embed = build_simple_alert(make_item())
    assert embed.title == "🆕 ▲ LONG NVDA · SIMPLE · Lv4"
    assert embed.push_text == "🆕 NEW SETUP · ▲ LONG NVDA · SIMPLE · Lv4"
    assert embed.footer.text == tokens.DISCLAIMER
```

In `tests/test_stats_commands.py` (`test_fake_item_from_plan_builds_embed_without_crashing_and_uses_the_shared_accent`), replace:

```python
    assert embed.title.startswith("🟢 LONG")
    assert embed.color.value == ui.accent_for_level(item.conf.level).value
```

with:

```python
    assert embed.title.startswith("🆕 ▲ LONG NVDA")
    assert embed.color.value == kinds.SETUP_RAMP[item.conf.level]
```

Add `from swingbot.core.presentation import kinds` to that file's imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_strategy_embeds.py tests/scanning/test_embeds_v3.py tests/scanning/test_simple_alerts.py tests/test_stats_commands.py`
Expected: FAIL. `strategy_plan_line` / `build_strategy_simple_embed` fail to import, and the titles and colours are the old ones.

- [ ] **Step 3: Write the implementation**

In `swingbot/core/scanning/alert_embeds.py`, add below `from swingbot.core import presentation as ui`:

```python
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind
```

Replace the whole `build_strategy_alert_embed` function with:

```python
def strategy_plan_line(plan) -> str:
    """``Fibonacci · 4w · LONG · VALIDATED`` -- a v2 plan in one line, no raw
    ``bullish`` and no ✅ (outcome-only glyph)."""
    return (f"{plan.strategy} · {plan.horizon_key} · {kinds.side_word(plan.direction)} · "
            f"{kinds.plan_badge_text(plan.badge)}")


def _strategy_levels(plan) -> str:
    return ui.levels_block(direction=plan.direction, entry=plan.trigger_price,
                           stop=plan.stop_loss, tp1=plan.tp1, tp2=plan.tp2)


def build_strategy_alert_embed(plan) -> "discord.Embed":
    """Render a strategy-sourced plan with its frozen badge and ledger."""
    embed = ui.push_embed(Kind.STRATEGY_SIGNAL, plan.ticker, plan.direction, plan.strategy,
                          description=_strategy_levels(plan))
    ui.apply_chrome(embed, kind=Kind.STRATEGY_SIGNAL,
                    level=getattr(plan, "confidence_level", None), plan_id=plan.plan_id)
    embed.add_field(name="Plan (v2)", value=strategy_plan_line(plan), inline=False)
    for name, value in (("Entry", plan.trigger_price), ("Stop", plan.stop_loss), ("TP1", plan.tp1)):
        embed.add_field(name=name, value=f"{value:.2f}")
    if plan.tp2 is not None:
        embed.add_field(name="TP2", value=f"{plan.tp2:.2f}")
    embed.add_field(name="Ledger", value=("main" if plan.ledger == "main" else
                    "weak — P&L tracked separately, never summed into main"), inline=False)
    return embed


def build_strategy_simple_embed(plan) -> "discord.Embed":
    """The simple-channel mirror of a strategy signal (v110 §6.1): the same
    identity as the full embed, with the levels block and one context line,
    and no fields, so it reads on a phone. Replaces the plain ``str`` that
    `_send_alerts` could never send as ``embed=``."""
    embed = ui.push_embed(
        Kind.STRATEGY_SIGNAL, plan.ticker, plan.direction, plan.strategy,
        description=f"{_strategy_levels(plan)}\n{strategy_plan_line(plan)} · ledger {plan.ledger}")
    ui.apply_chrome(embed, kind=Kind.STRATEGY_SIGNAL,
                    level=getattr(plan, "confidence_level", None), plan_id=plan.plan_id)
    return embed


def _alert_detail(level: int, all_ok: bool) -> str:
    """``Lv4 ⭐`` for a clean top setup, ``Lv3 ⚠️ review`` when a gate failed."""
    if not all_ok:
        return f"Lv{level} ⚠️ review"
    return f"Lv{level} ⭐" if level >= 4 else f"Lv{level}"
```

In `build_embed`, replace:

```python
    is_bull = result.trend == "bullish"
    direction = "LONG (buy)" if is_bull else "SHORT (sell)"
    all_ok = item.all_requirements_met
    compact = layout == "compact"
    priority_marker = "⭐ " if (conf.level >= 4 and all_ok) else ""
    needs_review_marker = "⚠️ " if not all_ok else ""
    plan_v2 = _v2_plan(item)
    title = f"{needs_review_marker}{priority_marker}{'🟢' if is_bull else '🔴'} {direction} — {result.ticker}"
    embed = discord.Embed(title=title)
    embed.color = ui.accent_for_level(conf.level)
```

with:

```python
    is_bull = result.trend == "bullish"
    all_ok = item.all_requirements_met
    compact = layout == "compact"
    plan_v2 = _v2_plan(item)
    # v110: title, push line, stripe and footer all come from the registry.
    # The ⭐ stays in the title: the scan summary's ✨ looks for it.
    embed = ui.push_embed(Kind.SETUP_ALERT, result.ticker, result.trend,
                          _alert_detail(conf.level, all_ok))
```

Replace:

```python
    if blocked is not None:
        sections["blocked"].append(blocked)
        embed.color = ui.accent_blocked()
```

with:

```python
    if blocked is not None:
        sections["blocked"].append(blocked)
```

In the intraday field, change `"✅ confirms — last 1h close is on the plan's side of today's VWAP"` to `"✔ confirms — last 1h close is on the plan's side of today's VWAP"`.

Replace the last chrome call:

```python
    ui.apply_chrome(embed, accent=embed.color, plan_id=plan_v2.plan_id if plan_v2 else None)
```

with:

```python
    ui.apply_chrome(embed, kind=Kind.SETUP_ALERT, level=conf.level, blocked=blocked is not None,
                    plan_id=plan_v2.plan_id if plan_v2 else None)
```

In `_legacy_simple_alert`, delete these three lines:

```python
    is_bull = result.trend == "bullish"
    direction = "LONG" if is_bull else "SHORT"
    arrow = "▲" if is_bull else "▼"
```

Replace the embed construction and chrome, from `embed = discord.Embed(` through the final `apply_chrome(...)` call, with:

```python
    embed = ui.push_embed(
        Kind.SETUP_SIMPLE, result.ticker, result.trend, f"Lv{conf.level}",
        description=(
            f"{headline}\n"
            f"Confidence: {ui.confidence_label(conf.level, conf.score)}\n"
            f"Horizon: {result.horizon_label}\n"
            f"Setup: {setup}\n\n"
            f"{plan_line}"
        ),
    )
    ui.apply_chrome(embed, kind=Kind.SETUP_SIMPLE, level=conf.level,
                    plan_id=plan_v2.plan_id if plan_v2 else None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_strategy_embeds.py tests/scanning/test_embeds_v3.py tests/scanning/test_simple_alerts.py tests/test_stats_commands.py tests/presentation/test_no_adhoc_color.py`
Expected: PASS, 0 failed. `test_all_three_embeds_share_timestamp_and_disclaimer_and_preserve_ids` still passes, because the closed-trade and near-close footers change only in V110-6.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/scanning/alert_embeds.py`
Expected: `build_embed` below 41 (it loses three conditional expressions). No other function is listed.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/alert_embeds.py tests/scanning/test_strategy_embeds.py tests/scanning/test_embeds_v3.py tests/scanning/test_simple_alerts.py tests/test_stats_commands.py
git commit -m "feat(v110): NEW SETUP identity for the full alert, simple mirror and strategy signal; strategy simple embed

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/scanning/alert_embeds.py tests/scanning/test_strategy_embeds.py tests/scanning/test_embeds_v3.py tests/scanning/test_simple_alerts.py tests/test_stats_commands.py
```

---

### Task V110-5: Execution feed — ticket, FILLED, MANAGE and EXITED kinds

Load the `alert-surface` skill first.

**Files:**
- Modify: `swingbot/core/scanning/execution_embeds.py` (whole module body below the imports)
- Test: `tests/scanning/test_execution_embeds.py`, `tests/scanning/test_simple_alerts.py` (DO NOT PLACE title), `tests/scanning/test_execution_feed_routing.py` (FILLED title)

**Interfaces:**
- Consumes:
  - V110-1: `Kind`, `Family`, `kinds.outcome_detail` and `kinds.outcome_for_r`.
  - V110-2: `ui.levels_block` and `ui.result_headline`.
  - V110-3: `ui.push_embed` and `ui.apply_chrome(kind=…)`.
  - Existing: `instructions.total_r`, `DO_NOT_PLACE` and `CLOSE_AT_MARKET`.
- Produces:
  - `execution_embeds.render(instruction, kind, *, block=None, r=None) -> PushEmbed`. `kind` is now **required**.
  - `execution_embeds.plan_levels_block(plan, entry) -> str` and `execution_embeds.plan_result_block(plan, exit_price, r) -> str`, both consumed by V110-6.
  - `build_ticket_embed` and `build_instruction_embed`, with unchanged signatures, now return `PushEmbed`.

- [ ] **Step 1: Write the failing tests**

Replace everything in `tests/scanning/test_execution_embeds.py` from `def test_render_title_and_body_order():` to the end with:

```python
def test_render_title_and_body_order():
    embed = execution_embeds.render(_instruction(warnings=("⚠ heat",)), Kind.MOVE_STOP)
    assert embed.title == "✂️ ▲ LONG NVDA · MOVE STOP"
    assert embed.push_text == "✂️ MANAGE · ▲ LONG NVDA · MOVE STOP"
    assert embed.description.splitlines() == ["⚠ heat", "**MOVE STOP → 107.30 now**", "trail; +0.6R"]
    assert embed.footer.text == "MANAGE · plan plan-123"


def test_render_puts_the_ansi_block_first():
    embed = execution_embeds.render(_instruction(), Kind.FILLED, block="```ansi\nX\n```")
    assert embed.description.startswith("```ansi\nX\n```\n**MOVE STOP")


@pytest.mark.parametrize("kind,level,r,expected", [
    (Kind.TICKET_PLACE, 5, None, kinds.SETUP_RAMP[5]),
    (Kind.TICKET_DO_NOT_PLACE, 5, None, kinds.SETUP_BLOCKED),
    (Kind.EXITED, None, 2.5, kinds.RESULT_GREENS[2]),
    (Kind.EXITED, None, -1.0, kinds.RESULT_REDS[1]),
    (Kind.EXITED, None, 0.0, kinds.RESULT_GREY),
    (Kind.MOVE_STOP, None, None, kinds.MANAGE_AMBER),
])
def test_render_takes_the_registry_stripe(kind, level, r, expected):
    assert execution_embeds.render(_instruction(level=level), kind, r=r).color.value == expected


def test_result_titles_carry_the_outcome_mark():
    embed = execution_embeds.render(_instruction(verb="EXITED"), Kind.EXITED, r=1.8)
    assert embed.title == "🏁 ▲ LONG NVDA · EXITED · ✅ WIN +1.8R"
    assert embed.push_text.startswith("🏁 RESULT · ▲ LONG NVDA · EXITED")


def test_ticket_and_event_embeds():
    item = make_item(plan_v2=make_plan_v2(entry_type="stop_entry", trigger_price=101.0))
    item.paper_logged = True
    ticket = execution_embeds.build_ticket_embed(item, item.plan_v2)
    assert ticket.title == "🆕 ▲ LONG NVDA · PLACE"
    assert ticket.description.startswith("```ansi\n")
    assert "**BUY STOP 101.00 · size n/a**" in ticket.description
    assert ticket.footer.text.startswith(tokens.DISCLAIMER)
    event = execution_embeds.build_instruction_embed(
        item.plan_v2, PlanEvent(item.plan_v2.plan_id, "cancelled_expired", {"bars_waited": 6}))
    assert event.title == "🚫 ▲ LONG NVDA · CANCEL"


def test_risk_cap_cancel_is_its_own_manage_kind():
    plan = make_plan_v2()
    event = execution_embeds.build_instruction_embed(plan, PlanEvent(
        plan.plan_id, "cancelled_risk_cap", {"entry_price": 102.5, "stop_loss": 98.4,
                                             "planned_loss_pct": 4.0, "max_planned_loss_pct": 2.0}))
    assert event.title == "🚫 ▲ LONG NVDA · RISK CAP"


def test_filled_event_is_an_entry_with_a_price_block():
    plan = make_plan_v2()
    embed = execution_embeds.build_instruction_embed(
        plan, PlanEvent(plan.plan_id, "filled", {"entry_price": 100.5}))
    assert embed.title == "🎯 ▲ LONG NVDA · FILLED"
    assert embed.color.value == kinds.ENTRY_TEAL
    assert embed.footer.text.startswith("ENTRY")
    assert "entry 100.50" in ansi._ESCAPE_RE.sub("", embed.description)


def test_closed_event_is_a_result_with_the_realised_r():
    plan = make_plan_v2()          # entry 100, stop 95
    embed = execution_embeds.build_instruction_embed(plan, PlanEvent(
        plan.plan_id, "closed", {"reason": "win", "exit_price": 110.0, "session": "regular"}))
    assert embed.title == "🏁 ▲ LONG NVDA · EXITED · ✅ WIN +2.0R"
    assert embed.color.value == kinds.RESULT_GREENS[2]
    assert ansi.paint("2.0R", "green") in embed.description


def test_move_stop_events_split_into_break_even_tp1_and_move_stop():
    plan = make_plan_v2()
    be = execution_embeds.build_instruction_embed(
        plan, PlanEvent(plan.plan_id, "be_moved", {"working_stop": 100.0}))
    assert be.title == "🛡️ ▲ LONG NVDA · BREAK-EVEN"
```

Also change the imports at the top of `tests/scanning/test_execution_embeds.py` to:

```python
import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import ansi, kinds, tokens
from swingbot.core.presentation.instructions import Instruction
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import execution_embeds
from tests.scanning.test_embeds_v3 import make_item, make_plan_v2
```

In `tests/scanning/test_simple_alerts.py` (`test_unlogged_v2_alert_says_do_not_place`), change `assert embed.title.endswith("— DO NOT PLACE")` to:

```python
    assert embed.title == "🆕 ▲ LONG NVDA · DO NOT PLACE"
    assert embed.color.value == kinds.SETUP_BLOCKED
```

In `tests/scanning/test_execution_feed_routing.py` (`test_fill_uses_feed_not_alerts_and_close_is_notice`), change `assert feed.sent[0]["embed"].title.endswith("— FILLED")` to `assert feed.sent[0]["embed"].title.endswith("· FILLED")`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_execution_embeds.py tests/scanning/test_simple_alerts.py tests/scanning/test_execution_feed_routing.py`
Expected: FAIL. `render()` takes no `kind`, and the titles use the old `— VERB` shape.

- [ ] **Step 3: Write the implementation**

Replace `swingbot/core/scanning/execution_embeds.py` in full with:

```python
"""Discord rendering for the v81 execution feed.

Message wording is projected by presentation.instructions. This module picks
the v110 registry kind for each message, adds the ANSI price block where the
kind carries one (NEW SETUP ticket, ENTRY fill, RESULT close), and applies the
shared chrome.
"""
import discord

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.presentation import kinds
from swingbot.core.presentation.instructions import (CLOSE_AT_MARKET, DO_NOT_PLACE, Instruction,
                                                     block_warnings, instruction_for,
                                                     ticket_for, total_r)
from swingbot.core.presentation.kinds import Family, Kind

from .plan_table import _sizing_snapshot


#: feed transition -> registry kind; "filled" and "closed" are styled in _event_style.
_EVENT_KINDS = {
    "be_moved": Kind.BE_MOVED,
    "tp1_partial": Kind.TP1_HIT,
    "stop_moved": Kind.MOVE_STOP,
    "cancelled_expired": Kind.CANCEL,
    "cancelled_invalidated": Kind.CANCEL,
    "cancelled_risk_cap": Kind.RISK_CAP,
}


def render(instruction: Instruction, kind: Kind, *, block: str | None = None,
           r: float | None = None) -> discord.Embed:
    """Registry title and push line; body = ANSI block (if any), warnings,
    bold headline, instruction lines."""
    detail = (kinds.outcome_detail(kinds.outcome_for_r(r), r)
              if kind.family is Family.RESULT else "")
    embed = ui.push_embed(kind, instruction.ticker, instruction.direction, detail)
    body = [*instruction.warnings, f"**{instruction.headline}**", *instruction.lines]
    embed.description = "\n".join([block, *body] if block else body)
    ui.apply_chrome(embed, kind=kind, level=instruction.level, r=r, plan_id=instruction.plan_id)
    return embed


def _entry(plan) -> float:
    return plan.entry_price if plan.entry_price is not None else plan.trigger_price


def _move_pct(entry: float | None, exit_price: float | None, direction: str) -> float | None:
    if not entry or exit_price is None:
        return None
    sign = 1 if direction == "bullish" else -1
    return (exit_price - entry) / entry * 100 * sign


def plan_levels_block(plan, entry: float | None) -> str:
    """A plan's levels block from ``entry`` (trigger for a ticket, fill for an entry)."""
    return ui.levels_block(direction=plan.direction, entry=entry, stop=plan.stop_loss,
                           tp1=plan.tp1, tp2=plan.tp2)


def plan_result_block(plan, exit_price: float | None, r: float | None) -> str:
    """A plan's RESULT block: entry → exit / stop and the realised R."""
    return ui.result_headline(direction=plan.direction, entry=plan.entry_price,
                              exit_price=exit_price, stop=plan.stop_loss,
                              pct=_move_pct(plan.entry_price, exit_price, plan.direction), r=r)


def build_ticket_embed(item, plan) -> discord.Embed:
    """Render a new v2 alert's order ticket."""
    instruction = ticket_for(
        plan, logged=item.paper_logged, not_logged_reason=item.not_logged_reason,
        sizing=_sizing_snapshot(_entry(plan), plan), currency=config.CURRENCY_SYMBOL,
        warnings=block_warnings(heat=getattr(item, "heat_blocked", None),
                                cluster=getattr(item, "cluster_blocked", None),
                                kill=getattr(item, "kill_switch_blocked", None)),
        level=item.conf.level,
    )
    kind = Kind.TICKET_DO_NOT_PLACE if instruction.verb == DO_NOT_PLACE else Kind.TICKET_PLACE
    return render(instruction, kind, block=plan_levels_block(plan, plan.trigger_price))


def _event_style(plan, event, instruction: Instruction) -> tuple:
    """(kind, ANSI block or None, realised R or None) for one feed event."""
    if event.transition == "closed":
        exit_price = event.detail.get("exit_price")
        r = total_r(plan, exit_price)
        kind = Kind.CLOSE_AT_MARKET if instruction.verb == CLOSE_AT_MARKET else Kind.EXITED
        return kind, plan_result_block(plan, exit_price, r), r
    if event.transition == "filled":
        return Kind.FILLED, plan_levels_block(plan, event.detail["entry_price"]), None
    return _EVENT_KINDS.get(event.transition, Kind.PLAN_UPDATE), None, None


def build_instruction_embed(plan, event) -> discord.Embed:
    """Render one lifecycle event for the execution feed."""
    instruction = instruction_for(plan, event, sizing=_sizing_snapshot(_entry(plan), plan))
    kind, block, r = _event_style(plan, event, instruction)
    return render(instruction, kind, block=block, r=r)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_execution_embeds.py tests/scanning/test_simple_alerts.py tests/scanning/test_execution_feed_routing.py tests/presentation/test_instructions.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/scanning/execution_embeds.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/execution_embeds.py tests/scanning/test_execution_embeds.py tests/scanning/test_simple_alerts.py tests/scanning/test_execution_feed_routing.py
git commit -m "feat(v110): execution feed renders through registry kinds with ANSI price blocks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/scanning/execution_embeds.py tests/scanning/test_execution_embeds.py tests/scanning/test_simple_alerts.py tests/scanning/test_execution_feed_routing.py
```

---

### Task V110-6: Closed trade, near close, plan-event embeds and their sends

Load the `alert-surface` skill first. `PLAN_EVENT_STYLES` is **removed**. Its replacement is `PLAN_EVENT_KINDS` plus `CLOSE_REASON_STYLES`. `git grep -n PLAN_EVENT_STYLES` shows that only `lifecycle_embeds.py` and `tests/scanning/test_transition_embeds.py` use it. `engine.py` / `embeds.py` never re-exported it, and their `__all__` stays unchanged.

**Files:**
- Modify: `swingbot/core/scanning/lifecycle_embeds.py`:
  - `build_closed_trade_embed`, `notify_closed_trades`
  - `build_near_close_embed`, `notify_near_close`
  - `PLAN_EVENT_STYLES` and the `_GOOD/_BAD/_NEUTRAL/_INERT` constants (removed)
  - `build_plan_event_embed`
  - the three `send` calls in `notify_plan_events`
- Test: `tests/scanning/test_transition_embeds.py`, `tests/scanning/test_embeds_v3.py`, `tests/tracking/test_near_tp_bypass.py`, `tests/scanning/test_execution_feed_routing.py`, `tests/scanning/test_lifecycle_push.py` (new)

**Interfaces:**
- Consumes:
  - V110-1: `Kind`, `kinds.outcome_detail`, `outcome_for_r`, `result_r`, `outcome_mark` and the colour constants.
  - V110-2: `ui.result_headline`.
  - V110-3: `ui.push_embed`, `ui.push_kwargs` and `ui.apply_chrome(kind=…)`.
  - V110-4: `alert_embeds.strategy_plan_line`.
  - V110-5: `execution_embeds.plan_levels_block` and `plan_result_block`.
  - Existing: `instructions.total_r`.
- Produces:
  - `lifecycle_embeds.PLAN_EVENT_KINDS: dict[str, Kind]`.
  - `lifecycle_embeds.CLOSE_REASON_STYLES: dict[str, tuple[Kind, str, str]]` (kind, outcome, phrase).
  - Every lifecycle send passes `**ui.push_kwargs(embed)`.

- [ ] **Step 1: Write the failing tests**

In `tests/scanning/test_transition_embeds.py`, replace the imports with:

```python
import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import ansi, kinds
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning.embeds import build_plan_event_embed
from swingbot.core.scanning.lifecycle_embeds import CLOSE_REASON_STYLES, PLAN_EVENT_KINDS
from swingbot.core.scanning import plan_table
from tests.planning.test_plan_engine_model import _plan
```

Replace `test_filled_embed`, `test_expired_and_invalidated_embeds`, `test_risk_cap_cancellation_embed_explains_why` and `test_be_moved_embed` with:

```python
def test_filled_embed():
    e = _embed("filled", {"entry_price": 106.0})
    assert "ENTRY TRIGGERED" in e.title and e.title.startswith("🎯")
    assert any("106" in (f.value or "") for f in e.fields)
    assert e.color.value == kinds.ENTRY_TEAL
    assert e.push_text.startswith("🎯 ENTRY · ▲ LONG AAPL")
    assert e.footer.text == "ENTRY · plan p1"
    assert "entry 106.00" in ansi._ESCAPE_RE.sub("", e.description)


def test_expired_and_invalidated_embeds():
    expired = _embed("cancelled_expired", {"bars_waited": 6})
    assert expired.title.startswith("🏁") and "EXPIRED" in expired.title and "⏹️" in expired.title
    assert any("6 bar" in (f.value or "") for f in expired.fields)
    assert expired.color.value == kinds.RESULT_GREY

    invalidated = _embed("cancelled_invalidated", {"live_price": 94.0})
    assert "INVALIDATED" in invalidated.title and "⏹️" in invalidated.title
    assert "❌" not in invalidated.title
    assert any("94.00" in (f.value or "") for f in invalidated.fields)


def test_risk_cap_cancellation_embed_explains_why():
    e = _embed("cancelled_risk_cap", {"entry_price": 102.5, "stop_loss": 98.4,
                                      "planned_loss_pct": 4.0, "max_planned_loss_pct": 2.0})
    assert "🚫" in e.title and "risk cap" in e.title.lower()
    why = next(f.value for f in e.fields if f.name == "Why")
    assert "4.00%" in why and "2.0%" in why
    assert PLAN_EVENT_KINDS["cancelled_risk_cap"] is Kind.RISK_CAP
    assert e.color.value == kinds.MANAGE_AMBER


def test_be_moved_embed():
    e = _embed("be_moved", {"working_stop": 100.0})
    assert "🛡" in e.title
    assert any("100" in (f.value or "") for f in e.fields)
    assert e.color.value == kinds.MANAGE_AMBER
```

Replace `test_every_plan_event_uses_a_shared_ramp_colour`, `test_good_bad_and_neutral_plan_events_use_their_semantic_ramp_endpoints` and `test_a_terminal_target_close_reads_as_a_win` with:

```python
def test_close_reasons_map_to_result_kinds_with_their_outcome():
    assert CLOSE_REASON_STYLES["loss"][:2] == (Kind.STOPPED, "loss")
    assert CLOSE_REASON_STYLES["scratch"][:2] == (Kind.SCRATCHED, "scratch")
    for reason in ("win", "tp1_runner_be", "tp1_runner_tp2", "tp1_runner_trail"):
        assert CLOSE_REASON_STYLES[reason][:2] == (Kind.WIN, "win")


def test_a_stopped_close_is_red_and_says_loss():
    e = _embed("closed", {"reason": "loss", "exit_price": 94.0}, entry_price=100.0)
    assert e.title == "🏁 ▲ LONG AAPL · STOPPED · ❌ LOSS −1.2R"
    assert e.color.value in kinds.RESULT_REDS
    assert e.footer.text == "RESULT · plan p1"


def test_a_terminal_target_close_reads_as_a_win():
    """v70: an ACTIVE plan with no tp2 closes with reason 'win'."""
    e = _embed("closed", {"reason": "win", "exit_price": 111.0}, entry_price=100.0)
    assert "✅ WIN" in e.title and "target hit" in e.title
    assert "🟢" not in e.title
    assert any("111" in (f.value or "") for f in e.fields)
    assert e.color.value == kinds.RESULT_GREENS[2]        # (111 - 100) / 5 = +2.2R
    assert e.push_text.startswith("🏁 RESULT · ▲ LONG AAPL · WIN")
    assert ansi.paint("2.2R", "green") in e.description


def test_an_unknown_transition_is_a_plan_update():
    e = _embed("pyramid_add")
    assert e.title == "🛡️ ▲ LONG AAPL · PLAN UPDATE"


def test_the_plan_line_names_the_side_and_drops_the_check_mark():
    e = _embed("be_moved", {"working_stop": 100.0}, badge="VALIDATED")
    plan_field = next(f.value for f in e.fields if f.name == "Plan (v2)")
    assert "LONG" in plan_field and "bullish" not in plan_field and "✅" not in plan_field
```

Keep `test_tp1_partial_embed_*`, `test_partial_position_line_*` and `test_close_reasons_have_distinct_copy` unchanged.

In `tests/scanning/test_embeds_v3.py`, replace `test_closed_trade_outcomes_use_the_shared_ramp_endpoints` with:

```python
def test_closed_trade_outcomes_take_the_result_ramp():
    assert build_closed_trade_embed(_make_closed_trade(status="win")).color.value in kinds.RESULT_GREENS
    assert build_closed_trade_embed(_make_closed_trade(status="loss")).color.value in kinds.RESULT_REDS
    assert build_closed_trade_embed(_make_closed_trade(status="closed")).color.value == kinds.RESULT_GREY


def test_closed_trade_title_and_push_line_come_from_the_registry():
    embed = build_closed_trade_embed(_make_closed_trade(status="win"))
    assert embed.title == "🏁 ▲ LONG NVDA · CLOSED · ✅ WIN +2.0R"
    assert embed.push_text == "🏁 RESULT · ▲ LONG NVDA · CLOSED · ✅ WIN +2.0R"
    assert ansi.paint("2.0R", "green") in embed.description
    manual = build_closed_trade_embed(_make_closed_trade(status="closed"))
    assert manual.title == "🏁 ▲ LONG NVDA · CLOSED · 🔒 MANUAL CLOSE"
```

Replace the body of `test_all_three_embeds_share_timestamp_and_disclaimer_and_preserve_ids`, from the `# All three share the identical disclaimer prefix` comment through `assert "plan 12345678" in scan_embed.footer.text`, with:

```python
    # v110: each family owns its footer -- only NEW SETUP keeps the disclaimer.
    assert scan_embed.footer.text == f"{tokens.DISCLAIMER} · plan 12345678"
    assert closed_embed.footer.text == "RESULT"
    assert near_close_embed.footer.text == "WATCH"
```

Leave the rest of that test (the `" · plan " not in closed_embed.footer.text` and Trade-ID assertions) unchanged, and rename the test to `test_all_three_embeds_are_timestamped_with_family_footers_and_keep_ids`.

In `tests/tracking/test_near_tp_bypass.py`, replace the first two tests with:

```python
def test_near_stop_warns_in_the_watch_orange():
    embed = build_near_close_embed(_warning("stop-loss"))
    assert embed.color.value == kinds.WATCH_STOP_ORANGE
    assert embed.title == "👀 ▲ LONG AAPL · NEARING STOP · 1.0% away"
    assert embed.push_text == "👀 WATCH · ▲ LONG AAPL · NEARING STOP · 1.0% away"
    assert embed.footer.text == "WATCH"


def test_near_target_uses_the_watch_lime_and_explicit_title():
    stop = build_near_close_embed(_warning("stop-loss"))
    target = build_near_close_embed(_warning("take-profit"))
    assert target.color.value == kinds.WATCH_TP_LIME
    assert "stop" in stop.title.lower()
    assert "NEARING TP" in target.title
```

Change that file's `from swingbot.core.presentation import tokens` to `from swingbot.core.presentation import kinds`.

In `tests/scanning/test_execution_feed_routing.py`:
- Append to `test_feed_pings_and_history_is_silent`:

  ```python
      assert feed.sent[0]["content"] == "🛡️ MANAGE · ▲ LONG AAPL · BREAK-EVEN"
      assert history.sent[0]["content"] == feed.sent[0]["content"]
  ```

- Append to `test_non_feed_events_stay_history_only`:

  ```python
      assert history.sent[0]["content"] == "🛡️ MANAGE · ▲ LONG AAPL · PLAN UPDATE"
  ```

Create `tests/scanning/test_lifecycle_push.py`:

```python
"""v110 §4: closed-trade and near-close posts carry the registry push line."""
import asyncio
from types import SimpleNamespace

from swingbot import config
from swingbot.core.scanning import lifecycle_embeds


class _Chan:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append(kwargs)


def _bot(chan):
    return SimpleNamespace(get_channel=lambda _id: chan)


def _trade():
    return {"id": "trade-42", "ticker": "NVDA", "status": "win", "entry": 100.0,
            "exit_price": 110.0, "stop_loss": 95.0, "take_profit": 110.0,
            "direction": "bullish", "strategy": "RSI Pullback", "horizon_key": "2w",
            "confidence_label": "High", "confidence_level": 4}


def test_closed_trade_is_sent_with_its_registry_push_line(monkeypatch):
    chan = _Chan()
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "5")
    asyncio.run(lifecycle_embeds.notify_closed_trades(_bot(chan), [_trade()]))
    sent = chan.sent[0]
    assert sent["content"] == sent["embed"].push_text
    assert sent["content"].startswith("🏁 RESULT · ▲ LONG NVDA · CLOSED · ✅ WIN")
    assert "**NVDA**" not in sent["content"]          # the old ✅ WIN — **TICK** header is gone


def test_near_close_is_sent_with_its_registry_push_line(monkeypatch):
    chan = _Chan()
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "5")
    trade = {**_trade(), "status": "open"}
    warning = {"trade": trade, "near_which": "take-profit", "sl_dist_pct": 4.0,
               "tp_dist_pct": 0.8, "current_price": 109.0}
    asyncio.run(lifecycle_embeds.notify_near_close(_bot(chan), [warning]))
    assert chan.sent[0]["content"] == "👀 WATCH · ▲ LONG NVDA · NEARING TP · 0.8% away"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_transition_embeds.py tests/scanning/test_embeds_v3.py tests/tracking/test_near_tp_bypass.py tests/scanning/test_execution_feed_routing.py tests/scanning/test_lifecycle_push.py`
Expected: FAIL. `CLOSE_REASON_STYLES` / `PLAN_EVENT_KINDS` fail to import, and the titles, colours and footers are the old ones.

- [ ] **Step 3: Write the implementation**

In `swingbot/core/scanning/lifecycle_embeds.py`, add below `from swingbot.core import presentation as ui`:

```python
from swingbot.core.presentation import kinds
from swingbot.core.presentation.instructions import total_r
from swingbot.core.presentation.kinds import Kind
from .alert_embeds import strategy_plan_line
from .execution_embeds import plan_levels_block, plan_result_block
```

**Closed trade.** Above `def build_closed_trade_embed`, add:

```python
_STATUS_OUTCOME = {"win": "win", "loss": "loss", "closed": "manual"}
_RESULT_FIELD_WORD = {
    "win": f"WIN {kinds.outcome_mark('win')}",
    "loss": f"LOSS {kinds.outcome_mark('loss')}",
    "manual": "MANUALLY CLOSED",
}
```

In `build_closed_trade_embed`, replace:

```python
    status   = trade["status"]   # "win" | "loss" | "closed"
    won      = status == "win"
    manual   = status == "closed"

    if manual:
        outcome_word = "MANUALLY CLOSED"
        icon  = "🔒"
    elif won:
        outcome_word = "WIN ✅"
        icon  = "✅"
    else:
        outcome_word = "LOSS ❌"
        icon  = "❌"
```

with:

```python
    # "win" | "loss" | "closed" (manual) -> the registry's outcome (v110).
    outcome = _STATUS_OUTCOME.get(trade["status"], "manual")
    outcome_word = _RESULT_FIELD_WORD[outcome]
```

Then replace:

```python
    title = f"{icon} {trade['ticker']} — {outcome_word}"
    outcome = "win" if won else "loss" if not manual else "scratch"
    embed = discord.Embed(title=title)
    embed.description = ui.plan_headline(
        direction=trade.get("direction", ""), entry=entry, target=exit_price,
        stop=trade.get("stop_loss"), target_pct=pct, stop_pct=None, r=r,
    )
    ui.apply_chrome(embed, accent=ui.accent_for_outcome(outcome),
                    plan_id=trade.get("plan_id"))
```

with:

```python
    detail = kinds.outcome_detail(outcome, None if outcome == "manual" else r)
    embed = ui.push_embed(
        Kind.CLOSED_TRADE, trade["ticker"], trade.get("direction"), detail,
        description=ui.result_headline(direction=trade.get("direction", ""), entry=entry,
                                       exit_price=exit_price, stop=trade.get("stop_loss"),
                                       pct=pct, r=r))
    ui.apply_chrome(embed, kind=Kind.CLOSED_TRADE, r=kinds.result_r(outcome, r),
                    plan_id=trade.get("plan_id"))
```

In `notify_closed_trades`, replace:

```python
            embed = build_closed_trade_embed(trade)
            # Compact header line so the embed title stands out
            header_map = {"win": "✅ WIN", "loss": "❌ LOSS", "closed": "🔒 CLOSED"}
            header = f"{header_map.get(status, status.upper())} — **{trade['ticker']}**"
            await channel.send(content=header, embed=embed)
```

with:

```python
            # v110: the registry push line replaces the old ✅ WIN — **TICK** header.
            await channel.send(**ui.push_kwargs(build_closed_trade_embed(trade)))
```

**Near close.** In `build_near_close_embed`, replace:

```python
    title = f"⚠️ APPROACHING {approaching_word} — {t['ticker']}"
    embed = discord.Embed(title=title)
    ui.apply_chrome(embed, accent=ui.accent_for_outcome("loss" if is_sl else "win"),
                    plan_id=t.get("plan_id"))
```

with:

```python
    kind = Kind.NEAR_STOP if is_sl else Kind.NEAR_TP
    distance = warning["sl_dist_pct" if is_sl else "tp_dist_pct"]
    embed = ui.push_embed(kind, t["ticker"], t.get("direction"), f"{distance:.1f}% away")
    ui.apply_chrome(embed, kind=kind, plan_id=t.get("plan_id"))
```

In `notify_near_close`, change `await channel.send(embed=build_near_close_embed(warning))` to `await channel.send(**ui.push_kwargs(build_near_close_embed(warning)))`.

**Plan events.** Delete the `_GOOD`, `_BAD`, `_NEUTRAL` and `_INERT` constants, the whole `PLAN_EVENT_STYLES` dict and the whole `build_plan_event_embed` function. Put this in their place:

```python
#: v2 plan transition -> registry kind (v110 §2). "closed" is keyed by reason below.
PLAN_EVENT_KINDS = {
    "filled": Kind.ENTRY_TRIGGERED,
    "cancelled_expired": Kind.EXPIRED,
    "cancelled_invalidated": Kind.INVALIDATED,
    "cancelled_risk_cap": Kind.RISK_CAP,
    "be_moved": Kind.BE_MOVED,
    "tp1_partial": Kind.TP1_HIT,
}

#: close reason -> (kind, outcome, phrase). STOPPED and SCRATCHED already say
#: it in their label; the phrases keep the four WIN closes distinct.
CLOSE_REASON_STYLES = {
    "loss": (Kind.STOPPED, "loss", ""),
    "scratch": (Kind.SCRATCHED, "scratch", ""),
    "win": (Kind.WIN, "win", "target hit"),
    "tp1_runner_be": (Kind.WIN, "win", "runner closed at its floor"),
    "tp1_runner_tp2": (Kind.WIN, "win", "runner hit TP2"),
    "tp1_runner_trail": (Kind.WIN, "win", "trail locked profit"),
}

_ENDED_OUTCOME = {Kind.EXPIRED: "expired", Kind.INVALIDATED: "invalidated"}


def _event_style(plan, event) -> tuple:
    """(kind, title detail, stripe R) for one plan event."""
    if event.transition == "closed":
        kind, outcome, phrase = CLOSE_REASON_STYLES.get(
            event.detail.get("reason"), (Kind.EXITED, None, "closed"))
        r = total_r(plan, event.detail.get("exit_price"))
        outcome = outcome or kinds.outcome_for_r(r)
        detail = kinds.outcome_detail(outcome, r)
        return kind, (f"{detail} · {phrase}" if phrase else detail), kinds.result_r(outcome, r)
    kind = PLAN_EVENT_KINDS.get(event.transition, Kind.PLAN_UPDATE)
    ended = _ENDED_OUTCOME.get(kind)
    return kind, (kinds.outcome_detail(ended) if ended else ""), None


def _filled_fields(embed, plan, d) -> None:
    embed.description = plan_levels_block(plan, d["entry_price"])
    embed.add_field(name="Entry", value=f"{d['entry_price']:.2f}")
    embed.add_field(name="Stop", value=f"{plan.stop_loss:.2f}")
    embed.add_field(name="TP1", value=f"{plan.tp1:.2f}")


def _be_moved_fields(embed, plan, d) -> None:
    embed.add_field(name="New stop", value=f"{d['working_stop']:.2f} (entry)")


def _tp1_partial_fields(embed, plan, d) -> None:
    pct, amount = banked_leg_pct_and_amount(plan, d["exit_price"], d["fraction"])
    banked = f"{d['fraction']:.0%} @ {d['exit_price']:.2f} ({d['r']:+.2f}R"
    if pct is not None:
        banked += f" · {pct:+.1f}%"
    if amount is not None:
        banked += f" · {signed_money(amount, config.CURRENCY_SYMBOL)}"
    embed.add_field(name="Banked", value=banked + ")")
    embed.add_field(name="Partial position", value=partial_position_line(plan), inline=False)


def _closed_fields(embed, plan, d) -> None:
    exit_price = d.get("exit_price")
    embed.description = plan_result_block(plan, exit_price, total_r(plan, exit_price))
    embed.add_field(name="Exit", value=f"{d.get('exit_price', 0):.2f}")


def _expired_fields(embed, plan, d) -> None:
    embed.description = plan_levels_block(plan, plan.trigger_price)
    embed.add_field(name="Why", value=(
        f"Never triggered — {d['bars_waited']} bar(s) waited, past the "
        f"{plan.expiry_bars}-bar window (trigger {plan.trigger_price:.2f})"), inline=False)


def _invalidated_fields(embed, plan, d) -> None:
    embed.description = plan_levels_block(plan, plan.trigger_price)
    embed.add_field(name="Why", value=(
        f"Price closed through the stop before entry triggered: "
        f"{d['live_price']:.2f} vs stop {plan.stop_loss:.2f}"), inline=False)


def _risk_cap_fields(embed, plan, d) -> None:
    embed.add_field(name="Why", value=(
        f"Trigger filled at {d['entry_price']:.2f} against stop {d['stop_loss']:.2f} — "
        f"{d['planned_loss_pct']:.2f}% planned risk, above the "
        f"{d['max_planned_loss_pct']:.1f}% hard cap. Never opened; no position, no P&L."),
        inline=False)


_EVENT_FIELDS = {
    "filled": _filled_fields,
    "be_moved": _be_moved_fields,
    "tp1_partial": _tp1_partial_fields,
    "closed": _closed_fields,
    "cancelled_expired": _expired_fields,
    "cancelled_invalidated": _invalidated_fields,
    "cancelled_risk_cap": _risk_cap_fields,
}


def build_plan_event_embed(plan, event) -> discord.Embed:
    """Per-transition Discord embed for the v2 plan lifecycle (Task 72), styled
    by the v110 registry. Field text is unchanged from the pre-v110 builder."""
    kind, detail, stripe_r = _event_style(plan, event)
    embed = ui.push_embed(kind, plan.ticker, plan.direction, detail)
    ui.apply_chrome(embed, kind=kind, r=stripe_r, plan_id=plan.plan_id)
    embed.add_field(name="Plan (v2)", value=strategy_plan_line(plan), inline=False)
    fields = _EVENT_FIELDS.get(event.transition)
    if fields is not None:
        fields(embed, plan, event.detail)
    return embed
```

In `notify_plan_events`, change the three sends to:
- `await history.send(**ui.push_kwargs(build_plan_event_embed(plan, event)))`
- `await feed.send(**ui.push_kwargs(embed))`
- `await (silence(history) if pinged else history).send(**ui.push_kwargs(embed))`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_transition_embeds.py tests/scanning/test_embeds_v3.py tests/tracking/test_near_tp_bypass.py tests/scanning/test_execution_feed_routing.py tests/scanning/test_lifecycle_push.py tests/scanning/test_scanning_package_structure.py tests/presentation/test_surface_agreement.py`
Expected: PASS, 0 failed. `test_scanning_package_structure` confirms that every `engine.__all__` name still resolves.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/scanning/lifecycle_embeds.py`
Expected:
- `build_closed_trade_embed` below its baseline of 20 (the four-way `if/elif` and two conditional expressions are gone).
- `regenerate_chart_for_trade` and `notify_plan_events` unchanged at 12.
- `build_plan_event_embed`, `_event_style` and the `_*_fields` helpers absent.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/lifecycle_embeds.py tests/scanning/test_transition_embeds.py tests/scanning/test_embeds_v3.py tests/tracking/test_near_tp_bypass.py tests/scanning/test_execution_feed_routing.py tests/scanning/test_lifecycle_push.py
git commit -m "feat(v110): RESULT/WATCH/ENTRY/MANAGE kinds for lifecycle embeds; sends carry the push line

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/scanning/lifecycle_embeds.py tests/scanning/test_transition_embeds.py tests/scanning/test_embeds_v3.py tests/tracking/test_near_tp_bypass.py tests/scanning/test_execution_feed_routing.py tests/scanning/test_lifecycle_push.py
```

---

### Task V110-7: `!trade` and `!today` read the registry's closed-trade marks

Command replies keep their look (spec: out of scope). Only the duplicated icon maps are replaced by `kinds.outcome_mark`, so the marks cannot drift from the pushed messages.

**Files:**
- Modify: `swingbot/commands/trades.py` (`_build_trade_detail_embed`'s status `if/elif` chain, and the closed-today `icon = …` line in `summary_cmd`)
- Test: `tests/test_trades_display.py`

**Interfaces:**
- Consumes: V110-1's `kinds.outcome_mark` and `kinds.OUTCOME_MARKS`.
- Produces: `trades._status_style(status) -> tuple[str, str, str]` (icon, accent outcome, status word).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_trades_display.py`:

```python
import pytest

from swingbot.commands.trades import _status_style
from swingbot.core.presentation import kinds


@pytest.mark.parametrize("status,icon,accent,word", [
    ("open", "🔵", "scratch", "OPEN"),
    ("win", "✅", "win", "WIN ✅"),
    ("loss", "❌", "loss", "LOSS ❌"),
    ("closed", "🔒", "scratch", "MANUALLY CLOSED"),
])
def test_status_styles_read_the_registry_marks(status, icon, accent, word):
    assert _status_style(status) == (icon, accent, word)


def test_closed_trade_marks_are_the_registrys_not_a_local_copy():
    source = MODULE.read_text(encoding="utf-8")
    assert '"✅"' not in source and '"❌"' not in source and '"🔒"' not in source
    assert _status_style("win")[0] == kinds.OUTCOME_MARKS["win"]


def test_trade_detail_title_shape_is_unchanged():
    embed = _build_trade_detail_embed(_winning_trade())
    assert embed.title == "✅ Trade trade-win — PENNY"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/test_trades_display.py`
Expected: FAIL — `ImportError: cannot import name '_status_style'`.

- [ ] **Step 3: Write the implementation**

In `swingbot/commands/trades.py`, add `from swingbot.core.presentation import kinds` next to the existing `presentation` import. Add above `_build_trade_detail_embed`:

```python
_OPEN_STYLE = ("🔵", "scratch", "OPEN")
_CLOSED_STYLES = {
    "win": (kinds.outcome_mark("win"), "win", f"WIN {kinds.outcome_mark('win')}"),
    "loss": (kinds.outcome_mark("loss"), "loss", f"LOSS {kinds.outcome_mark('loss')}"),
}
_MANUAL_STYLE = (kinds.outcome_mark("manual"), "scratch", "MANUALLY CLOSED")
#: trade status -> the registry outcome whose mark the !today list shows.
_STATUS_OUTCOME = {"win": "win", "loss": "loss"}


def _status_style(status: str) -> tuple[str, str, str]:
    """(title icon, accent outcome, status word) for !trade. Closed-trade marks
    come from the v110 registry so they match the pushed RESULT messages."""
    if status == "open":
        return _OPEN_STYLE
    return _CLOSED_STYLES.get(status, _MANUAL_STYLE)
```

In `_build_trade_detail_embed`, replace:

```python
    if is_open:
        icon, accent = "🔵", ui.accent_for_outcome("scratch")
        status_word = "OPEN"
    elif match["status"] == "win":
        icon, accent = "✅", ui.accent_for_outcome("win")
        status_word = "WIN ✅"
    elif match["status"] == "loss":
        icon, accent = "❌", ui.accent_for_outcome("loss")
        status_word = "LOSS ❌"
    else:
        icon, accent = "🔒", ui.accent_for_outcome("scratch")
        status_word = "MANUALLY CLOSED"
```

with:

```python
    icon, accent_outcome, status_word = _status_style(match["status"])
    accent = ui.accent_for_outcome(accent_outcome)
```

`is_open` is still read later in the function, so keep its assignment. In `summary_cmd`, replace:

```python
            icon = "✅" if t["status"] == "win" else ("❌" if t["status"] == "loss" else "🔒")
```

with:

```python
            icon = kinds.outcome_mark(_STATUS_OUTCOME.get(t["status"], "manual"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/test_trades_display.py tests/presentation/test_no_adhoc_color.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/commands/trades.py`
Expected:
- `_build_trade_detail_embed` below 17.
- `summary_cmd` below 54.
- `format_trade_row` (16), `performance_cmd` (12) and `_primary_source_label` (9) unchanged.
- `_status_style` absent.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/trades.py tests/test_trades_display.py
git commit -m "refactor(v110): !trade and !today read closed-trade marks from the registry

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/commands/trades.py tests/test_trades_display.py
```
