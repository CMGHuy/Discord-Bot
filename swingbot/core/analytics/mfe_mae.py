"""Maximum Favorable/Adverse Excursion and exit efficiency, computed from a
ticker's cached daily bars for one closed trade -- the "how good was this
exit, really" number the auto-journal (journal.py, Task A20) is built
around: a trade that closed +1R after running to +3R in its favor tells a
very different story than one that closed +1R after only ever reaching
+1.1R.

Pure function, no I/O -- the caller (journal.py) is responsible for
fetching `df` (see Task A22's journal_trade_close)."""
from __future__ import annotations

import datetime as dt

from swingbot.core.analytics.metrics import r_multiple


def _parse_dt(iso_str) -> dt.datetime | None:
    if not iso_str:
        return None
    try:
        return dt.datetime.fromisoformat(iso_str)
    except (TypeError, ValueError):
        return None


def compute_mfe_mae(trade: dict, df) -> dict | None:
    """Maximum favorable/adverse excursion (in R-multiples of the trade's
    own original risk) across the bars the trade was actually open for,
    plus exit efficiency (how much of the best-available move was
    actually banked at exit).

    None whenever the inputs don't support a real answer: missing
    entry/stop_loss, zero risk, missing/unparseable opened_at/closed_at,
    a None/empty `df`, or a date slice that lands on zero bars (e.g. the
    cached data doesn't cover the trade's window). Never raises.
    """
    entry = trade.get("entry")
    stop = trade.get("stop_loss")
    if entry is None or stop is None:
        return None
    risk = abs(entry - stop)
    if risk == 0:
        return None

    start = _parse_dt(trade.get("opened_at"))
    end = _parse_dt(trade.get("closed_at"))
    if start is None or end is None:
        return None
    if df is None or df.empty:
        return None

    idx = df.index
    tz_aware = getattr(idx, "tz", None) is not None
    if tz_aware:
        start_cmp = start if start.tzinfo else start.replace(tzinfo=dt.timezone.utc)
        end_cmp = end if end.tzinfo else end.replace(tzinfo=dt.timezone.utc)
    else:
        start_cmp = start.replace(tzinfo=None)
        end_cmp = end.replace(tzinfo=None)

    # Normalize to midnight (day boundary) so comparison is date-level, not
    # exact-timestamp-level; this ensures the entry day's bar (indexed at
    # midnight) is correctly included regardless of opened_at's time-of-day.
    start_cmp = start_cmp.replace(hour=0, minute=0, second=0, microsecond=0)
    end_cmp = end_cmp.replace(hour=0, minute=0, second=0, microsecond=0)

    sliced = df.loc[(idx >= start_cmp) & (idx <= end_cmp)]
    if sliced.empty:
        return None

    is_bull = trade.get("direction") == "bullish"
    if is_bull:
        mfe_r = (float(sliced["High"].max()) - entry) / risk
        mae_r = max(0.0, (entry - float(sliced["Low"].min())) / risk)
    else:
        mfe_r = (entry - float(sliced["Low"].min())) / risk
        mae_r = max(0.0, (float(sliced["High"].max()) - entry) / risk)

    r_real = r_multiple(trade)
    exit_efficiency = None
    if r_real is not None and mfe_r > 0:
        exit_efficiency = max(-5.0, min(1.0, r_real / mfe_r))

    return {
        "mfe_r": round(mfe_r, 4),
        "mae_r": round(mae_r, 4),
        "exit_efficiency": round(exit_efficiency, 4) if exit_efficiency is not None else None,
    }
