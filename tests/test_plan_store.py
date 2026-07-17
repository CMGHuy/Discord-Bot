from swingbot.core.plan_engine import PlanStatus, record_transition
from swingbot.core.plan_store import PlanStore
from tests.test_plan_engine_model import _plan


def test_add_get_update_roundtrip(tmp_path):
    store = PlanStore(path=str(tmp_path / "plans.json"))
    p = _plan()
    store.add(p)
    got = store.get("p1")
    assert got is not None and got.ticker == "AAPL"

    record_transition(got, PlanStatus.ACTIVE, reason="fill", at="t1")
    store.update(got)
    fresh = PlanStore(path=str(tmp_path / "plans.json"))   # reload from disk
    assert fresh.get("p1").status == PlanStatus.ACTIVE
    assert fresh.get("p1").status_history[-1]["reason"] == "fill"


def test_open_plans_filters_terminal_states(tmp_path):
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_plan(plan_id="a"))                                   # PENDING
    active = _plan(plan_id="b"); record_transition(active, PlanStatus.ACTIVE, at="t")
    store.add(active)
    done = _plan(plan_id="c")
    record_transition(done, PlanStatus.CANCELLED, reason="expired", at="t")
    store.add(done)
    assert {p.plan_id for p in store.open_plans()} == {"a", "b"}


def test_update_unknown_plan_raises(tmp_path):
    store = PlanStore(path=str(tmp_path / "plans.json"))
    import pytest
    with pytest.raises(KeyError):
        store.update(_plan(plan_id="ghost"))


def test_corrupt_file_yields_empty_store_not_crash(tmp_path):
    path = tmp_path / "plans.json"
    path.write_text("{torn write", encoding="utf-8")
    store = PlanStore(path=str(path))
    assert store.all() == []


def test_no_tmp_file_left_behind(tmp_path):
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_plan())
    assert not (tmp_path / "plans.json.tmp").exists()
