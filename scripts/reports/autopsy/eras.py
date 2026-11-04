"""v200 Part 3: exit-model eras around the production deploy of b4ef2e87.

Each trade falls in one era by when it was open, checked in order:

| condition                                                         | era        |
|-------------------------------------------------------------------|------------|
| closed_at_utc is None                                             | None       |
| closed_at_utc < boundary                                          | pre        |
| opened_at_utc is None                                             | None       |
| Eastern date of opened_at_utc > Eastern date of the boundary      | post       |
| otherwise (opened before or on the boundary's Eastern day)        | straddle   |

Era numbers carry no CI and no q; the merge never reads them.
"""
import datetime as dt

from swingbot.core.market.session import US_MARKET_TZ

from .cells import net_value

# Copied from docs/superpowers/results/2026-10-29-v200-prod-reads.md (V200-1).
ERA_BOUNDARY_UTC = dt.datetime(2026, 9, 15, 8, 54, 50, tzinfo=dt.timezone.utc)
ERA_BOUNDARY_SOURCE = "VM /opt/swing-bot git reflog: 8c0aeec965ff reset at 2026-09-15T08:54:50Z"
ERAS = ("pre", "straddle", "post")


def _eastern_date(stamp: dt.datetime) -> dt.date:
    return stamp.astimezone(US_MARKET_TZ).date()


def era_of(row, boundary: dt.datetime = ERA_BOUNDARY_UTC) -> str | None:
    """The row's era, or None when it cannot be placed in time."""
    if row.closed_at_utc is None:
        return None
    if row.closed_at_utc < boundary:
        return "pre"
    if row.opened_at_utc is None:
        return None
    if _eastern_date(row.opened_at_utc) > _eastern_date(boundary):
        return "post"
    return "straddle"


def _one(members: list) -> dict:
    if not members:
        return {"n": 0, "win_rate": None, "net_expr": None}
    wins = sum(1 for m in members if m.gross_r > 0)
    return {"n": len(members), "win_rate": round(wins / len(members), 4),
            "net_expr": round(sum(net_value(m) for m in members) / len(members), 4)}


def era_stats(members: list, boundary: dt.datetime = ERA_BOUNDARY_UTC) -> dict[str, dict]:
    """All three eras with n, win rate and net ExpR (4 places, None at n 0)."""
    grouped: dict[str, list] = {era: [] for era in ERAS}
    for member in members:
        era = era_of(member, boundary)
        if era is not None:
            grouped[era].append(member)
    return {era: _one(grouped[era]) for era in ERAS}


def sign_flip(stats: dict | None) -> bool:
    """True when pre and post net ExpR are both known and of opposite sign."""
    if not stats:
        return False
    pre, post = stats["pre"]["net_expr"], stats["post"]["net_expr"]
    return pre is not None and post is not None and pre * post < 0
