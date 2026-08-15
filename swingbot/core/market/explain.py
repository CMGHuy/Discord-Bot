"""
Builds a concise signal explanation for a scenario -- the "why" context
that appears as the Discord embed description. Numbers (entry, stop,
target, R:R) are already shown in the embed's trade-plan field, so this
stays focused on WHAT confirmed the level and WHAT happens next, not a
second copy of the plan.

Format (3-5 lines max):
  Line 1: strategy count + which families + target level + direction
  Line 2: stop basis (brief)
  Line 3: both outcome branches in one line
  Line 4: earnings warning, if applicable
"""

# One very short phrase per strategy family -- just enough to say WHAT
# the method measures, not a full sentence. Keeps line 1 scannable.
_STRATEGY_SHORT = {
    "EMA": "EMA",
    "VWAP": "VWAP",
    "Fibonacci": "Fib retracement",
    "Rolling S/R": "rolling S/R",
    "Zigzag Pivot": "pivot",
    "Bollinger Bands": "Bollinger Band",
    "Donchian Channel": "Donchian",
    "Floor Pivot": "floor pivot",
    "Trendline": "trendline",
    "FVG": "FVG",
    "Volatility Squeeze": "squeeze breakout",
    "Candlestick Pattern": "candlestick",
}


def _family_list(families: list) -> str:
    """'EMA, VWAP, Fib retracement' — short names, comma-separated."""
    return ", ".join(_STRATEGY_SHORT.get(f, f) for f in families) if families else "n/a"


def build_explanation(result, earnings_info=None,
                      target_confluence: tuple = None,
                      stop_confluence: tuple = None,
                      confirmed_by: list = None,
                      plan=None) -> str:
    scenario = result.scenario
    is_bull = scenario.direction == "bullish"
    level_word = "resistance" if is_bull else "support"
    opp_word = "support" if is_bull else "resistance"
    arrow = "↑" if is_bull else "↓"

    # Target strategies
    if target_confluence:
        t_count, t_families = target_confluence
    else:
        t_families = list(dict.fromkeys(scenario.target_sources))
        t_count = len(t_families)

    # Stop strategies
    if stop_confluence:
        s_count, s_families = stop_confluence
    else:
        s_families = list(dict.fromkeys(scenario.stop_sources))
        s_count = len(s_families)

    t_str = _family_list(t_families)
    s_str = _family_list(s_families)
    plural = "" if t_count == 1 else "s"

    lines = []

    # Line 0: trigger-aware entry wording -- makes clear whether this trade
    # is already live at market or still waiting on a stop trigger to hit.
    if plan is not None and getattr(plan, "entry_type", None) == "stop_entry":
        trigger_word = "BUY STOP above" if is_bull else "SELL STOP below"
        lines.append(
            f"⏱️ Waits for a **{trigger_word} {plan.trigger_price:.2f}** before this trade is live."
        )
    elif plan is not None and getattr(plan, "entry_type", None) == "market":
        lines.append("▶️ Enters at market -- no trigger to wait for.")

    # Line 1: what's confirmed and where
    lines.append(
        f"{arrow} **{result.ticker}** — {t_count} method{plural} ({t_str}) "
        f"converge on {level_word} **{scenario.take_profit:.2f}** "
        f"(+{scenario.target_distance_pct:.1f}%, {result.horizon_label.lower()})."
    )

    # Line 2: stop basis
    lines.append(
        f"🛑 Stop at **{scenario.stop_loss:.2f}** "
        f"({'-' if is_bull else '+'}{scenario.stop_distance_pct:.1f}%) "
        f"— {s_str}."
    )

    # Line 2b: Break & Retest — what to wait for before entering
    # `confirmed_by` is the scenario's full multi-strategy/multi-horizon
    # agreement list (scan_engine.py's ScanItem.combined_from) -- NOT an
    # attribute of `result` itself (a plain result object never has a
    # `confirmed_by` field), so it has to be passed in explicitly by the
    # caller rather than looked up via hasattr(result, ...), which would
    # always be False and silently skip every secondary confirming
    # strategy's contribution to this check.
    strategy_names = []
    if hasattr(result, "strategy"):
        strategy_names.append(result.strategy)
    if confirmed_by:
        for cb in confirmed_by:
            if isinstance(cb, dict):
                strategy_names.append(cb.get("strategy", ""))
            elif hasattr(cb, "strategy"):
                strategy_names.append(cb.strategy)
    is_bnr = any("break" in s.lower() and "retest" in s.lower() for s in strategy_names)
    if is_bnr:
        level_label = "resistance" if is_bull else "support"
        entry_bar = "green candle close" if is_bull else "red candle close"
        lines.append(
            f"⏳ **Wait for the retest**: after the breakout, let price pull back to "
            f"the broken {level_label} (~{scenario.stop_loss:.2f} area) and wait for a "
            f"confirming {entry_bar} — entering on the breakout bar itself carries "
            f"significantly higher false-breakout risk."
        )

    # Line 3: outcome branches (one line)
    if scenario.target2_price is not None:
        t2_str = (
            f"continues → **{scenario.target2_price:.2f}** "
            f"(+{scenario.target2_distance_pct:.1f}%)"
        )
    else:
        t2_str = "continues → no further level"
    lines.append(
        f"🔀 At {scenario.take_profit:.2f}: {t2_str} "
        f"| reverses → stop {scenario.stop_loss:.2f}."
    )

    # Line 4: earnings warning
    if earnings_info is not None:
        edate, days = earnings_info
        lines.append(
            f"⚠️ Earnings **{edate}** ({days}d) — inside hold window, "
            f"volatility spike can gap through stop and target."
        )

    return "\n".join(lines)
