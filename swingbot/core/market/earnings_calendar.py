"""One authoritative earnings calendar for gates, labels, and measurement."""
from __future__ import annotations

import bisect
import csv
import datetime as dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from swingbot.core.market.session import SessionCalendar, now_et, nyse_calendar

BEFORE_OPEN = "before_open"
AFTER_CLOSE = "after_close"
UNCONFIRMED = "unconfirmed"
TIMINGS = (BEFORE_OPEN, AFTER_CLOSE, UNCONFIRMED)
CSV_FIELDS = ("report_date", "timing", "report_ts_et")
EARNINGS_CSV_DIR = Path(__file__).resolve().parents[3] / "market_data" / "earnings"
_OPEN, _CLOSE = dt.time(9, 30), dt.time(16, 0)


@dataclass(frozen=True)
class Report:
    date: dt.date
    timing: str


@dataclass(frozen=True)
class Label:
    date: dt.date
    timing: str
    sessions: int


def classify_timing(ts: dt.datetime) -> str:
    time = now_et(ts).time()
    return BEFORE_OPEN if time < _OPEN else AFTER_CLOSE if time >= _CLOSE else UNCONFIRMED


def report_from_timestamp(ts: dt.datetime) -> Report:
    et = now_et(ts)
    return Report(et.date(), classify_timing(et))


def reaction_session(report: Report, calendar: SessionCalendar) -> dt.date | None:
    return calendar.session_on_or_after(report.date) if report.timing == BEFORE_OPEN else calendar.next_session(report.date)


def next_reaction_distance(asof_pos: int, reaction_positions: Sequence[int]) -> int | None:
    index = bisect.bisect_left(reaction_positions, asof_pos)
    return None if index == len(reaction_positions) else reaction_positions[index] - asof_pos


def sessions_to_reaction_from(asof: dt.date, reactions: Iterable[dt.date], calendar: SessionCalendar) -> int | None:
    asof_pos = calendar.position_on_or_before(asof)
    if asof_pos is None:
        return None
    positions = sorted({position for reaction in reactions if (position := calendar.position_on_or_after(reaction)) is not None})
    return next_reaction_distance(asof_pos, positions)


def is_exposed(distance: int | None, k: int) -> bool:
    return distance is not None and 1 <= distance <= k


class EarningsSource(Protocol):
    def reports(self, ticker: str) -> list[Report]: ...


class CsvSource:
    def __init__(self, directory: Path | str = EARNINGS_CSV_DIR):
        self._dir, self._cache = Path(directory), {}

    def _path(self, ticker: str) -> Path:
        return self._dir / f"{ticker.upper()}.csv"

    def has_data(self, ticker: str) -> bool:
        return self._path(ticker).exists()

    def reports(self, ticker: str) -> list[Report]:
        key = ticker.upper()
        if key not in self._cache:
            reports = []
            path = self._path(key)
            if path.exists():
                with path.open(newline="", encoding="utf-8") as handle:
                    for row in csv.DictReader(handle):
                        if row["timing"] not in TIMINGS:
                            raise ValueError(f"{path}: unknown timing {row['timing']!r}")
                        reports.append(Report(dt.date.fromisoformat(row["report_date"]), row["timing"]))
            self._cache[key] = sorted(reports, key=lambda report: report.date)
        return list(self._cache[key])


class LiveSource:
    def reports(self, ticker: str) -> list[Report]:
        from swingbot.core.market import events
        return sorted({report_from_timestamp(ts) for ts in events.get_earnings_datetimes(ticker)}, key=lambda report: (report.date, report.timing))


def next_report(ticker: str, asof: dt.date, *, source: EarningsSource, calendar: SessionCalendar | None = None) -> Report | None:
    calendar = calendar or nyse_calendar()
    asof_position = calendar.position_on_or_before(asof)
    if asof_position is None:
        return None
    eligible = []
    for report in source.reports(ticker):
        reaction = reaction_session(report, calendar)
        position = calendar.position_on_or_after(reaction) if reaction else None
        if position is not None and position >= asof_position:
            eligible.append((position, report))
    return min(eligible, default=(None, None))[1]


def sessions_to_reaction(ticker: str, asof: dt.date, *, source: EarningsSource, calendar: SessionCalendar | None = None) -> int | None:
    calendar = calendar or nyse_calendar()
    return sessions_to_reaction_from(asof, (reaction for report in source.reports(ticker) if (reaction := reaction_session(report, calendar)) is not None), calendar)


def earnings_label(ticker: str, now: dt.datetime | None = None, *, source: EarningsSource | None = None, calendar: SessionCalendar | None = None) -> Label | None:
    calendar, source = calendar or nyse_calendar(), source or LiveSource()
    today, today_pos = now_et(now).date(), calendar.position_on_or_before(now_et(now).date())
    if today_pos is None:
        return None
    labels = []
    for report in source.reports(ticker):
        position = calendar.position_on_or_after(report.date)
        if report.date >= today and position is not None and 0 <= position - today_pos <= 1:
            labels.append(Label(report.date, report.timing, position - today_pos))
    return min(labels, key=lambda label: label.sessions) if labels else None
