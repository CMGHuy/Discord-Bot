"""Scan-path gate wiring — no live bot, no network. scan_engine, providers
and the plan store are stubbed; these tests pin the wiring invariants
(gatekeeper-v7 Part 5, G119-G134)."""
import datetime as dt

import swingbot.commands.scanning as scanning
import swingbot.config as config
from swingbot.core.gate.types import CheckResult, GateResult

# ---------------------------------------------------------------------------
# G119 — scan entry: snapshot + gate context assembly
# ---------------------------------------------------------------------------


def _flags(monkeypatch, *, macro, gate):
    monkeypatch.setattr(config, "MACRO_ENABLED", macro, raising=False)
    monkeypatch.setattr(config, "GATE_ENABLED", gate, raising=False)


def test_context_none_when_everything_off(monkeypatch):
    _flags(monkeypatch, macro=False, gate=False)
    assert scanning.build_gate_context() is None


def test_context_built_once_per_scan(monkeypatch):
    calls = {"snap": 0}

    def fake_load():
        calls["snap"] += 1
        return {"built_at": "2026-07-14T12:00:00", "stale": False}

    _flags(monkeypatch, macro=True, gate=False)
    monkeypatch.setattr(scanning, "_load_macro_snapshot", fake_load)
    ctx = scanning.build_gate_context(now=dt.datetime(2026, 7, 14, 12, 0))
    # per-candidate work only READS the assembled context — a 60-candidate
    # scan performs exactly one snapshot load, regardless of ticker count
    for _ in range(60):
        assert ctx.macro_snap["stale"] is False
    assert calls["snap"] == 1


def test_context_macro_only_skips_gate_inputs(monkeypatch):
    _flags(monkeypatch, macro=True, gate=False)
    monkeypatch.setattr(scanning, "_load_macro_snapshot",
                        lambda: {"built_at": "t", "stale": False})
    ctx = scanning.build_gate_context()
    assert ctx.macro_snap is not None                  # embeds get their line
    assert ctx.open_plans == [] and ctx.spy_df is None # gate inputs not fetched


def test_context_degrades_when_snapshot_unreadable(monkeypatch):
    def boom():
        raise OSError("disk")

    _flags(monkeypatch, macro=True, gate=True)
    monkeypatch.setattr(scanning, "_load_macro_snapshot", boom)
    ctx = scanning.build_gate_context()
    assert ctx is not None and ctx.macro_snap is None  # degrade, never crash


def test_context_fetches_gate_inputs_when_enabled(monkeypatch):
    _flags(monkeypatch, macro=False, gate=True)
    monkeypatch.setattr(scanning, "_load_macro_snapshot", lambda: {"never": "called"})

    class FakeStore:
        def open_plans(self):
            return ["plan-1"]

    monkeypatch.setattr("swingbot.core.plan_store.PlanStore", FakeStore)
    monkeypatch.setattr("swingbot.core.data.get_daily_data", lambda t: "SPY_DF")
    ctx = scanning.build_gate_context()
    assert ctx.macro_snap is None            # MACRO_ENABLED off -> never loaded
    assert ctx.open_plans == ["plan-1"]
    assert ctx.spy_df == "SPY_DF"


# ---------------------------------------------------------------------------
# G120 — event blackout scan gate
# ---------------------------------------------------------------------------

NOW = dt.datetime(2026, 7, 14, 18, 0, tzinfo=dt.timezone.utc)


def _event(kind="cpi", label="CPI", importance=3, date="2026-07-14", time_et="20:30"):
    return {"date": date, "time_et": time_et, "kind": kind, "label": label,
           "importance": importance}


def _snap(built_at=NOW, ev=None):
    return {"built_at": built_at.isoformat(), "stale": False,
           "events": {"next_high_impact": ev, "within_24h": [], "today": []}}


def _blackout_flags(monkeypatch, *, enabled, enforce, before=24.0, after=2.0):
    monkeypatch.setattr(config, "GATE_BLACKOUT_ENABLED", enabled, raising=False)
    monkeypatch.setattr(config, "GATE_BLACKOUT_ENFORCE", enforce, raising=False)
    monkeypatch.setattr(config, "GATE_BLACKOUT_HOURS_BEFORE", before, raising=False)
    monkeypatch.setattr(config, "GATE_BLACKOUT_HOURS_AFTER", after, raising=False)


def test_blackout_default_is_annotate(monkeypatch):
    # CPI at 20:30 ET today, NOW is 18:00 UTC = 14:00 ET -> ~6.5h out
    _blackout_flags(monkeypatch, enabled=True, enforce=False)
    verdict = scanning.blackout_decision(_snap(ev=_event()), NOW)
    assert verdict["action"] == "annotate"             # plan ships, loudly
    assert "CPI" in verdict["line"] and "⚠️" in verdict["line"]


def test_blackout_hold_requires_both_flags(monkeypatch):
    _blackout_flags(monkeypatch, enabled=True, enforce=True)
    verdict = scanning.blackout_decision(_snap(ev=_event()), NOW)
    assert verdict["action"] == "hold"
    assert verdict["release_at"] > NOW.isoformat()     # after + GATE_BLACKOUT_HOURS_AFTER


def test_blackout_ignores_low_importance_and_far_events(monkeypatch):
    _blackout_flags(monkeypatch, enabled=True, enforce=True)
    assert scanning.blackout_decision(_snap(ev=_event(importance=2)), NOW) is None
    far = _event(date="2026-07-20", time_et="08:30")
    assert scanning.blackout_decision(_snap(ev=far), NOW) is None


def test_blackout_no_next_event_is_none(monkeypatch):
    _blackout_flags(monkeypatch, enabled=True, enforce=True)
    assert scanning.blackout_decision(_snap(ev=None), NOW) is None


def test_blackout_stale_calendar_never_holds(monkeypatch, caplog):
    _blackout_flags(monkeypatch, enabled=True, enforce=True)
    stale_built = NOW - dt.timedelta(days=8)
    verdict = scanning.blackout_decision(_snap(built_at=stale_built, ev=_event()), NOW)
    assert verdict["action"] == "annotate"             # holding auto-disabled
    assert any("stale" in r.message.lower() for r in caplog.records)


def test_blackout_flag_off_is_none(monkeypatch):
    _blackout_flags(monkeypatch, enabled=False, enforce=True)
    assert scanning.blackout_decision(_snap(ev=_event()), NOW) is None


def test_blackout_no_snapshot_is_none(monkeypatch):
    _blackout_flags(monkeypatch, enabled=True, enforce=True)
    assert scanning.blackout_decision(None, NOW) is None


# ---------------------------------------------------------------------------
# G121 — per-candidate gate evaluation in the scan path
# ---------------------------------------------------------------------------


def _gate_result(statuses, tier="C", hard_blocks=()):
    checks = tuple(CheckResult(f"c{i}", "setup", s, 10.0, s, {})
                   for i, s in enumerate(statuses))
    return GateResult(ticker="T", strategy="S", as_of="2026-07-14",
                      checks=checks, score=10.0, tier=tier,
                      hard_blocks=tuple(hard_blocks), macro_stale=False)


def test_inform_never_drops_property():
    """Invariant 1: inform mode passes EVERY result — including all-fail
    and hard-blocked ones. The checklist is information, not a gateway."""
    worst_cases = [
        _gate_result(["fail"] * 7, tier="C", hard_blocks=("rf_news_whipsaw",)),
        _gate_result(["fail", "unknown", "fail"], tier="C"),
        _gate_result(["pass"] * 7, tier="A+"),
    ]
    for result in worst_cases:
        decision, out = scanning.gate_candidate(result, "inform", "A")
        assert decision == "pass"                      # alert always ships
        assert out.advisory_decision in ("pass", "downgrade", "block")


def test_unknown_never_blocks_even_in_enforce():
    """Invariant 2 (the G43 proof through the gate): a result whose low
    tier comes from unknowns — not observed failures — never blocks."""
    dark = _gate_result(["unknown"] * 7, tier="C")
    decision, out = scanning.gate_candidate(dark, "enforce", "A")
    assert decision == "pass"
    assert out.advisory_decision == "block"            # the would-be verdict stays honest


def test_enforce_blocks_only_on_observed_evidence():
    flagged = _gate_result(["fail"] * 5 + ["pass"] * 2, tier="C")
    decision, _ = scanning.gate_candidate(flagged, "enforce", "A")
    assert decision == "block"                         # real fails may block
    mixed = _gate_result(["unknown"] * 6 + ["fail"], tier="C")
    decision, _ = scanning.gate_candidate(mixed, "enforce", "A")
    assert decision == "pass"                          # unknown-dominated → pass


def test_shadow_passes_and_records_would_block():
    result = _gate_result(["fail"] * 7, tier="C")
    decision, out = scanning.gate_candidate(result, "shadow", "A")
    assert decision == "pass" and out.advisory_decision == "block"


# ---------------------------------------------------------------------------
# G128 — re-check at entry trigger
# ---------------------------------------------------------------------------


def _recheck_result(fired):
    checks = tuple(CheckResult(f, "redflag", "fail", 6.0, f, {}) for f in fired)
    return GateResult(ticker="T", strategy="S", as_of="2026-07-15",
                      checks=checks, score=50.0, tier="B", hard_blocks=(),
                      macro_stale=False)


def test_recheck_delta_only_new_flags():
    stored = {"checks": [{"check_id": "rf_thin_session", "status": "fail"}]}
    new = _recheck_result(["rf_thin_session", "rf_news_whipsaw"])
    assert scanning.recheck_delta(stored, new) == ["rf_news_whipsaw"]   # already-known flag not re-warned


def test_recheck_delta_clean_is_empty():
    assert scanning.recheck_delta({"checks": []}, _recheck_result([])) == []


def test_recheck_delta_no_stored_gate_treats_all_as_new():
    assert scanning.recheck_delta(None, _recheck_result(["rf_news_whipsaw"])) == ["rf_news_whipsaw"]


def test_registry_trigger_subset_is_cheap():
    from swingbot.core.gate.registry import CHECKS
    subset = {cid for cid, spec in CHECKS.items() if spec.trigger_recheck}
    assert subset == {"rf_news_whipsaw", "rf_thin_session",
                      "not_chasing", "calendar_checked"}


# ---------------------------------------------------------------------------
# G134 — kill-switch + throttle interop
# ---------------------------------------------------------------------------


def test_size_multipliers_compose_multiplicatively():
    # throttle 0.5 × tier 0.75 → 0.375; None means "no opinion" (×1)
    assert scanning.compose_size_multipliers(0.5, 0.75) == 0.375
    assert scanning.compose_size_multipliers(None, 0.75) == 0.75
    assert scanning.compose_size_multipliers(None, None) == 1.0
    assert scanning.compose_size_multipliers(0.0, 2.0) == 0.0     # floored at 0
    assert scanning.compose_size_multipliers(-0.5, 1.0) == 0.0    # negative → 0


def test_killswitch_outranks_any_tier():
    """'No new entries' beats an A+ pass — and a gate block stays a block."""
    assert scanning.entry_allowed_with_killswitch(True, "pass") is False
    assert scanning.entry_allowed_with_killswitch(True, "block") is False
    assert scanning.entry_allowed_with_killswitch(False, "pass") is True
    assert scanning.entry_allowed_with_killswitch(False, "block") is False
