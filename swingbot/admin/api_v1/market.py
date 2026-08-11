"""GET /api/v1/market/ohlcv/{ticker} — daily bars for the chart.

Read-only, 260 bars by default (~1 trading year), capped at 1000. The cap is
not a tuning knob: the client picks how much work this request does, and a
chart cannot usefully draw more than that anyway.

Both the frame lookup and the level mapping come from `app.py`
(`_ohlcv_frame`, `trade_levels`, `ohlcv_bars`) rather than being rebuilt
here. The Angular and Jinja charts are both live for the whole migration; a
second bar serialisation would let them disagree about rounding, and a
second level mapping would let one of them draw a take-profit line at the
wrong price -- which looks entirely plausible on screen.

`_ohlcv_frame` tries a live fetch and falls back to the backtest CSV cache,
so the chart still renders offline. That is one of the repo's TWO parallel
OHLCV caches (`data/backtest_cache/`, flat per-ticker dailies -- not
`market_data/`, which is timeframe-first and belongs to the edge engine).
Reusing the accessor is also how this endpoint avoids having to know that.
"""
from __future__ import annotations

from flask import jsonify

from . import api_v1, error
from .auth import require_auth

DEFAULT_BARS = 260
MAX_BARS = 1000


@api_v1.route("/market/ohlcv/<ticker>", methods=["GET"])
@require_auth
def ohlcv(ticker: str):
    """`levels` is present only when `trade_id` is given AND resolves.

    An unresolvable `trade_id` is a 404 rather than a chart with the levels
    quietly missing. The request was "this trade's chart"; answering with a
    plain one that looks complete is how a user reads a chart believing the
    lines are simply not set. A client wanting bars regardless just omits
    the parameter.
    """
    from flask import request

    from swingbot.admin.app import (_ohlcv_frame, _trade_for_levels,
                                    ohlcv_bars, trade_levels)

    raw_bars = request.args.get("bars")
    if raw_bars is None:
        bars = DEFAULT_BARS
    else:
        try:
            bars = int(raw_bars)
        except (TypeError, ValueError):
            return error("invalid", f"bars must be an integer, got {raw_bars!r}", 400)
        # Clamped, not rejected: "more than the cap" means "as much as you
        # have", which is what the caller gets.
        bars = max(1, min(bars, MAX_BARS))

    ticker = ticker.upper()
    df = _ohlcv_frame(ticker)
    if df is None or not len(df):
        return error("not_found", f"No OHLCV data for {ticker!r}.", 404)

    payload = {"ticker": ticker, "bars": ohlcv_bars(df.tail(bars))}

    trade_id = request.args.get("trade_id")
    if trade_id:
        trade = _trade_for_levels(trade_id)
        if not trade:
            return error("not_found", f"No trade with id {trade_id!r}", 404)
        payload["levels"] = trade_levels(trade)

    return jsonify(payload)
