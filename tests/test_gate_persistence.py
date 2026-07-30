import json

import pytest

import swingbot.core.gate.persistence as persistence
from swingbot.core.gate.persistence import attach_to_plan, blocked_log, shadow_log
from swingbot.core.gate.types import CheckResult, GateResult
from swingbot.core.plan_store import PlanStore
from tests.fixtures.gate.plans import make_plan


def _result(tier="B"):
    checks = (CheckResult("rf_fake_breakout", "redflag", "fail", 10.0, "trap", {}),)
    return GateResult(ticker="TEST", strategy="Break & Retest", as_of="2026-07-14",
                      checks=checks, score=48.0, tier=tier,
                      hard_blocks=(), macro_stale=False, advisory_decision="block")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "BLOCKED_PATH", str(tmp_path / "blocked.jsonl"))
    monkeypatch.setattr(persistence, "SHADOW_PATH", str(tmp_path / "shadow.jsonl"))
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(make_plan())
    return store


def test_attach_round_trip(env):
    assert attach_to_plan(env, "p_test_0001", _result()) is True
    stored = env.get_extra("p_test_0001", "gate")
    assert stored["tier"] == "B" and stored["checks"][0]["check_id"] == "rf_fake_breakout"
    assert env.get("p_test_0001") is not None          # legacy load path unbroken
    assert attach_to_plan(env, "p_missing", _result()) is False


def test_logs_append_valid_jsonl(env):
    blocked_log(_result("C"), "block", "rf_fake_breakout")
    shadow_log(_result(), plan_id="p_test_0001")
    for path in (persistence.BLOCKED_PATH, persistence.SHADOW_PATH):
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh]
        assert len(rows) == 1 and rows[0]["ticker"] == "TEST"
    with open(persistence.SHADOW_PATH, encoding="utf-8") as fh:
        row = json.loads(fh.readline())
    assert row["advisory_decision"] == "block"
    assert row["fired_flags"] == ["rf_fake_breakout"]
