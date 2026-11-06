"""v205 L1-a: write the day's FX rate from 08:00 Berlin (`snap`) and fill past days (`backfill`, the v205 one-off).

The row for (base, account, Berlin day D) holds `fx_daily.rate_before(frame, D)`:
the last positive daily close dated strictly before D, read from the pair file
the refresher keeps up to date (`fx._pair_frame(..., refresh=False)`: the cache
file as it stands, never a fetch, so there is no third OHLCV cache). Rows are
written insert-if-absent and never updated, so the first value written is the
day's value. The rule reads only bars before D. A refresher that was down at
08:00, or a currency first seen later in the day, therefore writes the same
value on its next cycle.

Only a FINAL bar may back a row (`_final_through`). An FX bar spans one London
day and Yahoo serves the day in progress, so the file's newest bar may be
partial; a later fetch overwrites it, and a row frozen from it would differ
from the backfill. Both `snap` and `backfill` skip a day whose bar is not
proven final and leave it to a later cycle.

"In use" is the major code of every `known` answer in the quote-currency store,
except the account's own major. Rows hold majors only; a minor unit's scale is
applied by the reader (`fx.fx_rate`), never stored.

Display only, like `fx`. Imports nothing from the admin or flask.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from swingbot.core.db.repositories.market_refresh import fx_daily_rate_repo, quote_currency_repo
from swingbot.core.market.session import BERLIN_TZ
from swingbot.core.marketdata import data_store, fx, fx_daily

log = logging.getLogger(__name__)

#: The Berlin hour from which the day's row is written.
SNAP_HOUR = 8

#: An FX daily bar covers one London calendar day (Yahoo's exchange zone for `=X`).
LONDON_TZ = ZoneInfo("Europe/London")


def pairs_in_use() -> list[tuple[str, str]]:
    """Sorted (base major, account major) for every known quote currency but the account's own."""
    account = fx._major(fx.account_currency_code())[0]
    bases = {fx._major(code)[0] for code in quote_currency_repo().known_codes() if code}
    return sorted((base, account) for base in bases if base != account)


def _berlin(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("fx_snap needs an aware datetime, got a naive one")
    return now.astimezone(BERLIN_TZ)


def _pair_frame(base: str, account: str):
    return fx._pair_frame(f"{base}{account}=X", refresh=False)


def _written_at(base: str, account: str) -> datetime | None:
    """The pair file's mtime (aware UTC), None without a file. Callers read it
    BEFORE the frame, so the frame they then read is at least this new."""
    try:
        stamp = os.path.getmtime(data_store.cache_path(f"{base}{account}=X", "daily"))
    except OSError:
        return None
    return datetime.fromtimestamp(stamp, tz=timezone.utc)


def _london_start(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=LONDON_TZ)


def _written_after_close(bar: date, written_at: datetime | None) -> bool:
    """True when the file was written after `bar`'s London day ended with only
    weekend days since. On a weekday a successful fetch also brings that
    weekday's bar; its absence means the fetch failed and the refresh only
    touched the file (`data_refresh._apply_incremental`), which proves nothing."""
    if written_at is None or written_at < _london_start(bar + timedelta(days=1)):
        return False
    written_day = written_at.astimezone(LONDON_TZ).date()
    return all(day.weekday() >= 5 for day in _days(bar + timedelta(days=1), written_day))


def _final_through(frame, written_at: datetime | None) -> date | None:
    """The newest bar date of `frame` known to be final, or None.

    A bar with a later bar after it is final: the fetch that brought the later
    bar started at or before it (incremental fetches overlap the last cached
    bar and overwrite it) after its London day ended. The newest bar is final
    only by `_written_after_close`."""
    dates = sorted(set(fx_daily._bar_dates(frame.index).astype(object)))
    if not dates:
        return None
    if _written_after_close(dates[-1], written_at):
        return dates[-1]
    return dates[-2] if len(dates) > 1 else None


def _is_final(found: tuple[float, date], final: date | None) -> bool:
    return final is not None and found[1] <= final


def _row(base: str, account: str, day: date, found: tuple[float, date], *,
         now: datetime, source: str) -> dict:
    rate, bar_date = found
    return {"base": base, "account": account, "day": day, "rate": rate,
            "bar_date": bar_date, "snapped_at": now, "source": source}


def _last_weekday_before(day: date) -> date:
    """The latest Mon-Fri date strictly before `day`."""
    prev = day - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    return prev


_stale_logged: set[tuple[str, str, str, date]] = set()


def _log_once(what: str, base: str, account: str, day: date) -> None:
    """One INFO line per (reason, pair, day): the refresher retries every cycle."""
    if (what, base, account, day) in _stale_logged:
        return
    _stale_logged.add((what, base, account, day))
    log.info("fx snap %s: %s%s frame %s, no row this cycle", day.isoformat(), base, account, what)


def _is_current(base: str, account: str, frame, day: date) -> bool:
    """True when the frame's newest bar reaches the last weekday before `day`.

    Insert-if-absent makes a snap from a stale file permanent, so a stale or
    missing frame writes nothing this cycle (logged once per pair per day)."""
    current = False
    if frame is not None and len(frame):
        newest = fx_daily._bar_dates(frame.index).max().astype(object)
        current = newest >= _last_weekday_before(day)
    if not current:
        _log_once("is stale or missing", base, account, day)
    return current


def _snap_rate(base: str, account: str, day: date) -> tuple[float, date] | None:
    """The day's rate from a current frame whose bar is final, else None (logged once)."""
    written_at = _written_at(base, account)
    frame = _pair_frame(base, account)
    if not _is_current(base, account, frame, day):
        return None
    found = fx_daily.rate_before(frame, day)
    if found is None or _is_final(found, _final_through(frame, written_at)):
        return found
    _log_once("holds a bar that may still be forming", base, account, day)
    return None


def snap(now: datetime) -> int:
    """Write the Berlin day's row for every pair in use that lacks one; rows written.

    Nothing before 08:00 Berlin. A pair with no frame, a frame not current for
    the day (see `_is_current`), a bar not proven final (`_final_through`), or
    whose newest bar before the day is more than FALLBACK_DAYS old, gets no row."""
    local = _berlin(now)
    if local.hour < SNAP_HOUR:
        return 0
    day = local.date()
    repo = fx_daily_rate_repo()
    rows = []
    for base, account in pairs_in_use():
        if day in repo.days_present(base, account):
            continue
        found = _snap_rate(base, account, day)
        if found is not None:
            rows.append(_row(base, account, day, found, now=now, source="snap"))
    written = repo.insert_if_absent(rows)
    if written:
        log.info("fx snap %s: %d fx_daily_rates row(s)", day.isoformat(), written)
    return written


#: Rows per INSERT. A row binds 8 parameters and Postgres allows 65,535 per
#: statement; one pair's history since 2003 is about 8,400 days.
INSERT_CHUNK = 1000


def _days(first: date, last: date):
    day = first
    while day <= last:
        yield day
        day += timedelta(days=1)


def _pair_rows(base: str, account: str, *, start: date | None, end: date,
               now: datetime, present: set[date]) -> list[dict]:
    """The backfill rows of one pair: each absent day after its first bar that
    the rule serves from a final bar (a day backed by a bar still forming is
    left for the snap, exactly as `snap` would leave it)."""
    written_at = _written_at(base, account)
    frame = _pair_frame(base, account)
    if frame is None or not len(frame) or "Close" not in frame.columns:
        return []
    first = fx_daily._bar_dates(frame.index).min().astype(object) + timedelta(days=1)
    if start is not None and start > first:
        first = start
    final = _final_through(frame, written_at)
    rows = []
    for day in _days(first, end):
        found = None if day in present else fx_daily.rate_before(frame, day)
        if found is not None and _is_final(found, final):
            rows.append(_row(base, account, day, found, now=now, source="backfill"))
    return rows


def planned_rows(*, start: date | None = None, end: date | None = None,
                 now: datetime | None = None) -> list[dict]:
    """Every row a backfill would write now (the dry run prints their counts)."""
    now = now or datetime.now(timezone.utc)
    last = end or _berlin(now).date()
    repo = fx_daily_rate_repo()
    rows: list[dict] = []
    for base, account in pairs_in_use():
        rows += _pair_rows(base, account, start=start, end=last, now=now,
                           present=repo.days_present(base, account))
    return rows


def backfill(*, start: date | None = None, end: date | None = None,
             now: datetime | None = None) -> int:
    """Fill every past Berlin day the frames allow (insert-if-absent; idempotent). Rows written."""
    rows = planned_rows(start=start, end=end, now=now)
    repo = fx_daily_rate_repo()
    written = sum(repo.insert_if_absent(rows[i:i + INSERT_CHUNK])
                  for i in range(0, len(rows), INSERT_CHUNK))
    log.info("fx backfill: %d of %d planned fx_daily_rates row(s) written", written, len(rows))
    return written
