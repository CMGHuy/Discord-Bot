"""Section-2 setup-quality checks. Raw helpers (volume_ratio,
momentum_with_plan) are shared by the confluence counter (G53)."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from swingbot.core.gate.registry import register
from swingbot.core.gate.types import CheckResult

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
