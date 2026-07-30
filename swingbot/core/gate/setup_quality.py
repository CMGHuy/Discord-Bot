"""Section-2 setup-quality checks. Raw helpers (volume_ratio,
momentum_with_plan) are shared by the confluence counter (G53)."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from swingbot.core.gate.registry import CHECKS, ThresholdSpec, register
from swingbot.core.gate.types import CheckResult
from swingbot.core.indicators import rsi, macd

ET = ZoneInfo("America/New_York")

# Strategies whose entry IS a level break — cross-checked against the real
# ALL_STRATEGIES names (backtest.py:426); revisited deliberately in G80.
BREAKOUT_FAMILY = ("Break & Retest", "Support/Resistance", "Volume Profile")
MEANREV_FAMILY = ("RSI", "RSI Divergence")


def check_signal_confirmed(df_daily, plan, macro_snap, *, now=None, **ctx) -> CheckResult:
    """HARD BLOCK: never alert on an unclosed pattern."""
    now_et = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ET)
    session_open = (now_et.weekday() < 5
                    and dt.time(9, 30) <= now_et.time() < dt.time(16, 0))
    if plan.created_at == now_et.date().isoformat() and session_open:
        return CheckResult("signal_confirmed", "setup", "fail", 10.0,
                           "signal bar is still forming — pattern not closed",
                           {"created_at": plan.created_at,
                            "now_et": now_et.isoformat()})
    if plan.strategy in BREAKOUT_FAMILY and plan.entry_type == "market":
        level = plan.trigger_price
        bullish = plan.direction == "bullish"
        close = float(df_daily["Close"].iloc[-1])
        hi, lo = float(df_daily["High"].iloc[-1]), float(df_daily["Low"].iloc[-1])
        beyond = close > level if bullish else close < level
        poked = hi >= level if bullish else lo <= level
        if poked and not beyond:
            return CheckResult("signal_confirmed", "setup", "fail", 10.0,
                               "breakout bar closed back inside the level — "
                               "intrabar poke, not a confirmed close",
                               {"level": level, "close": close})
    return CheckResult("signal_confirmed", "setup", "pass", 10.0,
                       "signal bar closed / pattern confirmed",
                       {"created_at": plan.created_at})


register(check_id="signal_confirmed", section="setup", weight=10.0,
         func=check_signal_confirmed, hard_block=True)


def volume_ratio(df_daily) -> float | None:
    """Signal-bar volume vs 20d average — shared with G54."""
    vol = df_daily["Volume"]
    if len(vol) < 21:
        return None
    avg20 = float(vol.iloc[-21:-1].mean())
    return float(vol.iloc[-1]) / avg20 if avg20 > 0 else None


def _cached_rsi(closes, *, cache: dict | None = None):
    """Same compute-once-per-run_checklist-call pattern as swing_levels/
    htf_trend/atr (G87 perf guard) — rsi(closes) on the full Close series
    is computed identically by momentum_with_plan, check_momentum and
    check_divergence_against (and, conditionally, two redflags checks)."""
    if cache is None:
        return rsi(closes)
    key = ("rsi", id(closes), len(closes))
    if key in cache:
        return cache[key]
    result = rsi(closes)
    cache[key] = result
    return result


def _cached_macd(closes, *, cache: dict | None = None):
    if cache is None:
        return macd(closes)
    key = ("macd", id(closes), len(closes))
    if key in cache:
        return cache[key]
    result = macd(closes)
    cache[key] = result
    return result


def momentum_with_plan(df_daily, plan, *, cache: dict | None = None) -> bool | None:
    """True unless RSI slope AND MACD histogram both point against the
    plan — shared with G55."""
    closes = df_daily["Close"]
    if len(closes) < 40:
        return None
    rsi_series = _cached_rsi(closes, cache=cache)
    rsi_slope = float(rsi_series.iloc[-1] - rsi_series.iloc[-6])
    hist = float(_cached_macd(closes, cache=cache)["histogram"].iloc[-1])
    bullish = plan.direction == "bullish"
    rsi_against = rsi_slope < 0 if bullish else rsi_slope > 0
    macd_against = hist < 0 if bullish else hist > 0
    return not (rsi_against and macd_against)


def _confluence_factors(df_daily, plan, macro_snap, **ctx) -> dict[str, bool]:
    from swingbot.core.gate.context_htf import htf_trend
    from swingbot.core.gate.levels import (_safe_atr, nearest_round,
                                           swing_levels)
    cache = ctx.get("_gate_cache")
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    atr_val = _safe_atr(df_daily, entry, cache=cache)
    bullish = plan.direction == "bullish"
    swings = swing_levels(df_daily, cache=cache)
    at_level = any(abs(l.price - entry) <= 0.5 * atr_val for l in swings)
    _, round_dist = nearest_round(entry, atr=atr_val)
    closes = df_daily["Close"]
    sma_support = False
    if len(closes) >= 200:
        for period in (20, 50, 200):
            sma = closes.rolling(period).mean()
            near = abs(float(sma.iloc[-1]) - entry) <= 0.5 * atr_val
            pointing = (float(sma.iloc[-1] - sma.iloc[-6]) > 0) == bullish
            if near and pointing:
                sma_support = True
                break
    ratio = volume_ratio(df_daily)
    trend = htf_trend(df_daily, cache=cache)
    with_htf = trend["weekly"] == ("up" if bullish else "down")
    return {
        "at_swing_level": at_level,
        "near_round": round_dist <= 0.5,
        "sma_support": sma_support,
        "volume": bool(ratio and ratio >= 1.3),
        "momentum": bool(momentum_with_plan(df_daily, plan, cache=cache)),
        "with_htf": with_htf,
    }


def check_confluence(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    factors = _confluence_factors(df_daily, plan, macro_snap, **ctx)
    fired = [name for name, on in factors.items() if on]
    n = len(fired)
    status = "pass" if n >= 3 else "warn" if n == 2 else "fail"
    return CheckResult("confluence", "setup", status, 10.0,
                       f"{n} independent factors agree: {', '.join(fired) or 'none'}",
                       {"factors": fired, "count": n})


register(check_id="confluence", section="setup", weight=10.0, func=check_confluence)


def check_volume(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    spec = CHECKS["volume_confirms"]
    ratio = volume_ratio(df_daily)
    if ratio is None:
        return CheckResult("volume_confirms", "setup", "unknown", 8.0,
                           "insufficient volume history", {})
    evidence = {"ratio": round(ratio, 2)}
    if ratio >= spec.threshold("pass_mult"):
        return CheckResult("volume_confirms", "setup", "pass", 8.0,
                           f"signal volume {ratio:.1f}x the 20d average", evidence)
    if ratio >= spec.threshold("warn_mult"):
        return CheckResult("volume_confirms", "setup", "warn", 8.0,
                           f"signal volume only {ratio:.1f}x average", evidence)
    # dead volume: fail-grade for breakout entries, warn-only for mean reversion
    if plan.strategy in BREAKOUT_FAMILY:
        return CheckResult("volume_confirms", "setup", "fail", 8.0,
                           f"breakout on dead volume ({ratio:.1f}x) — the #1 trap",
                           evidence)
    return CheckResult("volume_confirms", "setup", "warn", 8.0,
                       f"dead volume ({ratio:.1f}x)", evidence)


register(check_id="volume_confirms", section="setup", weight=8.0, func=check_volume,
         thresholds={
             "pass_mult": ThresholdSpec("pass_mult", 1.3, 1.0, 3.0, 0.1,
                 "lower to accept quieter signal bars",
                 presets={"strict": 1.5, "balanced": 1.3, "relaxed": 1.1}),
             "warn_mult": ThresholdSpec("warn_mult", 0.8, 0.3, 1.2, 0.1,
                 "lower to fail only on truly dead volume",
                 presets={"strict": 0.9, "balanced": 0.8, "relaxed": 0.6}),
         })


def check_momentum(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    closes = df_daily["Close"]
    if len(closes) < 40:
        return CheckResult("momentum_agrees", "setup", "unknown", 6.0,
                           "insufficient history", {})
    cache = ctx.get("_gate_cache")
    rsi_series = _cached_rsi(closes, cache=cache)
    rsi_slope = float(rsi_series.iloc[-1] - rsi_series.iloc[-6])
    hist = float(_cached_macd(closes, cache=cache)["histogram"].iloc[-1])
    bullish = plan.direction == "bullish"
    rsi_against = rsi_slope < 0 if bullish else rsi_slope > 0
    macd_against = hist < 0 if bullish else hist > 0
    evidence = {"rsi_slope5": round(rsi_slope, 2), "macd_hist": round(hist, 4)}
    if rsi_against and macd_against:
        return CheckResult("momentum_agrees", "setup", "fail", 6.0,
                           "RSI slope AND MACD histogram both point against the plan",
                           evidence)
    if rsi_against or macd_against:
        which = "RSI slope" if rsi_against else "MACD histogram"
        return CheckResult("momentum_agrees", "setup", "warn", 6.0,
                           f"{which} points against the plan", evidence)
    return CheckResult("momentum_agrees", "setup", "pass", 6.0,
                       "momentum agrees with the plan", evidence)


register(check_id="momentum_agrees", section="setup", weight=6.0, func=check_momentum)


def _pivot_high_positions(series, span=3) -> list[int]:
    vals = series.values
    out = []
    for i in range(span, len(vals) - span):
        win = vals[i - span:i + span + 1]
        if vals[i] == win.max() and (win == vals[i]).sum() == 1:
            out.append(i)
    return out


def check_divergence_against(df_daily, plan, macro_snap, **ctx) -> CheckResult:
    """Momentum diverging AGAINST the move at entry. Distinct from G60,
    which polices divergence-ENTRY strategies for missing confirmation."""
    closes_full = df_daily["Close"]
    if len(closes_full) < 60:
        return CheckResult("divergence_against", "setup", "unknown", 6.0,
                           "insufficient history", {})
    window = closes_full.iloc[-60:]
    rsi_window = _cached_rsi(closes_full, cache=ctx.get("_gate_cache")).iloc[-60:]
    bullish = plan.direction == "bullish"
    price_probe = window if bullish else -window       # shorts: mirror via negation
    rsi_probe = rsi_window if bullish else -rsi_window
    pivots = _pivot_high_positions(price_probe, span=3)[-3:]
    divergent_pairs = 0
    for a, b in zip(pivots, pivots[1:]):
        if price_probe.iloc[b] > price_probe.iloc[a] \
                and rsi_probe.iloc[b] < rsi_probe.iloc[a]:
            divergent_pairs += 1
    evidence = {"divergent_pairs": divergent_pairs, "pivots_found": len(pivots)}
    if divergent_pairs == 0:
        return CheckResult("divergence_against", "setup", "pass", 6.0,
                           "no momentum divergence against the move", evidence)
    if divergent_pairs >= 2 and plan.strategy != "RSI Divergence":
        return CheckResult("divergence_against", "setup", "fail", 6.0,
                           "2-swing momentum divergence against the move", evidence)
    return CheckResult("divergence_against", "setup", "warn", 6.0,
                       "momentum divergence forming against the move", evidence)


register(check_id="divergence_against", section="setup", weight=6.0,
         func=check_divergence_against)
