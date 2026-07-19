"""
Generates a candlestick chart annotated with the full scenario: entry
(= today's current price in this model), stop-loss, target 1 (the next
support/resistance), and -- when there is one -- target 2 (the stretch
target beyond it), each as a labeled horizontal line with shaded
risk/reward zones. Every price label is shown in the ticker's own
trading currency (USD for a NASDAQ/NYSE stock, EUR for a Euronext one,
etc. -- see data.get_currency_symbol), not a single hardcoded symbol
applied to everything.

The chart is zoomed to the last ~4 weeks of trading by default (not the
full lookback the underlying horizon uses for its indicators) -- this
makes the current price action big and legible instead of a tiny sliver
at the edge of a multi-month chart, which is what actually matters for
judging "does this key level look real right now". 4 weeks is a floor,
not a fixed size, though: if a diagonal trendline (see below) needs a
longer fit window to be shown in full, the visible window EXPANDS to
fit it -- a trendline cut off mid-line the moment it scrolls out of
frame would be actively misleading about how well-supported it is.
Horizontal level lines are still drawn at their correct prices
regardless of how far price has to travel to reach them; the y-axis is
explicitly expanded to fit all of them even if none of the visible
candles get close.

Confirmed-strategy overlay: rather than always drawing a generic
diagonal trendline regardless of what actually confirmed the trade, the
chart draws whichever REAL method(s) from levels.py's confluence system
produced target 1's and the stop's level -- an actual Fibonacci fan, the
actual unfilled FVG zone, the actual VWAP/EMA/Bollinger curve, the
actual Donchian/floor-pivot/rolling-S/R line, or (if that's genuinely
what confirmed it) the diagonal trendline -- one overlay for whichever
side of the scenario has a drawable source, in a fixed accent color per
side (target vs stop) so the chart stays a two-color read regardless of
which specific method gets picked. When a scenario is confirmed by
several independent methods at once (see confidence.py), the single
most visually distinctive one is drawn (see `chart_drawing._pick_primary_source`)
-- drawing every clustered source at once would just be noise. Purely
additive: if `target_sources`/`stop_sources` aren't passed, or nothing
in them is drawable, this falls back to the old plain trendline-only
behavior so older call sites keep working.

When the trendline IS the one drawn, it's shown with the actual swing
high/low pivots it was fit through marked as diamonds along the line --
a bare diagonal line doesn't make clear how well- or poorly-supported
it really is; seeing the touch points does.

When levels sit close together (a tight stop, or a target barely beyond
entry), their price labels would naturally land on top of each other and
become unreadable -- `chart_drawing._spread_labels` pushes them apart
vertically by a minimum gap while drawing a short leader line back to the
real price, so every value stays legible no matter how close the actual
levels are.

This module holds only the two top-level entry points
(generate_trade_chart, generate_all_strategy_charts) -- the theme/style
constants, small drawing/geometry helpers, the confirmed-strategy-overlay
dispatcher, and the left-side Volume Profile panel each live in their own
sibling module (chart_style.py, chart_drawing.py, chart_strategy_overlay.py,
chart_volume_profile.py) so this file stays focused on assembling one
chart end to end rather than also containing every low-level drawing
primitive it calls along the way. All five live together in this
core/charts/ subpackage since they're one cohesive rendering unit.
"""
import logging
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.offsetbox import AnnotationBbox, HPacker, TextArea
import mplfinance as mpf
import pandas as pd

from .. import levels
from ..indicators import macd as _compute_macd, rsi as _compute_rsi, keltner_channel as _compute_kc
from ..volatility import adx_trend_strength
from ..trendlines import strongest_trendline_pair

from .chart_style import (
    CHIP_BG, CURRENT_PRICE_COLOR, DEFAULT_LOOKBACK_DAYS,
    DEFAULT_TRENDLINE_LOOKBACK_DAYS, DISCLAIMER_TEXT, ENTRY_COLOR, KC_COLOR,
    MACD_LINE_COLOR, MIN_LABEL_GAP_FRAC, MUTED_TEXT_COLOR, PRO_STYLE,
    REWARD_BAND_ALPHA, RISK_BAND_ALPHA, RSI_LINE_COLOR, RUNNER_BAND_ALPHA,
    SIGNAL_LINE_COLOR, SPINE_COLOR, STOP_COLOR,
    STOP_STRATEGY_COLOR, TARGET2_COLOR, TARGET_COLOR, TARGET_STRATEGY_COLOR,
    TEXT_COLOR, TRENDLINE_RESISTANCE_COLOR, TRENDLINE_SUPPORT_COLOR,
    VOLUME_PROFILE_PANEL_GAP_FRAC, VOLUME_PROFILE_PANEL_WIDTH_FRAC,
    _label_bbox,
)
from .chart_drawing import _draw_trendline, _fib_anchor_points, _pick_primary_source, _spread_labels
from .chart_strategy_overlay import _draw_confirmed_strategy, _draw_confirmed_strategy_secondary
from .chart_volume_profile import _draw_volume_profile_panel

log = logging.getLogger("swing-bot.trade_chart")


def _fmt_note_date(d) -> str:
    try:
        return d.strftime("%Y-%m-%d")
    except Exception:
        return str(d)


def _trendline_note_lines(df: pd.DataFrame, window_bars: int, slope: float, intercept: float, label: str) -> list:
    """
    The 2 points a drawn trendline segment actually connects -- its own
    fit window's start and end bar, evaluated ON the fitted line itself
    (matching exactly what `_draw_trendline` renders, not a raw candle
    price) -- reported with real calendar dates instead of the chart's
    own window-relative bar index, and tagged by which one is the higher
    price ("high") and which is the lower ("low"): a trendline can slope
    either up or down, so "first in time" and "highest price" aren't
    always the same point.
    """
    idx_start = len(df) - window_bars
    idx_end = len(df) - 1
    y0 = slope * 0 + intercept
    y1 = slope * (window_bars - 1) + intercept
    pts = sorted([(y0, df.index[idx_start]), (y1, df.index[idx_end])], key=lambda t: t[0])
    lo_price, lo_date = pts[0]
    hi_price, hi_date = pts[1]
    return [
        f"{label}: 2 pts used",
        f"  low  {_fmt_note_date(lo_date)}  {lo_price:.2f}",
        f"  high {_fmt_note_date(hi_date)}  {hi_price:.2f}",
    ]


def _fib_note_lines(df: pd.DataFrame, lookback: int, label: str) -> list:
    """
    The 0% and 100% anchor points a Fibonacci retracement fan was
    actually measured between. `indicators.fibonacci_levels()` itself
    only returns the two swing PRICES, not which bar each one came from
    -- this re-derives the real dates from that same lookback window.
    """
    window = df.tail(min(lookback, len(df)))
    date_high = window["High"].idxmax()
    date_low = window["Low"].idxmin()
    swing_high = float(window["High"].max())
    swing_low = float(window["Low"].min())
    return [
        f"{label}: 0%/100% pts",
        f"  0%   {_fmt_note_date(date_high)}  {swing_high:.2f}",
        f"  100% {_fmt_note_date(date_low)}  {swing_low:.2f}",
    ]


def generate_trade_chart(
    ticker: str,
    df: pd.DataFrame,
    entry: float,
    stop_loss: float,
    take_profit: float,
    direction: str,
    strategy: str,
    horizon_label: str,
    out_dir: str,
    filename: str = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    currency_symbol: str = "€",
    target2: float = None,
    trendline_lookback: int = DEFAULT_TRENDLINE_LOOKBACK_DAYS,
    target_sources: list = None,
    stop_sources: list = None,
    horizon: dict = None,
    market_price: float = None,
    plan_v2=None,
) -> str:
    # Pick the single most informative confirming method per side (see
    # _pick_primary_source) -- this is what actually gets drawn instead
    # of a generic trendline. `horizon` is the scenario's own horizon
    # dict (EMA periods, VWAP window, fib lookback, ...) so whatever
    # gets drawn uses the exact same parameters that produced the level
    # in the first place; falls back to an empty dict (sane generic
    # defaults inside each drawer) if the caller didn't pass one.
    h = horizon or {}
    target_primary = _pick_primary_source(target_sources or [])
    stop_primary = _pick_primary_source(stop_sources or [])
    is_bull = direction == "bullish"

    # Entry is a PLANNED level (see trade_plan.py) -- it doesn't have to be
    # where price is trading right now; several strategies deliberately
    # suggest a pullback/retest entry instead of chasing an extended move.
    # market_price defaults to entry for callers that haven't been updated
    # to pass it (e.g. the !strategycharts diagnostic tool, which really
    # does mean "right now" for its entry) -- in that case the two are
    # identical and the chart collapses back to a single combined line/label,
    # same as before this parameter existed.
    if market_price is None:
        market_price = entry
    entry_is_market_price = (
        entry == 0 or abs(market_price - entry) / abs(entry) < 0.0005
    )

    # The diagonal trendline is the one overlay that needs its whole fit
    # window visible up front (showing it cut off mid-line would
    # misrepresent how well-supported it is), so it's still fit here,
    # using the FULL df, before the chart's display window is decided --
    # but ONLY if a trendline is actually what's being drawn for one of
    # the two sides; every other overlay just reads off the already-
    # windowed `recent` frame below and needs no such special handling.
    need_target_trendline = bool(target_primary) and target_primary.startswith("Trendline")
    need_stop_trendline = bool(stop_primary) and stop_primary.startswith("Trendline")
    trend_info = None
    if need_target_trendline or need_stop_trendline or (target_primary is None and stop_primary is None):
        # Also fit it as the fallback path (no drawable confirming
        # source on either side) so old behavior is preserved exactly.
        trend_info = strongest_trendline_pair(df, trendline_lookback, entry)
    trendline_window_bars = trend_info["window_bars"] if trend_info else 0

    # Same idea for a Fibonacci fan: if it's actually what's being drawn,
    # its 0%/100% anchor points (the real swing high/low the ratios were
    # measured from -- see chart_strategy_overlay's Fib block) need to be
    # inside the visible window too, or they'd be silently uncomputable to
    # place on-chart even though the ratio LINES themselves (flat, so
    # unaffected by window size) would still show up fine.
    def _is_fib(label):
        return bool(label) and (label.startswith("Fib") or label in ("Swing high", "Swing low"))

    fib_window_bars = 0
    if _is_fib(target_primary) or _is_fib(stop_primary):
        fib_lookback = h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS)
        anchors = _fib_anchor_points(df, fib_lookback)
        earliest_fib_bar = min(anchors["high_bar_abs"], anchors["low_bar_abs"])
        fib_window_bars = min(len(df) - earliest_fib_bar, len(df))

    effective_lookback_days = max(lookback_days, trendline_window_bars, fib_window_bars, 1)
    window_expanded = effective_lookback_days > lookback_days

    recent = df.tail(effective_lookback_days).copy()
    recent_len = len(recent)

    hlines_prices = [entry, stop_loss, take_profit]
    hlines_colors = [ENTRY_COLOR, STOP_COLOR, TARGET_COLOR]
    if target2 is not None:
        hlines_prices.append(target2)
        hlines_colors.append(TARGET2_COLOR)
    if not entry_is_market_price:
        hlines_prices.append(market_price)
        hlines_colors.append(CURRENT_PRICE_COLOR)

    hlines_cfg = dict(
        hlines=hlines_prices,
        colors=hlines_colors,
        linestyle="--",
        linewidths=1.4,
        alpha=0.9,
    )

    direction_label = "LONG (buy)" if is_bull else "SHORT (sell)"
    if window_expanded:
        _expand_reasons = []
        if trendline_window_bars > lookback_days:
            _expand_reasons.append("trendline")
        if fib_window_bars > lookback_days:
            _expand_reasons.append("Fibonacci anchors")
        _reason = " & ".join(_expand_reasons) if _expand_reasons else "overlay"
        window_note = f"last {effective_lookback_days} sessions, extended from {lookback_days} to fit the {_reason}"
    else:
        window_note = f"last {lookback_days} sessions"

    # ---------------------------------------------------------------
    # Indicator panels: MACD, RSI, Keltner Channel
    # Computed on the FULL df for accuracy (indicators need lookback
    # history), then sliced to the chart's visible window length.
    # ---------------------------------------------------------------
    addplots = []
    _rsi_current = None
    _macd_dir = None
    _adx_info = None

    try:
        # MACD (12,26,9) -- histogram bars + MACD line + signal line
        _m = _compute_macd(df["Close"], 12, 26, 9)
        mhist = _m["histogram"].iloc[-recent_len:].fillna(0).values
        mline = _m["macd"].iloc[-recent_len:].bfill().values
        msig  = _m["signal"].iloc[-recent_len:].bfill().values
        hist_colors = [TARGET_COLOR if float(v) >= 0 else STOP_COLOR for v in mhist]
        _macd_dir = "▲ rising" if float(mhist[-1]) > float(mhist[-2]) else "▼ falling"
        addplots += [
            mpf.make_addplot(mhist, panel=2, type="bar", color=hist_colors,
                             alpha=0.75, width=0.7),
            mpf.make_addplot(mline, panel=2, color=MACD_LINE_COLOR, secondary_y=False),
            mpf.make_addplot(msig,  panel=2, color=SIGNAL_LINE_COLOR, secondary_y=False),
        ]
    except Exception as exc:
        log.debug("MACD panel skipped: %s", exc)

    try:
        # RSI(14) -- single line, overbought/oversold reference added post-plot
        _r = _compute_rsi(df["Close"], 14)
        rsi_arr = _r.iloc[-recent_len:].fillna(50).values
        _rsi_current = round(float(_r.iloc[-1]), 1)
        addplots.append(mpf.make_addplot(rsi_arr, panel=3, color=RSI_LINE_COLOR))
    except Exception as exc:
        log.debug("RSI panel skipped: %s", exc)

    try:
        # Keltner Channel on the main price panel (faint cyan) -- gives
        # squeeze context even when it isn't the primary drawn strategy.
        _kc = _compute_kc(df)
        kc_up  = _kc["upper"].iloc[-recent_len:].bfill().values
        kc_low = _kc["lower"].iloc[-recent_len:].bfill().values
        addplots += [
            mpf.make_addplot(kc_up,  panel=0, color=KC_COLOR,
                             linestyle="--", alpha=0.55, secondary_y=False),
            mpf.make_addplot(kc_low, panel=0, color=KC_COLOR,
                             linestyle="--", alpha=0.55, secondary_y=False),
        ]
    except Exception as exc:
        log.debug("Keltner Channel overlay skipped: %s", exc)

    try:
        _adx_info = adx_trend_strength(df)
    except Exception:
        pass

    # Build compact stats subtitle (all indicators now computed).
    # Goes into the chart title so the stats live ABOVE the candles,
    # not overlapping them. Keeps the price panel clean.
    _t1_pct  = abs(take_profit - entry) / entry * 100 if entry else 0.0
    _sl_pct  = abs(entry - stop_loss)   / entry * 100 if entry else 0.0
    _rr      = round(_t1_pct / _sl_pct, 2) if _sl_pct else 0.0

    # Build colored stat tokens: (text, color) pairs for the subtitle row.
    # These are rendered AFTER mpf.plot() using offsetbox so each token
    # can have its own color (matplotlib title strings don't support mixed colors).
    _SEP = ("  |  ", MUTED_TEXT_COLOR)
    _stat_tokens = [
        (f"T1 {'+' if is_bull else '-'}{_t1_pct:.1f}%", TARGET_COLOR),
        _SEP,
        (f"SL {'-' if is_bull else '+'}{_sl_pct:.1f}%", STOP_COLOR),
        _SEP,
        (f"R:R {_rr:.2f}", CURRENT_PRICE_COLOR),
    ]
    if target2 is not None:
        _t2_pct = abs(target2 - entry) / entry * 100 if entry else 0.0
        _stat_tokens += [_SEP, (f"T2 {'+' if is_bull else '-'}{_t2_pct:.1f}%", TARGET2_COLOR)]
    if _rsi_current is not None:
        _rtag = " OB" if _rsi_current >= 70 else (" OS" if _rsi_current <= 30 else "")
        _rsi_clr = STOP_COLOR if _rsi_current >= 70 else (TARGET_COLOR if _rsi_current <= 30 else RSI_LINE_COLOR)
        _stat_tokens += [_SEP, (f"RSI {_rsi_current:.0f}{_rtag}", _rsi_clr)]
    if _adx_info and _adx_info.get("adx") is not None:
        _atag = "strong" if _adx_info["strong"] else ("trend" if _adx_info["trending"] else "range")
        _adx_clr = TARGET_COLOR if _adx_info["strong"] else (SIGNAL_LINE_COLOR if _adx_info["trending"] else MUTED_TEXT_COLOR)
        _stat_tokens += [_SEP, (f"ADX {_adx_info['adx']:.0f} {_atag}", _adx_clr)]
    if _macd_dir:
        _macd_clr = TARGET_COLOR if "bull" in _macd_dir.lower() else (STOP_COLOR if "bear" in _macd_dir.lower() else MACD_LINE_COLOR)
        _stat_tokens += [_SEP, (f"MACD {_macd_dir}", _macd_clr)]

    # Single-line title (first row only — stats are drawn separately with color)
    title = (
        f"{ticker} — {strategy} ({horizon_label}) — {direction_label}"
        f"  [{currency_symbol.strip()}, {window_note}]"
    )

    # Panel ratios: price (4) : volume (1) : MACD (1.4) : RSI (1.1)
    # addplots are dicts returned by mpf.make_addplot -- use .get(), not getattr.
    has_macd = any(ap.get("panel") == 2 for ap in addplots)
    has_rsi  = any(ap.get("panel") == 3 for ap in addplots)
    if has_macd and has_rsi:
        panel_ratios = (4, 0.9, 1.5, 1.2)
        fig_height = 11.0
    elif has_macd or has_rsi:
        panel_ratios = (4, 0.9, 1.5)
        fig_height = 9.5
    else:
        panel_ratios = (4, 0.9)
        fig_height = 7.0

    _plot_kwargs = dict(
        type="candle",
        style=PRO_STYLE,
        title=dict(title=title, color=TEXT_COLOR, fontsize=12.5, fontweight="bold"),
        volume=True,
        hlines=hlines_cfg,
        returnfig=True,
        # Wider than a plain candlestick chart would need on its own --
        # the left-side volume profile panel added after mpf.plot() below
        # carves its space out of this width via fig.subplots_adjust(left=...),
        # so the extra inches keep the candlestick area from feeling cramped.
        figsize=(13.5, fig_height),
        panel_ratios=panel_ratios,
        update_width_config=dict(candle_linewidth=1.0, candle_width=0.62, volume_width=0.62),
    )
    if addplots:
        _plot_kwargs["addplot"] = addplots

    fig, axes = mpf.plot(recent, **_plot_kwargs)
    try:
        ax = axes[0]

        # Remove the auto-generated mplfinance legend from the main price panel
        # (candlestick + KC + addplot entries create a cluttered legend that
        # covers key levels -- all label context comes from our own annotations).
        if ax.get_legend():
            ax.get_legend().remove()

        # ---------------------------------------------------------------
        # Overlay legend — top-right of the price panel, one row per line type
        # so the user can tell apart the dashed horizontal levels, the KC bands,
        # and the strategy curves at a glance.
        # ---------------------------------------------------------------
        try:
            import matplotlib.patches as mpatches
            import matplotlib.lines as mlines
            _legend_handles = []
            _legend_handles.append(mlines.Line2D([], [], color=ENTRY_COLOR, linewidth=1.4,
                                                 linestyle="--", label="Entry"))
            _legend_handles.append(mlines.Line2D([], [], color=TARGET_COLOR, linewidth=1.4,
                                                 linestyle="--", label="Target 1"))
            _legend_handles.append(mlines.Line2D([], [], color=STOP_COLOR, linewidth=1.4,
                                                 linestyle="--", label="Stop Loss"))
            if target2 is not None:
                _legend_handles.append(mlines.Line2D([], [], color=TARGET2_COLOR, linewidth=1.4,
                                                     linestyle="--", label="Target 2"))
            # Keltner Channel bands (only if plotted)
            if any(ap.get("panel") == 0 and ap.get("color") == KC_COLOR for ap in addplots):
                _legend_handles.append(mlines.Line2D([], [], color=KC_COLOR, linewidth=1.2,
                                                     linestyle="--", label="KC (EMA20 ±1.5×ATR)"))
            # Strategy overlays (primary confirming method per side)
            if target_primary and not target_primary.startswith("Trendline"):
                _legend_handles.append(mlines.Line2D([], [], color=TARGET_STRATEGY_COLOR, linewidth=1.5,
                                                     linestyle="-", label=f"Target: {target_primary}"))
            if stop_primary and not stop_primary.startswith("Trendline"):
                _legend_handles.append(mlines.Line2D([], [], color=STOP_STRATEGY_COLOR, linewidth=1.5,
                                                     linestyle="-", label=f"Stop: {stop_primary}"))
            if _legend_handles:
                _leg = ax.legend(
                    handles=_legend_handles,
                    loc="upper left",
                    fontsize=7,
                    framealpha=0.88,
                    facecolor=CHIP_BG,
                    edgecolor=SPINE_COLOR,
                    labelcolor=TEXT_COLOR,
                    handlelength=2.2,
                    borderpad=0.6,
                    labelspacing=0.35,
                )
                ax.add_artist(_leg)
        except Exception as _le:
            log.debug("Overlay legend failed: %s", _le)

        # ---------------------------------------------------------------
        # Colored stats subtitle row — placed just below the chart title
        # using offsetbox so each token (T1/SL/R:R/RSI/ADX/MACD) renders
        # in its own semantically appropriate color.
        # ---------------------------------------------------------------
        try:
            _text_areas = []
            for _tok_text, _tok_color in _stat_tokens:
                _text_areas.append(
                    TextArea(
                        _tok_text,
                        textprops=dict(
                            color=_tok_color,
                            fontsize=8.5,
                            fontweight="bold",
                            fontfamily="monospace",
                        ),
                    )
                )
            _hbox = HPacker(children=_text_areas, pad=2, sep=0)
            _ab = AnnotationBbox(
                _hbox,
                xy=(0.5, 1.0),
                xycoords="axes fraction",
                xybox=(0, 6),
                boxcoords="offset points",
                frameon=True,
                box_alignment=(0.5, 0.0),
                bboxprops=dict(
                    facecolor=CHIP_BG, edgecolor=SPINE_COLOR,
                    linewidth=0.7, alpha=0.94,
                    boxstyle="round,pad=0.35",
                ),
            )
            ax.add_artist(_ab)
        except Exception as _e:
            log.debug("Stats subtitle rendering failed: %s", _e)

        # Give sub-panels breathing room so tick labels, titles and dashed
        # reference lines don't bleed into adjacent panels.
        # hspace=0.55 ≈ 55% of average panel height as padding between panels;
        # the extra breathing room prevents the MACD panel title from bleeding
        # into the bottom of the volume bars above it at typical 150 dpi output.
        # top=0.91 reserves space above axes[0] for the two-line title.
        # left=... reserves a strip on the left of the whole figure for the
        # volume profile panel added further below (_draw_volume_profile_panel) --
        # done here (before that panel exists) since subplots_adjust reflows
        # every mplfinance-created panel that's already on the figure.
        try:
            fig.subplots_adjust(
                hspace=0.55, top=0.91, bottom=0.05,
                left=VOLUME_PROFILE_PANEL_WIDTH_FRAC + VOLUME_PROFILE_PANEL_GAP_FRAC + 0.02,
            )
        except Exception:
            pass

        # ---------------------------------------------------------------
        # Sub-panel annotations: MACD and RSI get proper titles, y-axis
        # value labels, reference-line labels, and a current-value callout
        # at the right edge so the reader knows what each panel shows.
        #
        # Axis index (mplfinance layout):
        #   axes[0] = price, axes[1] = price twin
        #   axes[2] = volume, axes[3] = volume twin
        #   axes[4] = MACD (if present), axes[5] = MACD twin
        #   axes[6] = RSI  (if present), axes[7] = RSI twin
        #   (if no MACD: RSI is at axes[4], axes[5])
        # ---------------------------------------------------------------
        try:
            if has_macd and len(axes) > 4:
                ax_macd = axes[4]

                # Zero line with label
                ax_macd.axhline(0, color=MUTED_TEXT_COLOR, linewidth=0.9, linestyle="--",
                                alpha=0.6, zorder=1)
                ax_macd.text(0.005, 0.5, "0", transform=ax_macd.transAxes,
                             fontsize=6.5, color=MUTED_TEXT_COLOR, va="center", ha="left", alpha=0.9)

                # Y-axis tick formatting
                ax_macd.tick_params(axis="y", labelsize=7, labelcolor=MUTED_TEXT_COLOR, length=3)
                ax_macd.tick_params(axis="x", labelsize=6.5, labelcolor=MUTED_TEXT_COLOR, length=2)

                # Panel title in top-left corner
                macd_last = float(mline[-1]) if len(mline) else 0
                sig_last  = float(msig[-1])  if len(msig)  else 0
                hist_last = float(mhist[-1]) if len(mhist) else 0
                cross_str = ("▲ bullish cross" if macd_last > sig_last else "▼ bearish cross")
                hist_clr = TARGET_COLOR if hist_last >= 0 else STOP_COLOR
                ax_macd.text(0.002, 0.97,
                             f"MACD (12, 26, 9)   MACD {macd_last:+.3f}   Signal {sig_last:+.3f}   Hist {hist_last:+.3f}   {cross_str}",
                             transform=ax_macd.transAxes, fontsize=7, fontweight="bold",
                             va="top", ha="left", color=TEXT_COLOR,
                             bbox=dict(boxstyle="round,pad=0.2", facecolor=CHIP_BG, edgecolor=SPINE_COLOR, alpha=0.9))

                # Current MACD & signal values at right edge
                x_right = len(recent) - 1
                ax_macd.annotate(f"{macd_last:+.3f}", xy=(x_right, macd_last),
                                 xytext=(x_right + 1, macd_last),
                                 fontsize=6, color=MACD_LINE_COLOR, va="center", ha="left", clip_on=False)
                ax_macd.annotate(f"{sig_last:+.3f}", xy=(x_right, sig_last),
                                 xytext=(x_right + 1, sig_last),
                                 fontsize=6, color=SIGNAL_LINE_COLOR, va="center", ha="left", clip_on=False)

                # Legend: color swatch labels — placed at lower-right to avoid
                # covering the zero-line and MACD panel title at upper-left.
                ax_macd.plot([], [], color=MACD_LINE_COLOR, label="MACD", linewidth=1.2)
                ax_macd.plot([], [], color=SIGNAL_LINE_COLOR, label="Signal", linewidth=1.2)
                ax_macd.plot([], [], color=hist_clr, linewidth=4, alpha=0.75, label="Hist")
                ax_macd.legend(
                    loc="lower right", fontsize=6, framealpha=0.9,
                    facecolor=CHIP_BG, edgecolor=SPINE_COLOR, labelcolor=TEXT_COLOR,
                    ncol=3, handlelength=1.2, borderpad=0.4, labelspacing=0.2,
                )
        except Exception as _e:
            log.debug("MACD panel annotation failed: %s", _e)

        try:
            rsi_ax_idx = 6 if has_macd else 4
            if has_rsi and len(axes) > rsi_ax_idx:
                ax_rsi = axes[rsi_ax_idx]

                # Overbought / oversold bands
                ax_rsi.axhspan(70, 100, color=STOP_COLOR,   alpha=0.10, zorder=0)
                ax_rsi.axhspan(0,  30,  color=TARGET_COLOR, alpha=0.10, zorder=0)
                ax_rsi.axhline(70, color=STOP_COLOR,   linewidth=0.9, linestyle="--", alpha=0.65)
                ax_rsi.axhline(30, color=TARGET_COLOR, linewidth=0.9, linestyle="--", alpha=0.65)
                ax_rsi.axhline(50, color=MUTED_TEXT_COLOR, linewidth=0.6, linestyle=":",  alpha=0.5)

                # Reference-line labels on the right side
                for level, label, clr in [(70, "OB 70", STOP_COLOR), (50, "50", MUTED_TEXT_COLOR), (30, "OS 30", TARGET_COLOR)]:
                    ax_rsi.text(0.998, level, label, transform=ax_rsi.get_yaxis_transform(),
                                fontsize=6.5, color=clr, va="center", ha="right", alpha=0.9)

                ax_rsi.set_ylim(0, 100)
                ax_rsi.set_yticks([0, 30, 50, 70, 100])
                ax_rsi.tick_params(axis="y", labelsize=7, labelcolor=MUTED_TEXT_COLOR, length=3)
                ax_rsi.tick_params(axis="x", labelsize=6.5, labelcolor=MUTED_TEXT_COLOR, length=2)

                # Panel title
                rsi_val = _rsi_current if _rsi_current is not None else float(rsi_arr[-1])
                rsi_tag = "Overbought" if rsi_val >= 70 else ("Oversold" if rsi_val <= 30 else "Neutral")
                rsi_clr = STOP_COLOR if rsi_val >= 70 else (TARGET_COLOR if rsi_val <= 30 else RSI_LINE_COLOR)
                ax_rsi.text(0.002, 0.97,
                            f"RSI (14)   Current: {rsi_val:.1f}   {rsi_tag}",
                            transform=ax_rsi.transAxes, fontsize=7, fontweight="bold",
                            va="top", ha="left", color=TEXT_COLOR,
                            bbox=dict(boxstyle="round,pad=0.2", facecolor=CHIP_BG, edgecolor=SPINE_COLOR, alpha=0.9))

                # Current RSI value at right edge
                x_right = len(recent) - 1
                ax_rsi.annotate(f"{rsi_val:.1f}", xy=(x_right, rsi_val),
                                xytext=(x_right + 1, rsi_val),
                                fontsize=7, color=rsi_clr, fontweight="bold",
                                va="center", ha="left", clip_on=False)
        except Exception as _e:
            log.debug("RSI panel annotation failed: %s", _e)

        # Keltner Channel label on the main price panel -- bottom-RIGHT
        # corner, deliberately apart from the "confirmed by" annotation
        # that lives at bottom-left, so the two never collide.
        try:
            if any(ap.get("panel") == 0 and ap.get("color") == KC_COLOR for ap in addplots):
                ax.text(0.997, 0.02, "KC (EMA20 ± 1.5×ATR10)",
                        transform=ax.transAxes, fontsize=6.5, color=KC_COLOR,
                        va="bottom", ha="right", alpha=0.9,
                        bbox=_label_bbox(KC_COLOR, alpha=0.7))
        except Exception:
            pass

        # ---------------------------------------------------------------

        # Explicitly fit the y-axis to the visible candles, every level line,
        # AND the trendline's own endpoints -- with only ~4 weeks of candles
        # shown (or the expanded window, if a trendline needed more), a
        # target/stop/trendline endpoint can easily sit outside the visible
        # candle range, and all of them need to be fully on-screen with room
        # for their labels.
        trendline_endpoints = []
        if trend_info:
            for side_key in ("support", "resistance"):
                side = trend_info.get(side_key)
                if side:
                    y0 = side["slope"] * 0 + side["intercept"]
                    y1 = side["slope"] * (trendline_window_bars - 1) + side["intercept"]
                    trendline_endpoints.extend([y0, y1])

        all_prices = list(recent["High"]) + list(recent["Low"]) + hlines_prices + trendline_endpoints
        lo, hi = min(all_prices), max(all_prices)
        pad = (hi - lo) * 0.12 if hi > lo else max(hi * 0.02, 0.5)

        # Whether the reference-point Note (below) will actually be shown --
        # if so, reserve extra headroom above the highest price so the Note's
        # own top-right corner spot doesn't land at the same height as
        # whichever price label (often Target 1) ends up sitting at/near the
        # top of the visible range, which would otherwise draw the two right
        # on top of each other.
        note_will_show = bool(
            (target_primary is None and stop_primary is None and trend_info) or
            (target_primary and (target_primary.startswith("Trendline") or target_primary.startswith("Fib")
                                  or target_primary in ("Swing high", "Swing low"))) or
            (stop_primary and (stop_primary.startswith("Trendline") or stop_primary.startswith("Fib")
                                or stop_primary in ("Swing high", "Swing low")))
        )
        top_pad = pad * 1.9 if note_will_show else pad
        ax.set_ylim(lo - pad, hi + top_pad)
        ylim = ax.get_ylim()

        # Off-candle label margin columns, computed here -- BEFORE the
        # confirming-strategy/trendline overlays are drawn below -- so
        # their own labels can be placed in a dedicated column away from
        # the candles too, not just the entry/stop/target labels further
        # out (unchanged, still `label_x`). Two separate columns, nearer
        # (strategy/trendline) and farther (entry/stop/target), so the two
        # groups of labels don't end up colliding with EACH OTHER either.
        x_right = len(recent) - 1
        extra_width = max(6, len(recent) * 1.1)
        label_x = x_right + extra_width * 0.45
        strategy_label_x = x_right + extra_width * 0.18
        _strategy_label_occupied = []
        _strategy_min_gap = (ylim[1] - ylim[0]) * MIN_LABEL_GAP_FRAC

        # The scenario's target side is resistance for a bullish setup,
        # support for a bearish one; the stop side is the opposite -- same
        # convention levels.py's build_scenarios() uses.
        target_side = "resistance" if is_bull else "support"
        stop_side = "support" if is_bull else "resistance"

        def _draw_side_trendline(side_key: str, overlay_color: str, label_suffix: str):
            if not trend_info or not trend_info.get(side_key):
                return
            info = trend_info[side_key]
            # Touches come straight from trendlines.strongest_trendline_pair()
            # now -- the SAME pivots that earned the line its "Nx touch"
            # score, already converted into this window's coordinates (and
            # trendline_window_bars was expanded, if needed, to make sure
            # every one of them actually falls inside it). Previously this
            # recomputed touches independently at chart-render time via
            # _trendline_touch_points(), using a different pivot threshold
            # (the horizon's max_risk_pct instead of trendlines.py's own
            # PIVOT_THRESHOLD_PCT/TOUCH_TOLERANCE_PCT) and restricted to
            # whatever the (unexpanded) window happened to already cover --
            # so the label could claim "6x touch" while only 2-3 diamonds
            # were ever actually drawable. Using the real detection-time
            # touches directly makes the diamonds always match the label.
            touches = info.get("touches", [])
            _draw_trendline(ax, recent_len, trendline_window_bars, info["slope"], info["intercept"],
                             overlay_color, f"Trendline ({info['strength']}x){label_suffix}", touch_points=touches,
                             label_x=strategy_label_x, occupied=_strategy_label_occupied, min_gap=_strategy_min_gap)

        if target_primary is None and stop_primary is None:
            # No confirming-source info was passed in at all (older call
            # site, or a caller that just wants the plain snapshot) -- fall
            # back to the original behavior: both trendline sides, if any,
            # in their fixed support/resistance colors.
            _draw_side_trendline("support", TRENDLINE_SUPPORT_COLOR, "")
            _draw_side_trendline("resistance", TRENDLINE_RESISTANCE_COLOR, "")
        else:
            # Draw the primary confirming method for each side at full opacity,
            # then draw up to 1 secondary source per side at reduced opacity
            # (no label) -- shows multiple convergences without clutter.
            if target_primary and target_primary.startswith("Trendline"):
                _draw_side_trendline(target_side, TARGET_STRATEGY_COLOR, " (target)")
            elif target_primary:
                _draw_confirmed_strategy(ax, df, recent_len, h, target_primary, TARGET_STRATEGY_COLOR,
                                          label_x=strategy_label_x, occupied=_strategy_label_occupied,
                                          min_gap=_strategy_min_gap)

            # Secondary target sources (dimmed, no label)
            for sec_src in (target_sources or [])[1:3]:  # at most 2 secondaries
                if sec_src != target_primary and not sec_src.startswith("Trendline"):
                    _draw_confirmed_strategy_secondary(ax, df, recent_len, h, sec_src, TARGET_STRATEGY_COLOR)

            if stop_primary and stop_primary.startswith("Trendline"):
                _draw_side_trendline(stop_side, STOP_STRATEGY_COLOR, " (stop)")
            elif stop_primary:
                _draw_confirmed_strategy(ax, df, recent_len, h, stop_primary, STOP_STRATEGY_COLOR,
                                          label_x=strategy_label_x, occupied=_strategy_label_occupied,
                                          min_gap=_strategy_min_gap)

            # Secondary stop sources (dimmed, no label)
            for sec_src in (stop_sources or [])[1:2]:
                if sec_src != stop_primary and not sec_src.startswith("Trendline"):
                    _draw_confirmed_strategy_secondary(ax, df, recent_len, h, sec_src, STOP_STRATEGY_COLOR)

        # ---------------------------------------------------------------
        # Reference-point Note -- top-right corner of the price panel.
        # Whenever a trendline or Fibonacci fan is the actual method
        # drawn for target/stop (or, in the plain fallback with no
        # confirming-source info at all, either trendline side), spells
        # out the literal points it was measured from -- real price AND
        # real calendar date -- as plain text rather than more on-chart
        # drawing: a reference "clue" the user can read, not clutter.
        # ---------------------------------------------------------------
        note_lines = []
        try:
            if target_primary is None and stop_primary is None:
                if trend_info and trend_info.get("support"):
                    s = trend_info["support"]
                    note_lines += _trendline_note_lines(df, trendline_window_bars, s["slope"], s["intercept"],
                                                         "Trendline (support)")
                if trend_info and trend_info.get("resistance"):
                    r = trend_info["resistance"]
                    note_lines += _trendline_note_lines(df, trendline_window_bars, r["slope"], r["intercept"],
                                                         "Trendline (resistance)")
            else:
                if target_primary and target_primary.startswith("Trendline") and trend_info and trend_info.get(target_side):
                    t = trend_info[target_side]
                    note_lines += _trendline_note_lines(df, trendline_window_bars, t["slope"], t["intercept"],
                                                         "Trendline (target)")
                if stop_primary and stop_primary.startswith("Trendline") and trend_info and trend_info.get(stop_side):
                    t = trend_info[stop_side]
                    note_lines += _trendline_note_lines(df, trendline_window_bars, t["slope"], t["intercept"],
                                                         "Trendline (stop)")

                fib_sides = []
                if target_primary and (target_primary.startswith("Fib") or target_primary in ("Swing high", "Swing low")):
                    fib_sides.append("target")
                if stop_primary and (stop_primary.startswith("Fib") or stop_primary in ("Swing high", "Swing low")):
                    fib_sides.append("stop")
                if fib_sides:
                    note_lines += _fib_note_lines(df, h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS),
                                                   "Fib (" + "/".join(fib_sides) + ")")
        except Exception as _ne:
            log.debug("Reference-point note failed: %s", _ne)

        if note_lines:
            ax.text(
                0.997, 0.985, "\n".join(note_lines), transform=ax.transAxes,
                fontsize=6.6, color=TEXT_COLOR, va="top", ha="right", zorder=8,
                fontfamily="monospace", linespacing=1.5,
                bbox=dict(boxstyle="round,pad=0.35", facecolor=CHIP_BG, edgecolor=SPINE_COLOR, alpha=0.92),
            )

        # Shade the reward zone (entry -> target 1) and risk zone (entry -> stop-loss).
        # Target 2, if present, gets a lighter shade further out -- the "if it
        # keeps going" stretch scenario, not the primary plan.
        reward_alpha = REWARD_BAND_ALPHA
        risk_alpha = RISK_BAND_ALPHA
        runner_alpha = RUNNER_BAND_ALPHA if plan_v2 is not None else 0.05
        ax.axhspan(min(entry, take_profit), max(entry, take_profit), color=TARGET_COLOR, alpha=reward_alpha, zorder=0)
        ax.axhspan(min(entry, stop_loss), max(entry, stop_loss), color=STOP_COLOR, alpha=risk_alpha, zorder=0)
        if target2 is not None:
            ax.axhspan(min(take_profit, target2), max(take_profit, target2), color=TARGET2_COLOR, alpha=runner_alpha, zorder=0)

        # Entry is a planned level and doesn't have to be where price is
        # trading right now (see trade_plan.py -- several strategies suggest a
        # pullback/retest entry rather than chasing an extended move). Show a
        # single combined label when they're the same price (avoids two
        # always-overlapping marks for the strategies/tools where entry IS
        # simply "now"); show both, separately, when they differ.
        raw_labels = [
            (entry, ENTRY_COLOR, "Entry / current price" if entry_is_market_price else "Entry (plan)"),
            (stop_loss, STOP_COLOR, "Stop"),
            (take_profit, TARGET_COLOR, "Target 1"),
        ]
        if not entry_is_market_price:
            raw_labels.append((market_price, CURRENT_PRICE_COLOR, "Current price"))
        if target2 is not None:
            raw_labels.append((target2, TARGET2_COLOR, "Target 2"))
        spread = _spread_labels(raw_labels, ylim)

        for price, label_y, color, label in spread:
            if abs(label_y - price) > 1e-9:
                # Leader line back to the real price when the label had to move.
                ax.plot([x_right, label_x], [price, label_y], color=color, linewidth=0.9, alpha=0.55,
                         linestyle=":", zorder=5, solid_capstyle="round")
            ax.text(
                label_x, label_y, f" {label} {currency_symbol}{price:.2f}",
                color="white", va="center", ha="left", fontsize=9, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", facecolor=color, edgecolor="none", alpha=0.9),
                       zorder=7,
            )

        ax.set_xlim(ax.get_xlim()[0], label_x + extra_width * 0.55)

        # v2 plan overlays (Tasks 81-82): trigger line for stop-entry plans,
        # TP1/TP2 zones, and (once PARTIAL) the live runner trail.
        if plan_v2 is not None:
            # Corner tag: charts get shared/saved detached from their embed
            # (which carries the same marker), so the image itself says it
            # was priced by the v2 plan engine. Drawn ABOVE the axes on the
            # stat-chip row -- inside the panel every corner is taken
            # (overlay legend upper-left, note block upper-right, KC label
            # lower-right, confirmed-by lower-left).
            ax.text(0.0, 1.012, "v2", transform=ax.transAxes,
                    va="bottom", ha="left", fontsize=8.5, fontweight="bold",
                    color="white",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor=CHIP_BG,
                              edgecolor=SPINE_COLOR, linewidth=0.7, alpha=0.94),
                    zorder=8)
            entry_lvl = plan_v2.entry_price or plan_v2.trigger_price
            if plan_v2.entry_type == "stop_entry" and plan_v2.status == "PENDING":
                trigger_word = "BUY STOP" if plan_v2.direction == "bullish" else "SELL STOP"
                ax.annotate(
                    trigger_word, xy=(x_right, plan_v2.trigger_price), xytext=(x_right - 4, plan_v2.trigger_price),
                    color=ENTRY_COLOR, fontsize=8, fontweight="bold", ha="right", va="center", zorder=9,
                    arrowprops=dict(arrowstyle="->", color=ENTRY_COLOR, lw=1.3),
                    bbox=dict(boxstyle="round,pad=0.2", facecolor=CHIP_BG, edgecolor=ENTRY_COLOR, alpha=0.85),
                )
            ax.axhline(plan_v2.tp1, linewidth=1.0, color=TARGET_COLOR)
            ax.axhspan(min(entry_lvl, plan_v2.tp1), max(entry_lvl, plan_v2.tp1),
                       alpha=0.08, color=TARGET_COLOR)          # leg-1 reward zone
            if plan_v2.tp2 is not None:
                ax.axhline(plan_v2.tp2, linestyle=":", linewidth=1.0,
                           color=TARGET_COLOR)
                ax.axhspan(min(plan_v2.tp1, plan_v2.tp2),
                           max(plan_v2.tp1, plan_v2.tp2),
                           alpha=0.05, color=TARGET_COLOR)      # runner zone
            if plan_v2.status == "PARTIAL":
                # working trail level (already ratcheted by the manager)
                if plan_v2.working_stop is not None:
                    ax.axhline(plan_v2.working_stop, linestyle=":", linewidth=1.4,
                               color=CURRENT_PRICE_COLOR)
                    ax.annotate("trail", xy=(0.99, plan_v2.working_stop),
                                xycoords=("axes fraction", "data"), ha="right",
                                va="bottom", fontsize=8, color=CURRENT_PRICE_COLOR)
                ax.annotate("TP1 banked ✓", xy=(0.01, plan_v2.tp1),
                            xycoords=("axes fraction", "data"), ha="left",
                            va="bottom", fontsize=8, color=TARGET_COLOR)

            # Status watermark: large, faint text bottom-right of the price
            # panel so the chart still communicates plan lifecycle state
            # even when saved/shared detached from its Discord embed.
            status_text = getattr(plan_v2, "status", None)
            if status_text:
                ax.text(
                    0.98, 0.04, status_text, transform=ax.transAxes, fontsize=20, fontweight="bold",
                    color=MUTED_TEXT_COLOR, alpha=0.5, ha="right", va="bottom", zorder=1,
                )

        # Confirmed-by annotation: small note at bottom-left of the price panel.
        # Kept separate from the title stats so the title stays one clean line.
        conf_parts = []
        if target_primary:
            n_extra = len([s for s in (target_sources or []) if s != target_primary])
            conf_parts.append(f"Target: {target_primary}" + (f" +{n_extra}" if n_extra else ""))
        if stop_primary:
            conf_parts.append(f"Stop: {stop_primary}")
        if conf_parts:
            ax.text(
                0.002, 0.015, "  |  ".join(conf_parts),
                transform=ax.transAxes, va="bottom", ha="left", fontsize=7.5,
                color=MUTED_TEXT_COLOR, alpha=0.95, zorder=7,
                bbox=dict(boxstyle="round,pad=0.2", facecolor=CHIP_BG, edgecolor=SPINE_COLOR, alpha=0.85),
            )

        # Volume Profile panel -- drawn last, immediately before saving, so
        # it inherits the price panel's FINAL y-axis (via sharey), after
        # every set_ylim() adjustment above for labels/trendline endpoints
        # has already happened. Passing that same final `ylim` as
        # `price_range` forces the profile's buckets to span the exact
        # same range the panel is about to be drawn across -- otherwise
        # the buckets only cover the recent lookback window's own (often
        # much narrower) High/Low extremes, leaving the rest of the
        # panel's height with no bucket, and so no bar, at all.
        try:
            _draw_volume_profile_panel(fig, ax, df, h.get("sr_lookback", 20), entry_price=entry, price_range=ylim)
        except Exception as exc:
            log.debug("Volume Profile panel skipped: %s", exc)

        # Legal/liability fine print -- deliberately the very last thing drawn,
        # below every panel (price, volume, MACD/RSI when present), in figure
        # coordinates (not tied to any one axes) so it always sits at the true
        # bottom of the image regardless of how many indicator panels this
        # particular chart has. Placed slightly below y=0 so bbox_inches="tight"
        # below expands the saved image to include it as its own line rather
        # than overlapping the lowest panel's x-axis tick labels.
        fig.text(
            0.5, 0.015, DISCLAIMER_TEXT,
            ha="center", va="bottom", fontsize=9, color="#e2b25a", fontweight="bold",
        )

        os.makedirs(out_dir, exist_ok=True)
        filename = filename or f"{ticker}_trade_chart.png"
        path = os.path.join(out_dir, filename)
        fig.savefig(path, dpi=150, bbox_inches="tight")
    finally:
        plt.close(fig)

    return path


def generate_all_strategy_charts(
    ticker: str,
    df: pd.DataFrame,
    direction: str,
    horizon_label: str,
    out_dir: str,
    h: dict,
    currency_symbol: str = "€",
    filename_prefix: str = None,
) -> dict:
    """
    Generates ONE standalone chart per supported strategy family
    (see levels.ALL_STRATEGY_FAMILIES) for a single ticker -- each one
    showing what THAT ONE STRATEGY, in isolation, currently thinks the
    next target level is, using generate_trade_chart()'s normal
    overlay-drawing machinery so every chart looks and reads exactly
    like a real alert chart.

    This is a diagnostic/exploration tool for !strategycharts, not
    part of the alert pipeline.  scan_engine.py's real scenarios only
    ever show the confirmed, multi-strategy consensus level.

    Returns {strategy_family_name: chart_path_or_None}.
    """
    is_bull = direction == "bullish"
    current_price = float(df["Close"].iloc[-1])

    try:
        all_candidates = levels.collect_candidate_levels(df, h, current_price)
    except Exception:
        all_candidates = []

    result = {}
    for family in levels.ALL_STRATEGY_FAMILIES:
        family_candidates = [
            (p, s) for p, s in all_candidates
            if levels.strategy_family(s) == family
        ]
        if not family_candidates:
            result[family] = None
            continue

        above = sorted(
            [levels.Level(price=p, sources=[s]) for p, s in family_candidates if p > current_price],
            key=lambda lv: lv.price,
        )
        below = sorted(
            [levels.Level(price=p, sources=[s]) for p, s in family_candidates if p <= current_price],
            key=lambda lv: lv.price,
            reverse=True,
        )

        if is_bull:
            if not above or not below:
                result[family] = None
                continue
            target_lv, stop_lv = above[0], below[0]
        else:
            if not below or not above:
                result[family] = None
                continue
            target_lv, stop_lv = below[0], above[0]

        try:
            prefix = filename_prefix or ticker
            fname = f"{prefix}_{family.lower().replace(' ', '_')}_{horizon_label}.png"
            path = generate_trade_chart(
                ticker=ticker,
                df=df,
                entry=current_price,
                stop_loss=stop_lv.price,
                take_profit=target_lv.price,
                direction=direction,
                strategy=family,
                horizon_label=horizon_label,
                out_dir=out_dir,
                filename=fname,
                currency_symbol=currency_symbol,
                target_sources=list(target_lv.sources),
                stop_sources=list(stop_lv.sources),
                horizon=h,
            )
            result[family] = path
        except Exception as exc:
            log.warning("generate_all_strategy_charts: %s/%s failed: %s", ticker, family, exc)
            result[family] = None

    return result
