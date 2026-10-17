"""v81 execution embed rendering uses the shared presentation kit."""
import pytest

from swingbot import config
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import ansi, kinds, tokens
from swingbot.core.presentation.instructions import Instruction, Money
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import execution_embeds
from tests.scanning.test_embeds_v3 import make_item, make_plan_v2

_REAL_LINKED_TRADE = execution_embeds._linked_trade      # captured before the autouse patch


@pytest.fixture(autouse=True)
def _unsized(monkeypatch):
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: None)
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: None)


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
    assert "**▶ BUY STOP 101.00 · size n/a**" in ticket.description
    assert ticket.footer.text.startswith(tokens.DISCLAIMER)
    event = execution_embeds.build_instruction_embed(
        item.plan_v2, PlanEvent(item.plan_v2.plan_id, "cancelled_expired", {"bars_waited": 6}))
    assert event.title == "🏁 ▲ LONG NVDA · EXPIRED · ⏹️"


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
    tp1 = execution_embeds.build_instruction_embed(plan, PlanEvent(plan.plan_id, "tp1_partial", {
        "fraction": 0.5, "exit_price": 105.0, "r": 1.0, "working_stop": 100.0}))
    assert tp1.title == "💰 ▲ LONG NVDA · TP1"
    moved = execution_embeds.build_instruction_embed(plan, PlanEvent(plan.plan_id, "stop_moved", {
        "new": 102.0, "r_moved": 0.4}))
    assert moved.title == "✂️ ▲ LONG NVDA · MOVE STOP"


def test_closed_loss_is_a_red_result():
    plan = make_plan_v2()          # entry 100, stop 95
    embed = execution_embeds.build_instruction_embed(plan, PlanEvent(
        plan.plan_id, "closed", {"reason": "stop", "exit_price": 95.0, "session": "regular"}))
    assert embed.title.startswith("🏁 ▲ LONG NVDA · EXITED · ❌ LOSS")
    assert embed.color.value == kinds.RESULT_REDS[1]


def test_extended_hours_close_is_close_at_market():
    plan = make_plan_v2()
    embed = execution_embeds.build_instruction_embed(plan, PlanEvent(
        plan.plan_id, "closed", {"reason": "stop", "exit_price": 95.0, "session": "extended"}))
    assert "CLOSE AT MARKET" in embed.title
    assert embed.description.count("CLOSE AT MARKET now") == 1


@pytest.mark.parametrize("transition,word", [("cancelled_invalidated", "INVALIDATED"),
                                              ("cancelled_expired", "EXPIRED")])
def test_expired_and_invalidated_post_as_grey_result_never_scratch(transition, word):
    plan = make_plan_v2()
    embed = execution_embeds.build_instruction_embed(plan, PlanEvent(plan.plan_id, transition, {}))
    assert embed.title == f"🏁 ▲ LONG NVDA · {word} · ⏹️"
    assert "SCRATCH" not in embed.title and "⚪" not in embed.title
    assert "SCRATCH" not in embed.push_text
    assert embed.color.value == kinds.RESULT_GREY


def test_ticket_money_comes_from_the_sizing_snapshot(monkeypatch):
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot",
                        lambda entry, plan: {"shares": 10.7, "risk_amount": 50.0})
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    item = make_item(plan_v2=make_plan_v2(entry_type="stop_entry", trigger_price=101.0))
    item.paper_logged = True
    text = execution_embeds.build_ticket_embed(item, item.plan_v2).description
    # make_plan_v2: entry_price 100, stop 95, TP1 110, TP2 120 -> 10 sh, 5 + 5
    assert "**▶ BUY STOP 101.00 · 10 sh**" in text
    assert "🛑 SELL STOP 95.00 · if hit -$50.00 · −1.0R" in text
    assert "💰 SELL LIMIT 110.00 · 5 sh · if hit +$50.00 · +2.0R" in text
    assert "🏃 5 sh: 🎯 SELL LIMIT 120.00 · if hit +$100.00 · +4.0R" in text


def test_ticket_money_without_a_snapshot_is_unsized(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    assert execution_embeds._ticket_money(make_plan_v2()) == Money(currency="$", shares=None)


def _tp1_event(plan):
    return PlanEvent(plan.plan_id, "tp1_partial", {
        "fraction": 0.5, "exit_price": 110.0, "r": 2.0, "working_stop": 106.67})


def test_lifecycle_money_comes_from_the_linked_record(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: {
        "plan_id": plan_id, "shares": 10.5, "realized_pnl_amount": None})
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot",
                        lambda entry, plan: pytest.fail("re-sized at render time"))
    plan = make_plan_v2()          # entry 100, stop 95, TP1 110
    embed = execution_embeds.build_instruction_embed(plan, _tp1_event(plan))
    # 10 sh printed, 5 at TP1; realised = 10.5 × 0.5 × 10.00 = 52.50
    assert "**💰 TP1 FILLED 5 sh @ 110.00 · 🧾 +$52.50 · +2.0R**" in embed.description


def test_without_a_linked_record_shares_come_from_the_snapshot_and_no_dollars(monkeypatch):
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: {"shares": 10.5})
    plan = make_plan_v2()
    embed = execution_embeds.build_instruction_embed(plan, _tp1_event(plan))
    assert "**💰 TP1 FILLED 5 sh @ 110.00 · 🧾 +2.0R**" in embed.description
    assert "$" not in embed.description


def test_event_money_carries_the_records_settled_amount(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: {
        "shares": 54.41, "realized_pnl_amount": 412.5})
    assert execution_embeds._event_money(make_plan_v2()) == Money(
        currency="$", shares=54, realized_amount=412.5, record_shares=54.41)


def test_a_record_without_shares_falls_back_to_the_unpriced_snapshot(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: {
        "shares": None, "realized_pnl_amount": None})
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: {"shares": 7.9})
    assert execution_embeds._event_money(make_plan_v2()) == Money(currency="$", shares=7)


def test_linked_trade_never_raises(monkeypatch):
    from swingbot.core.tracking import performance

    class _Boom:
        def trade_for_plan(self, plan_id):
            raise RuntimeError("db down")

    monkeypatch.setattr(performance, "TradeLog", _Boom)
    assert _REAL_LINKED_TRADE("plan-1") is None
    assert _REAL_LINKED_TRADE("") is None


def test_be_moved_embed_projects_from_the_record(monkeypatch):
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: {
        "shares": 10.5, "realized_pnl_amount": None})
    plan = make_plan_v2()
    embed = execution_embeds.build_instruction_embed(
        plan, PlanEvent(plan.plan_id, "be_moved", {"working_stop": 100.0}))
    assert embed.description.splitlines() == [
        "**🛑 MOVE SELL STOP → 100.00 now**", "⚖ break-even", "🔒 if it fills: +$0.00 · 0.0R total"]


def _closed_loss(plan):
    return PlanEvent(plan.plan_id, "closed",
                     {"reason": "loss", "exit_price": 95.0, "session": "regular"})


def test_a_close_prints_the_linked_records_settled_dollars(monkeypatch):
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: {
        "plan_id": plan_id, "shares": 9.43, "realized_pnl_amount": -47.15,
        "status": "loss", "legs": []})
    plan = make_plan_v2()          # entry 100, stop 95
    embed = execution_embeds.build_instruction_embed(plan, _closed_loss(plan))
    money = tokens.fmt_money(-47.15, config.CURRENCY_SYMBOL)
    assert f"🧾 {money} · −1.0R (paper, gross)" in embed.description.splitlines()


def test_a_close_without_a_linked_record_prints_r_only(monkeypatch):
    monkeypatch.setattr(execution_embeds, "_linked_trade", lambda plan_id: None)
    plan = make_plan_v2()
    embed = execution_embeds.build_instruction_embed(plan, _closed_loss(plan))
    assert "🧾 −1.0R (paper, gross)" in embed.description.splitlines()
