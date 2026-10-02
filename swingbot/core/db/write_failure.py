"""A database write failure stops issuance (v116 Phase 3).

Writes already raise (the fail-fast rule). This decides which raises mean
"the book can no longer record what the scan is issuing", so the scan loop
pauses alerting instead of posting an alert whose trade or plan was never
stored. Every trading store is at db, so any database failure counts.
"""
from __future__ import annotations


class StoreWriteHalt(RuntimeError):
    """Raised in place of a swallowed store write during issuance.

    `alerts` carries the alerts the scan had already built (trade logged and
    plan stored) before the halt, so the caller can still post them: a trade
    in the book with no alert is never silently lost.
    """

    def __init__(self, *args, alerts=None):
        super().__init__(*args)
        self.alerts = list(alerts or [])


def is_store_write_failure(exc: BaseException | None) -> bool:
    """True if `exc` or anything in its cause chain is a database failure.

    Deliberately conservative: it cannot tell a write from a read, so it
    matches ANY SQLAlchemyError / DatabaseUnavailable. Every caller sits on a
    write path (`_persist_plan_v2`, the scan tick's failure handler), and a
    failing read at a db-stage store means the book is unreachable, so
    pausing until a human unpauses is the safe side to err on.
    """
    import sqlalchemy.exc as sa_exc

    from swingbot.core.db.engine import DatabaseUnavailable
    kinds = (sa_exc.SQLAlchemyError, DatabaseUnavailable, StoreWriteHalt)
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, kinds):
            return True
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return False


def halts_issuance(exc: BaseException) -> bool:
    """Every trading store is at db: any database failure halts issuance."""
    return is_store_write_failure(exc)
