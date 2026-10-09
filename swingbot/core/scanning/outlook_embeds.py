"""v144: the outlook's words -- the 23:30 digest, an outlook card's badge and
context field, and the wrap-up. Pure: no bot import; commands/scanning/outlook.py
turns the text into SYSTEM embeds and posts it."""
from __future__ import annotations

import datetime as dt
from collections import Counter

from swingbot.core.analytics.partials import is_filled
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.planning.session_expiry import cancel_reason
from swingbot.core.presentation.kinds import side_word

OUTLOOK_BADGE = "🌙"
WATCH_NOTE = "market entry: fills at the signal close, no resting order for tomorrow"
CONTEXT_FIELD = "Context (display only)"


def day_label(day: dt.date) -> str:
    return f"{day:%A} {day.isoformat()}"


def _head(line) -> str:
    return f"{line.ticker} {side_word(line.direction)} · {line.strategy}"


def _levels(line) -> str:
    return f"entry {line.entry:.2f} stop {line.stop:.2f} target {line.target:.2f}"


def _plan_row(line) -> str:
    risk = "risk n/a" if line.risk_dollars is None else f"risk ${line.risk_dollars:,.0f}"
    return f"{_head(line)} · {_levels(line)} · {risk}"


def _watch_row(line) -> str:
    return f"{_head(line)} · {_levels(line)}"


def _near_row(line) -> str:
    return f"{_head(line)} · {line.reason}"


def _sections(result) -> list[str]:
    blocks = (("Plans", result.plans, _plan_row),
              (f"Watch — {WATCH_NOTE}", result.watch, _watch_row),
              ("Near-misses", result.near_misses, _near_row))
    lines: list[str] = []
    for title, rows, render in blocks:
        if rows:
            lines.append(f"**{title} ({len(rows)})**")
            lines.extend(f"• {render(row)}" for row in rows)
    if result.skipped:
        lines.append(f"**Skipped — outlook plan already open ({len(result.skipped)})**: "
                     f"{', '.join(result.skipped)}")
    return lines


def _is_empty(result) -> bool:
    return not (result.plans or result.watch or result.near_misses or result.skipped)


def digest_text(result) -> str:
    """The 23:30 digest. Always says something, so silence never means failure."""
    if result.target is None:
        tomorrow = result.run_date + dt.timedelta(days=1)
        return f"No NYSE session tomorrow ({day_label(tomorrow)}) — no outlook issued."
    head = f"**Outlook for {day_label(result.target)}**"
    if result.unavailable:
        return f"{head}\nOutlook unavailable: {result.unavailable}"
    if _is_empty(result):
        return f"{head} — no plans, no watch names, no near-misses."
    return "\n".join([head, *result.regime_lines, *_sections(result)])


def card_badge(valid_session: dt.date) -> str:
    return f"{OUTLOOK_BADGE} **Outlook · valid {day_label(valid_session)} only**"


def decorate_card(embed, *, valid_session: dt.date, context_line: str | None) -> None:
    """The outlook badge above the regular plan embed's description, and the
    display-only context field. The ⚠ overlap field is lane_overlap's."""
    embed.description = f"{card_badge(valid_session)}\n{embed.description or ''}"[:4096]
    if context_line:
        embed.add_field(name=CONTEXT_FIELD, value=context_line, inline=False)


def _code(plan) -> str:
    return cancel_reason(plan) or "cancelled"


def _wrapup_row(plan) -> str:
    head = f"{plan.ticker} {side_word(plan.direction)}"
    if plan.status == PlanStatus.CANCELLED:
        return f"{head} — cancelled ({_code(plan)}): {plan.cancel_reason_message or _code(plan)}"
    if is_filled(plan):
        return f"{head} — filled at {plan.entry_price:.2f}"
    return f"{head} — {str(plan.status).lower()}"


def count_line(plans: list) -> str:
    filled = sum(1 for plan in plans if is_filled(plan))
    codes = Counter(_code(plan) for plan in plans if plan.status == PlanStatus.CANCELLED)
    detail = f" ({', '.join(f'{code} ×{n}' for code, n in sorted(codes.items()))})" if codes else ""
    return f"{len(plans)} issued · {filled} filled · {sum(codes.values())} cancelled{detail}"


def wrapup_text(day: dt.date, plans: list) -> str:
    return "\n".join([f"**Outlook wrap-up · {day_label(day)}**",
                      *(f"• {_wrapup_row(plan)}" for plan in plans), count_line(plans)])
