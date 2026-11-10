"""v209: the market-shock detector's store.

Writer: core/scanning/shock_scan.run_shock_pass (one call per stepped scan
pass), which hands over ShockReading.as_row() and ShockState.as_row() dicts.
`record` writes the reading, upserts the single state row and, when given,
enqueues the market_shock notice in ONE transaction, so last_reading_id never
dangles and a notice never outlives a rolled-back reading. Readers: the scan's
current_label() and the admin tape. Pruned nightly by loops.daily_recap.
"""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.codec import sanitise_non_finite
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.schema import market_shock_readings as readings
from swingbot.core.db.schema import market_shock_state as state_table

#: Restated from core/market/shock.LABELS so the db layer imports nothing from
#: core/market (tests pin the two equal).
LABELS = ("NORMAL", "SHOCK", "RECOVERY")
STATE_ROW_ID = 1
_READING_COLUMNS = ("as_of", "session_date", "breadth_frac", "breadth_speed",
                    "spy_atr_move", "qqq_atr_move", "vix_level", "vix_chg_pct",
                    "vix_off_high_pct", "sectors_down", "sectors_total", "n_names",
                    "insufficient")
_STATE_KEYS = ("label", "since", "session_date", "vix_session_high", "last_reading_id",
               "last_notice_at", "updated_at")


def _instant(value) -> dt.datetime | None:
    """An aware datetime from a datetime or ISO string; naive is refused."""
    if value is None:
        return None
    stamp = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("timezone_required")
    return stamp


def _day(value) -> dt.date | None:
    if value is None or isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def _check_labels(state: dict, state_after: str) -> None:
    if state.get("label") not in LABELS or state_after not in LABELS:
        raise ValueError(f"unknown shock label {state.get('label')!r}/{state_after!r}")
    if state["label"] != state_after:
        raise ValueError("state_after_mismatch")


def _reading_values(reading: dict, state_after: str) -> dict:
    values = {name: reading[name] for name in _READING_COLUMNS}
    values.update(as_of=_instant(values["as_of"]), session_date=_day(values["session_date"]),
                  state_after=state_after, doc=sanitise_non_finite(dict(reading)))
    return values


def _state_values(state: dict, reading_id: int) -> dict:
    return {"id": STATE_ROW_ID, "label": state["label"], "since": _instant(state.get("since")),
            "session_date": _day(state.get("session_date")),
            "vix_session_high": state.get("vix_session_high"), "last_reading_id": reading_id,
            "doc": {"state": sanitise_non_finite(dict(state))},
            "updated_at": sa.func.clock_timestamp()}


class MarketShockRepository(Repository):
    def __init__(self):
        super().__init__(readings, key="id")
        self._queue = NotifyQueueRepository()

    def record(self, reading: dict, state: dict, *, state_after: str,
               notice_event: dict | None = None, conn=None) -> int:
        """Insert `reading`, upsert state row 1 onto it, enqueue `notice_event`."""
        _check_labels(state, state_after)
        with self._tx(conn) as connection:
            reading_id = connection.execute(sa.insert(readings).values(
                **_reading_values(reading, state_after)).returning(readings.c.id)).scalar_one()
            values = _state_values(state, reading_id)
            if notice_event is not None:
                self._queue.enqueue(notice_event, conn=connection)
                values["last_notice_at"] = _instant(notice_event["queued_at"])
            update = {k: v for k, v in values.items() if k != "id"}
            connection.execute(pg_insert(state_table).values(**values).on_conflict_do_update(
                index_elements=[state_table.c.id], set_=update))
        return reading_id

    def current_state(self, *, conn=None) -> dict | None:
        statement = sa.select(state_table).where(state_table.c.id == STATE_ROW_ID)
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
        if row is None:
            return None
        mapping = row._mapping
        return {**{key: mapping[key] for key in _STATE_KEYS}, "doc": dict(mapping["doc"] or {})}

    def latest_reading(self, *, conn=None) -> dict | None:
        statement = (sa.select(readings.c.id, readings.c.state_after, readings.c.doc)
                     .order_by(readings.c.as_of.desc(), readings.c.id.desc()).limit(1))
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
        if row is None:
            return None
        return {**dict(row.doc or {}), "id": row.id, "state_after": row.state_after}

    def prune_before(self, cutoff: dt.datetime, *, conn=None) -> int:
        statement = sa.delete(readings).where(readings.c.as_of < _instant(cutoff))
        with self._tx(conn) as connection:
            return connection.execute(statement).rowcount


_repo: MarketShockRepository | None = None


def market_shock_repo() -> MarketShockRepository:
    global _repo
    if _repo is None:
        _repo = MarketShockRepository()
    return _repo
