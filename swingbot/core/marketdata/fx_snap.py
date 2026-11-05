"""v205 L1-a: write the day's FX rate from 08:00 Berlin (`snap`) and fill past days (`backfill`, the v205 one-off).

The row for (base, account, Berlin day D) holds `fx_daily.rate_before(frame, D)`:
the last positive daily close dated strictly before D, read from the pair file
the refresher keeps up to date (`fx._pair_frame(..., refresh=False)`: the cache
file as it stands, never a fetch, so there is no third OHLCV cache). Rows are
written insert-if-absent and never updated, so the first value written is the
day's value. The rule reads only bars before D. A refresher that was down at
08:00, or a currency first seen later in the day, therefore writes the same
value on its next cycle.

"In use" is the major code of every `known` answer in the quote-currency store,
except the account's own major. Rows hold majors only; a minor unit's scale is
applied by the reader (`fx.fx_rate`), never stored.

Display only, like `fx`. Imports nothing from the admin or flask.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from swingbot.core.db.repositories.market_refresh import fx_daily_rate_repo, quote_currency_repo
from swingbot.core.market.session import BERLIN_TZ
from swingbot.core.marketdata import fx, fx_daily

log = logging.getLogger(__name__)

#: The Berlin hour from which the day's row is written.
SNAP_HOUR = 8


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


_stale_logged: set[tuple[str, str, date]] = set()


def _is_current(base: str, account: str, frame, day: date) -> bool:
    """True when the frame's newest bar reaches the last weekday before `day`.

    Insert-if-absent makes a snap from a stale file permanent, so a stale or
    missing frame writes nothing this cycle (logged once per pair per day)."""
    current = False
    if frame is not None and len(frame):
        newest = fx_daily._bar_dates(frame.index).max().astype(object)
        current = newest >= _last_weekday_before(day)
    if not current and (base, account, day) not in _stale_logged:
        _stale_logged.add((base, account, day))
        log.info("fx snap %s: %s%s frame is stale or missing, no row this cycle",
                 day.isoformat(), base, account)
    return current


def snap(now: datetime) -> int:
    """Write the Berlin day's row for every pair in use that lacks one; rows written.

    Nothing before 08:00 Berlin. A pair with no frame, a frame not current for
    the day (see `_is_current`), or whose newest bar before the day is more
    than FALLBACK_DAYS old, gets no row."""
    local = _berlin(now)
    if local.hour < SNAP_HOUR:
        return 0
    day = local.date()
    repo = fx_daily_rate_repo()
    rows = []
    for base, account in pairs_in_use():
        if day in repo.days_present(base, account):
            continue
        frame = _pair_frame(base, account)
        if not _is_current(base, account, frame, day):
            continue
        found = fx_daily.rate_before(frame, day)
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
    """The backfill rows of one pair: each absent day after its first bar that the rule serves."""
    frame = _pair_frame(base, account)
    if frame is None or not len(frame) or "Close" not in frame.columns:
        return []
    first = fx_daily._bar_dates(frame.index).min().astype(object) + timedelta(days=1)
    if start is not None and start > first:
        first = start
    rows = []
    for day in _days(first, end):
        found = None if day in present else fx_daily.rate_before(frame, day)
        if found is not None:
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
