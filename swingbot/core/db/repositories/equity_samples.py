"""v172: raw equity samples (`equity_samples`) behind the Dashboard candle chart.

Writers: the trade monitor's recorder (`commands/scanning/equity_recorder.py`,
`insert_sample`) and `scripts/data/backfill_equity_samples.py` (`upsert_many`,
`replace_backfill`, `update_realized`). Reader: `admin/api_v1/equity.py`
(`list_rows`, `earliest_at`). Money arrives as `Decimal` (or float) and is
rounded to 2 dp ROUND_HALF_UP exactly once, here, on every write. The table
raises no SSE event.
"""
from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import equity_samples

SOURCES = ("live", "backfill")
KINDS = ("point", "day_high", "day_low")
KEY_CONSTRAINT = "equity_samples_at_source_kind_uq"
MONEY_FIELDS = ("realized_balance", "unrealized_pnl", "equity")
_CENT = Decimal("0.01")
#: The NYSE clock, restated so the db layer imports nothing from core/market.
_NEW_YORK = ZoneInfo("America/New_York")


def round_money(value: Decimal | float) -> float:
    """2 dp, ROUND_HALF_UP, via `Decimal(str(value))` -- the one rounding."""
    return float(Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP))


def _as_utc(value) -> dt.datetime:
    """A tz-aware UTC datetime from a datetime or ISO string; naive is UTC."""
    stamp = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(str(value))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(dt.timezone.utc)


def _prepared(row: dict) -> dict:
    """`row` checked and normalised for a write: known source/kind, UTC `at`,
    money rounded once, counts as ints."""
    if row.get("source") not in SOURCES:
        raise ValueError(f"source {row.get('source')!r} is not one of {SOURCES}")
    if row.get("kind") not in KINDS:
        raise ValueError(f"kind {row.get('kind')!r} is not one of {KINDS}")
    prepared = {**row, "at": _as_utc(row["at"]),
                "open_n": int(row["open_n"]), "skipped_n": int(row["skipped_n"])}
    for field in MONEY_FIELDS:
        prepared[field] = round_money(row[field])
    return prepared


class EquitySampleRepository(Repository):
    def __init__(self):
        super().__init__(equity_samples, key="id")

    def _with_id(self, row) -> dict:
        record = {**self._record(row), "id": row.id}
        record["at"] = _as_utc(record["at"])
        return record

    def insert_sample(self, row: dict, conn=None) -> int:
        """Insert one sample; its id, or 0 (nothing written) when its
        (at, source, kind) already exists."""
        statement = (pg_insert(self.table).values(**self._values(_prepared(row)))
                     .on_conflict_do_nothing(constraint=KEY_CONSTRAINT)
                     .returning(self.table.c.id))
        with self._tx(conn) as connection:
            inserted = connection.execute(statement).first()
        return 0 if inserted is None else int(inserted.id)

    def upsert_many(self, rows: list[dict], conn=None) -> int:
        """Insert `rows`, updating any whose (at, source, kind) exists; the count written."""
        if not rows:
            return 0
        values = [self._values(_prepared(row)) for row in rows]
        statement = pg_insert(self.table).values(values)
        updates = {name: statement.excluded[name] for name in values[0] if name != "id"}
        updates["updated_at"] = sa.func.clock_timestamp()
        statement = statement.on_conflict_do_update(constraint=KEY_CONSTRAINT, set_=updates)
        with self._tx(conn) as connection:
            connection.execute(statement)
        return len(rows)

    def replace_backfill(self, rows: list[dict], conn=None) -> int:
        """Delete every backfill row and insert `rows`, in one transaction."""
        if any(row.get("source") != "backfill" for row in rows):
            raise ValueError("replace_backfill writes backfill rows only")
        values = [self._values(_prepared(row)) for row in rows]
        with self._tx(conn) as connection:
            connection.execute(sa.delete(self.table).where(self.table.c.source == "backfill"))
            if values:
                connection.execute(sa.insert(self.table).values(values))
        return len(values)

    def _edge_at(self, func, source: str, conn) -> dt.datetime | None:
        statement = sa.select(func(self.table.c.at)).where(self.table.c.source == source)
        with self._tx(conn) as connection:
            value = connection.execute(statement).scalar_one()
        return None if value is None else _as_utc(value)

    def latest_at(self, source: str, conn=None) -> dt.datetime | None:
        """The newest sample time of `source`, or None when it has none."""
        return self._edge_at(sa.func.max, source, conn)

    def earliest_at(self, source: str, conn=None) -> dt.datetime | None:
        """The oldest sample time of `source`, or None when it has none."""
        return self._edge_at(sa.func.min, source, conn)

    def list_rows(self, *, sources: tuple[str, ...] = SOURCES, since: dt.datetime | None = None,
                  conn=None) -> list[dict]:
        """Rows of `sources` at or after `since`, ordered by `at` then `id`."""
        statement = (sa.select(self.table).where(self.table.c.source.in_(sources))
                     .order_by(self.table.c.at, self.table.c.id))
        if since is not None:
            statement = statement.where(self.table.c.at >= _as_utc(since))
        with self._tx(conn) as connection:
            rows = connection.execute(statement).all()
        return [self._with_id(row) for row in rows]

    def backfill_session_dates(self, conn=None) -> set[dt.date]:
        """New York calendar dates that already hold backfill rows."""
        statement = (sa.select(self.table.c.at).distinct()
                     .where(self.table.c.source == "backfill"))
        with self._tx(conn) as connection:
            stamps = connection.execute(statement).scalars().all()
        return {_as_utc(stamp).astimezone(_NEW_YORK).date() for stamp in stamps}

    def update_realized(self, sample_id: int, realized_balance: Decimal, equity: Decimal,
                        conn=None) -> None:
        """Rewrite one row's realized balance and equity; `unrealized_pnl` is kept."""
        statement = (sa.update(self.table).where(self.table.c.id == sample_id)
                     .values(realized_balance=round_money(realized_balance),
                             equity=round_money(equity),
                             updated_at=sa.func.clock_timestamp()))
        with self._tx(conn) as connection:
            connection.execute(statement)


_repo: EquitySampleRepository | None = None


def equity_samples_repo() -> EquitySampleRepository:
    global _repo
    if _repo is None:
        _repo = EquitySampleRepository()
    return _repo
