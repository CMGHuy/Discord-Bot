"""v81: the execution feed's delivery ledger on TradePlanV2, and the one
break-even formula the manager and the order ticket share."""
from swingbot.core.planning.plan_types import (breakeven_trigger, plan_from_dict,
                                               plan_to_dict)
from tests.planning.test_plan_engine_model import _plan


def test_a_new_plan_owes_the_reader_nothing():
    plan = _plan()
    assert plan.notified_stop is None
    assert plan.pending_notice is None


def test_a_row_persisted_before_v81_loads_with_an_empty_ledger():
    row = plan_to_dict(_plan())
    del row["notified_stop"], row["pending_notice"]
    plan = plan_from_dict(row)
    assert plan.notified_stop is None
    assert plan.pending_notice is None


def test_the_ledger_round_trips_through_the_persisted_dict():
    plan = _plan(notified_stop=101.5, pending_notice={
        "transition": "closed",
        "detail": {"reason": "loss", "exit_price": 94.5, "session": "regular"},
        "at": "2026-09-10T15:00:00+00:00",
    })
    assert plan_from_dict(plan_to_dict(plan)) == plan


def test_breakeven_trigger_is_the_fraction_of_the_way_to_tp1():
    plan = _plan(direction="bullish", tp1=110.0, breakeven_trigger_fraction=0.5)
    assert breakeven_trigger(plan, 100.0) == 105.0


def test_breakeven_trigger_mirrors_for_a_short():
    plan = _plan(direction="bearish", stop_loss=105.0, tp1=90.0,
                 breakeven_trigger_fraction=0.5)
    assert breakeven_trigger(plan, 100.0) == 95.0
