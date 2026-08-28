from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.scanning.embeds import build_plan_event_embed
from swingbot.core.scanning import plan_table
from tests.planning.test_plan_engine_model import _plan


def _embed(transition, detail=None, **plan_kw):
    return build_plan_event_embed(_plan(**plan_kw),
                                  PlanEvent("p1", transition, detail or {}))


def test_filled_embed():
    e = _embed("filled", {"entry_price": 106.0})
    assert "ENTRY TRIGGERED" in e.title and "🎯" in e.title
    assert any("106" in (f.value or "") for f in e.fields)


def test_expired_and_invalidated_embeds():
    assert "⏱" in _embed("cancelled_expired", {"bars_waited": 6}).title
    assert "❌" in _embed("cancelled_invalidated", {"live_price": 94.0}).title


def test_be_moved_embed():
    e = _embed("be_moved", {"working_stop": 100.0})
    assert "🛡" in e.title
    assert any("100" in (f.value or "") for f in e.fields)


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


def test_partial_position_line_falls_back_to_tp1_when_no_tp2():
    from swingbot.core.scanning.embeds import partial_position_line
    p = _plan(entry_price=100.0, stop_loss=95.0, tp1=102.0, tp2=None,
              legs_realized=[{"fraction": 0.5, "exit_price": 102.0,
                              "r": 1.4, "reason": "tp1"}],
              working_stop=101.33)
    assert partial_position_line(p) == ("entry 102.00 → target 102.00 "
                                        "(tp1, no tp2) / stop 101.33")


def test_partial_position_line_falls_back_to_runner_floor_when_no_working_stop():
    from swingbot.core.scanning.embeds import partial_position_line
    p = _plan(entry_price=100.0, stop_loss=95.0, tp1=102.0, tp2=105.0,
              legs_realized=[{"fraction": 0.5, "exit_price": 102.0,
                              "r": 1.4, "reason": "tp1"}],
              working_stop=None)
    # runner_floor(100, 102) = 100 + 2/3 * (102 - 100) = 101.33
    assert partial_position_line(p) == "entry 102.00 → target 105.00 / stop 101.33"


def test_close_reasons_have_distinct_copy():
    titles = {r: _embed("closed", {"reason": r, "exit_price": 100.0}).title
              for r in ("loss", "scratch", "tp1_runner_be", "tp1_runner_tp2",
                        "tp1_runner_trail")}
    assert len(set(titles.values())) == 5
