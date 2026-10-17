"""Append-only scan telemetry, slowdown detection and provider health."""
import datetime as dt
import json as _json
import os

import pandas as pd

from swingbot import config
from swingbot.core.market.session import nyse_calendar


TELEMETRY_PATH = os.path.join(config.DATA_DIR, "scan_telemetry.jsonl")


def log_scan_telemetry(stats: dict, path: str | None = None) -> None:
    """Append one scan row, including optional ``phases_s`` timing details.

    The compact append-only history feeds ``scan_slowdown()`` and the admin
    scan-health display.  Phase timings are intentionally raw numbers rather
    than a second derived view so operators can identify whether crawl,
    pricing, enrichment, analysis, or alert finalisation regressed.
    """
    import datetime as dt
    row = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), **stats}
    with open(path or TELEMETRY_PATH, "a", encoding="utf-8") as f:
        f.write(_json.dumps(row) + "\n")
    from swingbot.core.db import notify
    notify.publish("scan")


def recent_telemetry(n: int = 50, path: str | None = None) -> list:
    try:
        with open(path or TELEMETRY_PATH, encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return [_json.loads(l) for l in lines if l.strip()]
    except OSError:
        return []


def recent_scan_telemetry(n: int = 50, path: str | None = None) -> list:
    """The last ``n`` SCAN rows only. The file also carries rows with no
    ``duration_s`` -- deploy_marker.py's ``{"type": "deploy"}`` markers --
    and a reader that indexes ``duration_s`` must never see those."""
    rows = [r for r in recent_telemetry(n + 50, path=path)
            if isinstance(r, dict) and isinstance(r.get("duration_s"), (int, float))]
    return rows[-n:]


def scan_slowdown(path: str | None = None) -> bool:
    """True when the latest logged scan took more than 2x the median of
    the prior 20 -- a real slowdown, not noise from a single slow ticker."""
    rows = recent_scan_telemetry(21, path=path)
    if len(rows) < 6:
        return False
    import statistics
    prior = [r["duration_s"] for r in rows[:-1]]
    return rows[-1]["duration_s"] > 2 * statistics.median(prior)


# --- v148 O4: provider degradation metrics ------------------------------------

_MARKET_TZ = "America/New_York"


def fallback_rate(source_counts: list[dict]) -> float | None:
    """yfinance-fallback over everything Alpaca was asked for (hits + misses),
    pooled across `source_counts` -- daily-frame and live-price count dicts
    alike. None when Alpaca was asked for nothing (disabled, or its breaker
    open throughout). The one formula behind each scan's
    ``provider_fallback_rate`` and the Risk page's pooled rate (v106)."""
    hits = sum(int(d.get("alpaca", 0)) for d in source_counts)
    misses = sum(int(d.get("yfinance-fallback", 0)) for d in source_counts)
    return misses / (hits + misses) if hits + misses else None


def _is_empty(df) -> bool:
    return df is None or df.empty


def _previous_session(today: dt.date) -> dt.date | None:
    """The last NYSE session before `today` -- not BDay, which would flag the
    whole universe the day after a holiday. None outside the frozen calendar."""
    sessions = nyse_calendar().sessions(today - dt.timedelta(days=14),
                                        today - dt.timedelta(days=1))
    return sessions[-1] if sessions else None


def _last_bar_date(df) -> dt.date | None:
    """The last bar's market date: tz-aware -> New York; naive is taken as a
    market date already. None for a frame without a DatetimeIndex."""
    if not isinstance(df.index, pd.DatetimeIndex):
        return None
    last = df.index[-1]
    if last.tzinfo is not None:
        last = last.tz_convert(_MARKET_TZ)
    return last.date()


def _is_stale(df, previous: dt.date) -> bool:
    if _is_empty(df):
        return False
    last = _last_bar_date(df)
    return last is not None and last < previous


def _stale_count(tickers: list, frames: dict, today: dt.date) -> int | None:
    previous = _previous_session(today)
    if previous is None:
        return None
    return sum(1 for ticker in tickers if _is_stale(frames.get(ticker), previous))


def provider_health(tickers: list, frames: dict, data_sources: dict | None,
                    price_sources: dict | None, today: dt.date) -> dict:
    """v148 O4: one scan's provider degradation, four telemetry-row fields.

    `today` is the ET market date (``market_today()``), never
    ``date.today()``. `frames` is the scan's ticker -> frame dict, whose
    values may be None.

    - ``provider_fallback_rate``: :func:`fallback_rate` over this scan's
      `data_sources` + `price_sources`. Blind to a price chunk whose child was
      killed on timeout (it lands in the ``none`` bucket); that shows as the
      ``scan.run_bounded`` swallowed count instead.
    - ``empty_symbols`` / ``empty_rate``: tickers with no frame or an empty one.
    - ``stale_symbols``: frames whose last bar predates the previous NYSE
      session; None when the calendar cannot say. Display only -- no
      threshold is measured yet.
    """
    rate = fallback_rate([d for d in (data_sources, price_sources) if isinstance(d, dict)])
    empty = sum(1 for ticker in tickers if _is_empty(frames.get(ticker)))
    return {
        "provider_fallback_rate": None if rate is None else round(rate, 4),
        "empty_symbols": empty,
        "empty_rate": round(empty / len(tickers), 4) if tickers else None,
        "stale_symbols": _stale_count(tickers, frames, today),
    }
