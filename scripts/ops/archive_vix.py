"""Archive ^VIX: daily history from 2016-01-01 and every finished one-minute session.

Run it on weekdays after the US close (see ``install_vix_archive_cron.sh``);
re-running is safe. Files under ``market_data/vix/`` (gitignored, volume-mounted):

* ``VIX_daily.csv``                 Date, Open, High, Low, Close -- rewritten merged.
* ``intraday_1m/VIX_<day>_1m.csv``  one file per finished session, written once.

yfinance serves one-minute bars only for about the last 30 days, 7 days per
request, so a missed fortnight is the most that can be recovered; older gaps stay.
Exit 0 when the daily file is current, 1 when a download came back empty.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "market_data" / "vix"
SYMBOL = "^VIX"
DAILY_START = date(2016, 1, 1)
INTRADAY_DAYS = 29
CHUNK_DAYS = 7
SESSION_END_UTC_HOUR = 22   # the 1m series ends 21:14 UTC; later is never a partial day


def _download(start: date, end: date, interval: str) -> pd.DataFrame:
    import yfinance as yf
    return yf.download(SYMBOL, start=start.isoformat(), end=end.isoformat(),
                       interval=interval, progress=False, auto_adjust=False, prepost=False)


def _flat(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def merge_daily(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    """New rows win; the index is the tz-naive session date, sorted, unique."""
    new = _flat(new)[["Open", "High", "Low", "Close"]].dropna()
    new.index = pd.DatetimeIndex(new.index).tz_localize(None).normalize()
    new.index.name = "Date"
    if old is not None and len(old):
        new = pd.concat([old[~old.index.isin(new.index)], new])
    return new.sort_index()


def archive_daily(today: date, *, download=_download, out: Path = OUT) -> int:
    path = out / "VIX_daily.csv"
    old = pd.read_csv(path, index_col="Date", parse_dates=True) if path.exists() else None
    start = DAILY_START if old is None else (old.index.max().date() - timedelta(days=7))
    new = download(start, today + timedelta(days=1), "1d")
    if new is None or not len(new):
        return 1
    out.mkdir(parents=True, exist_ok=True)
    merge_daily(old, new).to_csv(path)
    return 0


def finished_days(df: pd.DataFrame, now: datetime) -> list[date]:
    """Session dates in a one-minute frame that cannot still be growing."""
    days = sorted({ts.date() for ts in pd.DatetimeIndex(df.index).tz_convert("UTC")})
    cutoff = now.astimezone(timezone.utc)
    return [d for d in days
            if datetime(d.year, d.month, d.day, SESSION_END_UTC_HOUR, tzinfo=timezone.utc) <= cutoff]


def _day_rows(df: pd.DataFrame, day: date) -> pd.DataFrame:
    return df[pd.DatetimeIndex(df.index).tz_convert("UTC").date == day]


def archive_intraday(now: datetime, *, download=_download, out: Path = OUT) -> int:
    folder = out / "intraday_1m"
    folder.mkdir(parents=True, exist_ok=True)
    wrote, start = 0, now.date() - timedelta(days=INTRADAY_DAYS)
    while start <= now.date():
        end = min(start + timedelta(days=CHUNK_DAYS), now.date() + timedelta(days=1))
        df = download(start, end, "1m")
        if df is not None and len(df):
            df = _flat(df)
            for day in finished_days(df, now):
                path = folder / f"VIX_{day.isoformat()}_1m.csv"
                if not path.exists():
                    _day_rows(df, day).to_csv(path)
                    wrote += 1
        start = end
    return wrote


def main() -> int:
    now = datetime.now(timezone.utc)
    rc = archive_daily(now.date())
    wrote = archive_intraday(now)
    print(f"{now:%Y-%m-%dT%H:%M:%SZ} daily rc={rc} intraday_new_sessions={wrote}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
