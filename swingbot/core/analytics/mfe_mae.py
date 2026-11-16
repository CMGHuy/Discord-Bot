"""Maximum Favorable/Adverse Excursion and exit efficiency for one closed
trade -- the "how good was this exit, really" number the auto-journal
(journal.py) is built around.

v228: the excursion is measured on the finest archived bars that cover the
trade (5min, 15min, hourly, then daily), and the result names the frame used
(`excursion_source`). Since 2026-10-01 most LONG trades close the day they
open, and a daily bar's range includes price before the fill and after the
exit. Intraday rules: the bar holding the fill is dropped (pre-fill prices),
the bar holding the exit is kept (overstates by at most one bar), and the
entry and exit prices are always points on the path (anchors), so a trade
inside one bar still gets a bounded answer -- a lower bound, since the
source names the bars consulted, not the precision achieved. The daily frame
keeps the pre-v228 arithmetic exactly.

Time basis: archive indexes from data_store.load_normalized are naive UTC
bar starts (pinned by tests/marketdata/test_archive_time_basis.py); journal
times are aware UTC ISO strings, converted to naive UTC before comparing.

Pure functions, no I/O -- excursion_frames.load_frames loads the frames."""
from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from swingbot.core.analytics.metrics import r_multiple

EXCURSION_SOURCES = ("5min", "15min", "hourly", "daily")
INTRADAY_SOURCES = ("5min", "15min", "hourly")
BAR_MINUTES = {"5min": 5, "15min": 15, "hourly": 60}
#: Two bars on one date further apart than this many bar lengths are a hole:
#: the frame is skipped like an uncovered one, never used silently.
DENSITY_BAR_LENGTHS = 4


def source_rank(source: str | None) -> int:
    """5min 0 ... daily 3; None or anything unknown ranks coarsest (4)."""
    try:
        return EXCURSION_SOURCES.index(source)
    except ValueError:
        return len(EXCURSION_SOURCES)


def coarser_sources(source: str) -> tuple[str | None, ...]:
    """Every stored source a result from `source` may replace, then None."""
    rank = source_rank(source)
    return tuple(s for s in EXCURSION_SOURCES if source_rank(s) > rank) + (None,)


def _parse_dt(iso_str) -> dt.datetime | None:
    if not iso_str:
        return None
    try:
        return dt.datetime.fromisoformat(iso_str)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class _Inputs:
    entry: float
    risk: float
    start: dt.datetime
    end: dt.datetime
    is_bull: bool


def _inputs(trade: dict) -> _Inputs | None:
    entry, stop = trade.get("entry"), trade.get("stop_loss")
    if entry is None or stop is None:
        return None
    risk = abs(entry - stop)
    if risk == 0:
        return None
    start = _parse_dt(trade.get("opened_at"))
    end = _parse_dt(trade.get("closed_at"))
    if start is None or end is None:
        return None
    return _Inputs(entry, risk, start, end, trade.get("direction") == "bullish")


def _naive_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(dt.timezone.utc).replace(tzinfo=None)


def _naive_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return idx


def _daily_slice(df: pd.DataFrame, inputs: _Inputs) -> pd.DataFrame:
    """The pre-v228 date-level slice, unchanged."""
    idx = df.index
    if getattr(idx, "tz", None) is not None:
        start = inputs.start if inputs.start.tzinfo else inputs.start.replace(tzinfo=dt.timezone.utc)
        end = inputs.end if inputs.end.tzinfo else inputs.end.replace(tzinfo=dt.timezone.utc)
    else:
        start, end = inputs.start.replace(tzinfo=None), inputs.end.replace(tzinfo=None)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = end.replace(hour=0, minute=0, second=0, microsecond=0)
    return df.loc[(idx >= start) & (idx <= end)]


def _cover(idx: pd.DatetimeIndex, start: dt.datetime, end: dt.datetime, bar: dt.timedelta) -> bool:
    return idx[0] <= start and idx[-1] >= end - bar


def _dense(idx: pd.DatetimeIndex, start: dt.datetime, end: dt.datetime, bar: dt.timedelta) -> bool:
    window = idx[(idx > start - bar) & (idx <= end)]
    if len(window) < 2:
        return True
    gaps = window[1:] - window[:-1]
    same_date = window[1:].normalize() == window[:-1].normalize()
    return not bool(((gaps > bar * DENSITY_BAR_LENGTHS) & same_date).any())


def _intraday_verdict(name: str, df: pd.DataFrame, inputs: _Inputs):
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    bar = dt.timedelta(minutes=BAR_MINUTES[name])
    idx = _naive_index(df)
    start, end = _naive_utc(inputs.start), _naive_utc(inputs.end)
    if not _cover(idx, start, end, bar):
        return "coverage", None
    if not _dense(idx, start, end, bar):
        return "density", None
    return "ok", df.loc[(idx >= start) & (idx <= end)]


def _verdict(name: str, df: pd.DataFrame | None, inputs: _Inputs):
    if name not in EXCURSION_SOURCES:
        return "unsupported", None
    if df is None or df.empty:
        return "empty", None
    if name == "daily":
        sliced = _daily_slice(df, inputs)
        return ("coverage", None) if sliced.empty else ("ok", sliced)
    return _intraday_verdict(name, df, inputs)


def _ordered(frames: Mapping[str, pd.DataFrame | None]):
    return sorted(frames.items(), key=lambda item: source_rank(item[0]))


def _excursion_r(sliced: pd.DataFrame, inputs: _Inputs) -> tuple[float, float]:
    high, low = float(sliced["High"].max()), float(sliced["Low"].min())
    if inputs.is_bull:
        return (high - inputs.entry) / inputs.risk, max(0.0, (inputs.entry - low) / inputs.risk)
    return (inputs.entry - low) / inputs.risk, max(0.0, (high - inputs.entry) / inputs.risk)


def _exit_r(trade: dict, inputs: _Inputs) -> float:
    """Signed R of the exit price; 0.0 (the entry anchor) when unknown."""
    try:
        price = float(trade.get("exit_price"))
    except (TypeError, ValueError):
        return 0.0
    move = price - inputs.entry if inputs.is_bull else inputs.entry - price
    return move / inputs.risk


def _anchored_r(sliced: pd.DataFrame, inputs: _Inputs, trade: dict) -> tuple[float, float]:
    mfe, mae = _excursion_r(sliced, inputs) if not sliced.empty else (0.0, 0.0)
    exit_r = _exit_r(trade, inputs)
    return max(mfe, 0.0, exit_r), max(mae, 0.0, -exit_r)


def _result(mfe_r: float, mae_r: float, trade: dict, source: str) -> dict:
    r_real = r_multiple(trade)
    exit_efficiency = None
    if r_real is not None and mfe_r > 0:
        exit_efficiency = max(-5.0, min(1.0, r_real / mfe_r))
    return {"mfe_r": round(mfe_r, 4), "mae_r": round(mae_r, 4),
            "exit_efficiency": round(exit_efficiency, 4) if exit_efficiency is not None else None,
            "excursion_source": source}


def frame_verdicts(trade: dict, frames: Mapping[str, pd.DataFrame | None]) -> dict[str, str]:
    """Why each frame was used or skipped, finest first; {} for an unusable trade."""
    inputs = _inputs(trade)
    if inputs is None:
        return {}
    return {name: _verdict(name, df, inputs)[0] for name, df in _ordered(frames)}


def compute_excursion(trade: dict, frames: Mapping[str, pd.DataFrame | None]) -> dict | None:
    """MFE/MAE/exit efficiency from the finest frame that covers the trade."""
    inputs = _inputs(trade)
    if inputs is None or not frames:
        return None
    for name, df in _ordered(frames):
        verdict, sliced = _verdict(name, df, inputs)
        if verdict != "ok":
            continue
        if name == "daily":
            mfe_r, mae_r = _excursion_r(sliced, inputs)
        else:
            mfe_r, mae_r = _anchored_r(sliced, inputs, trade)
        return _result(mfe_r, mae_r, trade, name)
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
