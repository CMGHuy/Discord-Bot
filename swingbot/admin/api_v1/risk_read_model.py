"""Risk reporting selection and weighting; never a trading-policy input."""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timezone
from typing import Callable

import numpy as np

from swingbot.core.marketdata import fx
from swingbot.core.infra.swallowed import swallowed

log = logging.getLogger(__name__)


class _WeightError(ValueError):
    pass


def _positive(value, reason: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _WeightError(reason) from exc
    if isinstance(value, bool) or not math.isfinite(result) or result <= 0:
        raise _WeightError(reason)
    return result


def _quote_rate(ticker: str, account: str, on: date) -> float:
    try:
        quote = fx.quote_currency_code(ticker)
    except Exception as exc:
        raise _WeightError("missing_quote_currency") from exc
    if not quote:
        raise _WeightError("missing_quote_currency")
    try:
        rate = fx.fx_rate(quote, account, on)
    except Exception as exc:
        raise _WeightError("missing_fx") from exc
    if rate is None:
        raise _WeightError("missing_fx")
    return _positive(rate, "invalid_fx")


def _position_notional(trade: dict, account: str, on: date) -> tuple[str, float, float]:
    ticker = trade.get("ticker")
    if not isinstance(ticker, str) or not ticker.strip():
        raise _WeightError("invalid_position")
    ticker = ticker.strip().upper()
    sign = {"bullish": 1.0, "bearish": -1.0}.get(trade.get("direction"))
    if sign is None:
        raise _WeightError("invalid_direction")
    entry = _positive(trade.get("entry"), "invalid_position")
    shares = _positive(trade.get("shares"), "invalid_position")
    value = _positive(entry * shares * _quote_rate(ticker, account, on), "invalid_position")
    return ticker, value, sign


def signed_weights(open_trades: list[dict], *, on: date,
                   account: str | None = None) -> tuple[dict[str, float], str | None]:
    if not open_trades:
        return {}, None
    try:
        account = account if account is not None else fx.account_currency_code()
        gross = 0.0
        signed: dict[str, float] = {}
        for trade in open_trades:
            ticker, notional, sign = _position_notional(trade, account, on)
            gross += notional
            signed[ticker] = signed.get(ticker, 0.0) + sign * notional
        gross = _positive(gross, "invalid_position")
        if any(not math.isfinite(value) for value in signed.values()):
            raise _WeightError("invalid_position")
        return {ticker: value / gross for ticker, value in signed.items()}, None
    except _WeightError as exc:
        return {}, str(exc)
    except Exception as exc:
        swallowed(log, "ops.risk_read_model.weights", exc, level=logging.DEBUG)
        return {}, "invalid_position"


def _valid_frame(frame) -> bool:
    try:
        close = frame["Close"]
        return not close.empty and bool(np.isfinite(close).all()) and bool((close > 0).all())
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def complete_bars(symbols: list[str], bars: dict) -> bool:
    return all(_valid_frame(bars.get(symbol)) for symbol in symbols)


def _close_stamp(row) -> datetime | None:
    if not isinstance(row, dict):
        return None
    value = row.get("closed_at")
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def _finite_outcome(outcome: Callable, row: dict) -> float | None:
    try:
        raw = outcome(row)
        if raw is None or isinstance(raw, bool):
            return None
        value = float(raw)
        return value if math.isfinite(value) else None
    except Exception as exc:
        swallowed(log, "ops.risk_read_model.outcome", exc, level=logging.DEBUG)
        return None


def chronological_records(closed: list[dict], *,
                          outcome: Callable[[dict], float | None] | None = None
                          ) -> tuple[list[dict], dict[str, int]]:
    """Select usable records in UTC close order, counting exclusions once."""
    selected = []
    invalid_date = invalid_outcome = 0
    for row in closed:
        stamp = _close_stamp(row)
        if stamp is None:
            invalid_date += 1
            continue
        if outcome is not None and _finite_outcome(outcome, row) is None:
            invalid_outcome += 1
            continue
        selected.append((stamp, str(row.get("id", "")), row))
    selected.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in selected], {
        "excluded_count": invalid_date + invalid_outcome,
        "invalid_date_count": invalid_date,
        "invalid_outcome_count": invalid_outcome,
    }

