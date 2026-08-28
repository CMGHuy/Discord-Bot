"""Trade-plan presentation helpers.

`plan_numbers_for_display` is THE cutover switch deciding whether every
consumer shows legacy scenario numbers or v2 plan numbers.
"""
from swingbot import config
from swingbot.core.backtesting.registry import Badge, decay_for
from swingbot.core.planning import account
from swingbot.core.planning.account import compute_position_size, load_account_config
from swingbot.core.planning.plan_engine import WEAK_CAUTION_TEXT, badge_stats_line, runner_floor

from .requirements import _sources_str
def plan_numbers_for_display(plan, legacy: dict) -> dict:
    """THE cutover switch: which numbers do embeds/charts/trade-logging
    show? flag != 'on' or no plan -> legacy scenario numbers (today's
    behavior); 'on' -> the v2 plan's numbers."""
    if config.PLAN_ENGINE_V2 != "on" or plan is None:
        return dict(legacy)
    return {"entry": plan.trigger_price, "stop_loss": plan.stop_loss,
            "take_profit": plan.tp1, "target2": plan.tp2}


def _ansi_bad(text: str) -> str:
    """Bold red, Discord ansi code-block palette -- used to mark a single failing requirement's row/value."""
    return f"[1;31m{text}[0m"


def _build_trade_plan_table(item) -> str:
    """
    Renders the full trade plan as a single aligned, monospace table
    (key : value rows in an ansi code block) -- every summarized
    parameter of the trade in one place, including which independent
    strategies (EMA/VWAP/Fibonacci/structure/pivots/FVG/...) agreed on
    the target and stop levels that produced this plan.

    Every row is always shown with its real computed value, regardless
    of whether it clears the configured requirement for that parameter
    (min reward %, stop distance, risk:reward, min strategies
    confirmed, min confidence) -- a scenario with a real entry point is
    never hidden just because one number falls short. Whichever
    row(s) correspond to an unmet requirement (see item.requirements)
    are rendered in bold red with the actual requirement appended, so
    it's always visible AT A GLANCE which specific parameter is holding
    a setup back, not just that "something" failed.
    """
    result, plan, conf = item.result, item.plan, item.conf
    is_bull = result.trend == "bullish"
    level_word = "Resistance" if is_bull else "Support"
    direction = "LONG (buy)" if is_bull else "SHORT (sell)"
    stop_sign = "-" if is_bull else "+"

    plan_v2 = getattr(item, "plan_v2", None)
    nums = plan_numbers_for_display(plan_v2, {
        "entry": plan.entry, "stop_loss": plan.stop_loss,
        "take_profit": plan.take_profit, "target2": plan.target2_price})
    entry, stop_loss = nums["entry"], nums["stop_loss"]
    take_profit, target2 = nums["take_profit"], nums["target2"]
    v2_priced = config.PLAN_ENGINE_V2 == "on" and plan_v2 is not None
    if entry == plan.entry and stop_loss == plan.stop_loss:
        # funnel returned the legacy numbers -- keep the scenario's own
        # (differently-rounded) distance/RR fields byte-identical
        stop_dist_pct = plan.stop_distance_pct
        target_dist_pct = plan.target_distance_pct
        target2_dist_pct = plan.target2_distance_pct
        rr = plan.risk_reward_ratio
    else:
        stop_dist_pct = abs(entry - stop_loss) / entry * 100
        target_dist_pct = abs(take_profit - entry) / entry * 100
        target2_dist_pct = (abs(target2 - entry) / entry * 100
                            if target2 is not None else None)
        risk = abs(entry - stop_loss)
        rr = round(abs(take_profit - entry) / risk, 2) if risk else plan.risk_reward_ratio

    req_by_key = {r.key: r for r in item.requirements}

    def _row_value(key: str, ok_value: str) -> str:
        """Plain value if the requirement passed (or doesn't apply); the requirement's own
        failure detail, bold red, if it didn't."""
        r = req_by_key.get(key)
        if r is None or r.passed:
            return ok_value
        return _ansi_bad(f"{ok_value}  ⚠ {r.detail}")

    stop_value = f"{stop_loss:.2f}  ({stop_sign}{stop_dist_pct:.1f}%)"
    min_stop_req, max_stop_req = req_by_key.get("min_stop_distance"), req_by_key.get("max_stop_distance")
    if min_stop_req and not min_stop_req.passed:
        stop_value = _ansi_bad(f"{stop_value}  ⚠ {min_stop_req.detail}")
    elif max_stop_req and not max_stop_req.passed:
        stop_value = _ansi_bad(f"{stop_value}  ⚠ {max_stop_req.detail}")

    rows = [
        ("Direction", direction),
        ("Entry (now)", f"{entry:.2f}"),
    ]
    if v2_priced:
        # Make it unmistakable that these prices came from the v2 plan
        # engine, not the legacy scenario sizing.
        rows.insert(0, ("Engine", "Plan Engine v2"))
    rows += [
        ("Stop loss", stop_value),
        (f"{level_word} 1 (Target)", _row_value("min_reward", f"{take_profit:.2f}  (+{target_dist_pct:.1f}%)")),
    ]
    if target2 is not None:
        rows.append((f"{level_word} 2 (Stretch)", f"{target2:.2f}  (+{target2_dist_pct:.1f}%)"))
    rows.append(("Reward:Risk", _row_value("min_risk_reward", f"{rr}:1")))
    rows.append(("Confidence", _row_value("min_confidence", f"{conf.label} (Lv{conf.level}/5)")))
    rows.append(("Target confirmed by", _row_value("min_confluence", _sources_str(plan.target_sources))))
    rows.append(("Stop confirmed by", _sources_str(plan.stop_sources)))

    # Position sizing -- uses the live account config so !account changes
    # are reflected immediately without a bot restart.
    account_cfg = load_account_config()
    pos = compute_position_size(entry, stop_loss, account_cfg)
    kill_blocked = getattr(item, "kill_switch_blocked", None)
    if kill_blocked is not None and pos:
        # Kill switch (E47): unlike E7/E8's heat/cluster caps just below in
        # build_embed (which only add a headline label -- this "Suggested
        # size" row stays at its uncapped value for those two), the kill
        # switch actually zeroes every number this row shows. Entries are
        # fully paused scan-wide, so the honest suggested size IS zero,
        # not a labeled-but-unchanged ideal.
        pos = dict(pos, shares=0.0, position_value=0.0, risk_amount=0.0)
    if pos and pos["balance"] > 0:
        cur = config.CURRENCY_SYMBOL
        cap_note = f"  [capped at {pos['max_position_pct']:.0f}% of account]" if pos["capped"] else ""
        rows.append((
            "Suggested size",
            f"~{pos['shares']:.1f} shares  "
            f"({cur}{pos['position_value']:,.0f} deployed, "
            f"{cur}{pos['risk_amount']:,.0f} at risk @ {pos['risk_pct']}% rule){cap_note}",
        ))
        # Possible P&L in real currency, not just % -- the "Suggested size"
        # row above already states the $ at risk, but never the $ upside,
        # so there was no way to see the actual dollar trade-off (risk $X to
        # make $Y) without doing the shares x distance math yourself.
        possible_profit = pos["shares"] * abs(take_profit - entry)
        pnl_line = f"+{cur}{possible_profit:,.0f} at target  /  -{cur}{pos['risk_amount']:,.0f} at stop"
        if target2 is not None:
            possible_profit2 = pos["shares"] * abs(target2 - entry)
            pnl_line += f"  (+{cur}{possible_profit2:,.0f} at stretch target)"
        rows.append(("Possible P&L", pnl_line))

    if plan_v2 is not None:
        rows.append(("Entry (v2)", entry_line(plan_v2)))
        cur = config.CURRENCY_SYMBOL
        tp1_row, runner_row = leg_rows(plan_v2, currency=cur, force_zero=kill_blocked is not None)
        rows.append(("TP1 leg (50%)", tp1_row))
        rows.append(("Runner leg (50%)", runner_row))

    key_width = max(len(k) for k, _ in rows)
    lines = [f"{k.ljust(key_width)} : {v}" for k, v in rows]
    return "```ansi\n" + "\n".join(lines) + "\n```"


def badge_field_for(plan) -> tuple[str, str] | None:
    """(field_name, field_value) for a v2 plan's pedigree, or None."""
    if plan is None:
        return None
    stats = plan.badge_stats or {}
    run_date = stats.get("run_date", "")
    badge = Badge(status=plan.badge, n=stats.get("n", 0),
                  win_rate=stats.get("win_rate", 0.0),
                  expectancy_r=stats.get("expectancy_r", 0.0),
                  window=stats.get("window", ""), run_date=run_date,
                  decay=decay_for(run_date))
    if plan.badge == "VALIDATED":
        return ("✅ VALIDATED", badge_stats_line(badge))
    caution = WEAK_CAUTION_TEXT.format(win_rate=badge.win_rate, n=badge.n)
    return ("⚠️ WEAK", f"**{caution}**")


def quality_lines(plan) -> tuple[str, str] | None:
    """('Quality: 82/100', 'regime +15 · htf +8 · ...') or None for
    unscored plans. Middle-dot separated, signed ints -- rendering is
    FIXED here; every consumer prints these two strings verbatim."""
    if plan is None or not plan.quality_breakdown:
        return None
    header = f"Quality: {plan.quality_score}/100"
    detail = " · ".join(f"{name} {pts:+d}" for name, pts in plan.quality_breakdown)
    return header, detail


def entry_line(plan) -> str:
    if plan.entry_type == "stop_entry":
        side = "BUY STOP above" if plan.direction == "bullish" else "SELL STOP below"
        return (f"Entry: {side} {plan.trigger_price:.2f} "
                f"(expires in {plan.expiry_bars} bars)")
    return f"Entry: market ~{plan.trigger_price:.2f}"


def _entry_price(plan) -> float:
    """plan.entry_price, falling back to trigger_price for a plan whose
    entry was never set (unfilled stop/limit entry)."""
    return plan.entry_price if plan.entry_price is not None else plan.trigger_price


def _sizing_snapshot(entry, plan) -> dict | None:
    """A fresh account.compute_position_size() snapshot, or None if sizing
    data isn't available -- swallows the exception rather than crashing,
    same render-time-snapshot convention used everywhere in this module."""
    try:
        return account.compute_position_size(entry, plan.stop_loss)
    except Exception:
        return None


def signed_money(amount: float, currency: str) -> str:
    """'+$500.00' / '-$500.00' -- an explicitly signed currency figure.

    One helper because this exact format string has now been hand-copied
    into three surfaces (the two-leg sizing block, the TP1-hit alert and
    the !liveplans board) and got the sign wrong twice on the way: once as
    a hardcoded '+' with no abs() ('+$-500.00'), and once as a bare '' for
    the negative branch, which renders a banked *loss* as a positive-looking
    '$500.00'. The sign is the whole point of the figure, so it lives in
    exactly one place now."""
    return f"{'+' if amount >= 0 else '-'}{currency}{abs(amount):,.2f}"


def leg_rows(plan, currency: str, force_zero: bool = False) -> tuple[str, str]:
    """('50% @ 102.00 → +$17.50', '50% → TP2 105.00 / trail') for the
    two-leg sizing block. P&L uses the SAME sizing snapshot source as the
    legacy table (account.compute_position_size at render time).

    force_zero=True (kill switch, Edge plan E47) zeroes the P&L this leg
    would otherwise show -- entries are paused, so 0 is the honest number,
    not a theoretical one."""
    entry = _entry_price(plan)
    frac1 = plan.tp1_fraction
    sizing = _sizing_snapshot(entry, plan)
    if force_zero and sizing:
        sizing = dict(sizing, shares=0.0)
    tp1_pct = f"{frac1:.0%} @ {plan.tp1:.2f}"
    if sizing and sizing.get("shares"):
        sign = 1 if plan.direction == "bullish" else -1
        pnl = sizing["shares"] * frac1 * (plan.tp1 - entry) * sign
        tp1_row = f"{tp1_pct} → {signed_money(pnl, currency)}"
    else:
        tp1_row = tp1_pct
    runner = f"{1 - frac1:.0%} → " + (f"TP2 {plan.tp2:.2f} / trail"
                                      if plan.tp2 else "trail")
    return tp1_row, runner


def banked_leg_pct_and_amount(plan, exit_price: float, fraction: float) -> tuple[float | None, float | None]:
    """(%, $) for one already-closed leg of a scale-out plan.

    % is normally computable from the plan's own entry (falling back to
    trigger_price the same way leg_rows() does, for a plan whose
    entry_price was never set) and the leg's own exit price. The $ amount
    needs a fresh account.compute_position_size() snapshot and is None when
    that returns nothing usable -- same render-time-snapshot convention and
    same silent-omission fallback leg_rows() already uses, not a zero and
    not a crash.

    A plan with no usable entry at all (both entry_price and trigger_price
    missing, or an entry of 0) yields (None, None) rather than a
    ZeroDivisionError/TypeError -- unreachable for a real filled plan, but
    the omit-never-crash convention applies to the % figure too, so every
    caller must be prepared for a None pct."""
    entry = _entry_price(plan)
    if not entry:
        return None, None
    sign = 1 if plan.direction == "bullish" else -1
    pct = (exit_price - entry) / entry * 100 * sign
    sizing = _sizing_snapshot(entry, plan)
    amount = None
    if sizing and sizing.get("shares"):
        amount = sizing["shares"] * fraction * (exit_price - entry) * sign
    return pct, amount


def partial_position_line(plan) -> str:
    """'entry 102.00 -> target 150.00 / stop 118.67' for the runner half of
    a PARTIAL plan -- the same entry -> target / stop shape used everywhere
    else in the bot's embeds, so it reads as one more position rather than
    a new format.

    Entry is the TP1 leg's own fill price (legs_realized[0]['exit_price']),
    not the plan's tp1 target level -- they are usually equal but the fill
    can differ on a gap-through. Falls back to plan.tp1 if legs_realized is
    somehow empty (a PARTIAL plan predating this field, same defensive
    fallback plan_manager.py's own PARTIAL step already uses).

    Target falls back to tp1 when the plan has no tp2 -- most strategies
    don't set one -- with a "(tp1, no tp2)" note, matching the precedent
    already set by admin/api_v1/trades.py's current_target."""
    leg = plan.legs_realized[0] if plan.legs_realized else None
    entry = leg["exit_price"] if leg else plan.tp1
    if plan.tp2 is not None:
        target, target_note = plan.tp2, ""
    else:
        target, target_note = plan.tp1, " (tp1, no tp2)"
    orig_entry = _entry_price(plan)
    stop = (plan.working_stop if plan.working_stop is not None
           else runner_floor(orig_entry, plan.tp1))
    return f"entry {entry:.2f} → target {target:.2f}{target_note} / stop {stop:.2f}"


def _v2_plan(item):
    """The real TradePlanV2 attached to this scan item, or None -- a
    separately-named field (ScanItem.plan_v2), NOT an attribute of
    item.plan (which is always the legacy confluence-scenario object)."""
    return getattr(item, "plan_v2", None)


