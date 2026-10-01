"""A database write failure at the db stage stops issuance (v116 Phase 3).

Writes already raise (the fail-fast rule). This decides which raises mean
"the book can no longer record what the scan is issuing", so the scan loop
pauses alerting instead of posting an alert whose trade or plan was never
stored. Only once a trading store is at `db`: before that the JSON file is
still the truth, and a database hiccup during a soak must not pause alerts.
"""
from __future__ import annotations

#: The stores an issued alert writes to.
TRADING_STORES = ("plans", "trades", "account", "journal")


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


def trading_store_at_db() -> bool:
    from swingbot.core.db import stages
    return any(stages.reads_db(store) for store in TRADING_STORES)


def halts_issuance(exc: BaseException) -> bool:
    return trading_store_at_db() and is_store_write_failure(exc)
