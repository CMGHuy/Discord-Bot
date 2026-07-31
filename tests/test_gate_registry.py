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


class TestApplicabilityMatrix:
    """Runs against the REAL registry (populated by importing swingbot.core.gate),
    not the wiped-per-test one — override the module's autouse fixture with a
    no-op of the same name so it doesn't clear CHECKS out from under us."""

    @pytest.fixture(autouse=True)
    def _clean_registry(self):
        yield

    def test_applicability_matrix_uses_real_strategy_names(self):
        import swingbot.core.gate  # noqa: F401 — ensure all checks registered
        from swingbot.core.backtest import ALL_STRATEGIES
        from swingbot.core.gate import registry as live_registry
        for spec in live_registry.CHECKS.values():
            if spec.applies_to is not None:
                unknown = set(spec.applies_to) - set(ALL_STRATEGIES)
                assert not unknown, f"{spec.check_id}: unknown strategies {unknown}"
        assert set(live_registry.CHECKS["rf_fake_breakout"].applies_to) == {
            "Break & Retest", "Support/Resistance", "Volume Profile"}
        assert live_registry.CHECKS["rf_divergence_trap"].applies_to == ("RSI Divergence",)
        assert live_registry.CHECKS["rf_extreme_fade"].applies_to is None
        # The plan's original ">= 20" floor assumed the pre-audit 26/27-check
        # registry (2026-07-28/29 win-rate audit cut it to 21 — see the plan
        # index). With exactly 2 checks intentionally strategy-restricted
        # (rf_fake_breakout, rf_divergence_trap) and everything else
        # universal, the honest floor for a strategy with neither restricted
        # check applicable is total - 2, not the stale absolute number.
        restricted = sum(1 for s in live_registry.CHECKS.values() if s.applies_to is not None)
        floor = len(live_registry.CHECKS) - restricted
        for strategy in ALL_STRATEGIES:
            assert len(live_registry.enabled_checks(strategy)) >= floor, strategy


class TestBacktestableSubset:
    """Runs against the REAL registry, same override pattern as
    TestApplicabilityMatrix above.

    NOTE: the G89 plan text's example sets name rf_rumor_spike,
    portfolio_room, size_formula, rf_buy_rumor_sell_fact, and rf_opex_pin
    as live-only/backtestable examples. All five are cut tasks from the
    2026-07-29 win-rate audit (G63, G64, G66, G69, G71 per the plan index's
    cut appendix) and were never registered — asserting on them would just
    be resurrecting dead scope. This test only asserts on check_ids that
    actually exist in the live registry."""

    @pytest.fixture(autouse=True)
    def _clean_registry(self):
        yield

    def test_backtestable_subset_membership(self):
        import swingbot.core.gate  # noqa: F401
        from swingbot.core.gate import registry as live

        live_only = {"calendar_checked", "trigger_objective"}
        for check_id in live_only:
            assert live.CHECKS[check_id].backtestable is False, check_id

        backtestable = {
            "htf_alignment", "level_map", "atr_normal", "confluence",
            "volume_confirms", "momentum_agrees", "signal_confirmed",
            "rf_fake_breakout", "rf_stop_sweep", "rf_dead_cat",
            "rf_divergence_trap", "rf_extreme_fade", "rf_news_whipsaw",
            "rf_thin_session", "rf_beta_move", "stop_structural",
            "rr_realistic", "not_chasing",
        }
        for check_id in backtestable:
            assert live.CHECKS[check_id].backtestable is True, check_id

        ids = {s.check_id for s in live.backtest_checks("Break & Retest")}
        assert "rf_fake_breakout" in ids
        assert "calendar_checked" not in ids
