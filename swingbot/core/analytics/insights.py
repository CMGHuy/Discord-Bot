"""Human-readable rollups over the journal + closed-trade record: the
weekly lessons digest (this task), the edge-decay report and top-lessons
list (Task A26). Every number is delegated to metrics.py/calibration.py --
this module only formats, it never computes a stat from scratch. Posting
these strings to Discord is entirely Plan B's job; every function here
returns plain strings and takes no bot/channel object."""
from __future__ import annotations

import datetime as dt
from collections import Counter

from swingbot.core.analytics import calibration, metrics

DISCORD_MESSAGE_LIMIT = 1900  # headroom under Discord's ~2000-char hard cap


def _date_of(iso_str: str | None) -> dt.date | None:
    if not iso_str:
        return None
    try:
        return dt.datetime.fromisoformat(iso_str).date()
    except ValueError:
        return None


def _in_window(iso_str: str | None, start: dt.date, end: dt.date) -> bool:
    d = _date_of(iso_str)
    return d is not None and start <= d <= end


def _chunk(lines: list[str], limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    """Greedily pack `lines` (already-formatted, newline-joinable strings)
    into as few messages as possible without any single message exceeding
    `limit` characters -- splits between lines only, never mid-line, so a
    long individual line can still overflow (acceptable here since every
    caller's individual lines are already bounded well under the limit by
    construction: a lesson string, a ticker, a tag)."""
    messages, current = [], []
    current_len = 0
    for line in lines:
        add_len = len(line) + 1
        if current and current_len + add_len > limit:
            messages.append("\n".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += add_len
    if current:
        messages.append("\n".join(current))
    return messages or [""]


def weekly_digest(entries: list[dict], closed: list[dict], today: dt.date) -> list[str]:
    """Trailing-7-day (today inclusive) lessons digest: headline stats,
    best/worst trade with its auto_lesson, top-3 tags by frequency, a
    tier-calibration one-liner, and up to 3 note excerpts."""
    window_start = today - dt.timedelta(days=6)
    week_closed = [t for t in closed if _in_window(t.get("closed_at"), window_start, today)]
    week_entries = [e for e in entries if _in_window(e.get("closed_at"), window_start, today)]

    n = len(week_closed)
    wr = metrics.win_rate(week_closed)
    er = metrics.expectancy_r(week_closed)
    total_pnl = sum(float(t.get("realized_pnl_amount") or 0.0) for t in week_closed)

    lines = [f"**📓 Weekly Lessons Digest — {window_start.isoformat()} to {today.isoformat()}**", ""]
    if n == 0:
        lines.append("n=0 trades closed this week — nothing to report.")
        return _chunk(lines)

    wr_str = f"{wr:.0f}" if wr is not None else "n/a"
    er_str = f"{er:+.2f}R" if er is not None else "n/a"
    lines.append(f"**{n} trade(s) closed** — WR {wr_str}%, expectancy {er_str}, P&L {total_pnl:+.2f}")

    ranked = sorted((e for e in week_entries if e.get("r_realized") is not None),
                    key=lambda e: e["r_realized"])
    if ranked:
        worst, best = ranked[0], ranked[-1]
        lines.append("")
        lines.append(f"**Best:** {best['ticker']} {best['r_realized']:+.2f}R — {best['auto_lesson']}")
        if worst is not best:
            lines.append(f"**Worst:** {worst['ticker']} {worst['r_realized']:+.2f}R — {worst['auto_lesson']}")

    tag_counts = Counter(tag for e in week_entries for tag in (e.get("tags") or []))
    if tag_counts:
        lines.append("")
        lines.append("**Top tags:** " + ", ".join(f"{tag} ({count})" for tag, count in tag_counts.most_common(3)))

    tier_rows = [r for r in calibration.tier_calibration(week_closed) if r["n"] > 0]
    if tier_rows:
        lines.append("")
        lines.append("**Tier calibration:** " + " · ".join(
            f"{r['tier']}: {r['win_rate']:.0f}% (n={r['n']}, band {r['expected_band']})" for r in tier_rows
        ))

    notes = [e for e in week_entries if (e.get("note") or "").strip()][:3]
    if notes:
        lines.append("")
        lines.append("**Notes:**")
        for e in notes:
            excerpt = e["note"][:140] + ("…" if len(e["note"]) > 140 else "")
            lines.append(f"• {e['ticker']}: {excerpt}")

    return _chunk(lines)
