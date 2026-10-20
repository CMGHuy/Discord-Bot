"""v172: GET /api/v1/equity/candles -- the Dashboard's equity candlestick chart.

Candles are built on request from raw rows (spec v172, approach A):
- `basis=mtm` (default): `equity_samples` rows, live and backfill for 1D/1W,
  live only for 1H/4H (intraday history starts at deploy, by design);
- `basis=realized`: one step per realized leg of the main book
  (`swingbot.core.tracking.equity.realized_legs`), never the samples.
Bucketing and `change` live in `swingbot.core.tracking.equity_candles`.
`limit` keeps the most recent candles after `change` is computed over the
whole series, so the first returned candle still compares with its real
predecessor. `currency_symbol` is `config.CURRENCY_SYMBOL`, the symbol the
Dashboard already shows (no ISO code exists in config).
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import jsonify, request

from swingbot import config
from swingbot.core.db.repositories.equity_samples import equity_samples_repo
from swingbot.core.tracking import equity, equity_candles

from . import ApiError, api_v1, iso
from .auth import require_auth

DEFAULT_LIMIT = 120
MAX_LIMIT = 500
BASES = ("mtm", "realized")
_INTRADAY = ("1H", "4H")


def _choice(name: str, allowed: tuple[str, ...], default: str) -> str:
    raw = request.args.get(name)
    if raw is None:
        return default
    if raw not in allowed:
        raise ApiError("invalid", f"{name} must be one of {', '.join(allowed)}", 400)
    return raw


def _limit() -> int:
    raw = request.args.get("limit")
    if raw is None:
        return DEFAULT_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 0
    if not 1 <= value <= MAX_LIMIT:
        raise ApiError("invalid", f"limit must be one of 1..{MAX_LIMIT}", 400)
    return value


def _mtm(tf: str) -> list[dict]:
    sources = ("live",) if tf in _INTRADAY else ("live", "backfill")
    return equity_candles.mtm_candles(equity_samples_repo().list_rows(sources=sources), tf)


def _realized(tf: str) -> list[dict]:
    from swingbot.core.tracking.performance import TradeLog
    trades = TradeLog().get_trades(status=None, limit=None, sort_by="opened_at") or []
    return equity_candles.realized_candles(equity.realized_legs(trades),
                                           equity.starting_balance(), tf)


@api_v1.route("/equity/candles", methods=["GET"])
@require_auth
def equity_candles_view():
    tf = _choice("tf", equity_candles.TIMEFRAMES, "1D")
    basis = _choice("basis", BASES, "mtm")
    limit = _limit()
    candles = _mtm(tf) if basis == "mtm" else _realized(tf)
    return jsonify({
        "tf": tf,
        "basis": basis,
        "currency_symbol": config.CURRENCY_SYMBOL,
        "candles": candles[-limit:],
        "recording_since": iso(equity_samples_repo().earliest_at("live")),
        "as_of": iso(datetime.now(timezone.utc)),
    })
