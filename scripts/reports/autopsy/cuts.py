"""Categorical cuts of the closed trades (spec section 1).

Each cut is (name, key): the key returns the trade's cell value, or None when
it cannot place the trade (counted as uncovered, in neither arm). Every input is
frozen at issuance (risk_features) or a calendar fact; the one exception is
sector_today, today's mapping, labelled not point-in-time in CUT_NOTES.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable, Mapping

from swingbot.core.market.market_events import FOMC_DECISION_DATES
from swingbot.core.market.opex import monthly_expiration

from .rows import BookRow

Key = Callable[[BookRow], "str | None"]

CATEGORICAL_CUT_NAMES = (
    "strategy_horizon", "direction", "ticker", "sector_today", "regime", "weekday",
    "friday_entry", "weekend_hold", "earnings_proximity", "opex_week", "fomc_proximity",
    "atr_pct_bucket", "session_bucket", "alert_hour",
)
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
#: (exclusive upper bound, label); a value at or past the last bound gets the top label.
EARNINGS_BUCKETS = ((0, "past"), (6, "le_5d"), (21, "6_20d"))
ATR_PCT_BUCKETS = ((1.5, "lt_1.5"), (3.0, "1.5_3"), (5.0, "3_5"))
FOMC_FIRST = dt.date(min(FOMC_DECISION_DATES).year, 1, 1)
FOMC_LAST = max(FOMC_DECISION_DATES)

CUT_NOTES = {
    "sector_today": "sector_today: today's sector map, not point-in-time",
    "fomc_proximity": f"fomc_proximity: FOMC dates cover {FOMC_FIRST} to {FOMC_LAST}; "
                      "trades outside are uncovered",
    "macro": "CPI and NFP omitted: market_events.py carries no past dates",
    "earnings_proximity": "earnings_proximity: days_to_earnings is opportunistic; "
                          "trades without it are uncovered",
}


def _day(text: str | None) -> dt.date | None:
    return dt.date.fromisoformat(text[:10]) if text else None


def _bucket(value: float, table, top: str) -> str:
    return next((label for bound, label in table if value < bound), top)


def _attr(name: str) -> Key:
    return lambda t: getattr(t, name)


def _strategy_horizon(t: BookRow) -> str | None:
    return f"{t.strategy}|{t.horizon}" if t.strategy and t.horizon else None


def _weekday(t: BookRow) -> str | None:
    day = _day(t.entry_date)
    return None if day is None else WEEKDAYS[day.weekday()]


def _friday_entry(t: BookRow) -> str | None:
    day = _day(t.entry_date)
    return None if day is None else ("yes" if day.weekday() == 4 else "no")


def _weekend_hold(t: BookRow) -> str | None:
    start, end = _day(t.entry_date), _day(t.exit_date)
    if start is None or end is None:
        return None
    first_saturday = start + dt.timedelta(days=(5 - start.weekday()) % 7 or 7)
    return "yes" if first_saturday < end else "no"


def _earnings(t: BookRow) -> str | None:
    if t.days_to_earnings is None:
        return None
    return _bucket(t.days_to_earnings, EARNINGS_BUCKETS, "gt_20d")


def _opex_week(t: BookRow) -> str | None:
    day = _day(t.entry_date)
    if day is None:
        return None
    expiry = monthly_expiration(day.year, day.month)
    return "opex_week" if day.isocalendar()[:2] == expiry.isocalendar()[:2] else "other"


def _fomc(t: BookRow) -> str | None:
    start, end = _day(t.entry_date), _day(t.exit_date)
    if start is None or end is None or start < FOMC_FIRST or end > FOMC_LAST:
        return None
    return "fomc_in_hold" if any(start <= d <= end for d in FOMC_DECISION_DATES) else "no_fomc"


def _atr_pct(t: BookRow) -> str | None:
    return None if t.atr_pct is None else _bucket(t.atr_pct, ATR_PCT_BUCKETS, "ge_5")


def _alert_hour(t: BookRow) -> str | None:
    return None if t.plan_hour is None else f"{t.plan_hour:02d}"


def _sector(sector_of: Mapping[str, str]) -> Key:
    return lambda t: sector_of.get(t.ticker) if t.ticker else None


def categorical_cuts(sector_of: Mapping[str, str]) -> tuple[tuple[str, Key], ...]:
    keys = (_strategy_horizon, _attr("direction"), _attr("ticker"), _sector(sector_of),
            _attr("regime2_state"), _weekday, _friday_entry, _weekend_hold, _earnings,
            _opex_week, _fomc, _atr_pct, _attr("session_bucket"), _alert_hour)
    return tuple(zip(CATEGORICAL_CUT_NAMES, keys))


def load_sector_map() -> dict[str, str]:
    """Today's {TICKER: sector} for S&P 500 and ETFs; {} when unavailable."""
    from swingbot.core.marketdata import universe
    try:
        mapping = universe.sector_map("sp500+etfs")
    except (OSError, ValueError, KeyError):
        return {}
    return {str(s).upper(): sec for s, sec in mapping.items() if sec}
