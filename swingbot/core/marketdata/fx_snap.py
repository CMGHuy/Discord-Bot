"""v205 L1-a: write the day's FX rate from 08:00 Berlin (`snap`); V205-14 adds `backfill`.

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
from datetime import date, datetime

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


def snap(now: datetime) -> int:
    """Write the Berlin day's row for every pair in use that lacks one; rows written.

    Nothing before 08:00 Berlin. A pair with no frame, or whose newest bar
    before the day is more than FALLBACK_DAYS old, gets no row."""
    local = _berlin(now)
    if local.hour < SNAP_HOUR:
        return 0
    day = local.date()
    repo = fx_daily_rate_repo()
    rows = []
    for base, account in pairs_in_use():
        if day in repo.days_present(base, account):
            continue
        found = fx_daily.rate_before(_pair_frame(base, account), day)
        if found is not None:
            rows.append(_row(base, account, day, found, now=now, source="snap"))
    written = repo.insert_if_absent(rows)
    if written:
        log.info("fx snap %s: %d fx_daily_rates row(s)", day.isoformat(), written)
    return written
