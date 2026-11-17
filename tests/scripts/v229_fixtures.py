"""v229: synthetic 5-minute archive frames, stamped like the VM archive --
bar START, tz-aware UTC, regular NYSE session only."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from swingbot.core.market.session import RTH_OPEN, US_MARKET_TZ, nyse_calendar, session_close
from swingbot.core.marketdata.data_store import safe_symbol

PRICE_COLUMNS = ["Open", "High", "Low", "Close"]


def et(text: str) -> pd.Timestamp:
    """An ET wall-clock 'YYYY-MM-DD HH:MM' as its UTC bar-start stamp."""
    return pd.Timestamp(text, tz=US_MARKET_TZ).tz_convert("UTC")


def _as_date(day) -> dt.date:
    return day if isinstance(day, dt.date) else dt.date.fromisoformat(str(day))


def session_stamps(day) -> list[pd.Timestamp]:
    """Every 5-minute bar start of one session, 09:30 ET to its close."""
    day = _as_date(day)
    start = pd.Timestamp(dt.datetime.combine(day, RTH_OPEN), tz=US_MARKET_TZ)
    end = pd.Timestamp(dt.datetime.combine(day, session_close(day)), tz=US_MARKET_TZ)
    return list(pd.date_range(start, end, freq="5min", inclusive="left").tz_convert("UTC"))


def five_min(days, *, base: float = 100.0, overrides: dict | None = None) -> pd.DataFrame:
    """Flat regular-session bars for every NYSE session in ``days``.

    ``overrides`` maps an ET 'YYYY-MM-DD HH:MM' bar start to
    (open, high, low, close); a key that is not a bar start is a KeyError."""
    cal = nyse_calendar()
    stamps = [ts for d in map(_as_date, days) if cal.is_session(d) for ts in session_stamps(d)]
    frame = pd.DataFrame(
        {"Open": base, "High": base + 0.05, "Low": base - 0.05, "Close": base, "Volume": 1000.0},
        index=pd.DatetimeIndex(stamps, name="Datetime"))
    for key, values in (overrides or {}).items():
        ts = et(key)
        if ts not in frame.index:
            raise KeyError(f"{key} ET is not a bar start in this frame")
        frame.loc[ts, PRICE_COLUMNS] = [float(v) for v in values]
    return frame


def write_bars(directory, ticker: str, frame: pd.DataFrame) -> Path:
    """Write ``frame`` as the archive would: <dir>/<SAFE>.csv, stamps with +00:00."""
    path = Path(directory) / f"{safe_symbol(ticker)}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path)
    return path
