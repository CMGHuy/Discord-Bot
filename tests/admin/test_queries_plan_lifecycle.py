"""_plan_lifecycle -- the Plans tab's funnel, fill-rate and badge/confidence-
level aggregation. Pure over a list of plan-shaped objects; no Flask, no
PlanStore -- the endpoint test (test_api_v1_analytics.py) covers the wiring.
"""
from types import SimpleNamespace

from swingbot.admin.queries import _plan_lifecycle
from swingbot.core.planning.plan_engine import PlanStatus


def _plan(status, history, created_at="2026-01-01", confidence_level=3, badge="VALIDATED"):
    return SimpleNamespace(
        status=status, status_history=history, created_at=created_at,
        confidence_level=confidence_level, badge=badge,
    )


def test_funnel_counts_by_furthest_stage_ever_reached():
    plans = [
        _plan(PlanStatus.CANCELLED, [{"status": "CANCELLED", "at": "2026-01-02"}]),
        _plan(PlanStatus.ACTIVE, [{"status": "ACTIVE", "at": "2026-01-02"}]),
        _plan(PlanStatus.PARTIAL, [
            {"status": "ACTIVE", "at": "2026-01-02"},
            {"status": "PARTIAL", "at": "2026-01-05"},
        ]),
        _plan(PlanStatus.CLOSED, [
            {"status": "ACTIVE", "at": "2026-01-02"},
            {"status": "PARTIAL", "at": "2026-01-05"},
            {"status": "CLOSED", "at": "2026-01-09"},
        ]),
        # Closed WITHOUT ever hitting PARTIAL -- stopped out directly.
        _plan(PlanStatus.CLOSED, [
            {"status": "ACTIVE", "at": "2026-01-02"},
            {"status": "CLOSED", "at": "2026-01-04"},
        ]),
    ]
    result = _plan_lifecycle(plans)
    assert result["funnel"] == {
        "posted": 5, "filled": 4, "hit_tp1": 2, "closed": 2,
    }


def test_funnel_a_still_pending_plan_is_in_flight_not_a_failure():
    plans = [_plan(PlanStatus.PENDING, [])]
    result = _plan_lifecycle(plans)
    assert result["funnel"]["posted"] == 1
    assert result["funnel"]["filled"] == 0
    assert result["in_flight"] == 1


def test_fill_rate_scoped_to_resolved_plans_only():
    plans = [
        _plan(PlanStatus.CANCELLED, [{"status": "CANCELLED", "at": "2026-01-03"}],
              created_at="2026-01-01"),
        _plan(PlanStatus.CLOSED, [
            {"status": "ACTIVE", "at": "2026-01-05"},
            {"status": "CLOSED", "at": "2026-01-10"},
        ], created_at="2026-01-01"),
        # Still open -- must NOT count toward fill_rate either way.
        _plan(PlanStatus.PENDING, [], created_at="2026-01-01"),
    ]
    result = _plan_lifecycle(plans)
    assert result["fill_rate"]["resolved_n"] == 2
    assert result["fill_rate"]["fill_rate_pct"] == 50.0
    # Jan 1 -> Jan 5 = 4 days, the only filled resolved plan.
    assert result["fill_rate"]["median_days_to_fill"] == 4.0


def test_fill_rate_null_with_no_resolved_plans():
    plans = [_plan(PlanStatus.PENDING, [])]
    result = _plan_lifecycle(plans)
    assert result["fill_rate"]["resolved_n"] == 0
    assert result["fill_rate"]["fill_rate_pct"] is None
    assert result["fill_rate"]["median_days_to_fill"] is None


def test_badge_and_confidence_level_counts():
    plans = [
        _plan(PlanStatus.PENDING, [], badge="VALIDATED", confidence_level=5),
        _plan(PlanStatus.PENDING, [], badge="VALIDATED", confidence_level=3),
        _plan(PlanStatus.PENDING, [], badge="WEAK", confidence_level=1),
    ]
    result = _plan_lifecycle(plans)
    assert result["badges"] == {"VALIDATED": 2, "WEAK": 1}
    assert result["confidence_levels"] == {"5": 1, "3": 1, "1": 1}


def test_empty_plan_list_returns_well_formed_zeros():
    result = _plan_lifecycle([])
    assert result["funnel"] == {"posted": 0, "filled": 0, "hit_tp1": 0, "closed": 0}
    assert result["in_flight"] == 0
    assert result["fill_rate"] == {"resolved_n": 0, "fill_rate_pct": None, "median_days_to_fill": None}
    assert result["badges"] == {}
    assert result["confidence_levels"] == {}
