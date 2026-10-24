"""V118-6: the one place the SHORT extra-lane execution notice is worded.

Discord (full + simple), email and push all call `short_lane_notice`, so the
borrow warning, decision date, stale marker and plan numbers cannot drift
apart. The numbers are whatever the caller already took from
`plan_numbers_for_display` (the clamped v2 stop included) -- this module never
re-derives a price. `CHECK BORROW AVAILABILITY` is a manual broker check: the
bot never verifies a locate and never places an order.

v183 adds the squeeze / earnings / ex-div lines read from the plan's stamped
`risk_notice` snapshot. `risk_notice_lines` is their only wording: Discord
full and simple, email, push and the plan page all take them from here, and
`alert_notice` appends them to every stamped short alert.
"""
import datetime as dt

BORROW_TEXT = "CHECK BORROW AVAILABILITY"
NOT_A_LOCATE = "Manual broker check — not a verified locate."
FIELD_NAME = "SHORT execution check"

SQUEEZE_PREFIX = "⚠ SQUEEZE RISK · "
SQUEEZE_NOT_CHECKED = "⚠ Squeeze data not checked — verify short interest at your broker"
EARNINGS_NOT_CHECKED = "Earnings: not checked"
_NA = "n/a"
_FLOAT_UNITS = ((1e9, "B"), (1e6, "M"), (1e3, "K"))


def _fmt_float_shares(v) -> str:
    """Float in B / M / K with one decimal; thousands separators below 1e3."""
    if v is None:
        return _NA
    for size, unit in _FLOAT_UNITS:
        if v >= size:
            return f"{v / size:.1f}{unit}"
    return f"{v:,.0f}"


def _num_or_na(v, fmt: str) -> str:
    return _NA if v is None else format(v, fmt)


def _si_line(si: dict) -> str:
    pct = _num_or_na(si.get("short_pct_float"), ".1f")
    pct = pct if pct == _NA else f"{pct}%"
    stale = " · STALE" if si.get("stale") else ""
    line = (f"Short interest {pct} of float · {_num_or_na(si.get('days_to_cover'), '.1f')} "
            f"days to cover · float {_fmt_float_shares(si.get('float_shares'))} "
            f"(as of {si.get('si_date') or _NA}{stale})")
    return f"{SQUEEZE_PREFIX}{line}" if squeeze_tripped(si) else line


def _sessions_text(n: int | None) -> str:
    if n is None:
        return ""
    if n == 0:
        return " (on the signal bar)"
    return f" (in {n} session{'' if n == 1 else 's'})"


_EARNINGS_FIXED = {"none_in_hold": "No earnings in hold", "not_checked": EARNINGS_NOT_CHECKED,
                   "etf": "Earnings: n/a (ETF)"}


def _earnings_line(e: dict | None) -> str:
    """A missing dict (or an unknown status) reads as not checked -- never comfort."""
    status = (e or {}).get("status", "not_checked")
    if status == "in_hold":
        return f"Earnings in hold: {e.get('date') or _NA}{_sessions_text(e.get('sessions'))}"
    return _EARNINGS_FIXED.get(status, EARNINGS_NOT_CHECKED)


def _ex_div_line(x: dict | None, currency: str) -> str | None:
    if x is None:
        return None
    head = f"Ex-div in hold: {x.get('date') or _NA}"
    amount = x.get("per_share")
    if amount is None:
        return f"{head} · amount n/a"
    est = " (est.)" if x.get("estimated") else ""
    return f"{head} · ~{currency}{amount:.2f}/sh owed{est}"


def squeeze_tripped(si: dict) -> bool:
    """The stamped decision; this module never reads the live thresholds, so the
    plan page cannot drift from the alert."""
    return bool(si.get("squeeze"))


def risk_notice_lines(snapshot: dict | None, *, currency: str = "$") -> list[str]:
    """The one wording of the v183 notice: short interest, earnings, ex-div."""
    if snapshot is None:
        return []
    si = snapshot.get("short_interest")
    ok = snapshot.get("si_status") == "ok" and isinstance(si, dict)
    lines = [_si_line(si) if ok else SQUEEZE_NOT_CHECKED,
             _earnings_line(snapshot.get("earnings"))]
    ex_div = _ex_div_line(snapshot.get("ex_div"), currency)
    return lines if ex_div is None else [*lines, ex_div]


def has_risk_notice(plan_v2) -> bool:
    return getattr(plan_v2, "risk_notice", None) is not None


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
    compression plan, else the V118 extra-lane notice ("" for a base alert),
    followed by the v183 squeeze/event lines when the plan carries a snapshot."""
    if plan_v2 is not None and is_compression(plan_v2):
        base = compression_pending_notice(plan_v2, currency=currency)
    else:
        base = short_lane_notice(context, nums, getattr(plan_v2, "expiry_bars", None),
                                 currency=currency)
    if not has_risk_notice(plan_v2):
        return base
    return _with_risk_lines(base, plan_v2.risk_notice, currency)


def _with_risk_lines(base: str, snapshot: dict, currency: str) -> str:
    """base, then the notice lines, then one borrow check (unless base has it)."""
    parts = [base] if base else []
    parts.extend(risk_notice_lines(snapshot, currency=currency))
    if BORROW_TEXT not in base:
        parts.append(BORROW_TEXT)
    return "\n".join(parts)


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
