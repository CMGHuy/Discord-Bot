from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.commands.plans import format_plans_board
from tests.planning.test_plan_engine_model import _plan


def test_empty_board():
    assert format_plans_board([]) == "No live v2 plans."


def test_board_groups_by_status(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    import swingbot.config as config
    monkeypatch.setattr(embeds.account, "compute_position_size",
                        lambda entry, stop: {"shares": 100.0,
                                             "position_value": 10_000.0,
                                             "mode": "risk_pct"})
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    pending = _plan(plan_id="a", ticker="AAPL", entry_type="stop_entry",
                    trigger_price=105.0, expiry_bars=5)
    active = _plan(plan_id="b", ticker="MSFT", entry_price=100.0)
    record_transition(active, PlanStatus.ACTIVE, at="t")
    partial = _plan(plan_id="c", ticker="NVDA", entry_price=100.0,
                    legs_realized=[{"fraction": 0.5, "exit_price": 110.0,
                                    "r": 2.0, "reason": "tp1"}],
                    working_stop=100.0)
    record_transition(partial, PlanStatus.ACTIVE, at="t")
    record_transition(partial, PlanStatus.PARTIAL, at="t")

    board = format_plans_board([pending, active, partial],
                               prices={"MSFT": 104.0})
    assert board.index("PENDING") < board.index("AAPL")
    assert board.index("ACTIVE") < board.index("MSFT")
    assert board.index("PARTIAL") < board.index("NVDA")
    assert "trigger 105.00" in board
    assert "banked +2.00R/+10.0%/+$500.00 on 50%" in board
    assert "entry 110.00 → TP2 105.00 / trail 100.00" in board


def test_board_partial_falls_back_to_tp1_when_no_tp2(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    monkeypatch.setattr(embeds.account, "compute_position_size",
                        lambda entry, stop: None)
    partial = _plan(plan_id="d", ticker="TSLA", entry_price=100.0, tp1=102.0, tp2=None,
                    legs_realized=[{"fraction": 0.5, "exit_price": 102.0,
                                    "r": 1.4, "reason": "tp1"}],
                    working_stop=101.0)
    record_transition(partial, PlanStatus.ACTIVE, at="t")
    record_transition(partial, PlanStatus.PARTIAL, at="t")
    board = format_plans_board([partial])
    assert "entry 102.00 → TP1 (no TP2) 102.00 / trail 101.00" in board
    assert "$" not in board
