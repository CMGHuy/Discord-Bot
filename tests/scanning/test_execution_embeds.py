"""v81 execution embed rendering uses the shared presentation kit."""
import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import ansi, kinds, tokens
from swingbot.core.presentation.instructions import Instruction
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import execution_embeds
from tests.scanning.test_embeds_v3 import make_item, make_plan_v2


@pytest.fixture(autouse=True)
def _unsized(monkeypatch):
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: None)


def _instruction(**kwargs):
    base = dict(verb="MOVE STOP", ticker="NVDA", direction="bullish",
                headline="MOVE STOP → 107.30 now", lines=("trail; +0.6R",),
                plan_id="plan-123456789")
    base.update(kwargs)
    return Instruction(**base)


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
