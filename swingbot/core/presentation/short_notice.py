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
