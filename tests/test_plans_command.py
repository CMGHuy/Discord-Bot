from swingbot.core.plan_engine import PlanStatus, record_transition
from swingbot.commands.plans import format_plans_board
from tests.test_plan_engine_model import _plan


def test_empty_board():
    assert format_plans_board([]) == "No live plans."


def test_board_groups_by_status():
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
    assert "banked +2.00R on 50%" in board
