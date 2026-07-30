"""Section-4 risk-definition checks. Advisory-only: these flag, they
never mutate the plan's v2-validated exit geometry."""
from __future__ import annotations

from swingbot.core.gate.levels import (_safe_atr, round_levels, swing_levels)
from swingbot.core.gate.registry import CHECKS, ThresholdSpec, register
from swingbot.core.gate.types import CheckResult


def check_stop_structural(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    spec = CHECKS["stop_structural"]
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    atr_val = _safe_atr(df_daily, entry)
    bullish = plan.direction == "bullish"
    swings = swing_levels(df_daily)
    if bullish:
        protective = [l.price for l in swings if l.kind == "support" and l.price < entry]
        nearest = max(protective) if protective else None
        margin = (nearest - plan.stop_loss) / atr_val if nearest is not None else None
        inside = nearest is not None and plan.stop_loss > nearest
    else:
        protective = [l.price for l in swings if l.kind == "resistance" and l.price > entry]
        nearest = min(protective) if protective else None
        margin = (plan.stop_loss - nearest) / atr_val if nearest is not None else None
        inside = nearest is not None and plan.stop_loss < nearest
    if nearest is None:
        return CheckResult("stop_structural", "risk", "warn", 20.0,
                           "no structure found to anchor the stop", {"atr": round(atr_val, 4)})
    on_level = next((lvl for lvl in [l.price for l in swings] + round_levels(entry)
                     if abs(plan.stop_loss - lvl) <= spec.threshold("at_level_atr") * atr_val),
                    None)
    evidence = {"nearest_structure": round(nearest, 4), "stop": plan.stop_loss,
                "margin_atr": round(margin, 2), "on_level": on_level}
    if inside:
        return CheckResult("stop_structural", "risk", "fail", 20.0,
                           f"stop {plan.stop_loss:.2f} sits INSIDE the protective "
                           f"structure ({nearest:.2f})", evidence)
    if margin < spec.threshold("beyond_atr"):
        return CheckResult("stop_structural", "risk", "warn", 20.0,
                           f"stop only {margin:.1f} ATR beyond structure — "
                           f"checklist wants ~1 ATR of air", evidence)
    if on_level is not None:
        return CheckResult("stop_structural", "risk", "warn", 20.0,
                           f"stop parked exactly at {on_level:.2f} — sweep bait",
                           evidence)
    return CheckResult("stop_structural", "risk", "pass", 20.0,
                       f"stop {margin:.1f} ATR beyond structure", evidence)


register(check_id="stop_structural", section="risk", weight=20.0,
         func=check_stop_structural,
         thresholds={
             "beyond_atr": ThresholdSpec("beyond_atr", 0.5, 0.1, 2.0, 0.1,
                 "lower to accept tighter stops behind structure",
                 presets={"strict": 0.8, "balanced": 0.5, "relaxed": 0.25}),
             "at_level_atr": ThresholdSpec("at_level_atr", 0.15, 0.05, 0.5, 0.05,
                 "lower to only flag stops sitting dead on a level",
                 presets={"strict": 0.25, "balanced": 0.15, "relaxed": 0.05}),
         })


def check_rr_realistic(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """R:R to the STRUCTURE-CAPPED target — min(TP1, nearest opposing
    wall) — the honest number, shown next to the nominal one."""
    spec = CHECKS["rr_realistic"]
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    risk = abs(entry - plan.stop_loss)
    if risk <= 0:
        return CheckResult("rr_realistic", "risk", "fail", 4.0,
                           "zero stop distance", {})
    bullish = plan.direction == "bullish"
    swings = swing_levels(df_daily)
    if bullish:
        opposing = [l.price for l in swings if l.kind == "resistance" and l.price > entry]
        capped_target = min([plan.tp1] + opposing)
        capped_rr = (capped_target - entry) / risk
    else:
        opposing = [l.price for l in swings if l.kind == "support" and l.price < entry]
        capped_target = max([plan.tp1] + opposing)
        capped_rr = (entry - capped_target) / risk
    nominal_rr = abs(plan.tp1 - entry) / risk
    evidence = {"nominal_rr": round(nominal_rr, 2), "capped_rr": round(capped_rr, 2),
                "capped_target": round(capped_target, 2)}
    if capped_rr >= spec.threshold("min_rr"):
        return CheckResult("rr_realistic", "risk", "pass", 4.0,
                           f"structure-capped R:R {capped_rr:.1f}", evidence)
    if capped_rr >= spec.threshold("warn_rr"):
        return CheckResult("rr_realistic", "risk", "warn", 4.0,
                           f"capped R:R only {capped_rr:.1f} "
                           f"(nominal {nominal_rr:.1f})", evidence)
    return CheckResult("rr_realistic", "risk", "fail", 4.0,
                       f"capped R:R {capped_rr:.1f} — the wall eats the trade "
                       f"(nominal {nominal_rr:.1f} is not the honest number)",
                       evidence)


register(check_id="rr_realistic", section="risk", weight=4.0,
         func=check_rr_realistic,
         thresholds={
             "min_rr": ThresholdSpec("min_rr", 1.5, 1.0, 3.0, 0.1,
                 "lower to accept slimmer capped targets (this is GATE_MIN_RR)",
                 presets={"strict": 2.0, "balanced": 1.5, "relaxed": 1.2}),
             "warn_rr": ThresholdSpec("warn_rr", 1.2, 0.8, 2.0, 0.1,
                 "lower to fail less often",
                 presets={"strict": 1.4, "balanced": 1.2, "relaxed": 1.0}),
         })
