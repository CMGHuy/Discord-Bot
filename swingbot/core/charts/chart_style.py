"""
Shared visual constants for every trade-chart module (trade_chart.py and
its sibling chart_*.py drawing helpers) -- the dark "TradingView/Bloomberg
terminal" theme (colors, mplfinance style object) plus a handful of sizing/
layout constants that more than one of those modules needs. Split out of
trade_chart.py so the theme/config lives in exactly one place regardless of
which drawing module needs it, instead of being duplicated or imported
awkwardly between sibling modules.
"""
import matplotlib
matplotlib.use("Agg")
import mplfinance as mpf

# ---------------------------------------------------------------------------
# Professional dark theme -- a TradingView/Bloomberg-terminal-style palette
# used for the whole chart (background, grid, candles, and every custom
# annotation below) instead of mplfinance's default light "yahoo" style, so
# a chart reads like a serious trading terminal rather than a generic light
# spreadsheet plot. Every custom text/box color elsewhere in this file is
# drawn from this same small palette so nothing clashes with a leftover
# light-theme color.
# ---------------------------------------------------------------------------
CHART_BG = "#131722"           # figure + every panel's background
GRID_COLOR = "#232734"         # gridlines -- subtle, never competes with data
SPINE_COLOR = "#2a2e39"        # axis borders
TEXT_COLOR = "#d1d4dc"         # primary text (titles, axis labels)
MUTED_TEXT_COLOR = "#787b86"   # secondary text (tick labels, fine print)
UP_COLOR = "#26a69a"           # bullish candle body/wick
DOWN_COLOR = "#ef5350"         # bearish candle body/wick
CHIP_BG = "#1c2030"            # background for the small rounded "chip" labels every overlay uses
CHIP_EDGE = "#363a45"          # neutral chip border when no accent color applies

ENTRY_COLOR = "#2f7dfa"
STOP_COLOR = "#ef5350"
TARGET_COLOR = "#00c896"
TARGET2_COLOR = "#ab47bc"
CURRENT_PRICE_COLOR = "#ffa726"  # distinct from entry -- entry is a planned limit level, this is where price actually is
TRENDLINE_SUPPORT_COLOR = "#26c6da"
TRENDLINE_RESISTANCE_COLOR = "#ec407a"

# Fixed accent colors for the confirmed-strategy overlay -- one per
# SIDE of the scenario (whatever confirmed target 1, whatever confirmed
# the stop), not per method, so the chart reads as a consistent
# two-color system no matter which specific method (EMA, VWAP, Fib,
# FVG, trendline, ...) actually gets picked for a given trade.
TARGET_STRATEGY_COLOR = "#ff9800"
STOP_STRATEGY_COLOR = "#29b6f6"

# Indicator-panel accent colors (MACD/Signal/RSI/Keltner Channel) -- picked
# to stay clearly distinct from the entry/stop/target family above even
# though both sets of colors now share the same dark background.
MACD_LINE_COLOR = "#42a5f5"
SIGNAL_LINE_COLOR = "#ff7043"
RSI_LINE_COLOR = "#ba68c8"
KC_COLOR = "#4dd0e1"

# Volume Profile is drawn on EVERY chart, always -- both as the left-side
# histogram panel (see chart_volume_profile._draw_volume_profile_panel) and,
# when Volume Profile actually confirmed this scenario's target/stop, as a
# highlighted level on the price panel itself. It gets its own dedicated,
# always-distinct color (a warm gold/amber tone, deliberately unlike any
# strategy or level color) so it reads as "background market structure"
# context rather than "the reason for this specific target/stop".
VOLUME_PROFILE_COLOR = "#d4a94c"

# Printed as fine print along the bottom of every generated trade chart (see
# trade_chart.py's generate_trade_chart, the single shared save point every
# chart -- scan alerts, !ticker, !strategycharts, !tradecharts, and the admin
# UI's chart image route -- all render through). This is a rule-based
# confluence tool, not licensed financial advice, and the image itself is
# what typically gets copied/forwarded/screenshotted around -- the chart
# needs to carry its own disclaimer rather than relying on whatever
# surrounding message/context it happens to be shared with.
DISCLAIMER_TEXT = "Not financial advice — for informational purposes only. Trade at your own risk."


def _label_bbox(color: str, alpha: float = 0.88) -> dict:
    """
    The one small rounded "chip" background every inline overlay label
    (EMA/VWAP/Fib/.../trendline/KC/Volume-Profile-panel text) is drawn
    with -- a dark fill with the line's own accent color as its border,
    consistent with the chart's overall dark theme. Without this, raw
    colored text floating directly over candles/gridlines is hard to
    read and, when two labels land close together, impossible to tell
    apart; a bordered chip keeps each one legible and visually distinct
    even when several sit close together.
    """
    return dict(boxstyle="round,pad=0.22", facecolor=CHIP_BG, edgecolor=color, linewidth=0.9, alpha=alpha)


# mplfinance market colors: candle body/wick/edge match (a solid, modern
# look rather than hollow candles), volume bars tinted the same up/down
# colors as the candles so the two panels read as one coherent story.
_MARKET_COLORS = mpf.make_marketcolors(
    up=UP_COLOR, down=DOWN_COLOR,
    edge={"up": UP_COLOR, "down": DOWN_COLOR},
    wick={"up": UP_COLOR, "down": DOWN_COLOR},
    volume={"up": UP_COLOR, "down": DOWN_COLOR},
    ohlc="inherit",
)

# The style object passed as mpf.plot(..., style=PRO_STYLE) -- built once at
# import time since it's pure configuration, not request-specific state.
PRO_STYLE = mpf.make_mpf_style(
    base_mpf_style="nightclouds",
    marketcolors=_MARKET_COLORS,
    facecolor=CHART_BG,
    figcolor=CHART_BG,
    edgecolor=SPINE_COLOR,
    gridcolor=GRID_COLOR,
    gridstyle="--",
    gridaxis="both",
    y_on_right=True,
    rc={
        "font.size": 9,
        "axes.labelcolor": TEXT_COLOR,
        "xtick.color": MUTED_TEXT_COLOR,
        "ytick.color": MUTED_TEXT_COLOR,
        "text.color": TEXT_COLOR,
        "axes.edgecolor": SPINE_COLOR,
    },
)

# Number of price buckets the left-side volume profile panel bins the
# lookback window into. Deliberately more granular than the 20 bins
# compute_hvn_level's own signal-detection callers use (that count is
# tuned for finding one busiest bucket, not for a good-looking
# histogram shape) -- more buckets makes the panel's profile silhouette
# read closer to a real market-profile chart. Raised from 26 -> 42 so
# each bucket's own price-value tick label (see
# chart_volume_profile._draw_volume_profile_panel) reads as a finer,
# more precise price ladder rather than a handful of coarse bands.
VOLUME_PROFILE_PANEL_BINS = 42

# Fraction of the total figure width reserved for the left-side volume
# profile panel (see chart_volume_profile._draw_volume_profile_panel) plus
# the gap between it and the price panel.
VOLUME_PROFILE_PANEL_WIDTH_FRAC = 0.15
VOLUME_PROFILE_PANEL_GAP_FRAC = 0.012

# Minimum number of trailing bars the volume profile PANEL bins across --
# deliberately much longer than the short sr_lookback (10-180 days,
# horizon-dependent) used elsewhere for HVN signal detection. The panel's
# job is to show volume-at-price across the ENTIRE visible price axis,
# which is padded and further widened to fit the entry/stop/target lines
# -- an entry can be a deliberate pullback level well away from wherever
# price has recently traded, not necessarily "now". A short lookback's
# own High/Low range routinely doesn't reach that far, which is what was
# leaving stretches of the panel with no bucket (and so no bar) at all.
# Using the longer of this and the caller's own lookback, capped at
# however much history is actually available, makes it far more likely
# any real historical trading at that price gets captured.
VOLUME_PROFILE_PANEL_LOOKBACK_DAYS = 180

# How many trailing bars of price history a Fair Value Gap zone is
# drawn extending forward from its formation bar to today -- an unfilled
# gap is still "live" all the way to now, not just at the moment it formed.
FVG_ZONE_ALPHA = 0.16

# Plan-driven R:R band alphas (trade_chart.py's plan_v2= kwarg, Task B30).
# RISK_BAND_ALPHA/REWARD_BAND_ALPHA match the long-standing hardcoded
# 0.08 used for the entry<->stop and entry<->target1 bands regardless
# of whether plan_v2 is present -- unifying the literal into a
# named constant, not changing its value. RUNNER_BAND_ALPHA (0.06) is
# NEW and used ONLY when plan_v2 is actually passed; the legacy no-plan
# path keeps its original 0.05 literal untouched so old callers render
# pixel-identically to before this task.
RISK_BAND_ALPHA = 0.08
REWARD_BAND_ALPHA = 0.08
RUNNER_BAND_ALPHA = 0.06

# Priority order used to pick ONE confirming method to actually draw
# when a scenario's target/stop level was confirmed by several at once
# (see chart_drawing._pick_primary_source) -- most visually distinctive /
# structurally informative first. A flat generic source (Rolling S/R, floor
# pivots, a lone swing high/low) barely differs from the horizontal
# target/stop line already on the chart, so it's only drawn if nothing more
# distinctive confirmed the same level. Bonus, non-level confidence.py
# sources (a candlestick pattern name, "Bollinger Squeeze Breakout")
# are never real price levels and are never picked.
METHOD_PRIORITY = [
    "FVG", "Volume Profile", "Trendline", "Fib", "VWAP", "EMA", "Bollinger", "Donchian",
    "Rolling", "Floor", "Swing", "Pivot",
]

# ~4 trading weeks of daily bars (Mon-Fri x4) -- the MINIMUM window
# shown, not a fixed one; see trade_chart.generate_trade_chart()'s
# window-expansion logic for when a trendline needs more room than this.
DEFAULT_LOOKBACK_DAYS = 20

# Default fit window (in trading days) for the chart's own trendline,
# used only when a caller doesn't pass a horizon-specific value --
# scan_engine.py's real call sites always pass the same horizon's
# fib_lookback that levels.py's confluence system used, so the line
# drawn matches the one that actually contributed to the scenario.
DEFAULT_TRENDLINE_LOOKBACK_DAYS = 90

# Neutral color for the shared first leg of each branch arrow (entry ->
# target 1) -- the move itself isn't "bullish continuation" or "bearish
# reversal" yet, that split only happens at the second leg.
PATH_COLOR = "#555555"

# Minimum vertical gap between two adjacent labels, as a fraction of the
# visible price range -- tuned so labels never visually touch at the
# fontsize/figure size used below, regardless of how close the actual
# price levels are to each other.
MIN_LABEL_GAP_FRAC = 0.07
