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

v181 § 6: `before=<t>` pages older history. It accepts exactly the `t` the
endpoint emits for that `tf` (`equity_candles.parse_bucket_label`) and keeps
candles whose bucket starts strictly before it, compared as instants. The
full series is built and `change`d first, then filtered and sliced, so a
page's `o`/`change` are the full-history values; `has_more` says whether
the slice cut older candles. Paging at the database is out of scope.
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


def _before(tf: str) -> datetime | None:
    raw = request.args.get("before")
    if raw is None:
        return None
    try:
        return equity_candles.parse_bucket_label(raw, tf)
    except ValueError:
        form = "an ISO datetime with offset" if tf in _INTRADAY else "an ISO date"
        raise ApiError("invalid", f"before must be {form}, the t of a {tf} candle",
                       400) from None


def _page(candles: list[dict], tf: str, before: datetime | None,
          limit: int) -> tuple[list[dict], bool]:
    """The newest `limit` candles older than `before` (all when None), and
    whether older ones remain. Instants, not wall clock: same-zone aware
    datetimes ignore `fold`, which would merge the two fall-back hours."""
    if before is not None:
        cutoff = before.timestamp()
        candles = [c for c in candles
                   if equity_candles.parse_bucket_label(c["t"], tf).timestamp() < cutoff]
    return candles[-limit:], len(candles) > limit


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
    before = _before(tf)
    candles = _mtm(tf) if basis == "mtm" else _realized(tf)
    page, has_more = _page(candles, tf, before, limit)
    return jsonify({
        "tf": tf,
        "basis": basis,
        "currency_symbol": config.CURRENCY_SYMBOL,
        "candles": page,
        "has_more": has_more,
        "recording_since": iso(equity_samples_repo().earliest_at("live")),
        "as_of": iso(datetime.now(timezone.utc)),
    })
