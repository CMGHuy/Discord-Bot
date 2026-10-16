"""Book rows: the VM export CSV (scripts/ops/export_book_rows.sh) as typed rows.

A ``trade`` row is one closed trade (journal x trades, left-joined to its
plan); a ``plan`` row is a plan that never became a trade, its trade columns
empty. Dates are US/Eastern ISO dates. Net R is MODELLED here with the backtest
friction model: no live store holds a net figure (spec, Data availability).
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import hashlib
from io import StringIO
import re
from dataclasses import dataclass, field
from pathlib import Path

from swingbot import config
from swingbot.core.edge.frictions import apply_frictions, commission_r
from swingbot.core.market.session import US_MARKET_TZ

EXPORT_COLUMNS = (
    "row_kind", "trade_id", "plan_id", "ticker", "strategy", "horizon", "direction",
    "plan_created_at", "plan_first_status_at", "plan_status", "plan_status_reason",
    "entry_type", "expiry_bars", "valid_session", "planned_entry", "opened_at", "entry",
    "stop_loss", "take_profit", "target2", "closed_at", "exit_price", "close_reason",
    "last_leg_reason", "outcome", "r_realized", "mfe_r", "mae_r", "exit_efficiency",
    "holding_days", "stop_width_atr", "atr_pct", "regime2_state", "session_bucket",
    "days_to_earnings", "rs_percentile",
)
REJECTION_COLUMNS = ("date", "reason", "count")

#: Below this fraction of the entry the stop is no longer the planned risk
#: (moved to breakeven): modelled slippage over it would be whole R of noise.
MIN_RISK_FRACTION = 0.001

_NULLS = {"", "nan", "none", "null"}
_SHORT = {"bearish", "short"}
# "...14:31:00+00" (Postgres text) -> "+00:00"; a date-only "2026-03-02" never matches.
_BARE_HOUR_OFFSET = re.compile(r"(\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)([+-]\d{2})$")


@dataclass
class BookRow:
    row_kind: str | None = None
    trade_id: str | None = None
    plan_id: str | None = None
    ticker: str | None = None
    strategy: str | None = None
    horizon: str | None = None
    direction: str | None = None
    plan_date: str | None = None
    plan_hour: int | None = None
    plan_status: str | None = None
    plan_status_reason: str | None = None
    entry_type: str | None = None
    expiry_bars: int | None = None
    valid_session: str | None = None
    planned_entry: float | None = None
    entry_date: str | None = None
    entry: float | None = None
    stop: float | None = None
    take_profit: float | None = None
    target2: float | None = None
    exit_date: str | None = None
    exit_price: float | None = None
    close_reason: str = ""
    outcome: str | None = None
    gross_r: float | None = None
    net_r: float | None = None
    mfe_r: float | None = None
    mae_r: float | None = None
    exit_efficiency: float | None = None
    holding_days: float | None = None
    stop_width_atr: float | None = None
    atr_pct: float | None = None
    days_to_earnings: float | None = None
    rs_percentile: float | None = None
    regime2_state: str | None = None
    session_bucket: str | None = None
    bars: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RejectionCount:
    date: str
    reason: str
    count: int


def _text(raw: str | None) -> str | None:
    value = (raw or "").strip()
    return value or None


def _float(raw: str | None) -> float | None:
    value = (raw or "").strip()
    if value.lower() in _NULLS:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _int(raw: str | None) -> int | None:
    number = _float(raw)
    return None if number is None else int(number)


def _timestamp(raw: str | None) -> dt.datetime | None:
    """A Postgres or ISO timestamp as an aware datetime; naive text is UTC."""
    value = _text(raw)
    if value is None:
        return None
    value = _BARE_HOUR_OFFSET.sub(r"\1\2:00", value.replace("Z", "+00:00"))
    stamp = dt.datetime.fromisoformat(value)
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=dt.timezone.utc)


def _eastern_date(raw: str | None) -> str | None:
    stamp = _timestamp(raw)
    return None if stamp is None else stamp.astimezone(US_MARKET_TZ).date().isoformat()


def _alert_hour(first_status_at: str | None, created_at: str | None) -> int | None:
    """Eastern hour the plan was issued. A created_at at exactly 00:00 UTC is a
    bar date with no time (TradePlanV2.created_at), so it gives no hour."""
    stamp = _timestamp(first_status_at)
    if stamp is None:
        stamp = _timestamp(created_at)
        if stamp is None or stamp.astimezone(dt.timezone.utc).time() == dt.time(0, 0):
            return None
    return stamp.astimezone(US_MARKET_TZ).hour


def _close_reason(close_reason: str | None, last_leg_reason: str | None) -> str:
    """metrics.close_reason_text: the last leg's reason wins, lower-cased."""
    return (_text(last_leg_reason) or _text(close_reason) or "").lower()


def _plan_fields(raw: dict) -> dict:
    created = _text(raw["plan_created_at"])
    return {
        "plan_date": created[:10] if created else None,
        "plan_hour": _alert_hour(raw["plan_first_status_at"], raw["plan_created_at"]),
        "plan_status": _text(raw["plan_status"]),
        "plan_status_reason": _text(raw["plan_status_reason"]),
        "entry_type": _text(raw["entry_type"]),
        "expiry_bars": _int(raw["expiry_bars"]),
        "valid_session": _text(raw["valid_session"]),
        "planned_entry": _float(raw["planned_entry"]),
    }


def _trade_fields(raw: dict) -> dict:
    return {
        "entry_date": _eastern_date(raw["opened_at"]),
        "entry": _float(raw["entry"]),
        "stop": _float(raw["stop_loss"]),
        "take_profit": _float(raw["take_profit"]),
        "target2": _float(raw["target2"]),
        "exit_date": _eastern_date(raw["closed_at"]),
        "exit_price": _float(raw["exit_price"]),
        "close_reason": _close_reason(raw["close_reason"], raw["last_leg_reason"]),
        "outcome": _text(raw["outcome"]),
    }


_JOURNAL_FLOATS = ("mfe_r", "mae_r", "exit_efficiency", "holding_days", "stop_width_atr",
                   "atr_pct", "days_to_earnings", "rs_percentile")


def _journal_fields(raw: dict) -> dict:
    out = {name: _float(raw[name]) for name in _JOURNAL_FLOATS}
    out["gross_r"] = _float(raw["r_realized"])
    out["regime2_state"] = _text(raw["regime2_state"])
    out["session_bucket"] = _text(raw["session_bucket"])
    return out


def _row(raw: dict, frictions: dict | None = None) -> BookRow:
    ident = {name: _text(raw[name]) for name in
             ("row_kind", "trade_id", "plan_id", "ticker", "strategy", "horizon", "direction")}
    row = BookRow(**ident, **_plan_fields(raw), **_trade_fields(raw), **_journal_fields(raw))
    row.net_r = modelled_net_r(row, frictions=frictions)
    return row


def _check_header(found, expected: tuple[str, ...], label: str) -> None:
    found = tuple(found or ())
    if found != expected:
        missing = [c for c in expected if c not in found]
        extra = [c for c in found if c not in expected]
        raise ValueError(f"{label}: header is not {','.join(expected)} "
                         f"(missing {missing}, extra {extra})")


def read_input(path: Path, input_fingerprints: dict | None = None) -> str:
    """Read once so the fingerprint describes exactly the bytes being parsed."""
    path = Path(path)
    data = path.read_bytes()
    if input_fingerprints is not None:
        input_fingerprints[str(path.resolve())] = hashlib.sha256(data).hexdigest()
    return data.decode("utf-8")


def friction_settings() -> dict:
    """Effective defaults consumed by the local net model, frozen once per CLI run."""
    return {"slippage_bps": getattr(config, "SLIPPAGE_BPS", 5.0),
            "commission_per_trade": getattr(config, "COMMISSION_PER_TRADE", 1.0),
            "commission_risk_basis": getattr(config, "COMMISSION_RISK_BASIS", 100.0),
            "min_risk_fraction": MIN_RISK_FRACTION}


def load_rows(path: Path, *, frictions: dict | None = None,
              input_fingerprints: dict | None = None) -> list[BookRow]:
    """Every export row, using one explicit friction snapshot and exact input hash."""
    settings = frictions if frictions is not None else friction_settings()
    reader = csv.DictReader(StringIO(read_input(path, input_fingerprints), newline=""))
    _check_header(reader.fieldnames, EXPORT_COLUMNS, str(path))
    return [_row(raw, settings) for raw in reader]


def closed_trades(rows) -> list[BookRow]:
    return [r for r in rows if r.row_kind == "trade" and r.gross_r is not None]


def plan_rows(rows) -> list[BookRow]:
    return [r for r in rows if r.row_kind == "plan"]


def _slip(price: float, side: str, bps: float) -> float:
    return abs(apply_frictions(price, side, slippage_bps=bps) - price)


def modelled_net_r(row: BookRow, *, frictions: dict | None = None) -> float | None:
    """Gross R less modelled slippage on both fills and the round-trip commission."""
    if row.gross_r is None or row.entry is None or row.stop is None:
        return None
    settings = frictions if frictions is not None else friction_settings()
    risk = abs(row.entry - row.stop)
    if risk < settings["min_risk_fraction"] * abs(row.entry) or risk == 0:
        return None
    short = (row.direction or "").lower() in _SHORT
    side_in, side_out = ("sell", "buy") if short else ("buy", "sell")
    exit_price = row.exit_price if row.exit_price is not None else row.entry
    bps = settings["slippage_bps"]
    slippage = _slip(row.entry, side_in, bps) + _slip(exit_price, side_out, bps)
    commission = commission_r(risk_dollars=settings["commission_risk_basis"],
                              commission=settings["commission_per_trade"])
    return row.gross_r - slippage / risk - commission


def load_rejections(path: Path, *, input_fingerprints: dict | None = None) -> list[RejectionCount]:
    """A ``rejections`` export: one count per (date, reason)."""
    reader = csv.DictReader(StringIO(read_input(path, input_fingerprints), newline=""))
    _check_header(reader.fieldnames, REJECTION_COLUMNS, str(path))
    return [RejectionCount(r["date"].strip(), r["reason"].strip(), int(r["count"]))
            for r in reader]
