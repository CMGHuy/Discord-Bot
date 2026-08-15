"""GET /api/v1/market/chart/{ticker}.

Read-only. THE chart endpoint, singular: bars, indicator panes, the volume
profile, the plan lines and the confirming-method overlays in ONE request,
keyed by ticker with the trade as an optional `trade_id`.

It used to be two. `/market/ohlcv/{ticker}` served plain bars and
`/market/chart/{trade_id}` served everything else, which meant a chart of a
watchlist ticker could only be the thin one -- and that split propagated all
the way up into two Angular stores and two chart components that had to be
kept in visual agreement by hand. Making the trade optional collapsed all
six into one. `ohlcv_bars`/`trade_levels` in `app.py` are what the deleted
route shared with the Jinja UI; the Jinja UI is gone (Release B), so this
module now carries the only serialisation.

Every number here is produced by the same Python that draws the PNG the bot
posts to Discord -- `swingbot.core.indicators`,
`signals.compute_volume_profile`, `charts.chart_geometry.overlay_geometry`
and `charts.trendline_fit`. A browser-side reimplementation of "where does
the 61.8% retracement sit" or "what is the 20-EMA here" would be a guarantee
that the chart a user zooms into eventually disagrees with the image they
were alerted with, and neither would look wrong on its own.

`_ohlcv_frame` tries a live fetch and falls back to the backtest CSV cache,
so the chart still renders offline. That is one of the repo's TWO parallel
OHLCV caches (`data/backtest_cache/`, flat per-ticker dailies -- not
`market_data/`, which is timeframe-first and belongs to the edge engine).
Reusing the accessor is also how this endpoint avoids having to know that.
"""
from __future__ import annotations

import math

from flask import jsonify

from . import api_v1, error
from .auth import require_auth

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


def _is_trendline_confirmed(trade: dict | None) -> bool:
    """Whether `trade`'s chart would actually draw a trendline -- the single
    condition the backfill gate and the legend-note gate below both share, so
    a trade confirmed by (say) an EMA and a Fib level alone never gets a
    trendline fitted, stored, or captioned for it.

    Mirrors trade_chart.py's own gate in `generate_trade_chart` (its
    `need_target_trendline`/`need_stop_trendline` locals, just before it
    decides whether to fit `trend_info` at all): true when either side's
    picked confirming source is a Trendline, OR -- the same "nothing else to
    draw" fallback the PNG falls back to -- when the trade carries no source
    info on either side at all (every trade logged before source tracking
    existed draws a trendline as its only option, same as the PNG).
    """
    if not trade:
        return False
    from swingbot.core.charts.chart_geometry import _pick_primary_source

    target_primary = _pick_primary_source(trade.get("target_sources") or [])
    stop_primary = _pick_primary_source(trade.get("stop_sources") or [])
    if target_primary is None and stop_primary is None:
        return True
    return bool(
        (target_primary and target_primary.startswith("Trendline"))
        or (stop_primary and stop_primary.startswith("Trendline"))
    )


def _chart_trendline_fit(trade: dict, df, horizon: dict, is_bull: bool) -> dict | None:
    """The trade's stored trendline fit, backfilling it once if absent.

    Every trade logged before the fit was written at plan creation has none,
    and until it does the SPA draws no trendline for it at all. So it is
    fitted here on first read and written back: the cost is paid once per
    trade ever, and -- more importantly -- the line stops moving between two
    viewings of the same old chart.

    A write on a GET, deliberately. It is a cache fill: idempotent (the store
    refuses to overwrite an existing fit), and a failure to write means
    "fitted again next time", never a failed request. The chart is served
    from the in-memory fit either way.

    The fit arguments are the trade's OWN entry and its horizon's
    fib_lookback -- scanning/engine.py's arguments, not this endpoint's
    `window` and last close. A backfill taken with different arguments would
    be a different line from the one the trade's PNG already drew, which is
    the failure this consolidation exists to end.
    """
    import logging

    from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS
    from swingbot.core.charts.trendline_fit import TRENDLINE_FIT_KEY, fit_trendline
    from swingbot.core.performance import TradeLog

    fit = trade.get(TRENDLINE_FIT_KEY)
    if fit:
        return fit

    entry = _num(trade.get("entry"))
    if entry is None:
        return None
    try:
        fit = fit_trendline(
            df,
            lookback=int(horizon.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS)),
            current_price=float(entry),
            is_bull=is_bull,
        )
    except Exception:
        logging.getLogger(__name__).warning(
            "Trendline backfill fit failed for %s", trade.get("id"), exc_info=True)
        return None

    if fit:
        try:
            TradeLog().store_trendline_fit(trade.get("id"), fit)
        except Exception:
            logging.getLogger(__name__).warning(
                "Trendline backfill write failed for %s", trade.get("id"), exc_info=True)
    return fit


def _stored_trendline_note_lines(fit: dict, label: str) -> list:
    """The stored fit's own two endpoints, captioned with the DATES THEY
    CARRY -- never re-derived from `df.index`.

    `trade_chart.py`'s `_trendline_note_lines` reads its dates off
    `df.index[len(df) - window_bars]`/`df.index[-1]`, which is correct there
    because the fit and the render share one frame in one call. It is wrong
    here: this endpoint's `df` is TODAY's frame, but `fit`
    (`trade["trendline_fit"]`) can be months old -- `_chart_trendline_fit`
    exists precisely so the line stops moving between two viewings, and a
    date re-derived from today's `df` would silently claim the line ends
    today when it doesn't. The prices come out right either way (they're
    derived from slope/intercept, which are frame-independent) -- only the
    dates need the fit's own `points` (see charts/trendline_fit.py) instead.
    """
    from datetime import datetime

    from swingbot.core.charts.trade_chart import _fmt_note_date

    points = fit.get("points") or []
    if len(points) != 2:
        return []
    pts = sorted(
        ((float(p["price"]), datetime.fromtimestamp(int(p["t"]))) for p in points),
        key=lambda t: t[0],
    )
    lo_price, lo_date = pts[0]
    hi_price, hi_date = pts[1]
    return [
        f"{label}: 2 pts used",
        f"  low  {_fmt_note_date(lo_date)}  {lo_price:.2f}",
        f"  high {_fmt_note_date(hi_date)}  {hi_price:.2f}",
    ]


def _chart_notes(trade: dict, df, fit: dict, overlays: list, horizon: dict) -> list:
    """The legend's fit notes, from the helpers the PNG prints.

    Same functions, so the image and the browser cannot describe the same
    line with different dates or prices. A note is only produced for a method
    that HAS one -- a trendline names the two points its segment connects, a
    fib fan its 0%/100% anchors, and everything else draws without a note
    rather than with an empty one.

    `fit` is already None for a trade that is not trendline-confirmed (see
    `_is_trendline_confirmed` and its call site in `chart()`), so the
    trendline note below is gated for free -- it only ever fires for a trade
    whose chart actually draws the line it would be captioning.
    """
    from swingbot.core.charts.trade_chart import DEFAULT_TRENDLINE_LOOKBACK_DAYS, _fib_note_lines

    notes = []
    if fit and fit.get("points"):
        try:
            notes += _stored_trendline_note_lines(
                fit, f"Trendline ({int(fit.get('strength', 0))}x)")
        except Exception:
            pass

    for overlay in overlays:
        source = overlay.get("source") or ""
        if source.startswith("Fib") or source in ("Swing high", "Swing low"):
            try:
                notes += _fib_note_lines(
                    df, int(horizon.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS)),
                    source)
            except Exception:
                pass
    return notes


@api_v1.route("/market/chart/<ticker>", methods=["GET"])
@require_auth
def chart(ticker: str):
    """Everything the SPA's interactive chart draws, in one request.

    Keyed by TICKER, with the trade as an optional `trade_id` parameter. The
    subject of a chart is the instrument; a plan is an annotation on top of
    it. Keyed by trade instead, there was no way to chart a watchlist ticker
    at all, which is what forced the second, thinner chart component this
    consolidation deletes.

    No `trade_id` means no plan: `levels` is null and `overlays` is empty,
    and no trade is looked up at all. Falling back to "some trade on this
    ticker" would draw plan lines nobody asked for, and which one it picked
    would be invisible on screen.

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

    ticker = (ticker or "").upper()
    trade_id = request.args.get("trade_id")
    trade = None
    if trade_id:
        trade = _trade_for_levels(trade_id)
        if not trade:
            # An unresolvable id stays a 404 rather than degrading to a plain
            # chart. The request was "this trade's chart"; answering with a
            # complete-looking one without its lines is how someone reads a
            # chart believing the levels are simply not set.
            return error("not_found", f"No trade with id {trade_id!r}", 404)
        trade_ticker = (trade.get("ticker") or "").upper()
        if trade_ticker and trade_ticker != ticker:
            # The path names what is charted. Drawing a trade's levels over
            # another instrument's bars produces a chart that is wrong in a
            # way nothing on screen shows.
            return error(
                "invalid",
                f"Trade {trade_id!r} is on {trade_ticker!r}, not {ticker!r}",
                400,
            )

    df = _ohlcv_frame(ticker)
    if df is None or not len(df):
        return error("not_found", f"No OHLCV data for {ticker!r}.", 404)

    # The scenario's OWN horizon dict, so every period and window below is
    # the one that actually confirmed the level. An unknown or missing
    # horizon_key falls back to {} rather than to a default horizon: the
    # geometry helpers each carry their own documented default, and picking
    # some other horizon's numbers here would draw a method the trade was
    # never confirmed by.
    horizon = HORIZONS.get((trade or {}).get("horizon_key")) or {}
    is_bull = (trade or {}).get("direction") == "bullish"

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

    # BOTH sides, target first: the method that confirmed the target and the
    # one holding the stop are different methods, and one overlay could only
    # ever tell half of it. Target leads because it is the side the trade is
    # aiming at. `recent_len=window` makes a curve's points line up 1:1 with
    # `bars`.
    #
    # `trend_info` stays unset and `trend_fit` carries the line instead: the
    # fit is read off the trade, never computed here. A second fit at render
    # time is what let the browser and the PNG disagree about the same line;
    # see charts/trendline_fit.py.
    #
    # Gated on `_is_trendline_confirmed`: a trade whose chart draws no
    # trendline at all (an EMA/Fib/etc.-only confirmation) has nothing for a
    # fit to be drawn or captioned FROM, so fitting and storing one for it on
    # first view would be a wasted computation and a locked file rewrite for
    # a line that never reaches the page.
    fit = (
        _chart_trendline_fit(trade, df, horizon, is_bull)
        if trade and _is_trendline_confirmed(trade) else None
    )

    overlays = []
    for side, key in (("target", "target_sources"), ("stop", "stop_sources")):
        overlay = overlay_geometry(df, side, (trade or {}).get(key) or [],
                                   horizon=horizon, recent_len=window,
                                   is_bull=is_bull, trend_fit=fit)
        if overlay is not None:
            overlays.append(overlay)

    payload = {
        # Echoed back because the client asks by ticker and renders many
        # charts: a response that does not say what it is of cannot be
        # matched to its request once two are in flight.
        "ticker": ticker,
        "ohlcv": bars,
        # Computed over the full loaded frame, then sliced -- see `_series`.
        "indicators": _indicators(df, window),
        "volume_profile": _volume_profile(df, window),
        # Decision 10's names, not trade_levels()' tp1/tp2: these feed price
        # lines whose axis tags read "target 1", and `working_stop` (the live
        # breakeven/trail floor) has no equivalent there at all. A missing
        # level stays null and is never substituted with 0 -- a target line
        # at 0.0 rescales the whole price axis and reads as a real level.
        # Null without a trade -- no plan, no lines. Not an empty dict of
        # nulls: "there is no plan here" and "the plan has no target" are
        # different answers and the client draws them differently.
        "levels": None if trade is None else {
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
        "overlays": overlays,
        # What the PNG prints under its legend, from the same helpers -- the
        # dates and prices a line was fitted between. Empty without a trade:
        # there is no fit to explain.
        "notes": _chart_notes(trade, df, fit, overlays, horizon) if trade else [],
        "currency": get_currency_symbol(ticker, config.CURRENCY_SYMBOL),
    }
    return jsonify(_json_safe(payload))
