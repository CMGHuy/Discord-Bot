import pytest

import swingbot.config as config
from swingbot.core.gate import registry
from swingbot.core.gate.registry import ThresholdSpec
from swingbot.core.gate.types import CheckResult


def _dummy_check(df_daily, plan, macro_snap, **ctx):
    return CheckResult("dummy", "context", "pass", 1.0, "ok", {})


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    monkeypatch.setattr(registry, "CHECKS", {})
    yield


def _th(name="rr_min", default=1.5):
    return ThresholdSpec(name, default, 1.0, 3.0, 0.1,
                         "lower to accept slimmer targets",
                         presets={"strict": 2.0, "balanced": default, "relaxed": 1.2})


def test_register_derives_flag_and_rejects_duplicates():
    spec = registry.register(check_id="dummy", section="context", weight=5.0, func=_dummy_check)
    assert registry.CHECKS["dummy"] is spec
    assert spec.config_flag == "GATE_CHECK_DUMMY"
    with pytest.raises(ValueError):
        registry.register(check_id="dummy", section="context", weight=5.0, func=_dummy_check)


def test_validate_registry_invariants():
    registry.register(check_id="ok", section="setup", weight=1.0, func=_dummy_check,
                      thresholds={"rr_min": _th()})
    registry.validate_registry()  # no raise
    bad = registry.CHECKS["ok"].__class__(
        check_id="bad", section="not_a_section", weight=1.0,
        func=_dummy_check, config_flag="GATE_CHECK_BAD")
    registry.CHECKS["bad"] = bad
    with pytest.raises(AssertionError):
        registry.validate_registry()


def test_enabled_checks_filters_strategy_and_flag(monkeypatch):
    registry.register(check_id="allstrats", section="context", weight=1.0, func=_dummy_check)
    registry.register(check_id="breakout_only", section="redflag", weight=1.0,
                      func=_dummy_check, applies_to=("Break & Retest",))
    assert [s.check_id for s in registry.enabled_checks("RSI Divergence")] == ["allstrats"]
    assert [s.check_id for s in registry.enabled_checks("Break & Retest")] == [
        "allstrats", "breakout_only"]
    monkeypatch.setattr(config, "GATE_CHECK_ALLSTRATS", False, raising=False)
    assert [s.check_id for s in registry.enabled_checks("RSI Divergence")] == []


def test_threshold_resolves_config_field_then_spec_default(monkeypatch):
    spec = registry.register(check_id="th", section="setup", weight=1.0,
                             func=_dummy_check, thresholds={"rr_min": _th()})
    assert spec.threshold("rr_min") == 1.5           # no Field yet -> spec default
    monkeypatch.setattr(config, "GATE_TH_TH_RR_MIN", 1.8, raising=False)
    assert spec.threshold("rr_min") == 1.8           # Field wins
