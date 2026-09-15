"""One partial plan must yield one answer across every v73 surface."""
import pytest

import swingbot.admin.app  # initialize API routes before endpoint import
from swingbot.admin.api_v1.trades import _row_from_plan
from swingbot.commands.plans import _partial_tail
from swingbot.core.presentation.plan_view import plan_view
from swingbot.core.scanning.plan_table import partial_position_line

PLAN = {"plan_id": "p1", "ticker": "AAPL", "status": "PARTIAL",
        "direction": "bullish", "strategy": "MACD", "horizon_key": "3m",
        "entry_price": 100.0, "trigger_price": 100.0, "stop_loss": 90.0,
        "tp1": 120.0, "tp2": None, "working_stop": None,
        "legs_realized": [{"fraction": 0.5, "exit_price": 121.0, "r": 2.1}],
        "tp1_fraction": 0.5, "expiry_bars": 5, "created_at": "2026-09-01",
        "badge": "WEAK", "quality_score": 3}


class Attr:
    def __init__(self, data): self._data = data
    def __getattr__(self, name): return self._data.get(name)


@pytest.fixture
def view():
    return plan_view(Attr(PLAN))


def test_projection_is_reference(view):
    assert (view.entry, round(view.stop, 2), view.target) == (121.0, 113.33, None)


def test_admin_row_agrees(view):
    row = _row_from_plan(dict(PLAN), None, set())
    assert (row["stop_loss"], row["target"], row["banked_exit_price"]) == (view.stop, view.target, view.entry)


def test_board_agrees(view):
    tail = _partial_tail(Attr(PLAN))
    assert f"{view.entry:.2f}" in tail and f"{view.stop:.2f}" in tail and "TP2" not in tail


def test_lifecycle_embed_agrees(view):
    line = partial_position_line(Attr(PLAN))
    assert f"{view.entry:.2f}" in line and f"{view.stop:.2f}" in line


def test_no_surface_shows_original_risk_stop():
    row = _row_from_plan(dict(PLAN), None, set())
    tail, line = _partial_tail(Attr(PLAN)), partial_position_line(Attr(PLAN))
    assert row["stop_loss"] != 90.0 and "90.00" not in tail and "90.00" not in line


def test_no_surface_shows_tp1_as_live_target():
    row = _row_from_plan(dict(PLAN), None, set())
    tail, line = _partial_tail(Attr(PLAN)), partial_position_line(Attr(PLAN))
    assert row["target"] is None and "target 120.00" not in line and "TP2 120.00" not in tail


def test_execution_feed_stop_agrees(view):
    """The fifth surface uses the legacy partial runner floor, not risk stop."""
    from swingbot.core.planning.plan_manager import resting_stop, stop_move_event
    from swingbot.core.presentation.instructions import instruction_for

    plan = Attr(PLAN)
    assert resting_stop(plan) == pytest.approx(view.stop)
    event = stop_move_event(plan, "2026-09-10", 0.25)
    assert event is not None
    headline = instruction_for(plan, event).headline
    assert f"{view.stop:.2f}" in headline and "90.00" not in headline
