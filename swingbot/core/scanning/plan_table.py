"""Trade-plan presentation helpers.

The wide key:value table retired in v62 had 65--70 character rows that
scrolled off a phone. The replacement is the two-line presentation headline.
`plan_numbers_for_display` remains the legacy/v2 pricing cutover switch.
"""
from swingbot import config
from swingbot.core.backtesting.registry import Badge, decay_for
from swingbot.core.planning import account
from swingbot.core.planning.plan_engine import WEAK_CAUTION_TEXT, badge_stats_line


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


# v86: the cohort line names its own cohort and numbers, the way
# badge_stats_line does. A vague "be careful" teaches the reader nothing and
# gets tuned out; "bearish setups in a volatile bear have closed 41.2% /
# -0.38R over 600 trades" is a fact they can act on.
COHORT_POOR_TEXT = (
    "⚠️ **Cohort:** {direction} setups in a {regime} regime have closed "
    "**{win_rate:.1f}% WR / {expectancy_r:+.2f}R** (n={n}, frozen {run_date}). "
    "Reduced size, manual confirmation."
)
COHORT_STRONG_TEXT = (
    "**Cohort:** {direction} setups in a {regime} regime have closed "
    "**{win_rate:.1f}% WR / {expectancy_r:+.2f}R** (n={n}, frozen {run_date})."
)
COHORT_UNKNOWN_TEXT = (
    "**Cohort:** Not enough closed trades under these conditions to say "
    "anything yet (n={n})."
)


def cohort_line(plan) -> str | None:
    """The one line a reader sees about how trades like this one have closed.
    Returns None when there is nothing honest to say -- an unstamped plan
    renders nothing rather than an empty reassurance."""
    stats = getattr(plan, "cohort_stats", None) or {}
    label = getattr(plan, "cohort_label", "COHORT_UNKNOWN")
    if not stats:
        return None
    fields = {
        "direction": plan.direction,
        "regime": stats.get("regime2_state") or "unknown",
        "win_rate": stats.get("win_rate", 0.0),
        "expectancy_r": stats.get("expectancy_r", 0.0),
        "n": stats.get("n_live", 0) + stats.get("n_backtest", 0),
        "run_date": stats.get("run_date", ""),
    }
    if label == "COHORT_POOR":
        return COHORT_POOR_TEXT.format(**fields)
    if label == "COHORT_STRONG":
        return COHORT_STRONG_TEXT.format(**fields)
    if label == "COHORT_UNKNOWN":
        return COHORT_UNKNOWN_TEXT.format(**fields)
    return None


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
    """Render a partial runner using the shared plan-view projection."""
    from swingbot.core.presentation.plan_view import plan_view

    # The lifecycle embed is built while recording a TP1 transition, before
    # some callers persist the new status. Its event already establishes that
    # this is a partial runner, so present that one attribute to the pure
    # projection without recreating any of its price derivation here.
    if plan.status != "PARTIAL":
        class PartialEventPlan:
            status = "PARTIAL"

            def __getattr__(self, name):
                return getattr(plan, name)

        view = plan_view(PartialEventPlan())
    else:
        view = plan_view(plan)
    if view.target is not None:
        return (f"entry {view.entry:.2f} → target {view.target:.2f} "
                f"/ stop {view.stop:.2f}")
    return f"entry {view.entry:.2f} → trailing stop {view.stop:.2f}"


def _v2_plan(item):
    """The real TradePlanV2 attached to this scan item, or None -- a
    separately-named field (ScanItem.plan_v2), NOT an attribute of
    item.plan (which is always the legacy confluence-scenario object)."""
    return getattr(item, "plan_v2", None)


