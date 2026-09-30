import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import ansi, kinds
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning.embeds import build_plan_event_embed
from swingbot.core.scanning.lifecycle_embeds import CLOSE_REASON_STYLES, PLAN_EVENT_KINDS
from swingbot.core.scanning import plan_table
from tests.planning.test_plan_engine_model import _plan


def _embed(transition, detail=None, **plan_kw):
    return build_plan_event_embed(_plan(**plan_kw),
                                  PlanEvent("p1", transition, detail or {}))


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


def test_tp1_partial_embed_shows_banked_stats_and_partial_position(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    from swingbot import config
    monkeypatch.setattr(plan_table.account, "compute_position_size",
                        lambda entry, stop: {"shares": 100.0,
                                             "position_value": 10_000.0,
                                             "mode": "risk_pct"})
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    e = _embed("tp1_partial", {"fraction": 0.5, "exit_price": 110.0, "r": 2.0},
              legs_realized=[{"fraction": 0.5, "exit_price": 110.0,
                              "r": 2.0, "reason": "tp1"}],
              working_stop=101.33)
    assert "💰" in e.title
    banked = next(f.value for f in e.fields if f.name == "Banked")
    assert "50% @ 110.00" in banked
    assert "+2.00R" in banked
    assert "+10.0%" in banked
    assert "+$500.00" in banked
    partial = next(f.value for f in e.fields if f.name == "Partial position")
    assert partial == "entry 110.00 → target 105.00 / stop 101.33"


def test_tp1_partial_embed_omits_dollar_figure_when_unsized(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    from swingbot import config
    monkeypatch.setattr(plan_table.account, "compute_position_size",
                        lambda entry, stop: None)
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    e = _embed("tp1_partial", {"fraction": 0.5, "exit_price": 110.0, "r": 2.0},
              legs_realized=[{"fraction": 0.5, "exit_price": 110.0,
                              "r": 2.0, "reason": "tp1"}],
              working_stop=101.33)
    banked = next(f.value for f in e.fields if f.name == "Banked")
    assert "$" not in banked


def test_tp1_partial_embed_signs_a_negative_banked_amount(monkeypatch):
    """A leg banked below entry (gap-through fill on a scale-out) must read
    '-$500.00', never '+$-500.00' -- the same sign-safe form leg_rows() uses."""
    import swingbot.core.scanning.embeds as embeds
    from swingbot import config
    monkeypatch.setattr(plan_table.account, "compute_position_size",
                        lambda entry, stop: {"shares": 100.0,
                                             "position_value": 10_000.0,
                                             "mode": "risk_pct"})
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    e = _embed("tp1_partial", {"fraction": 0.5, "exit_price": 90.0, "r": -1.0},
              entry_price=100.0, stop_loss=95.0,
              legs_realized=[{"fraction": 0.5, "exit_price": 90.0,
                              "r": -1.0, "reason": "tp1"}],
              working_stop=101.33)
    banked = next(f.value for f in e.fields if f.name == "Banked")
    assert "-$500.00" in banked
    assert "+$-" not in banked


def test_tp1_partial_embed_omits_pct_when_entry_is_unusable(monkeypatch):
    """banked_leg_pct_and_amount returns (None, None) for an unusable entry --
    the embed must drop the % clause rather than crash on the format spec."""
    import swingbot.core.scanning.embeds as embeds
    from swingbot import config
    monkeypatch.setattr(plan_table.account, "compute_position_size",
                        lambda entry, stop: None)
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    e = _embed("tp1_partial", {"fraction": 0.5, "exit_price": 110.0, "r": 2.0},
              entry_price=0.0, trigger_price=0.0,
              legs_realized=[{"fraction": 0.5, "exit_price": 110.0,
                              "r": 2.0, "reason": "tp1"}],
              working_stop=101.33)
    banked = next(f.value for f in e.fields if f.name == "Banked")
    assert banked == "50% @ 110.00 (+2.00R)"


def test_partial_position_line_marks_no_tp2_runner_as_trailing():
    from swingbot.core.scanning.embeds import partial_position_line
    p = _plan(status="PARTIAL", entry_price=100.0, stop_loss=95.0, tp1=102.0, tp2=None,
              legs_realized=[{"fraction": 0.5, "exit_price": 102.0,
                              "r": 1.4, "reason": "tp1"}],
              working_stop=101.33)
    # v73: TP1 was banked, so a runner with no TP2 has only its trail.
    assert partial_position_line(p) == "entry 102.00 → trailing stop 101.33"


def test_partial_position_line_falls_back_to_runner_floor_when_no_working_stop():
    from swingbot.core.scanning.embeds import partial_position_line
    p = _plan(status="PARTIAL", entry_price=100.0, stop_loss=95.0, tp1=102.0, tp2=105.0,
              legs_realized=[{"fraction": 0.5, "exit_price": 102.0,
                              "r": 1.4, "reason": "tp1"}],
              working_stop=None)
    # runner_floor(100, 102) = 100 + 2/3 * (102 - 100) = 101.33
    assert partial_position_line(p) == "entry 102.00 → target 105.00 / stop 101.33"


def test_close_reasons_have_distinct_copy():
    titles = {r: _embed("closed", {"reason": r, "exit_price": 100.0}).title
              for r in ("loss", "scratch", "win", "tp1_runner_be",
                        "tp1_runner_tp2", "tp1_runner_trail")}
    assert len(set(titles.values())) == 6


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
