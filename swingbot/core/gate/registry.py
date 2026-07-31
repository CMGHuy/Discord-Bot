"""Check registry + policy table.

Check modules (Phase G2) register themselves at import time via
register(); this module owns the invariants. Hard-block policy:
hard_block=True checks force tier C on `fail` even at score 100
(enforced by score.assign_tier via the hard_blocks list the
orchestrator assembles in G75).

Applicability matrix (strategies from backtest.ALL_STRATEGIES, G80 sign-off):
  rf_fake_breakout    -> Break & Retest, Support/Resistance, Volume Profile
                         (BREAKOUT_FAMILY — the only strategies with a level
                         to fake a break of)
  rf_divergence_trap  -> RSI Divergence (the only strategy the trap logic
                         detects against)
  rf_extreme_fade     -> all (its own logic already relaxes weak-ADX fades,
                         which is what mean-reversion entries are)
  everything else     -> all strategies (applies_to=None)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import swingbot.config as config

SECTIONS = ("context", "setup", "redflag", "risk", "timing")
PRESET_LEVELS = ("strict", "balanced", "relaxed")


@dataclass(frozen=True)
class ThresholdSpec:
    name: str
    default: float          # the *balanced* value
    min: float
    max: float
    step: float
    relax_direction: str    # help-text sentence, e.g. "raise to allow later entries"
    presets: dict           # {"strict": x, "balanced": y, "relaxed": z}


@dataclass(frozen=True)
class CheckSpec:
    check_id: str
    section: str
    weight: float
    func: Callable          # (df_daily, plan, macro_snap, **ctx) -> CheckResult
    hard_block: bool = False
    applies_to: tuple | None = None   # exact ALL_STRATEGIES names; None = all
    backtestable: bool = True         # finalized in G89
    trigger_recheck: bool = False     # cheap re-check subset (G128)
    config_flag: str = ""             # GATE_CHECK_<ID>, derived by register()
    thresholds: dict = field(default_factory=dict)   # name -> ThresholdSpec

    def threshold(self, name: str) -> float:
        """Config-Field-backed threshold lookup. The Field
        GATE_TH_{CHECK_ID}_{NAME} is generated in G79; until it exists
        the spec's balanced default applies. Check functions must use
        this — never module constants."""
        spec = self.thresholds[name]
        attr = f"GATE_TH_{self.check_id.upper()}_{name.upper()}"
        return float(getattr(config, attr, spec.default))


CHECKS: dict[str, CheckSpec] = {}


def register(**kw) -> CheckSpec:
    kw.setdefault("config_flag", f"GATE_CHECK_{kw['check_id'].upper()}")
    spec = CheckSpec(**kw)
    if spec.check_id in CHECKS:
        raise ValueError(f"duplicate check id {spec.check_id!r}")
    CHECKS[spec.check_id] = spec
    return spec


def validate_registry() -> None:
    """Invariants asserted by tests after every registration task."""
    for spec in CHECKS.values():
        assert spec.section in SECTIONS, f"{spec.check_id}: bad section {spec.section}"
        assert spec.weight >= 0, f"{spec.check_id}: negative weight"
        assert spec.config_flag == f"GATE_CHECK_{spec.check_id.upper()}", spec.check_id
        for th in spec.thresholds.values():
            assert th.min <= th.default <= th.max, f"{spec.check_id}.{th.name}"
            assert set(th.presets) == set(PRESET_LEVELS), f"{spec.check_id}.{th.name}"


def enabled_checks(strategy: str) -> list[CheckSpec]:
    out = []
    for spec in CHECKS.values():
        if spec.applies_to is not None and strategy not in spec.applies_to:
            continue
        if not getattr(config, spec.config_flag, True):   # Field generated in G79
            continue
        out.append(spec)
    return out


def backtest_checks(strategy: str) -> list[CheckSpec]:
    """The subset a historical replay can honestly evaluate. The backtest
    tier is computed from these only — G103's shadow comparison quantifies
    what the live-only checks add."""
    return [spec for spec in enabled_checks(strategy) if spec.backtestable]


def config_fields() -> list:
    """Every per-check enable + per-threshold Field, generated from the
    live registry so no strict number in the checklist is hardcoded —
    it's all reachable from the Settings page. Pushed to config via
    config.register_fields() at swingbot.core.gate import time."""
    from swingbot.config import Field
    fields = []
    for spec in CHECKS.values():
        fields.append(Field(
            spec.config_flag, spec.config_flag, "Gatekeeper",
            f"Check: {spec.check_id}", type="checkbox", default="true",
            help=f"Disable to remove {spec.check_id} from the checklist "
                 f"(visible only with GATE_ENABLED)."))
        for th in spec.thresholds.values():
            key = f"GATE_TH_{spec.check_id.upper()}_{th.name.upper()}"
            fields.append(Field(
                key, key, "Gatekeeper", f"{spec.check_id}: {th.name}",
                type="float", default=str(th.presets["balanced"]),
                min=th.min, max=th.max, step=th.step,
                help=f"{th.relax_direction}. Presets — strict "
                     f"{th.presets['strict']}, balanced {th.presets['balanced']}, "
                     f"relaxed {th.presets['relaxed']}."))
    return fields


def apply_strictness_preset(level: str) -> dict[str, float]:
    """{field_key: preset value} for every threshold the operator has NOT
    individually overridden (override = current value matches no preset).
    The caller (settings machinery / G180) writes the returned values."""
    out = {}
    for spec in CHECKS.values():
        for th in spec.thresholds.values():
            key = f"GATE_TH_{spec.check_id.upper()}_{th.name.upper()}"
            current = float(getattr(config, key, th.presets["balanced"]))
            if any(abs(current - v) < 1e-9 for v in th.presets.values()):
                out[key] = th.presets[level]
    return out
