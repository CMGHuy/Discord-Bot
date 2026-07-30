"""Section-5 timing & trigger checks."""
from __future__ import annotations

import datetime as dt
import math

import swingbot.config as config
from swingbot.core.gate.levels import _safe_atr
from swingbot.core.gate.registry import CHECKS, ThresholdSpec, register
from swingbot.core.gate.types import CheckResult

# TradePlanV2's machine-readable entry vocabulary (plan_engine.py) —
# extend here if the engine grows new entry types.
ENTRY_TYPES = ("stop_entry", "market")


def check_trigger_objective(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """Plan-integrity invariant (HB). Firing in production = engine bug
    surfaced loudly, not a market condition."""
    problems = []
    if plan.entry_type not in ENTRY_TYPES:
        problems.append(f"unknown entry_type {plan.entry_type!r}")
    if (plan.trigger_price is None or
        not isinstance(plan.trigger_price, (int, float)) or
        (isinstance(plan.trigger_price, float) and math.isnan(plan.trigger_price)) or
        plan.trigger_price <= 0):
        problems.append("no concrete trigger price")
    if problems:
        return CheckResult("trigger_objective", "timing", "fail", 6.0,
                           "plan has no objective trigger: " + "; ".join(problems),
                           {"entry_type": str(plan.entry_type),
                            "trigger_price": plan.trigger_price})
    return CheckResult("trigger_objective", "timing", "pass", 6.0,
                       f"objective trigger: {plan.entry_type} @ {plan.trigger_price:.2f}",
                       {"entry_type": plan.entry_type})


register(check_id="trigger_objective", section="timing", weight=6.0,
         func=check_trigger_objective, hard_block=True, backtestable=False)


def check_not_chasing(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """Distance current price has already run PAST the trigger, in ATRs.
    Late entry wrecks the R:R the plan was validated with."""
    spec = CHECKS["not_chasing"]
    price = float(df_daily["Close"].iloc[-1])
    atr_val = _safe_atr(df_daily, price, cache=ctx.get("_gate_cache"))
    bullish = plan.direction == "bullish"
    past = (price - plan.trigger_price) if bullish else (plan.trigger_price - price)
    dist_atr = round(past / atr_val, 2)
    evidence = {"dist_atr": dist_atr, "price": price, "trigger": plan.trigger_price}
    if dist_atr <= spec.threshold("pass_atr"):
        return CheckResult("not_chasing", "timing", "pass", 8.0,
                           "entry is fresh", evidence)
    if dist_atr <= spec.threshold("chase_atr_max"):
        return CheckResult("not_chasing", "timing", "warn", 8.0,
                           f"price already {dist_atr} ATR past the trigger", evidence)
    return CheckResult("not_chasing", "timing", "fail", 8.0,
                       f"chasing: {dist_atr} ATR past the trigger", evidence)


register(check_id="not_chasing", section="timing", weight=8.0,
         func=check_not_chasing, trigger_recheck=True,
         thresholds={
             "pass_atr": ThresholdSpec("pass_atr", 0.5, 0.1, 1.5, 0.1,
                 "raise to call later entries still fresh",
                 presets={"strict": 0.3, "balanced": 0.5, "relaxed": 0.8}),
             "chase_atr_max": ThresholdSpec("chase_atr_max", 1.0, 0.5, 3.0, 0.1,
                 "raise to allow later entries (this is GATE_CHASE_ATR_MAX)",
                 presets={"strict": 0.8, "balanced": 1.0, "relaxed": 1.5}),
         })


def check_calendar(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """Did the bot literally check the calendar this session? Complements
    rf_news_whipsaw: this checks that we LOOKED; G62 checks what we SAW."""
    if not getattr(config, "MACRO_ENABLED", False) or macro_snap is None:
        return CheckResult("calendar_checked", "timing", "unknown", 4.0,
                           "macro layer off — calendar not machine-checked", {})
    try:
        built = dt.datetime.fromisoformat(macro_snap["built_at"])
        age_min = (dt.datetime.now(dt.timezone.utc) - built).total_seconds() / 60.0
    except (KeyError, TypeError, ValueError):
        return CheckResult("calendar_checked", "timing", "unknown", 4.0,
                           "snapshot has no readable timestamp", {})
    ttl = float(getattr(config, "MACRO_SNAPSHOT_TTL_MIN", 30))
    populated = bool(macro_snap.get("events"))
    evidence = {"age_min": round(age_min, 1), "events_populated": populated}
    if age_min <= ttl and populated:
        return CheckResult("calendar_checked", "timing", "pass", 4.0,
                           "calendar checked this session", evidence)
    return CheckResult("calendar_checked", "timing", "warn", 4.0,
                       "macro snapshot stale or event section empty", evidence)


register(check_id="calendar_checked", section="timing", weight=4.0,
         func=check_calendar, backtestable=False)
