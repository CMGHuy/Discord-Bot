"""Durable manual lifecycle events with fenced, expiring delivery claims."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import logging
import re
from uuid import uuid4
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from swingbot.core.db.codec import normalise
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import manual_close_notify as queue
from swingbot.core.infra.lifecycle_events import validate_event

log = logging.getLogger(__name__)

DESTINATION_ERRORS = frozenset(("destination_unresolved", "channel_unavailable", "permission_denied"))


def _instant(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _check_now(now):
    if now.tzinfo is None:
        raise ValueError("timezone_required")


def _age(event, now):
    return max(0.0, (now - _instant(event["queued_at"])).total_seconds())


def _clear_lease(event):
    event.update(lease_token=None, lease_owner=None, lease_until=None)


class NotifyQueueRepository(Repository):
    def __init__(self):
        super().__init__(queue, key="id")

    def _record(self, row):
        return normalise(super()._record(row))

    def _values(self, record):
        values = super()._values(record)
        values["doc"].update({key: normalise(record[key]) for key in self.promoted if key in record})
        for key in ("queued_at", "next_attempt_at", "lease_until", "delivered_at"):
            if values.get(key) is not None:
                values[key] = _instant(values[key])
        return values

    def _write(self, connection, record):
        values = self._values(record)
        values["updated_at"] = sa.func.clock_timestamp()
        connection.execute(queue.update().where(queue.c.event_id == record["event_id"]).values(**values))

    def enqueue(self, event: dict, *, conn=None) -> None:
        validate_event(event)
        values = self._values(event)
        statement = pg_insert(queue).values(**values).on_conflict_do_nothing(
            index_elements=[queue.c.event_id])
        with self._tx(conn) as connection:
            inserted = connection.execute(statement.returning(queue.c.event_id)).scalar_one_or_none()
            row = connection.execute(sa.select(queue).where(
                queue.c.event_id == event["event_id"])).one()
            saved = self._record(row)
            keys = ("transition_id", "kind", "target_channel_id", "payload")
            if any(saved.get(key) != event.get(key) for key in keys):
                raise ValueError("conflicting_event")
        if inserted is not None and event.get("blocked"):
            log.error("lifecycle blocked event=%s kind=%s age_s=%.0f cause=%s",
                      event["event_id"], event["kind"], _age(event, datetime.now(timezone.utc)),
                      event.get("last_error") or "destination_unresolved")

    def pending(self, *, conn=None) -> int:
        return self.count(conn=conn, where=queue.c.delivered_at.is_(None))

    def claim_one(self, owner: str, *, now, conn=None) -> dict | None:
        _check_now(now)
        if not owner:
            raise ValueError("owner_required")
        available = sa.and_(queue.c.delivered_at.is_(None), queue.c.next_attempt_at <= now,
            sa.or_(queue.c.lease_until.is_(None), queue.c.lease_until <= now))
        statement = sa.select(queue).where(available).order_by(
            queue.c.next_attempt_at, queue.c.queued_at, queue.c.event_id
        ).limit(1).with_for_update(skip_locked=True)
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
            if row is None:
                return None
            event = self._record(row)
            event.update(lease_token=str(uuid4()), lease_owner=owner,
                         lease_until=(now + timedelta(seconds=120)).isoformat(),
                         attempt_count=int(event.get("attempt_count", 0)) + 1)
            self._write(connection, event)
        return event

    def _owned(self, connection, event_id, token, now):
        statement = sa.select(queue).where(
            queue.c.event_id == event_id, queue.c.lease_token == token,
            queue.c.lease_until > now, queue.c.delivered_at.is_(None)
        ).with_for_update()
        row = connection.execute(statement).one_or_none()
        return None if row is None else self._record(row)

    def acknowledge(self, event_id, token, message_id, *, now, conn=None) -> bool:
        _check_now(now)
        if not token or not message_id:
            raise ValueError("ack_identity_required")
        with self._tx(conn) as connection:
            event = self._owned(connection, event_id, token, now)
            if event is None:
                return False
            event.update(delivered_message_id=str(message_id), delivered_at=now.isoformat(),
                         blocked=False, last_error=None)
            _clear_lease(event)
            self._write(connection, event)
        return True

    def reschedule(self, event_id, token, *, now, delay_s, error_code, blocked, conn=None) -> bool:
        _check_now(now)
        if not token or delay_s < 0 or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", error_code):
            raise ValueError("invalid_retry_state")
        with self._tx(conn) as connection:
            event = self._owned(connection, event_id, token, now)
            if event is None:
                return False
            changed = blocked and (not event.get("blocked") or event.get("last_error") != error_code)
            event.update(next_attempt_at=(now + timedelta(seconds=delay_s)).isoformat(),
                         last_error=error_code, blocked=bool(blocked))
            _clear_lease(event)
            self._write(connection, event)
        if changed:
            log.error("lifecycle blocked event=%s kind=%s age_s=%.0f cause=%s",
                      event_id, event["kind"], _age(event, now), error_code)
        return True

    def health(self, *, now, conn=None) -> dict:
        _check_now(now)
        statement = sa.select(sa.func.count(), sa.func.min(queue.c.queued_at),
            sa.func.count().filter(queue.c.doc["blocked"].as_boolean().is_(True))
        ).select_from(queue).where(queue.c.delivered_at.is_(None))
        with self._tx(conn) as connection:
            pending, oldest, blocked = connection.execute(statement).one()
        age = None if oldest is None else max(0.0, (now - oldest).total_seconds())
        return dict(pending_count=int(pending), oldest_pending_age_seconds=age, blocked_count=int(blocked))

    def prune_delivered(self, *, now, conn=None) -> int:
        _check_now(now)
        statement = queue.delete().where(
            queue.c.delivered_at < now - timedelta(days=7),
            queue.c.doc["delivered_message_id"].astext.is_not(None),
            queue.c.doc["delivered_message_id"].astext != "")
        with self._tx(conn) as connection:
            return connection.execute(statement).rowcount

    def retarget(self, event_id, channel_id, *, actor, reason, now, conn=None) -> bool:
        _check_now(now)
        channel = str(channel_id)
        if not actor or not reason or not channel.isdecimal() or int(channel) <= 0:
            raise ValueError("invalid_retarget")
        statement = sa.select(queue).where(queue.c.event_id == event_id,
            queue.c.delivered_at.is_(None),
            sa.or_(queue.c.lease_until.is_(None), queue.c.lease_until <= now)
        ).with_for_update()
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
            if row is None:
                return False
            event = self._record(row)
            event.setdefault("retarget_history", []).append(dict(at=now.isoformat(), actor=actor,
                reason=reason, from_channel_id=event.get("target_channel_id"), to_channel_id=channel))
            event.update(target_channel_id=channel, next_attempt_at=now.isoformat())
            _clear_lease(event)
            if event.get("last_error") in DESTINATION_ERRORS:
                event.update(blocked=False, last_error=None)
            self._write(connection, event)
        log.info("lifecycle retarget event=%s channel=%s audit=retarget_history", event_id, channel)
        return True


_repo: NotifyQueueRepository | None = None


def notify_queue_repo() -> NotifyQueueRepository:
    global _repo
    if _repo is None:
        _repo = NotifyQueueRepository()
    return _repo
