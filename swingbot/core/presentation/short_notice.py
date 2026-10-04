"""V118-6: the one place the SHORT extra-lane execution notice is worded.

Discord (full + simple), email and push all call `short_lane_notice`, so the
borrow warning, decision date, stale marker and plan numbers cannot drift
apart. The numbers are whatever the caller already took from
`plan_numbers_for_display` (the clamped v2 stop included) -- this module never
re-derives a price. `CHECK BORROW AVAILABILITY` is a manual broker check: the
bot never verifies a locate and never places an order.
"""
import datetime as dt

BORROW_TEXT = "CHECK BORROW AVAILABILITY"
NOT_A_LOCATE = "Manual broker check — not a verified locate."
FIELD_NAME = "SHORT execution check"


def completed_session_date(now: dt.datetime | None = None) -> str:
    """ET date of the newest COMPLETED NYSE session (today only after the close)."""
    from swingbot.core.market.session import is_regular_session, nyse_calendar, now_et
    et = now_et(now)
    day = et.date()
    closed_today = not is_regular_session(now) and et.time() >= dt.time(16, 0)
    if not closed_today:
        day -= dt.timedelta(days=1)
    calendar = nyse_calendar()
    position = calendar.position_on_or_before(day)
    return day.isoformat() if position is None else calendar._sessions[position].isoformat()


def short_notice_line(mode: str, decision_bar_date: str, *, stale: bool) -> str:
    state = "STALE · " if stale else ""
    return f"{state}{mode} weakness · bar {decision_bar_date} · {BORROW_TEXT}"


def is_compression(plan) -> bool:
    """True for a persisted v119 compression-short plan (and only that)."""
    from swingbot.core.market.strategy_types import COMPRESSION_SHORT
    return getattr(plan, "strategy", None) == COMPRESSION_SHORT


def _px(value, currency: str) -> str:
    from swingbot.core.presentation.tokens import fmt_price
    return fmt_price(value, currency)


def _expiry_session(plan) -> str:
    """ISO date of the one session the resting sell stop lives for."""
    from swingbot.core.planning.plan_manager import _eligible_session
    session = _eligible_session(plan)
    return "the next session" if session is None else session.isoformat()


def compression_pending_notice(plan, *, currency: str = "$", shares: int | None = None) -> str:
    """The initial-alert text for the compression short, from the PERSISTED plan
    only: every channel (Discord full and simple, email, push) shows this block,
    so the trigger, stop, target, expiry and mode cannot drift apart."""
    context = plan.entry_context or {}
    size = "" if shares is None else f" · {shares:,} sh"
    head = (f"SHORT · {context.get('compression_mode', 'n/a')} weakness · completed bar "
            f"{context.get('compression_bar_date', 'n/a')} · {BORROW_TEXT}")
    levels = (f"SELL STOP (short) trigger {_px(plan.trigger_price, currency)}{size} · "
              f"structural stop {_px(plan.stop_loss, currency)} (BUY STOP) · "
              f"whole position support target {_px(plan.tp1, currency)}")
    expiry = (f"Expires {_expiry_session(plan)} at the close (1 session) — CANCEL the "
              "resting sell stop at your broker if it has not triggered")
    return f"{head}\n{levels}\n{expiry}\n{NOT_A_LOCATE} The bot places and cancels no orders."


def alert_notice(plan_v2, context: dict | None, nums: dict, *, currency: str = "$") -> str:
    """The one entry point every alert channel calls: the compression block for a
    compression plan, else the V118 extra-lane notice ("" for a base alert)."""
    if plan_v2 is not None and is_compression(plan_v2):
        return compression_pending_notice(plan_v2, currency=currency)
    return short_lane_notice(context, nums, getattr(plan_v2, "expiry_bars", None),
                             currency=currency)


CANCEL_STOP_TAIL = ("CANCEL the resting sell stop at your broker -- the bot cannot cancel it "
                    "for you")


def compression_cancel_why(plan, transition: str, detail: dict) -> str:
    """The reason line of an expired / risk-cap compression plan: it names the
    resting sell stop to cancel, never claims it was cancelled."""
    if transition == "cancelled_expired":
        return (f"not triggered in its one session ({_expiry_session(plan)}); {CANCEL_STOP_TAIL}")
    return (f"triggered at {_px(detail['entry_price'], '')} but risked "
            f"{detail['planned_loss_pct']:.1f}% against stop {_px(detail['stop_loss'], '')} -- "
            f"above the {detail['max_planned_loss_pct']:.1f}% cap; never opened as a paper "
            f"trade. {CANCEL_STOP_TAIL}; if it already filled, buy to cover")


def compression_due_lines(side_exit: str, qty: str, detail: dict, auction_clock: str) -> tuple:
    """(headline, lines) of the due notice: cover by the stated closing auction."""
    late = "LATE — " if detail.get("late") else ""
    headline = f"{late}{side_exit} {qty} in the closing auction ({auction_clock})"
    return headline, (
        "ten sessions since the fill; stage a market-on-close (MOC) buy to cover, "
        "and confirm your broker's order status before the auction",
        "ignore this if you already exited on a stop or target")


def staged_moc_line(side_exit: str) -> str:
    """A stop/target fired after the MOC was staged: the reader must cancel it."""
    return (f"CANCEL/VERIFY STAGED MOC: CANCEL or VERIFY the closing-auction {side_exit} "
            "order you staged at your broker -- the bot cannot cancel it for you")


def short_lane_notice(context: dict | None, nums: dict, expiry_bars: int | None,
                      *, currency: str = "$") -> str:
    """The notice text for an extra-lane alert; "" for a base-lane one (no context)."""
    if not context:
        return ""
    bar_date = context["decision_bar_date"]
    line = short_notice_line(context["mode"], bar_date,
                             stale=bar_date != completed_session_date())
    expiry = "n/a" if expiry_bars is None else f"{expiry_bars} bars after the signal bar"
    levels = (f"Entry {currency}{nums['entry']:.2f} · Stop {currency}{nums['stop_loss']:.2f} · "
              f"Target {currency}{nums['take_profit']:.2f} · Expires {expiry}")
    return f"{line}\n{levels}\n{NOT_A_LOCATE}"
