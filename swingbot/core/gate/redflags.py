"""The 11 red-flag detectors, ids rf_*. A fired flag = status "fail"
(warn-grade flags are noted per check); functions stay total — a
strategy the flag doesn't police returns pass with detail "n/a"."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import swingbot.config as config
from swingbot.core.gate.registry import CHECKS, ThresholdSpec, register
from swingbot.core.gate.setup_quality import BREAKOUT_FAMILY, volume_ratio
from swingbot.core.gate.types import CheckResult
from swingbot.core.indicators import adx, rsi
from swingbot.core.macro import calendar_events, earnings

ET = ZoneInfo("America/New_York")


def _rf(check_id, status, detail, evidence, weight) -> CheckResult:
    return CheckResult(check_id, "redflag", status, weight, detail, evidence)


def rf_fake_breakout(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    spec = CHECKS["rf_fake_breakout"]
    if plan.strategy not in BREAKOUT_FAMILY:
        return _rf("rf_fake_breakout", "pass", "n/a (not a breakout strategy)", {}, 10.0)
    level = plan.trigger_price
    bullish = plan.direction == "bullish"
    last_close = float(df_daily["Close"].iloc[-1])
    ratio = volume_ratio(df_daily)
    recent = df_daily.iloc[-3:]
    if bullish:
        broke_out = bool((recent["Close"] > level).any() or (recent["High"] > level).any())
        back_inside = last_close < level
        beyond_now = last_close > level
    else:
        broke_out = bool((recent["Close"] < level).any() or (recent["Low"] < level).any())
        back_inside = last_close > level
        beyond_now = last_close < level
    evidence = {"level": level, "close": last_close, "vol_ratio": ratio}
    if broke_out and back_inside:
        return _rf("rf_fake_breakout", "fail",
                   f"breakout closed back inside on {ratio or 0:.1f}x volume",
                   evidence, 10.0)
    if beyond_now and ratio is not None and ratio < spec.threshold("vol_mult"):
        return _rf("rf_fake_breakout", "fail",
                   f"breakout on dead volume ({ratio:.1f}x)", evidence, 10.0)
    prior = df_daily.iloc[-11:-1]
    if bullish:
        pokes = int(((prior["High"] >= level) & (prior["Close"] < level)).sum())
    else:
        pokes = int(((prior["Low"] <= level) & (prior["Close"] > level)).sum())
    if pokes >= int(spec.threshold("serial_pokes")):
        evidence["failed_pokes"] = pokes
        return _rf("rf_fake_breakout", "fail",
                   f"{pokes} failed pokes through {level:.2f} in the prior 10 bars "
                   f"— serial-liar level", evidence, 10.0)
    return _rf("rf_fake_breakout", "pass", "no fake-breakout signature", evidence, 10.0)


register(check_id="rf_fake_breakout", section="redflag", weight=10.0,
         func=rf_fake_breakout, applies_to=BREAKOUT_FAMILY,
         thresholds={
             "vol_mult": ThresholdSpec("vol_mult", 0.8, 0.3, 1.5, 0.1,
                 "lower to tolerate quieter breakouts",
                 presets={"strict": 1.0, "balanced": 0.8, "relaxed": 0.5}),
             "serial_pokes": ThresholdSpec("serial_pokes", 2, 1, 5, 1,
                 "raise to tolerate more failed pokes",
                 presets={"strict": 1, "balanced": 2, "relaxed": 3}),
         })


def rf_stop_sweep(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """Wick >= wick_body_mult x body through an obvious level with a close
    back on the far side, and no follow-through on the next bar. For
    sweep-reclaim strategies the registry applies_to marks this n/a."""
    spec = CHECKS["rf_stop_sweep"]
    from swingbot.core.gate.levels import _safe_atr, round_levels, swing_levels
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    atr_val = _safe_atr(df_daily, entry)
    levels = [l.price for l in swing_levels(df_daily)] + round_levels(entry)
    wick_mult = spec.threshold("wick_body_mult")
    for pos in (-2, -3):                        # signal bar or the bar before
        if len(df_daily) + pos < 0:
            continue
        bar, nxt = df_daily.iloc[pos], df_daily.iloc[pos + 1]
        body = abs(float(bar["Close"]) - float(bar["Open"])) or 1e-9
        lower_wick = min(float(bar["Close"]), float(bar["Open"])) - float(bar["Low"])
        upper_wick = float(bar["High"]) - max(float(bar["Close"]), float(bar["Open"]))
        for level in levels:
            swept_down = (float(bar["Low"]) < level < min(float(bar["Close"]), float(bar["Open"]))
                          and lower_wick >= wick_mult * body)
            swept_up = (float(bar["High"]) > level > max(float(bar["Close"]), float(bar["Open"]))
                        and upper_wick >= wick_mult * body)
            if not (swept_down or swept_up):
                continue
            follow_atr = abs(float(nxt["Close"]) - float(bar["Close"])) / atr_val
            if follow_atr < spec.threshold("follow_atr"):
                wick_body = round(max(lower_wick, upper_wick) / body, 2)
                return _rf("rf_stop_sweep", "fail",
                           f"stop-sweep wick through {level:.2f} "
                           f"({wick_body}x body), no follow-through",
                           {"level": level, "wick_body": wick_body,
                            "follow_atr": round(follow_atr, 2)}, 8.0)
    return _rf("rf_stop_sweep", "pass", "no sweep signature", {}, 8.0)


register(check_id="rf_stop_sweep", section="redflag", weight=8.0,
         func=rf_stop_sweep,
         thresholds={
             "wick_body_mult": ThresholdSpec("wick_body_mult", 1.5, 1.0, 4.0, 0.25,
                 "raise to ignore smaller wicks",
                 presets={"strict": 1.25, "balanced": 1.5, "relaxed": 2.5}),
             "follow_atr": ThresholdSpec("follow_atr", 0.5, 0.1, 1.5, 0.1,
                 "lower to require less follow-through before clearing",
                 presets={"strict": 0.8, "balanced": 0.5, "relaxed": 0.25}),
         })


def rf_dead_cat(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    spec = CHECKS["rf_dead_cat"]
    if plan.direction != "bullish":
        return _rf("rf_dead_cat", "pass", "n/a (bearish plan)", {}, 10.0)
    from swingbot.core.gate.context_htf import htf_trend
    closes = df_daily["Close"]
    if len(closes) < 60:
        return _rf("rf_dead_cat", "unknown", "insufficient history", {}, 10.0)
    if htf_trend(df_daily)["daily"] != "down":
        return _rf("rf_dead_cat", "pass", "not in a daily downtrend", {}, 10.0)
    tail = closes.iloc[-20:]
    low_pos = int(np.argmin(tail.values))
    low_val = float(tail.iloc[low_pos])
    bounce_pct = (float(tail.iloc[-1]) / low_val - 1.0) * 100.0
    evidence = {"bounce_pct": round(bounce_pct, 1),
                "days_since_low": len(tail) - 1 - low_pos}
    if bounce_pct < spec.threshold("bounce_pct"):
        return _rf("rf_dead_cat", "pass", "no meaningful bounce yet", evidence, 10.0)
    # structure shift = a pullback low ABOVE the low, then a new bounce high
    vals = tail.values[low_pos:]
    structure = False
    for i in range(1, len(vals) - 1):
        is_local_low = vals[i] < vals[i - 1] and vals[i] < vals[i + 1]
        if is_local_low and vals[i] > low_val and float(max(vals[i + 1:])) > float(max(vals[:i])):
            structure = True
            break
    evidence["structure_shift"] = structure
    if structure:
        return _rf("rf_dead_cat", "pass",
                   "higher-low + higher-high printed since the low", evidence, 10.0)
    return _rf("rf_dead_cat", "fail",
               f"dead-cat risk: +{bounce_pct:.1f}% V-bounce in a downtrend, "
               f"no structure shift yet", evidence, 10.0)


register(check_id="rf_dead_cat", section="redflag", weight=10.0, func=rf_dead_cat,
         thresholds={
             "bounce_pct": ThresholdSpec("bounce_pct", 5.0, 2.0, 15.0, 0.5,
                 "raise to flag only larger bounces",
                 presets={"strict": 4.0, "balanced": 5.0, "relaxed": 8.0}),
         })


def rf_divergence_trap(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """For divergence-ENTRY strategies: divergence exists but price has
    not confirmed it (no close beyond the intervening swing)."""
    if plan.strategy != "RSI Divergence":
        return _rf("rf_divergence_trap", "pass", "n/a (not a divergence entry)", {}, 8.0)
    from swingbot.core.gate.setup_quality import _pivot_high_positions
    closes_full = df_daily["Close"]
    if len(closes_full) < 60:
        return _rf("rf_divergence_trap", "unknown", "insufficient history", {}, 8.0)
    window = closes_full.iloc[-60:]
    rsi_window = rsi(closes_full).iloc[-60:]
    bullish = plan.direction == "bullish"
    price_probe = -window if bullish else window       # pivot LOWS via negation
    rsi_probe = -rsi_window if bullish else rsi_window
    pivots = _pivot_high_positions(price_probe, span=3)[-2:]
    if len(pivots) < 2:
        return _rf("rf_divergence_trap", "pass", "no divergence structure found", {}, 8.0)
    a, b = pivots
    # bullish: price lower low (probe higher) with RSI higher low (probe lower)
    divergent = (price_probe.iloc[b] > price_probe.iloc[a]
                 and rsi_probe.iloc[b] < rsi_probe.iloc[a])
    if not divergent:
        return _rf("rf_divergence_trap", "pass", "no active divergence", {}, 8.0)
    swing = float(window.iloc[a:b + 1].max()) if bullish else float(window.iloc[a:b + 1].min())
    last = float(window.iloc[-1])
    confirmed = last > swing if bullish else last < swing
    evidence = {"swing_level": round(swing, 2), "last_close": round(last, 2)}
    if confirmed:
        return _rf("rf_divergence_trap", "pass",
                   f"divergence confirmed by close beyond {swing:.2f}", evidence, 8.0)
    return _rf("rf_divergence_trap", "fail",
               "divergence without price confirmation — wait for the "
               "confirmation close", evidence, 8.0)


register(check_id="rf_divergence_trap", section="redflag", weight=8.0,
         func=rf_divergence_trap, applies_to=("RSI Divergence",))


def rf_extreme_fade(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """Fading a STRONG trend on overbought/oversold alone — "overbought
    can stay overbought". Weak-trend counter plays warn only (mean
    reversion's own edge IS fading; G80 relaxes applies_to accordingly)."""
    spec = CHECKS["rf_extreme_fade"]
    from swingbot.core.gate.context_htf import htf_trend
    trend = htf_trend(df_daily)["daily"]
    bullish = plan.direction == "bullish"
    counter = (trend == "down" and bullish) or (trend == "up" and not bullish)
    if not counter:
        return _rf("rf_extreme_fade", "pass", "not a counter-trend plan",
                   {"trend": trend}, 8.0)
    rsi_val = float(rsi(df_daily["Close"]).iloc[-1])
    adx_val = float(adx(df_daily).iloc[-1])
    extreme = (rsi_val <= spec.threshold("rsi_lo") if bullish
               else rsi_val >= spec.threshold("rsi_hi"))
    evidence = {"rsi": round(rsi_val, 1), "adx": round(adx_val, 1), "trend": trend}
    if not extreme:
        return _rf("rf_extreme_fade", "pass",
                   "counter-trend but not at an RSI extreme", evidence, 8.0)
    if adx_val > spec.threshold("adx_strong"):
        return _rf("rf_extreme_fade", "fail",
                   f"fading a strong trend (ADX {adx_val:.0f}) on RSI "
                   f"{rsi_val:.0f} alone", evidence, 8.0)
    return _rf("rf_extreme_fade", "warn",
               f"counter-trend fade (ADX {adx_val:.0f} — trend not strong)",
               evidence, 8.0)


register(check_id="rf_extreme_fade", section="redflag", weight=8.0,
         func=rf_extreme_fade,
         thresholds={
             "rsi_hi": ThresholdSpec("rsi_hi", 75.0, 60.0, 90.0, 1.0,
                 "raise to flag only more extreme overbought fades",
                 presets={"strict": 70.0, "balanced": 75.0, "relaxed": 85.0}),
             "rsi_lo": ThresholdSpec("rsi_lo", 25.0, 10.0, 40.0, 1.0,
                 "lower to flag only more extreme oversold fades",
                 presets={"strict": 30.0, "balanced": 25.0, "relaxed": 15.0}),
             "adx_strong": ThresholdSpec("adx_strong", 30.0, 20.0, 50.0, 1.0,
                 "raise to fail only against the very strongest trends",
                 presets={"strict": 25.0, "balanced": 30.0, "relaxed": 40.0}),
         })


def rf_news_whipsaw(df_daily, plan, macro_snap, *, now=None, **ctx) -> CheckResult:
    """HB inside the blackout window. Statuses are information — actually
    holding an entry additionally requires GATE_BLACKOUT_ENFORCE (G120)."""
    if not macro_snap or not macro_snap.get("events"):
        return _rf("rf_news_whipsaw", "unknown", "no event calendar available", {}, 10.0)
    now = now or dt.datetime.now(dt.timezone.utc)
    before = float(getattr(config, "GATE_BLACKOUT_HOURS_BEFORE", 18))
    after = float(getattr(config, "GATE_BLACKOUT_HOURS_AFTER", 2))
    seen = {}
    ev_section = macro_snap["events"]
    for e in (ev_section.get("within_24h") or []) + \
             ([ev_section["next_high_impact"]] if ev_section.get("next_high_impact") else []):
        seen[(e["date"], e["kind"])] = e
    for event in seen.values():
        hours = calendar_events.hours_until(event, now)
        if -after <= hours <= before:
            detail = f"{event['label']} in {hours:.0f}h — inside the blackout window"
            if event["importance"] >= 3:
                return _rf("rf_news_whipsaw", "fail", detail,
                           {"event": event, "hours": round(hours, 1)}, 10.0)
            return _rf("rf_news_whipsaw", "warn", detail,
                       {"event": event, "hours": round(hours, 1)}, 10.0)
    # Earnings blackout (reuses G33; defers to edge E18's gate if merged)
    days = int(getattr(config, "GATE_EARNINGS_BLACKOUT_DAYS", 3))
    within = earnings.earnings_within(plan.ticker, days, now=now.date())
    if within:
        return _rf("rf_news_whipsaw", "fail",
                   f"earnings within {days} days", {"earnings_within_days": days}, 10.0)
    return _rf("rf_news_whipsaw", "pass", "no high-impact event in the window", {}, 10.0)


register(check_id="rf_news_whipsaw", section="redflag", weight=10.0,
         func=rf_news_whipsaw, hard_block=True)


def rf_thin_session(df_daily, plan, macro_snap, *, now=None, **ctx) -> CheckResult:
    """warn-grade only — EOD swing entries mostly dodge intraday windows,
    but illiquid tickers and dead weeks still deserve the label."""
    from swingbot.core.macro.sessions import is_thin_window
    dollar_vol = float((df_daily["Close"] * df_daily["Volume"]).iloc[-20:].median())
    floor = float(getattr(config, "GATE_MIN_DOLLAR_VOL", 2_000_000))
    if dollar_vol < floor:
        return _rf("rf_thin_session", "warn",
                   f"median dollar volume ${dollar_vol:,.0f} below the "
                   f"${floor:,.0f} floor",
                   {"dollar_vol": round(dollar_vol)}, 6.0)
    now_et = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ET)
    thin, reason = is_thin_window(now_et)
    if thin:
        return _rf("rf_thin_session", "warn", f"thin session: {reason}",
                   {"reason": reason}, 6.0)
    return _rf("rf_thin_session", "pass", "normal liquidity conditions",
               {"dollar_vol": round(dollar_vol)}, 6.0)


register(check_id="rf_thin_session", section="redflag", weight=6.0,
         func=rf_thin_session, trigger_recheck=True)
