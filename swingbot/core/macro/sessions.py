"""NYSE session calendar: holidays, half-days (13:00 close), thin windows.
Rule-generated per https://www.nyse.com/markets/hours-calendars .

Rule-generated rather than a hand-typed 10-year table: the floating holidays
come from nth-weekday math, Good Friday from the anonymous Gregorian
computus, and observance shifts follow NYSE's rule (Sun->Mon, Sat->Fri,
except New Year's, which is simply not observed when it lands on a
Saturday). Only the two national-mourning closures are literals.
"""
from __future__ import annotations

import datetime as dt

EXTRA_CLOSURES = {
    "2018-12-05": "National day of mourning (G.H.W. Bush)",
    "2025-01-09": "National day of mourning (J. Carter)",
}


def _easter(year: int) -> dt.date:
    """Anonymous Gregorian computus."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = (h + ell - 7 * m + 114) % 31 + 1
    return dt.date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> dt.date:
    last = (dt.date(year, month + 1, 1) if month < 12
            else dt.date(year + 1, 1, 1)) - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _observed(d: dt.date) -> dt.date:
    if d.weekday() == 6:                # Sunday -> Monday
        return d + dt.timedelta(days=1)
    if d.weekday() == 5:                # Saturday -> Friday
        return d - dt.timedelta(days=1)
    return d


def holidays(year: int) -> dict[str, str]:
    out: dict[str, str] = {}
    ny = dt.date(year, 1, 1)
    if ny.weekday() == 6:
        out[(ny + dt.timedelta(days=1)).isoformat()] = "New Year's Day (observed)"
    elif ny.weekday() != 5:             # on a Saturday it is NOT observed
        out[ny.isoformat()] = "New Year's Day"
    out[_nth_weekday(year, 1, 0, 3).isoformat()] = "MLK Day"
    out[_nth_weekday(year, 2, 0, 3).isoformat()] = "Washington's Birthday"
    out[(_easter(year) - dt.timedelta(days=2)).isoformat()] = "Good Friday"
    out[_last_weekday(year, 5, 0).isoformat()] = "Memorial Day"
    if year >= 2022:
        out[_observed(dt.date(year, 6, 19)).isoformat()] = "Juneteenth"
    out[_observed(dt.date(year, 7, 4)).isoformat()] = "Independence Day"
    out[_nth_weekday(year, 9, 0, 1).isoformat()] = "Labor Day"
    out[_nth_weekday(year, 11, 3, 4).isoformat()] = "Thanksgiving"
    out[_observed(dt.date(year, 12, 25)).isoformat()] = "Christmas"
    for date, label in EXTRA_CLOSURES.items():
        if date.startswith(str(year)):
            out[date] = label
    return out


def half_days(year: int) -> dict[str, str]:
    out: dict[str, str] = {}
    if dt.date(year, 7, 4).weekday() in (1, 2, 3, 4):   # Jul 4 Tue-Fri -> Jul 3 Mon-Thu
        out[dt.date(year, 7, 3).isoformat()] = "July 3rd early close"
    after_tg = _nth_weekday(year, 11, 3, 4) + dt.timedelta(days=1)
    out[after_tg.isoformat()] = "Day after Thanksgiving"
    dec24 = dt.date(year, 12, 24)
    if dec24.weekday() < 5 and dt.date(year, 12, 25).weekday() != 5:
        out[dec24.isoformat()] = "Christmas Eve early close"
    return out


def is_holiday(date: str) -> bool:
    return date in holidays(int(date[:4]))


def is_half_day(date: str) -> bool:
    return date in half_days(int(date[:4]))


def is_thin_window(dt_et: dt.datetime) -> tuple[bool, str]:
    date = dt_et.date().isoformat()
    if is_holiday(date):
        return True, "market holiday"
    t = dt_et.time()
    if dt.time(9, 30) <= t < dt.time(10, 0):
        return True, "first 30 min after open"
    close = dt.time(13, 0) if is_half_day(date) else dt.time(16, 0)
    last10 = (dt.datetime.combine(dt_et.date(), close)
              - dt.timedelta(minutes=10)).time()
    if last10 <= t < close:
        return True, "last 10 min before close"
    if is_half_day(date) and t >= dt.time(12, 0):
        return True, "half-day session"
    if date[5:7] == "12" and "26" <= date[8:10] <= "31":
        return True, "holiday week (Christmas -> New Year)"
    return False, ""


def session_flag(date: str, time_et: dt.time | None = None) -> dict:
    """CheckResult-ready summary used by rf_thin_session (G65)."""
    year = int(date[:4])
    if is_holiday(date):
        return {"flag": "holiday", "detail": holidays(year)[date]}
    if is_half_day(date):
        return {"flag": "half_day", "detail": half_days(year)[date]}
    if time_et is not None:
        thin, reason = is_thin_window(
            dt.datetime.combine(dt.date.fromisoformat(date), time_et))
        if thin:
            return {"flag": "thin", "detail": reason}
    return {"flag": "normal", "detail": ""}
