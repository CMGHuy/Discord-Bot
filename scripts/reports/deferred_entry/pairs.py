"""v229 export reader, population funnel and pair assembly.

The export (scripts/ops/export_book_rows.sh rows) is read BY COLUMN NAME, so
today's 38 columns and v228's 39 both work; autopsy/rows.load_rows is never
used (v228 makes it refuse an older CSV). classify() names why each trade is
in or out -- every reason is counted, an absent archive file included
(known-traps: a silent skip would hide a measured answer)."""
from __future__ import annotations

import csv

import pandas as pd

from swingbot.core.backtesting.instrument.stats import iso_week_key
from swingbot.core.market.session import RTH_OPEN, nyse_calendar, session_close
from swingbot.core.scanning.risk_features import session_bucket

from .arms import deferral_bar, frictions_stamp, price_arms
from .bars import (DEFER_AT, ET, deferral_start, et_date, et_time, horizon_end,
                   session_close_utc, to_utc)
from .tradeability import event_flags, record

REQUIRED_COLUMNS = ("row_kind", "trade_id", "ticker", "direction", "entry_type",
                    "plan_created_at", "expiry_bars", "opened_at", "entry", "stop_loss",
                    "take_profit", "closed_at", "close_reason", "last_leg_reason", "outcome",
                    "r_realized", "session_bucket")
REASONS = ("not_trade", "not_market", "entry_type_unknown", "bad_levels", "outside_session",
           "close_bucket", "no_coverage", "pending", "no_deferral_bar", "eligible")
DIRECTIONS = {"bullish": "bullish", "long": "bullish", "bearish": "bearish", "short": "bearish"}
_SIGN = {"bullish": 1, "bearish": -1}
_LAST_BAR_SLACK = pd.Timedelta(minutes=15)
HOLD_SESSIONS = 5


def read_export(path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        present = set(reader.fieldnames or ())
        missing = [c for c in REQUIRED_COLUMNS if c not in present]
        if missing:
            raise ValueError(f"{path}: export lacks columns {', '.join(missing)}")
        return [dict(row) for row in reader]


def _text(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


def _float_or_none(text) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _levels(row: dict) -> tuple[str, float, float, float] | None:
    direction = DIRECTIONS.get(_text(row, "direction").lower())
    values = [_float_or_none(_text(row, k)) for k in ("entry", "stop_loss", "take_profit")]
    if direction is None or None in values:
        return None
    entry, stop, tp1 = values
    sign = _SIGN[direction]
    if sign * (entry - stop) <= 0 or sign * (tp1 - entry) <= 0:
        return None
    return direction, entry, stop, tp1


def _opened(row: dict) -> pd.Timestamp | None:
    try:
        return to_utc(_text(row, "opened_at"))
    except ValueError:
        return None


def _in_session(row: dict) -> bool:
    opened = _opened(row)
    if opened is None:
        return False
    d = et_date(opened)
    return nyse_calendar().is_session(d) and RTH_OPEN <= et_time(opened) < session_close(d)


_STATIC_CHECKS = (
    ("not_trade", lambda r: _text(r, "row_kind") != "trade"),
    ("entry_type_unknown", lambda r: not _text(r, "entry_type")),
    ("not_market", lambda r: _text(r, "entry_type").lower() != "market"),
    ("bad_levels", lambda r: _levels(r) is None),
    ("outside_session", lambda r: not _in_session(r)),
    ("close_bucket", lambda r: et_time(_opened(r)) >= DEFER_AT),
)


def _covered(bars, opened: pd.Timestamp, end: pd.Timestamp) -> bool:
    if bars is None or bars.empty:
        return False
    window = bars[(bars.index >= opened) & (bars.index < end)]
    if window.empty or window.index[-1] < end - _LAST_BAR_SLACK:
        return False
    have = set(window.index.tz_convert(ET).date)
    d = et_date(opened)
    cal = nyse_calendar()
    return all(s in have for s in cal.sessions(d, cal.session_after(d, HOLD_SESSIONS)))


def _coverage_reason(bars, opened: pd.Timestamp, archive_end) -> str:
    d = et_date(opened)
    end = horizon_end(d, HOLD_SESSIONS)
    if end is None:
        return "no_coverage"
    last = None if archive_end is None else to_utc(archive_end)
    if last is None or last < end - _LAST_BAR_SLACK:
        return "pending"
    if not _covered(bars, opened, end):
        return "no_coverage"
    if deferral_bar(bars, deferral_start(d), session_close_utc(d)) is None:
        return "no_deferral_bar"
    return "eligible"


def classify(row: dict, bars, *, archive_end) -> str:
    """The funnel reason of one export row (one of REASONS)."""
    for reason, failed in _STATIC_CHECKS:
        if failed(row):
            return reason
    return _coverage_reason(bars, _opened(row), archive_end)


def _live(row: dict) -> dict:
    return {"reason": _text(row, "last_leg_reason") or _text(row, "close_reason"),
            "outcome": _text(row, "outcome") or None,
            "r_realized": _float_or_none(_text(row, "r_realized") or None)}


def _closed_at(row: dict) -> pd.Timestamp | None:
    try:
        return to_utc(_text(row, "closed_at"))
    except ValueError:
        return None


def build_pair(row: dict, bars, *, rule_hash: str, earnings_lookup=None) -> dict:
    """One PAIR (index § Shared shapes) for a row classify() called eligible."""
    levels = _levels(row)
    if levels is None:
        raise ValueError(f"trade {_text(row, 'trade_id')}: bad levels")
    direction, entry, stop, tp1 = levels
    opened = to_utc(_text(row, "opened_at"))
    d = et_date(opened)
    deferral, close, end = deferral_start(d), session_close_utc(d), horizon_end(d, HOLD_SESSIONS)
    priced = price_arms(bars, direction=direction, entry=entry, stop=stop, tp1=tp1,
                        opened_at=opened, deferral=deferral, close=close, end=end)
    bar = deferral_bar(bars, deferral, close)
    live = _live(row)
    flags = event_flags(_text(row, "ticker"), d, earnings_lookup=earnings_lookup)
    trade_record = record(
        bars, direction=direction, entry=entry, stop=stop, tp1=tp1, opened_at=opened,
        deferral=bar.name, arms=priced, plan_created_at=_text(row, "plan_created_at"),
        expiry_bars=_text(row, "expiry_bars"), closed_at=_closed_at(row),
        live_reason=live["reason"], flags=flags)
    window = bars[(bars.index >= opened) & (bars.index < end)]
    return {
        "trade_id": _text(row, "trade_id"), "ticker": _text(row, "ticker"),
        "direction": direction, "opened_at": opened.isoformat(), "entry_date": d.isoformat(),
        "iso_week": iso_week_key(d),
        "bucket": session_bucket(opened.tz_convert(ET).to_pydatetime()),
        "trade": {"entry": entry, "stop_loss": stop, "take_profit": tp1},
        "arms": {name: result.to_dict() for name, result in priced.items()},
        "live": live,
        "tradeability": trade_record,
        "coverage": {"bars_from": window.index[0].isoformat(),
                     "bars_to": window.index[-1].isoformat(),
                     "deferral_bar": bar.name.isoformat()},
        "rule_hash": rule_hash,
        "frictions": frictions_stamp(),
    }
