"""v200: issue-time provenance is live only for the wall-clock stamp."""
import json
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
from swingbot.core.scanning import analyze
from tests.planning.test_gap_sizing import PRE_V183_PLAN_KEYS, _plan, _signed_gaps

ISSUED = "2026-08-04T13:02:11+00:00"


def _attach_issued(monkeypatch, plan, df, issued_at):
    """Attach with an explicit issue time, as the replay path does."""
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *args, **kwargs: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *args, **kwargs: plan)
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")
    monkeypatch.setattr(analyze, "stamp_entry_context", lambda plan, df, asof: None)
    item = SimpleNamespace(rs_combined=None, sector_rs_percentile=None, conf=None, htf_bias=None,
                           target_confluence=None)
    scenario = SimpleNamespace(direction=plan.direction, entry=100.0)
    analyze.attach_plan_v2(item, scenario, df, "ZZZ", "3m", issued_at=issued_at)
    return item.plan_v2


def test_the_field_defaults_to_none_and_leaves_the_doc_unchanged():
    plan = _plan("bullish")
    assert plan.issued_at_source is None
    assert "issued_at_source" not in plan_to_dict(plan)
    assert list(plan_to_dict(plan)) == PRE_V183_PLAN_KEYS


@pytest.mark.parametrize("source", ["live", "discord"])
def test_the_source_round_trips_through_json(source):
    plan = _plan("bullish")
    plan.issued_at, plan.issued_at_source = ISSUED, source
    doc = json.loads(json.dumps(plan_to_dict(plan)))
    assert doc["issued_at_source"] == source
    restored = plan_from_dict(doc)
    assert (restored.issued_at, restored.issued_at_source) == (ISSUED, source)


def test_a_doc_written_before_v200_loads_with_no_source():
    doc = plan_to_dict(_plan("bullish"))
    doc["issued_at"] = ISSUED
    doc.pop("issued_at_source", None)
    restored = plan_from_dict(doc)
    assert restored.issued_at == ISSUED and restored.issued_at_source is None


@pytest.mark.parametrize("passed", [None, ""])
def test_the_live_wall_clock_stamp_is_tagged_live(monkeypatch, passed):
    plan = _attach_issued(monkeypatch, _plan("bullish"), _signed_gaps(), passed)
    assert plan.issued_at is not None
    assert plan.issued_at_source == "live"
    assert list(plan_to_dict(plan)) == PRE_V183_PLAN_KEYS + ["issued_at_source"]


@pytest.mark.parametrize("passed", [ISSUED, "2025-01-10T21:00:00+00:00"])
def test_a_passed_issued_at_is_kept_and_carries_no_source(monkeypatch, passed):
    plan = _attach_issued(monkeypatch, _plan("bullish"), _signed_gaps(), passed)
    assert plan.issued_at == passed
    assert plan.issued_at_source is None
    assert "issued_at_source" not in plan_to_dict(plan)
