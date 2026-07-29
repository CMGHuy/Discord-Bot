"""ATR-percentile regime checks. Percentile uses MIDRANK so a
constant-volatility series sits at ~50, not 100."""
from __future__ import annotations

from swingbot.core.gate.registry import CHECKS, ThresholdSpec, register
from swingbot.core.gate.types import CheckResult
from swingbot.core.indicators import atr


def _atr_percentile(df_daily) -> tuple[float | None, float | None]:
    atr_pct = (atr(df_daily) / df_daily["Close"]).dropna()
    if len(atr_pct) < 60:
        return None, None
    window = atr_pct.iloc[-252:]
    last = float(atr_pct.iloc[-1])
    midrank = 100.0 * (float((window < last).mean())
                       + float((window <= last).mean())) / 2.0
    return midrank, last * 100.0


def check_atr_normal(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    spec = CHECKS["atr_normal"]
    pctile, atr_pct = _atr_percentile(df_daily)
    if pctile is None:
        return CheckResult("atr_normal", "context", "unknown", 6.0,
                           "insufficient history for ATR percentile", {})
    evidence = {"percentile": round(pctile, 1), "atr_pct": round(atr_pct, 2)}
    if pctile > spec.threshold("pct_spike"):
        return CheckResult("atr_normal", "context", "fail", 6.0,
                           f"ATR spiked ({pctile:.0f}th pct) — stop math unreliable",
                           evidence)
    if pctile < spec.threshold("pct_low"):
        return CheckResult("atr_normal", "context", "warn", 6.0,
                           f"volatility compressed ({pctile:.0f}th pct) — "
                           f"breakout fuel but whipsaw risk", evidence)
    if pctile > spec.threshold("pct_high"):
        return CheckResult("atr_normal", "context", "warn", 6.0,
                           f"volatility elevated ({pctile:.0f}th pct)", evidence)
    return CheckResult("atr_normal", "context", "pass", 6.0,
                       f"volatility normal ({pctile:.0f}th pct)", evidence)


register(check_id="atr_normal", section="context", weight=6.0, func=check_atr_normal,
         thresholds={
             "pct_low": ThresholdSpec("pct_low", 20.0, 0.0, 40.0, 5.0,
                 "lower to accept more compression without a warn",
                 presets={"strict": 25.0, "balanced": 20.0, "relaxed": 10.0}),
             "pct_high": ThresholdSpec("pct_high", 80.0, 60.0, 100.0, 5.0,
                 "raise to accept more elevated volatility",
                 presets={"strict": 75.0, "balanced": 80.0, "relaxed": 90.0}),
             "pct_spike": ThresholdSpec("pct_spike", 95.0, 80.0, 100.0, 1.0,
                 "raise to fail only on the most extreme spikes",
                 presets={"strict": 90.0, "balanced": 95.0, "relaxed": 99.0}),
         })
