"""Durable lifecycle intent; preserves pending work on upgrade and downgrade."""
from copy import deepcopy
from datetime import datetime, timezone
import logging
from uuid import NAMESPACE_URL, uuid5
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import context, op

revision = "v197_001"
down_revision = "v205_001"
branch_labels = None
depends_on = None
FIELDS = ("event_id", "next_attempt_at", "lease_token", "lease_until", "delivered_at")
TIMES = frozenset(("next_attempt_at", "lease_until", "delivered_at"))


def _destination():
    value = context.get_x_argument(as_dictionary=True).get("lifecycle_channel_id")
    return value if value and value.isdecimal() and int(value) > 0 else None


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _complete(payload, kind):
    required = ("ticker", "direction", "prior_status", "new_status", "reason", "occurred_at")
    if not all(payload.get(key) for key in required):
        return False
    if kind == "plan_transition":
        return bool(payload.get("plan_id")) and payload["new_status"] in ("CLOSED", "CANCELLED")
    trade = payload.get("trade", {})
    return bool(trade.get("id")) and "entry" in trade and trade.get("status") in ("closed", "win", "loss")


def _payload(old, kind):
    result = {key: old.get(key) for key in ("ticker", "direction", "plan_id", "trade_id")}
    result.update(prior_status=old.get("prior_status"), new_status=old.get("status"),
                  reason=old.get("reason") or old.get("close_reason"),
                  occurred_at=old.get("occurred_at") or old.get("closed_at"))
    if kind == "trade_closed":
        trade = deepcopy(old)
        trade["id"] = trade.pop("trade_id", None)
        result["trade"] = trade
    return result


def _upgrade_record(row, destination):
    old = deepcopy(row["doc"])
    if old.get("event_id") and old.get("transition_id") and "payload" in old:
        return old  # this revision's demoted shape, including delivered/leased state
    kind = "plan_transition" if old.get("kind") == "plan_transition" else "trade_closed"
    transition_id = f"legacy-manual-close-notify:{row['id']}"
    event_id = str(uuid5(NAMESPACE_URL, f"swingbot:lifecycle:{transition_id}:{kind}"))
    payload = _payload(old, kind)
    error = None if destination else "destination_unresolved"
    if not _complete(payload, kind):
        error = "legacy_snapshot_incomplete"
    at = _iso(row["queued_at"])
    return dict(event_id=event_id, transition_id=transition_id, kind=kind,
                target_channel_id=destination, queued_at=at, payload=payload,
                attempt_count=0, next_attempt_at=at, lease_token=None,
                lease_owner=None, lease_until=None, last_error=error, blocked=bool(error),
                delivered_message_id=None, delivered_at=None, retarget_history=[],
                legacy_payload=old)


def _table():
    return sa.Table("manual_close_notify", sa.MetaData(), autoload_with=op.get_bind())


def _columns(record):
    result = {name: record.get(name) for name in FIELDS}
    for name in TIMES:
        if isinstance(result[name], str):
            result[name] = datetime.fromisoformat(result[name])
    return result


def upgrade():
    for name in FIELDS:
        kind = sa.TIMESTAMP(timezone=True) if name in TIMES else sa.Text()
        op.add_column("manual_close_notify", sa.Column(name, kind, nullable=True))
    table = _table()
    conn = op.get_bind()
    destination = _destination()
    for row in conn.execute(sa.select(table)).mappings():
        record = _upgrade_record(row, destination)
        conn.execute(table.update().where(table.c.id == row["id"])
                     .values(doc=record, **_columns(record)))
        if record.get("blocked") and not row["doc"].get("event_id"):
            age = max(0.0, (datetime.now(timezone.utc) - row["queued_at"]).total_seconds())
            logging.getLogger("alembic.runtime.migration").error(
                "lifecycle blocked event=%s kind=%s age_s=%.0f cause=%s",
                record["event_id"], record["kind"], age, record["last_error"])
    op.alter_column("manual_close_notify", "event_id", nullable=False)
    op.alter_column("manual_close_notify", "next_attempt_at", nullable=False)
    op.create_index("manual_close_notify_event_uidx", "manual_close_notify", ["event_id"], unique=True)
    op.create_index("manual_close_notify_due_idx", "manual_close_notify",
                    ["next_attempt_at", "queued_at"], postgresql_where=sa.text("delivered_at IS NULL"))
    op.create_index("manual_close_notify_delivered_idx", "manual_close_notify", ["delivered_at"],
                    postgresql_where=sa.text("delivered_at IS NOT NULL"))


def downgrade():
    table = _table()
    conn = op.get_bind()
    for row in conn.execute(sa.select(table)).mappings():
        record = deepcopy(row["doc"])
        record.update({name: _iso(row[name]) for name in (*FIELDS, "queued_at")})
        conn.execute(table.update().where(table.c.id == row["id"]).values(doc=record))
    for name in ("delivered_idx", "due_idx", "event_uidx"):
        op.drop_index(f"manual_close_notify_{name}", table_name="manual_close_notify")
    for name in reversed(FIELDS):
        op.drop_column("manual_close_notify", name)
