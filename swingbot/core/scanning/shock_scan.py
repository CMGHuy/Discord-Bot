"""v209: the market-shock pass -- every wiring decision of the detector.

`run_shock_pass` (V209-6a) is called once per scan pass by
scan_run._sync_run_scan (V209-6b). Only the scheduled session scan passes
step_shock=True, and only inside the NYSE regular session (holiday and half-day
aware) does it measure, step and record a reading; every other pass only reads
the stored label for the plan stamp. "Last" is the pass's live quote; prev_close
and ATR14 come from completed daily bars only. A failure never fails the scan.

Spec: docs/superpowers/specs/2026-11-05-v209-market-shock-detector-design.md
"""
from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from datetime import date, datetime, timezone

import pandas as pd

from swingbot import config
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.market import indicators, session, shock
from swingbot.core.marketdata import asset_class
from swingbot.core.marketdata.shared import tape

log = logging.getLogger(__name__)

MODES = ("off", "shadow", "live")
VIX_SYMBOL = "^VIX"
MIN_COMPLETED_BARS = 15
_NO_VIX = shock.VixTape(None, None, None)

#: ShockThresholds field -> config attribute (V209-1). SHOCK_READINGS_KEEP_DAYS is
#: retention, read by loops._prune_shock_readings, not a threshold.
THRESHOLD_ATTRS = {
    "atr_k": "SHOCK_ATR_K", "breadth_enter": "SHOCK_BREADTH_ENTER",
    "sectors_frac": "SHOCK_SECTORS_FRAC", "breadth_fast": "SHOCK_BREADTH_FAST",
    "speed_enter": "SHOCK_SPEED_ENTER", "vix_spike_pct": "SHOCK_VIX_SPIKE_PCT",
    "vix_relief": "SHOCK_VIX_RELIEF", "breadth_reenter": "SHOCK_BREADTH_REENTER",
    "breadth_exit": "SHOCK_BREADTH_EXIT",
    "recovery_vix_off_high_pct": "RECOVERY_VIX_OFF_HIGH_PCT",
    "recovery_spy_retrace": "RECOVERY_SPY_RETRACE", "min_dwell_min": "SHOCK_MIN_DWELL_MIN",
    "recovery_min_dwell_min": "RECOVERY_MIN_DWELL_MIN", "min_names": "SHOCK_MIN_NAMES",
    "vix_max_age_s": "SHOCK_VIX_MAX_AGE_S", "open_settle_min": "SHOCK_OPEN_SETTLE_MIN",
    "quote_max_age_s": "SHOCK_QUOTE_MAX_AGE_S",
}


def shock_mode() -> str:
    mode = str(getattr(config, "MARKET_SHOCK_MODE", "off") or "off").strip().lower()
    return mode if mode in MODES else "off"


def thresholds_from_config() -> shock.ShockThresholds:
    defaults = shock.ShockThresholds()
    values = {}
    for name, attr in THRESHOLD_ATTRS.items():
        default = getattr(defaults, name)
        values[name] = type(default)(getattr(config, attr, default))
    return shock.ShockThresholds(**values)


def _number(value) -> float | None:
    """A finite float, or None for None/NaN/inf/garbage."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _aware(stamp: datetime) -> datetime:
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)


def read_vix(now: datetime, th: shock.ShockThresholds) -> shock.VixTape:
    """The ^VIX tape row (never fetches); empty when missing, a proxy, or stale."""
    try:
        entry = tape.read_tape([VIX_SYMBOL]).get(VIX_SYMBOL)
    except Exception as exc:
        swallowed(log, "scan.shock.vix", exc, "shock: ^VIX tape read failed: %s", exc)
        return _NO_VIX
    if entry is None or entry.is_proxy or _number(entry.price) is None or entry.as_of is None:
        return _NO_VIX
    as_of = _aware(entry.as_of)
    if (now - as_of).total_seconds() > th.vix_max_age_s:
        return _NO_VIX
    return shock.VixTape(_number(entry.price), _number(entry.change_pct), as_of)


def _completed(df: pd.DataFrame | None, today: date) -> pd.DataFrame | None:
    """Completed daily bars: drop bar[-1] when it is dated today (ET)."""
    if df is None or len(df) == 0:
        return None
    return df.iloc[:-1] if pd.Timestamp(df.index[-1]).date() >= today else df


def _name_row(ticker: str, df, last, sector, today: date, is_equity: bool) -> shock.NameRow:
    done = _completed(df, today)
    prev_close = _number(done["Close"].iloc[-1]) if done is not None and len(done) else None
    atr14 = None
    if done is not None and len(done) >= MIN_COMPLETED_BARS:
        atr14 = _number(indicators.atr(done, 14).iloc[-1])
    return shock.NameRow(ticker, sector, last, prev_close, atr14, is_equity)


def _quote(quotes: Mapping[str, float], ticker: str) -> float | None:
    value = _number(quotes.get(ticker))
    return value if value is not None and value > 0 else None


def _fresh_quotes(live_prices, quotes_at, now, th) -> Mapping[str, float]:
    if quotes_at is None or (now - quotes_at).total_seconds() > th.quote_max_age_s:
        return {}
    return live_prices or {}


def _benchmark(ticker: str, df, quotes, today: date) -> shock.NameRow | None:
    if df is None or len(df) == 0:
        return None
    return _name_row(ticker, df, _quote(quotes, ticker), None, today, False)


def _minutes_since_open(now: datetime) -> float:
    et = session.now_et(now)
    opened = datetime.combine(et.date(), session.RTH_OPEN, tzinfo=et.tzinfo)
    return (et - opened).total_seconds() / 60.0


def build_snapshot(frames, live_prices, sector_of, *, now, quotes_at, vix, th, spy_ticker,
                   spy_df=None, qqq_ticker="QQQ") -> shock.ShockSnapshot:
    today = session.market_today(now)
    quotes = _fresh_quotes(live_prices, quotes_at, now, th)
    names = tuple(
        _name_row(t, df, _quote(quotes, t), sector_of.get(t), today,
                  asset_class.classify(t) == "equity")
        for t, df in list(frames.items()) if df is not None and len(df))
    spy_frame = spy_df if spy_df is not None else frames.get(spy_ticker)
    return shock.ShockSnapshot(
        as_of=now, session_date=today, minutes_since_open=_minutes_since_open(now),
        names=names, spy=_benchmark(spy_ticker, spy_frame, quotes, today),
        qqq=_benchmark(qqq_ticker, frames.get(qqq_ticker), quotes, today), vix=vix)


def should_step(step_shock: bool, now: datetime) -> bool:
    return bool(step_shock) and shock_mode() != "off" and session.is_nyse_regular_session(now)
