"""Trade-plan presentation helpers.

The wide key:value table retired in v62 had 65--70 character rows that
scrolled off a phone. The replacement is the two-line presentation headline.
`plan_numbers_for_display` remains the legacy/v2 pricing cutover switch.
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


