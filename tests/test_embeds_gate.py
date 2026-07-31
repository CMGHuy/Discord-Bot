"""Alert embed checklist field (G123). gate_embed_fields is the pure render
matrix; build_embed wiring is proven end-to-end at the bottom of this file.

Note: the plan's Task G82 ("checklist Discord embed string builders") was
cut by the 2026-07 win-rate audit as pure display formatting -- this file's
_result() fixture (a B-tier, 2-flag GateResult) is defined fresh here
rather than imported from a tests/test_gate_render.py that was never
built."""
import dataclasses

from swingbot import config
from swingbot.core.gate.render import gate_embed_fields
from swingbot.core.gate.types import CheckResult, GateResult
from swingbot.core.scanning.embeds import build_embed
from swingbot.core.scanning.engine import ScanItem
from tests.test_embeds_v3 import (
    PERF_STATS_EMPTY, _isolated_scan_snapshots,  # noqa: F401 -- autouse fixture
    make_conf, make_legacy_plan, make_plan_v2, make_result,
)


def _result(**overrides) -> GateResult:
    checks = (
        CheckResult("htf_trend", "context", "pass", 15.0, "aligned with the higher timeframe", {}),
        CheckResult("rf_fake_breakout", "redflag", "fail",
                   12.0, "breakout on dead volume (0.4x)", {}),
        CheckResult("rf_thin_session", "redflag", "warn", 6.0, "thin session", {}),
        CheckResult("not_chasing", "timing", "pass", 8.0, "not chasing", {}),
    )
    base = dict(ticker="TEST", strategy="Break & Retest", as_of="2026-07-14",
               checks=checks, score=61.0, tier="B", hard_blocks=(),
               macro_stale=False, advisory_decision="downgrade")
    base.update(overrides)
    return GateResult(**base)


def test_inform_renders_checklist_and_flags():
    fields = gate_embed_fields(_result(), "inform", show_in_shadow=False)
    names = [n for n, _ in fields]
    assert names[0] == "📋 Checklist — B (61)"
    assert any(n.startswith("🚩") for n in names)      # flags fired → table field
    # the fixture's advisory_decision is "downgrade", not "block" → no ⛔ line
    assert not any("ships anyway" in v for _, v in fields)


def test_advisory_block_line_golden():
    result = dataclasses.replace(_result(), advisory_decision="block")
    fields = gate_embed_fields(result, "inform", show_in_shadow=False)
    flat = "\n".join(v for _, v in fields)
    assert "⛔ 2 red flags — plan ships anyway; your call" in flat
    assert "Fake breakout" in flat


def test_shadow_render_matrix():
    assert gate_embed_fields(_result(), "shadow", show_in_shadow=False) == []
    assert gate_embed_fields(_result(), "shadow", show_in_shadow=True) != []
    assert gate_embed_fields(_result(), "enforce", show_in_shadow=False) != []


def test_none_result_renders_nothing():
    assert gate_embed_fields(None, "inform", show_in_shadow=False) == []


def test_clean_result_has_no_redflag_field():
    all_pass = tuple(dataclasses.replace(c, status="pass") if c.status != "pass" else c
                     for c in _result().checks)
    clean = dataclasses.replace(_result(), checks=all_pass,
                                advisory_decision="pass", tier="A+", score=95.0)
    fields = gate_embed_fields(clean, "inform", show_in_shadow=False)
    names = [n for n, _ in fields]
    assert names == ["📋 Checklist — A+ (95)"]           # no red-flag field at all


# --------------------------------------------------------------------------
# build_embed wiring: item.gate_result -> the "gate" section, in order,
# nothing added when there's no gate result at all.
# --------------------------------------------------------------------------


def _item(gate_result=None):
    return ScanItem(
        result=make_result(), plan=make_legacy_plan(), conf=make_conf(),
        requirements=[], combined_from=[{"strategy": "RSI Pullback", "horizon_key": "2w"}],
        plan_v2=None, gate_result=gate_result,
    )


def _build(item):
    return build_embed(item, explanation="Test explanation.", perf_stats=PERF_STATS_EMPTY,
                       open_positions_warning=None, chart_filename=None)


def test_build_embed_renders_gate_fields_when_present(monkeypatch):
    monkeypatch.setattr(config, "GATE_MODE", "inform", raising=False)
    embed = _build(_item(gate_result=_result()))
    names = [f.name for f in embed.fields]
    assert any(n.startswith("📋 Checklist") for n in names)
    assert any(n.startswith("🚩") for n in names)


def test_build_embed_no_gate_fields_when_result_is_none(monkeypatch):
    monkeypatch.setattr(config, "GATE_MODE", "inform", raising=False)
    embed = _build(_item(gate_result=None))
    names = [f.name for f in embed.fields]
    assert not any(n.startswith("📋 Checklist") or n.startswith("🚩") for n in names)


def test_build_embed_respects_shadow_gate(monkeypatch):
    monkeypatch.setattr(config, "GATE_MODE", "shadow", raising=False)
    monkeypatch.setattr(config, "GATE_SHOW_IN_SHADOW", False, raising=False)
    embed = _build(_item(gate_result=_result()))
    names = [f.name for f in embed.fields]
    assert not any(n.startswith("📋 Checklist") for n in names)
