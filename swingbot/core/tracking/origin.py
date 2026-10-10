"""v144: which lane issued a plan or trade.

`origin` is frozen at creation, like `ledger`. `None` is the regular lane, and
every record written before v144 reads as regular because it has no key at all.
Every pooled figure (ExpR, win rate, the snapshot, the dashboard, the journal
overrides, the soak verdict) keeps to `is_regular`; a cohort view asks
`in_cohort(record, NEXT_SESSION)`. Pure: no imports, so planning, tracking,
analytics and the admin can all read it.
"""
from __future__ import annotations

NEXT_SESSION = "next_session"
ORIGINS = (NEXT_SESSION,)
ALL = "all"


def origin_of(record) -> str | None:
    """The origin of a trade/journal dict or a plan object; None = regular."""
    if isinstance(record, dict):
        return record.get("origin")
    return getattr(record, "origin", None)


def is_regular(record) -> bool:
    return origin_of(record) is None


def in_cohort(record, cohort: str | None) -> bool:
    """`cohort` None = the regular lane only; ALL = every record; else that origin."""
    if cohort == ALL:
        return True
    return origin_of(record) == cohort
