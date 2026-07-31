import json
import types

import pytest

import swingbot.commands.scanning as scanning
import swingbot.config as config
import swingbot.core.gate.persistence as persistence
from swingbot.core.plan_store import PlanStore
from tests.fixtures.gate import uptrend_daily
from tests.fixtures.gate.plans import make_plan


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "SHADOW_PATH", str(tmp_path / "shadow.jsonl"))
    monkeypatch.setattr(config, "GATE_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "GATE_MIN_TIER", "C", raising=False)
    store = PlanStore(path=str(tmp_path / "plans.json"))
    plan = make_plan(created_at="2026-07-13")
    store.add(plan)
    candidate = types.SimpleNamespace(ticker="TEST", strategy=plan.strategy,
                                      plan=plan, df_daily=uptrend_daily())
    return store, candidate


@pytest.mark.parametrize("mode", ["shadow", "inform", "enforce"])
def test_shadow_log_written_in_every_mode(env, monkeypatch, mode):
    store, candidate = env
    monkeypatch.setattr(config, "GATE_MODE", mode, raising=False)
    decision, result = scanning._gate_evaluate(candidate, store, macro_snap=None)
    assert result is not None
    assert store.get_extra(candidate.plan.plan_id, "gate")            # attached
    with open(persistence.SHADOW_PATH, encoding="utf-8") as fh:
        row = json.loads(fh.readline())
    assert row["plan_id"] == candidate.plan.plan_id
    assert row["advisory_decision"] in ("pass", "downgrade", "block")


def test_shadow_mode_renders_nothing(env, monkeypatch):
    store, candidate = env
    monkeypatch.setattr(config, "GATE_MODE", "shadow", raising=False)
    monkeypatch.setattr(config, "GATE_SHOW_IN_SHADOW", False, raising=False)
    _, result = scanning._gate_evaluate(candidate, store, macro_snap=None)
    assert scanning._gate_render_payload(result) is None    # embeds byte-identical
    monkeypatch.setattr(config, "GATE_MODE", "inform", raising=False)
    assert scanning._gate_render_payload(result) is not None


def test_gate_disabled_is_noop(env, monkeypatch):
    store, candidate = env
    monkeypatch.setattr(config, "GATE_ENABLED", False, raising=False)
    assert scanning._gate_evaluate(candidate, store, macro_snap=None) == ("pass", None)
