"""v171 D2: a plan stores the quote it was built from; pre-v171 plans read None."""
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import TradePlanV2, plan_from_dict, plan_to_dict
from tests.planning.test_plan_engine_model import _plan

FIELDS = ("quote_at", "quote_kind", "quote_age_s", "quote_session", "price_confirmed")
STAMP = {"quote_at": "2026-10-16T14:30:01+00:00", "quote_kind": "mid",
         "quote_age_s": 1.4, "quote_session": "regular", "price_confirmed": True}


def test_new_fields_default_to_none():
    plan = _plan()
    assert all(getattr(plan, name) is None for name in FIELDS)


def test_fields_round_trip_through_the_dict():
    back = plan_from_dict(plan_to_dict(_plan(**STAMP)))
    assert {name: getattr(back, name) for name in FIELDS} == STAMP


def test_a_pre_v171_dict_reads_every_field_as_none():
    d = plan_to_dict(_plan())
    for name in FIELDS:
        d.pop(name)
    back = plan_from_dict(d)
    assert isinstance(back, TradePlanV2)
    assert all(getattr(back, name) is None for name in FIELDS)


def test_fields_round_trip_through_the_plan_store():
    store = PlanStore()
    store.add(_plan(plan_id="v171-q1", **STAMP))
    back = store.get("v171-q1")
    assert {name: getattr(back, name) for name in FIELDS} == STAMP


def test_unconfirmed_scan_price_round_trips_false_not_none():
    back = plan_from_dict(plan_to_dict(_plan(quote_kind="scan", price_confirmed=False)))
    assert back.price_confirmed is False and back.quote_kind == "scan"
