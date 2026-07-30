"""Gatekeeper public API: run_checklist(), GateResult, CheckResult."""
from __future__ import annotations

import logging

import swingbot.config as config

log = logging.getLogger("swing-bot.gate")

# Importing the check modules runs their register() side effects.
from swingbot.core.gate import (atr_regime, context_htf, levels,      # noqa: F401,E402
                                redflags, risk_def, setup_quality, timing)
from swingbot.core.gate.registry import CHECKS, config_fields, enabled_checks  # noqa: E402
from swingbot.core.gate.score import assign_tier, score               # noqa: E402
from swingbot.core.gate.types import CheckResult, GateResult          # noqa: E402

config.register_fields(config_fields())


def run_checklist(ticker, strategy, plan, df_daily, *, macro_snap=None,
                  open_plans=None, account=None, headlines=None,
                  spy_df=None, now=None, subset: str | None = None) -> GateResult:
    """Deterministic given inputs. An exception inside any check makes THAT
    check unknown (+log) — never a scan crash. subset="trigger" runs only
    the cheap trigger_recheck checks (G128)."""
    # _gate_cache (G87 perf guard): a fresh dict per run_checklist call —
    # swing_levels/htf_trend/atr get recomputed by 4+ checks on the same
    # df_daily; memoizing them here keyed on id(df_daily) cuts the median
    # eval time under the 50ms budget. Scoped to this single call only (not
    # a module-level cache) so nothing can leak across tickers/calls.
    ctx = {"open_plans": open_plans, "account": account,
           "headlines": headlines, "spy_df": spy_df, "now": now,
           "_gate_cache": {}}
    checks: list[CheckResult] = []
    for spec in enabled_checks(strategy):
        if subset == "trigger" and not spec.trigger_recheck:
            continue
        try:
            result = spec.func(df_daily, plan, macro_snap, **ctx)
        except Exception:  # noqa: BLE001
            log.warning("check %s raised — recorded as unknown",
                        spec.check_id, exc_info=True)
            result = CheckResult(spec.check_id, spec.section, "unknown",
                                 spec.weight, "check errored — treated as unknown", {})
        checks.append(result)
    hard_blocks = tuple(c.check_id for c in checks
                        if c.status == "fail" and CHECKS[c.check_id].hard_block)
    total = score(checks)
    tier = assign_tier(
        total, hard_blocks,
        aplus_cut=float(getattr(config, "GATE_TIER_APLUS_CUT", 90.0)),
        a_cut=float(getattr(config, "GATE_TIER_A_CUT", 75.0)),
        b_cut=float(getattr(config, "GATE_TIER_B_CUT", 55.0)))
    return GateResult(
        ticker=ticker, strategy=strategy,
        as_of=str(df_daily.index[-1].date()),
        checks=tuple(checks), score=total, tier=tier,
        hard_blocks=hard_blocks,
        macro_stale=bool(macro_snap.get("stale")) if macro_snap else True)
