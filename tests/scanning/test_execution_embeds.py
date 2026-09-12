"""v81 execution embed rendering uses the shared presentation kit."""
import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import tokens
from swingbot.core.presentation.instructions import Instruction
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
    embed = execution_embeds.render(_instruction(warnings=("⚠ heat",)))
    assert embed.title == "▲ LONG NVDA — MOVE STOP"
    assert embed.description.splitlines() == ["⚠ heat", "**MOVE STOP → 107.30 now**", "trail; +0.6R"]
    assert "plan plan-123" in embed.footer.text


@pytest.mark.parametrize("tone,level,expected", [
    ("level", 5, tokens.ACCENT_RAMP[5]), ("inert", None, tokens.ACCENT_BLOCKED),
    ("good", None, tokens.ACCENT_RAMP[5]), ("bad", None, tokens.ACCENT_RAMP[1]),
])
def test_render_uses_shared_accents(tone, level, expected):
    assert execution_embeds.render(_instruction(tone=tone, level=level)).color.value == expected


def test_ticket_and_event_embeds():
    item = make_item(plan_v2=make_plan_v2(entry_type="stop_entry", trigger_price=101.0))
    item.paper_logged = True
    ticket = execution_embeds.build_ticket_embed(item, item.plan_v2)
    assert ticket.title == "▲ LONG NVDA — PLACE"
    assert "**BUY STOP 101.00 · size n/a**" in ticket.description
    event = execution_embeds.build_instruction_embed(
        item.plan_v2, PlanEvent(item.plan_v2.plan_id, "cancelled_expired", {"bars_waited": 6}))
    assert event.title == "▲ LONG NVDA — CANCEL"
