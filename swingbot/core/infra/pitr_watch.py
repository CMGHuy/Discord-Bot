"""Point-in-time-recovery alarms the bot polls (v116 Phase 0).

Two conditions, each posted to the ops channel once per episode:

* the WAL archiver is failing. A failing ``archive_command`` piles WAL up on
  the database disk, so a silent archiver ends in a full disk AND a PITR window
  that quietly stopped growing -- this alarm is not optional (spec § Proof);
* the disk holding data/ and backups/ (one VM disk) is more than 80% full.

Pure apart from ``read_archiver`` and ``disk_used_pct``.
"""
from __future__ import annotations

import datetime as dt
import logging
import shutil
from dataclasses import dataclass

log = logging.getLogger(__name__)

DISK_ALARM_PCT = 80.0
ARCHIVER_SQL = ("SELECT failed_count, last_failed_time, last_archived_time "
                "FROM pg_stat_archiver")


@dataclass(frozen=True)
class ArchiverSample:
    failed_count: int
    last_failed_time: dt.datetime | None
    last_archived_time: dt.datetime | None


@dataclass(frozen=True)
class Notice:
    recovered: bool
    detail: str
    description: str


def read_archiver() -> ArchiverSample | None:
    """The pg_stat_archiver row, or None when the database cannot be read."""
    import sqlalchemy as sa

    from swingbot.core.db.engine import get_engine
    try:
        with get_engine().connect() as conn:
            row = conn.execute(sa.text(ARCHIVER_SQL)).one()
    except Exception:  # noqa: BLE001 -- unreadable is "unknown", not an alarm
        log.debug("pitr watch: pg_stat_archiver unreadable", exc_info=True)
        return None
    return ArchiverSample(int(row[0] or 0), row[1], row[2])


def archiver_failing(previous: ArchiverSample | None, current: ArchiverSample) -> bool:
    grew = previous is not None and current.failed_count > previous.failed_count
    failed, archived = current.last_failed_time, current.last_archived_time
    stuck = failed is not None and (archived is None or failed > archived)
    return grew or stuck


def disk_used_pct(path: str) -> float:
    usage = shutil.disk_usage(path)
    return 100.0 * usage.used / usage.total if usage.total else 0.0


class PitrWatch:
    """Successive samples in, at most one alert and one recovery per episode out."""

    def __init__(self) -> None:
        self._previous: ArchiverSample | None = None
        self.archiver_alarm = False
        self.disk_alarm = False

    def tick(self, sample: ArchiverSample | None, used_pct: float) -> list[Notice]:
        notices = self._archiver(sample) if sample is not None else []
        return notices + self._disk(used_pct)

    def _archiver(self, sample: ArchiverSample) -> list[Notice]:
        failing = archiver_failing(self._previous, sample)
        self._previous = sample
        if failing == self.archiver_alarm:
            return []
        self.archiver_alarm = failing
        if not failing:
            return [Notice(True, "WAL archiving healthy again", "The archiver is keeping up again.")]
        return [Notice(False, "WAL archiving failing", (
            f"pg_stat_archiver.failed_count = {sample.failed_count}, last failure "
            f"{sample.last_failed_time}. WAL is piling up on the database disk and the "
            "point-in-time window has stopped growing. Check `docker compose logs db`."))]

    def _disk(self, used_pct: float) -> list[Notice]:
        over = used_pct > DISK_ALARM_PCT
        if over == self.disk_alarm:
            return []
        self.disk_alarm = over
        if not over:
            return [Notice(True, f"backups disk back to {used_pct:.0f}%",
                           "Disk usage is below the alarm threshold again.")]
        return [Notice(False, f"backups disk {used_pct:.0f}% full (alarm above {DISK_ALARM_PCT:.0f}%)", (
            f"The VM disk holding data/ and backups/ is {used_pct:.1f}% used. pgBackRest, "
            "restic and pg_dump all write there."))]
