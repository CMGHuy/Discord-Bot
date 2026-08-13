"""GET /api/v1/market/ohlcv/{ticker} and /api/v1/market/chart/{trade_id}.

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

`/market/chart/{trade_id}` (SR33, spec Decision 10) is the SPA's interactive
trade chart in ONE request: bars, indicator panes, the volume profile, the
plan lines and the confirming-method overlay. Every one of those numbers is
produced by the same Python that draws the PNG the bot posts to Discord --
`swingbot.core.indicators`, `signals.compute_volume_profile` and
`charts.chart_geometry.overlay_geometry`. A browser-side reimplementation of
"where does the 61.8% retracement sit" or "what is the 20-EMA here" would be
a guarantee that the chart a user zooms into eventually disagrees with the
image they were alerted with, and neither would look wrong on its own.
"""
from __future__ import annotations

import math

from flask import jsonify

from . import api_v1, error
from .auth import require_auth

DEFAULT_BARS = 260
MAX_BARS = 1000

# --- /market/chart -------------------------------------------------------
#
# The visible window, in bars. 120 is about six months of dailies, which is
# what a swing chart is read at. The bounds exist because `window` also sizes
# the overlay's point list and the volume-profile lookback, so it is real
# server work and not just a slice.
DEFAULT_WINDOW = 120
MIN_WINDOW = 20
MAX_WINDOW = 500

# Indicator parameters, and the minimum number of bars each one needs before
# its output means anything. These are explicit rather than derived from
# whether pandas happened to emit a NaN: an EWM with `adjust=False` produces
# a *number* from bar one, so "is it NaN" would happily serve a 26-slow MACD
# computed from three bars. See `_indicators`.
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
MACD_MIN_BARS = MACD_SLOW + MACD_SIGNAL          # 35
RSI_PERIOD = 14
RSI_MIN_BARS = RSI_PERIOD + 1                    # 15 -- rsi() diffs first
KC_EMA_PERIOD, KC_ATR_PERIOD, KC_MULTIPLIER = 20, 10, 1.5
KC_MIN_BARS = max(KC_EMA_PERIOD, KC_ATR_PERIOD)  # 20


def _num(value):
    """A plain finite float, or None for anything JSON cannot carry.

    Mirrors `chart_geometry._price`, deliberately: the two halves of this
    payload (the overlay, from that module; everything else, from here) must
    degrade the same way, or one pane would show a gap where the other shows
    a warm-up artefact.
    """
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _json_safe(value):
    """Recursively replace non-finite floats with None.

    Python's `json` emits bare `NaN` / `Infinity` tokens, which are not JSON
    and which `JSON.parse` rejects **outright** -- so a single warm-up bar
    anywhere in this payload does not degrade one pane, it fails the entire
    chart load with a parse error the user sees as a blank panel. That
    failure mode is bad enough to be checked at the boundary rather than
    trusted field by field, hence one final pass over the whole response.

    Ints are passed through untouched: bar timestamps are epoch SECONDS and
    must stay ints for the client's time conversion.
    """
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _series(values, window: int) -> list:
    """A pandas Series -> the last `window` values as JSON-safe floats.

    The series arrives computed over the FULL frame; slicing happens here,
    afterwards. Doing it the other way round is the NO-LOOKAHEAD violation
    this endpoint is most likely to grow: an EMA over 60 visible bars is a
    different number from an EMA over all history at *every* point, not just
    near the left edge, so the chart would show an indicator the scan never
    saw -- and it would change under the user as they widened the window.
    """
    return [_num(v) for v in values.tail(window).values]


def _indicators(df, window: int) -> dict:
    """The three indicator panes, each computed over `df` then sliced.

    An indicator the frame is too short for is **omitted from the dict
    entirely** -- not emitted as a list of nulls, and not as an empty list.
    That is spec Decision 10's third degraded state and it mirrors the PNG
    generator: the client omits the pane, so a trade that renders without a
    MACD panel in Discord renders without one here. A list of nulls would
    instead draw an empty pane with a price axis and no line, which reads as
    "this indicator is flat" rather than "there is not enough history".
    """
    from swingbot.core.indicators import keltner_channel, macd, rsi

    n = len(df)
    out = {}

    if n >= MACD_MIN_BARS:
        m = macd(df["Close"], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
        out["macd"] = {
            "line": _series(m["macd"], window),
            "signal": _series(m["signal"], window),
            "hist": _series(m["histogram"], window),
        }

    if n >= RSI_MIN_BARS:
        out["rsi"] = _series(rsi(df["Close"], period=RSI_PERIOD), window)

    if n >= KC_MIN_BARS:
        kc = keltner_channel(df, ema_period=KC_EMA_PERIOD, atr_period=KC_ATR_PERIOD,
                             multiplier=KC_MULTIPLIER)
        # The middle band is the same 20-EMA the price pane can already draw
        # as an overlay; only the envelope is carried, which is what the
        # squeeze is read from.
        out["kc"] = {"upper": _series(kc["upper"], window),
                     "lower": _series(kc["lower"], window)}

    return out


def _volume_profile(df, window: int) -> list:
    """The horizontal volume histogram, one row per bin, `price` at the bin's
    CENTRE (`compute_volume_profile` returns n+1 edges and n volumes).

    Binned over the visible window rather than the PNG's wider panel
    lookback: there, the lookback is widened to fill a price axis that has
    been stretched to fit a distant entry/stop. This chart has no such axis
    to fill -- it is interactive, and the client re-requests with a different
    `window` when the user zooms -- so the profile describes exactly the bars
    on screen, which is the only reading of it that stays true as they move.

    An empty list when there is not enough history: unlike an indicator, the
    profile is an overlay on the price pane rather than a pane of its own, so
    there is nothing to omit.
    """
    from swingbot.core.signals import compute_volume_profile

    # compute_volume_profile needs 2 bars of margin beyond its lookback.
    lookback = min(window, len(df) - 2)
    if lookback < 1:
        return []
    profile = compute_volume_profile(df, lookback)
    if not profile:
        return []

    edges = profile["bin_edges"]
    return [{"price": _num((edges[i] + edges[i + 1]) / 2), "volume": _num(vol)}
            for i, vol in enumerate(profile["bin_volumes"])]


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


@api_v1.route("/market/chart/<trade_id>", methods=["GET"])
@require_auth
def chart(trade_id: str):
    """Everything the SPA's interactive trade chart draws, in one request.

    One request rather than five because the panes must agree: the bars, the
    indicator series, the volume profile and the overlay are all slices of
    the SAME loaded frame at the SAME window, and five endpoints would let a
    retry or a race serve panes computed from frames a fetch apart.

    Both `_ohlcv_frame` and `_trade_for_levels` are imported INSIDE the view,
    exactly as `ohlcv` above does it. A module-level `from ... import` binds
    the original functions at import time, and tests (plus anything else
    patching `swingbot.admin.app`) would then be patching an attribute
    nothing reads. It also keeps this module free of admin imports at import
    time -- see the package docstring's note about the circular-import
    deadlock app.py documents.
    """
    from flask import request

    from swingbot import config
    from swingbot.admin.app import _ohlcv_frame, _trade_for_levels
    from swingbot.core.charts.chart_geometry import bar_epochs, overlay_geometry
    from swingbot.core.data import get_currency_symbol
    from swingbot.core.strategy_types import HORIZONS

    raw_window = request.args.get("window")
    if raw_window is None:
        window = DEFAULT_WINDOW
    else:
        try:
            window = int(raw_window)
        except (TypeError, ValueError):
            return error("invalid", f"window must be an integer, got {raw_window!r}", 400)
        # REJECTED, not clamped -- the opposite of `bars` on /market/ohlcv
        # above, and deliberately so. There, "more than the cap" sensibly
        # means "as much history as exists". Here `window` is what the chart
        # SHOWS: silently handing back 500 bars to a caller that asked for
        # 5000 gives it a chart it did not ask for, with nothing in the
        # response saying so.
        if not MIN_WINDOW <= window <= MAX_WINDOW:
            return error(
                "invalid",
                f"window must be between {MIN_WINDOW} and {MAX_WINDOW}, got {window}",
                400,
            )

    trade = _trade_for_levels(trade_id)
    if not trade:
        return error("not_found", f"No trade with id {trade_id!r}", 404)

    ticker = (trade.get("ticker") or "").upper()
    df = _ohlcv_frame(ticker)
    if df is None or not len(df):
        return error("not_found", f"No OHLCV data for {ticker!r}.", 404)

    # The scenario's OWN horizon dict, so every period and window below is
    # the one that actually confirmed the level. An unknown or missing
    # horizon_key falls back to {} rather than to a default horizon: the
    # geometry helpers each carry their own documented default, and picking
    # some other horizon's numbers here would draw a method the trade was
    # never confirmed by.
    horizon = HORIZONS.get(trade.get("horizon_key")) or {}
    is_bull = trade.get("direction") == "bullish"

    visible = df.tail(window)
    bars = [
        # `t` is an int epoch SECOND, not the "YYYY-MM-DD" string
        # /market/ohlcv returns. One time type across the whole payload: the
        # overlay shapes carry epochs, and lightweight-charts converts both
        # through the same timeToCoordinate -- mixing representations in one
        # chart is how a shape lands a year away from its candle. Built with
        # chart_geometry.bar_epochs so the bars and the overlay cannot
        # disagree about what instant a bar is.
        {"t": t, "o": round(float(r["Open"]), 4), "h": round(float(r["High"]), 4),
         "l": round(float(r["Low"]), 4), "c": round(float(r["Close"]), 4),
         "v": float(r["Volume"])}
        for t, (_idx, r) in zip(bar_epochs(visible), visible.iterrows())
    ]

    # ONE overlay per chart, target side preferred: it is the side the trade
    # is aiming at. A trade confirmed only on its stop still gets its method
    # drawn rather than nothing. `recent_len=window` makes a curve's points
    # line up 1:1 with `bars`.
    #
    # `trend_info` is deliberately left unset. generate_trade_chart() fits
    # the trendline pair once, before it decides its display window (the
    # window is then expanded to fit the line's own touches); re-fitting here
    # would be a second source of truth for the same line. A Trendline-only
    # source therefore yields no overlay here, which is the same "nothing
    # drawable" outcome as a candlestick-pattern-only source.
    overlay = None
    for side, key in (("target", "target_sources"), ("stop", "stop_sources")):
        overlay = overlay_geometry(df, side, trade.get(key) or [], horizon=horizon,
                                   recent_len=window, is_bull=is_bull)
        if overlay is not None:
            break

    payload = {
        "ohlcv": bars,
        # Computed over the full loaded frame, then sliced -- see `_series`.
        "indicators": _indicators(df, window),
        "volume_profile": _volume_profile(df, window),
        # Decision 10's names, not trade_levels()' tp1/tp2: these feed price
        # lines whose axis tags read "target 1", and `working_stop` (the live
        # breakeven/trail floor) has no equivalent there at all. A missing
        # level stays null and is never substituted with 0 -- a target line
        # at 0.0 rescales the whole price axis and reads as a real level.
        "levels": {
            "entry": _num(trade.get("entry")),
            "stop": _num(trade.get("stop_loss")),
            "target1": _num(trade.get("take_profit")),
            "target2": _num(trade.get("target2_price")),
            "working_stop": _num(trade.get("working_stop")),
        },
        # Passed through from chart_geometry unchanged, `source` included:
        # reshaping it here would be the second implementation the module
        # exists to prevent, and `source` is the method label the legend
        # prints.
        "overlay": overlay,
        "currency": get_currency_symbol(ticker, config.CURRENCY_SYMBOL),
    }
    return jsonify(_json_safe(payload))
