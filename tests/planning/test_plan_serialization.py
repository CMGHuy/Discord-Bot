import dataclasses

from swingbot.core.planning.plan_engine import plan_to_dict, plan_from_dict
from tests.planning.test_plan_engine_model import _plan


def test_exact_round_trip():
    p = _plan(quality_breakdown=[("regime", 15), ("badge", 20)],
              status_history=[{"status": "ACTIVE", "reason": "x", "at": "t"}])
    q = plan_from_dict(plan_to_dict(p))
    for f in dataclasses.fields(type(p)):
        # JSON turns breakdown tuples into lists -- normalize before comparing
        a, b = getattr(p, f.name), getattr(q, f.name)
        if f.name == "quality_breakdown":
            a = [list(x) for x in a]
        assert a == b, f.name


def test_unknown_keys_ignored_and_missing_new_fields_defaulted():
    d = plan_to_dict(_plan())
    d["some_future_key"] = 123
    q = plan_from_dict(d)          # must not raise
    assert q.plan_id == "p1"


def test_json_safe():
    import json
    json.dumps(plan_to_dict(_plan()))   # must not raise


def test_legacy_plan_record_with_tier_still_loads():
    """v32 Task 11: A/B/C tier was retired from TradePlanV2. Persisted
    records written before this land still carry a `tier` key -- loading
    one must not raise, users have live plans on disk. Already true by
    construction (plan_from_dict filters to known dataclass fields, see
    test_unknown_keys_ignored_and_missing_new_fields_defaulted above), but
    this pins the exact scenario the plan calls out by name."""
    d = plan_to_dict(_plan())
    d["tier"] = "A"
    q = plan_from_dict(d)
    assert q.ticker == "AAPL"
    assert not hasattr(q, "tier")
    assert q.confidence_level is None
