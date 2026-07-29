"""Section-2 setup-quality checks. Raw helpers (volume_ratio,
momentum_with_plan) are shared by the confluence counter (G53)."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from swingbot.core.gate.registry import register
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


def momentum_with_plan(df_daily, plan) -> bool | None:
    """True unless RSI slope AND MACD histogram both point against the
    plan — shared with G55."""
    closes = df_daily["Close"]
    if len(closes) < 40:
        return None
    rsi_slope = float(rsi(closes).iloc[-1] - rsi(closes).iloc[-6])
    hist = float(macd(closes)["histogram"].iloc[-1])
    bullish = plan.direction == "bullish"
    rsi_against = rsi_slope < 0 if bullish else rsi_slope > 0
    macd_against = hist < 0 if bullish else hist > 0
    return not (rsi_against and macd_against)


def _confluence_factors(df_daily, plan, macro_snap, **ctx) -> dict[str, bool]:
    from swingbot.core.gate.context_htf import htf_trend
    from swingbot.core.gate.levels import (_safe_atr, nearest_round,
                                           swing_levels)
    entry = plan.entry_price if plan.entry_price is not None else plan.trigger_price
    atr_val = _safe_atr(df_daily, entry)
    bullish = plan.direction == "bullish"
    swings = swing_levels(df_daily)
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
    trend = htf_trend(df_daily)
    with_htf = trend["weekly"] == ("up" if bullish else "down")
    return {
        "at_swing_level": at_level,
        "near_round": round_dist <= 0.5,
        "sma_support": sma_support,
        "volume": bool(ratio and ratio >= 1.3),
        "momentum": bool(momentum_with_plan(df_daily, plan)),
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
