"""v173 §1: record_transition(extra=) merges extra keys into the appended entry."""
import pytest

from swingbot.core.planning import plan_engine
from swingbot.core.planning.plan_types import PlanStatus, record_transition
from tests.planning.test_plan_engine_model import _plan


def _active():
    plan = _plan()
    record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at="2026-10-01T14:00:00+00:00")
    return plan


def test_without_extra_the_entry_keeps_exactly_three_keys():
    plan = _active()
    record_transition(plan, PlanStatus.CLOSED, reason="manual", at="2026-10-02T15:00:00+00:00")
    assert plan.status_history[-1] == {"status": "CLOSED", "reason": "manual",
                                       "at": "2026-10-02T15:00:00+00:00"}


def test_extra_is_merged_into_the_entry():
    plan = _active()
    stamp = {"exit_price": 101.5, "price_source": "quote",
             "quote_ts": "2026-10-02T15:00:00+00:00", "bars_asof": "2026-10-01"}
    record_transition(plan, PlanStatus.CLOSED, reason="manual",
                      at="2026-10-02T15:00:00+00:00", extra={"override": stamp})
    assert plan.status_history[-1] == {"status": "CLOSED", "reason": "manual",
                                       "at": "2026-10-02T15:00:00+00:00", "override": stamp}
    assert plan.status == PlanStatus.CLOSED


def test_extra_none_value_is_kept_as_a_key():
    """A failed stamp is written as override: null, not left out."""
    plan = _active()
    record_transition(plan, PlanStatus.CLOSED, reason="manual", at="t", extra={"override": None})
    assert "override" in plan.status_history[-1]
    assert plan.status_history[-1]["override"] is None


def test_an_illegal_transition_still_raises_and_appends_nothing():
    plan = _plan()   # PENDING
    with pytest.raises(ValueError):
        record_transition(plan, PlanStatus.CLOSED, reason="manual", at="t",
                          extra={"override": None})
    assert plan.status_history == []
    assert plan.status == PlanStatus.PENDING


def test_extra_cannot_overwrite_the_three_core_keys():
    plan = _active()
    record_transition(plan, PlanStatus.CLOSED, reason="manual", at="t",
                      extra={"status": "X", "reason": "Y", "at": "Z", "override": None})
    entry = plan.status_history[-1]
    assert (entry["status"], entry["reason"], entry["at"]) == ("CLOSED", "manual", "t")


def test_plan_engine_reexports_the_same_function():
    assert plan_engine.record_transition is record_transition
