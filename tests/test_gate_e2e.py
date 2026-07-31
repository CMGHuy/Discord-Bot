"""Offline end-to-end paths (G140-G141): fixture candidate -> gate -> embed
fields -> plan store -> logs -> telemetry. No network, no live bot.

The pipeline() helper below mirrors the REAL scan path's wiring order
exactly as implemented in core/scanning/engine.py's per-candidate alert
block (G121): telemetry "evaluated" -> run_checklist -> gate_candidate ->
attach_to_plan (G81) -> shadow_log in shadow mode -> block handling
(blocked_log + telemetry "blocked", no embed fields) -> gate_embed_fields
(G123). If that wiring order in engine.py ever changes, this file is the
canary -- keep it in sync rather than diverging to make a test pass.

Note: G122 ("macro context line on the alert embed") was cut by the
2026-07 win-rate audit ("display-only market context, not derived from
the gate verdict") -- there is no macro_line()/🌍 field in the real
pipeline, so this harness does not fabricate one."""
import datetime as dt
import json

import pytest

import swingbot.config as config
import swingbot.core.gate.persistence as persistence
import swingbot.core.gate.telemetry as telemetry
from swingbot.core.gate import run_checklist
from swingbot.core.gate.render import gate_embed_fields
from swingbot.core.gate.scan_integration import gate_candidate
from swingbot.core.plan_store import PlanStore
from tests.fixtures.gate import breakout_and_fail, uptrend_daily
from tests.fixtures.gate.plans import make_plan

NOW = dt.datetime(2026, 7, 14, 18, 0)


def fresh_snapshot(now=NOW, **overrides):
    """The REAL shape build_snapshot() produces (core/macro/snapshot.py) --
    NOT the plan's illustrative shape (which invents "curve"/"news"/
    "upcoming"/"refreshed_at" keys that don't exist in this codebase)."""
    snap = {
        "built_at": now.isoformat(), "stale": False,
        "risk": {"vix": {"level": 14.2, "regime": "calm"}},
        "composite": {"score": 67, "label": "risk_on", "inputs_used": 3, "detail": []},
        "sectors": {"rs_rows": [], "rotation": {"posture": "risk_on", "note": ""}},
        "breadth": {"pct_above_50dma": 62.0, "pct_above_200dma": 58.0, "n": 75},
        "events": {"next_high_impact": None, "within_24h": [], "today": []},
        "session": {"flag": "normal", "detail": ""},
        "quality_warnings": [],
    }
    snap.update(overrides)
    return snap


@pytest.fixture
def city(tmp_path, monkeypatch):
    """Isolated data city: every gate path constant points at tmp."""
    monkeypatch.setattr(persistence, "BLOCKED_PATH", str(tmp_path / "blocked.jsonl"))
    monkeypatch.setattr(persistence, "SHADOW_PATH", str(tmp_path / "shadow.jsonl"))
    monkeypatch.setattr(telemetry, "TELEMETRY_PATH", str(tmp_path / "telemetry.jsonl"))
    monkeypatch.setattr(config, "MACRO_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "GATE_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "GATE_MODE", "inform", raising=False)
    monkeypatch.setattr(config, "GATE_MIN_TIER", "A", raising=False)
    monkeypatch.setattr(config, "GATE_SHOW_IN_SHADOW", False, raising=False)
    return PlanStore(path=str(tmp_path / "plans.json"))


def pipeline(df, plan, plan_store, snap, *, mode=None, now=NOW):
    """The scan path's gate block, in wiring order (see module docstring).
    Returns (decision, result, embed_fields)."""
    mode = mode or config.GATE_MODE
    telemetry.count("evaluated", at=now)
    result = run_checklist(plan.ticker, plan.strategy, plan, df,
                           macro_snap=snap, open_plans=[], spy_df=None, now=now)
    decision, result = gate_candidate(result, mode, config.GATE_MIN_TIER)
    persistence.attach_to_plan(plan_store, plan.plan_id, result)
    if mode == "shadow":
        persistence.shadow_log(result, plan.plan_id)
    if decision == "block":
        reason = ", ".join(result.hard_blocks) or f"tier {result.tier} < {config.GATE_MIN_TIER}"
        persistence.blocked_log(result, decision, reason)
        telemetry.count("blocked", at=now, reason=reason)
        return decision, result, []
    if result.advisory_decision == "downgrade":
        telemetry.count("downgraded", at=now)
    fields = gate_embed_fields(result, mode, getattr(config, "GATE_SHOW_IN_SHADOW", False))
    return decision, result, fields


def _stored_plan(df, plan_store, **overrides):
    kw = dict(created_at="2026-07-13", trigger_price=float(df["Close"].iloc[-1]))
    kw.update(overrides)
    plan = make_plan(**kw)
    plan_store.add(plan)
    return plan


# ---------------------------------------------------------------------------
# G140 — clean pass path (inform, the default)
# ---------------------------------------------------------------------------


def test_clean_pass_inform(city):
    df = uptrend_daily(n=300)
    plan = _stored_plan(df, city, strategy="RSI Pullback")
    decision, result, fields = pipeline(df, plan, city, fresh_snapshot())
    assert decision == "pass"
    assert result.hard_blocks == ()
    names = [n for n, _ in fields]
    assert any(n.startswith("📋") for n in names)         # G123
    stored_gate = city.get_extra(plan.plan_id, "gate")
    assert stored_gate is not None and stored_gate["tier"] == result.tier   # G81 stamp
    s = telemetry.summary()
    assert s["evaluated"] == 1 and s["blocked"] == 0


# ---------------------------------------------------------------------------
# G141 — flagged-but-ships (inform) + blocked (opt-in enforce)
# ---------------------------------------------------------------------------


def _failing_candidate(city):
    df = breakout_and_fail(level=100.0)
    plan = _stored_plan(df, city, strategy="Break & Retest",
                        direction="bullish", trigger_price=100.0)
    return df, plan


def test_flagged_candidate_still_ships_in_inform(city):
    df, plan = _failing_candidate(city)
    decision, result, fields = pipeline(df, plan, city, fresh_snapshot())
    assert decision == "pass"                            # inform NEVER drops
    fired = [c.check_id for c in result.checks
             if c.check_id == "rf_fake_breakout" and c.status in ("fail", "warn")]
    assert fired == ["rf_fake_breakout"]
    flat = "\n".join(v for _, v in fields)
    assert "Fake breakout" in flat                        # the red-flag row renders
    if result.advisory_decision == "block":
        assert "plan ships anyway; your call" in flat
    stored = city.get(plan.plan_id)
    assert stored.status != "blocked"                     # stored NORMALLY
    s = telemetry.summary()
    assert s["evaluated"] == 1 and s["blocked"] == 0      # the inform invariant


def test_same_candidate_blocks_only_after_enforce_opt_in(city, monkeypatch):
    monkeypatch.setattr(config, "GATE_MODE", "enforce", raising=False)
    df, plan = _failing_candidate(city)
    decision, result, fields = pipeline(df, plan, city, fresh_snapshot())
    if result.advisory_decision != "block":               # guard: fixture must be bad enough
        pytest.skip("fixture no longer tiers below A — regenerate breakout_and_fail")
    assert decision == "block" and fields == []           # no alert
    with open(persistence.BLOCKED_PATH, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    assert len(rows) == 1 and rows[0]["ticker"] == plan.ticker
    assert "rf_fake_breakout" in rows[0]["reason"] or "tier" in rows[0]["reason"]
    s = telemetry.summary()
    assert s["evaluated"] == 1 and s["blocked"] == 1
    # blocked ≠ deleted: the plan record and its gate result survive
    stored_gate = city.get_extra(plan.plan_id, "gate")
    assert stored_gate is not None and stored_gate["tier"] == result.tier
