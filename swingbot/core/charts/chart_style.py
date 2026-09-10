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
import os
from matplotlib import font_manager as _fm

_INTER = os.path.join(os.path.dirname(__file__), "..", "..", "admin", "static", "vendor", "inter", "inter-500.woff2")
# matplotlib cannot load woff2 — only register if a ttf/otf is present.
# Optional nicety: drop Inter-Medium.ttf into that folder to activate; the
# charts fall back to the default sans (DejaVu) otherwise, by design.
_INTER_TTF = _INTER.replace("inter-500.woff2", "Inter-Medium.ttf")
if os.path.exists(_INTER_TTF):
    _fm.fontManager.addfont(_INTER_TTF)
    matplotlib.rcParams["font.family"] = "Inter"

# ---------------------------------------------------------------------------
# The admin palette, on every Discord chart -- spec v80 D5, direction C
# ("TradingView Blue").
#
# THEME copies, byte for byte, the tokens it names from
# frontend/src/styles/tokens.css: D1's colours and D2's chart series. Every
# colour constant below is one of them. tests/charts/test_chart_theme.py reads
# that file, maps each constant to its token, and holds three rules:
#   1. roles drawn together are distinct (OKLab dE >= 10);
#   2. indicator panes may reuse a series;
#   3. nothing but the gain/loss constants sits within dE 10 of gain or loss.
# Change a colour in tokens.css and that test names the constant to follow.
# ---------------------------------------------------------------------------
THEME = {
    "surface": "#131722",
    "surface-raised": "#1c212d",
    "border": "#2a2e39",
    "border-strong": "#363a45",
    "text": "#d9dce4",
    "text-muted": "#9195a0",
    "text-faint": "#4e5361",
    "pos": "#17c98e",
    "neg": "#ff5470",
    "warn": "#ffb43d",
    "info": "#b39ddb",
    "chart-1": "#4c8dff",
    "chart-2": "#c97a22",
    "chart-3": "#a868e0",
    "chart-5": "#1a9db3",
}

CHART_BG = THEME["surface"]             # figure + every panel's background: TradingView's chart pane
GRID_COLOR = THEME["border"]            # gridlines -- subtle, never competes with data
SPINE_COLOR = THEME["border-strong"]    # axis borders
TEXT_COLOR = THEME["text"]              # primary text (titles, axis labels)
MUTED_TEXT_COLOR = THEME["text-muted"]  # tick labels, fine print: 5.97:1 on CHART_BG (#666666 was 3.6:1)
UP_COLOR = THEME["pos"]                 # bullish candle body/wick
DOWN_COLOR = THEME["neg"]               # bearish candle body/wick
CHIP_BG = THEME["surface-raised"]       # background for the small rounded "chip" labels every overlay uses
CHIP_EDGE = THEME["border-strong"]      # neutral chip border when no accent color applies

# One green and one red across the whole image, per the palette's first rule:
# green and red mean P&L direction and nothing else. A target IS the profit
# side and a stop IS the loss side, so they take the same two colours the
# candles do rather than near-miss shades of them -- the old #00c896 target
# against #26a69a candles was two greens that meant the same thing. Line
# weight, dashing and the labelled chip are what separate a level from a
# candle body, not a third hue.
ENTRY_COLOR = THEME["chart-1"]
STOP_COLOR = THEME["neg"]
TARGET_COLOR = THEME["pos"]
TARGET2_COLOR = THEME["chart-3"]
CURRENT_PRICE_COLOR = THEME["warn"]  # distinct from entry -- entry is a planned limit level, this is where price actually is

# Support and resistance take the stop-side and target-side strategy colours
# below. The two never share a chart: trade_chart.py draws plain trendlines
# only when no confirming source was passed and the strategy overlays
# otherwise, so the pairing costs no distinctness and keeps the side meaning
# (for a long, support is the stop side). Resistance was pink #ec407a, OKLab
# dE 5.9 from loss: a line that read as a loss on every chart.
TRENDLINE_SUPPORT_COLOR = THEME["chart-5"]
TRENDLINE_RESISTANCE_COLOR = THEME["chart-2"]
AVWAP_COLOR = THEME["info"]

# Fixed accent colors for the confirmed-strategy overlay -- one per
# SIDE of the scenario (whatever confirmed target 1, whatever confirmed
# the stop), not per method, so the chart reads as a consistent
# two-color system no matter which specific method (EMA, VWAP, Fib,
# FVG, trendline, ...) actually gets picked for a given trade.
TARGET_STRATEGY_COLOR = THEME["chart-2"]
STOP_STRATEGY_COLOR = THEME["chart-5"]

# Indicator-panel accent colors (MACD/Signal/RSI). Indicator panes may reuse
# series (D5 rule 2); the three also colour the stat chips above the price
# pane, where they sit >= 13.7 dE from each other, from TP2 and from amber.
MACD_LINE_COLOR = THEME["chart-1"]
SIGNAL_LINE_COLOR = THEME["chart-2"]
RSI_LINE_COLOR = THEME["chart-5"]

# Keltner bands are background context on the price pane, dashed at 55%
# alpha, so they take the neutral muted grey rather than a hue. Six series
# cannot give seven price-pane roles each a hue >= 10 dE from every other:
# chart-1/chart-6 sit 6.8 apart and chart-2/chart-4 6.2.
KC_COLOR = THEME["text-muted"]

# Volume Profile is drawn on EVERY chart, always -- both as the left-side
# overlay (see chart_volume_profile._draw_volume_profile_overlay) and,
# when Volume Profile actually confirmed this scenario's target/stop, as a
# highlighted level on the price panel itself. It takes info lavender:
# background market structure is a neutral fact, not a level, and lavender
# is unlike every strategy or level colour on the pane (>= 10.2 dE, the
# nearest being the grey Keltner bands).
VOLUME_PROFILE_COLOR = THEME["info"]

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
# look rather than hollow candles), volume bars tinted translucent variants
# of the up/down colors so the volume panel doesn't compete with the price panel.
_MARKET_COLORS = mpf.make_marketcolors(
    up=UP_COLOR, down=DOWN_COLOR,
    edge={"up": UP_COLOR, "down": DOWN_COLOR},
    wick={"up": UP_COLOR, "down": DOWN_COLOR},
    volume={"up": UP_COLOR + "55", "down": DOWN_COLOR + "55"},
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
    # Solid hairlines, matching chart-init.js:26 -- lightweight-charts draws
    # plain one-pixel grid lines. gridcolor is deliberately NOT touched here:
    # it is GRID_COLOR, which is palette and pinned by test_chart_theme.py.
    gridstyle="-",
    gridaxis="both",
    y_on_right=True,
    rc={
        "font.size": 9,
        "grid.linewidth": 0.5,
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
# chart_volume_profile._draw_volume_profile_overlay) reads as a finer,
# more precise price ladder rather than a handful of coarse bands.
VOLUME_PROFILE_PANEL_BINS = 42

# Widest volume-profile bucket, as a fraction of the price panel's width.
# The profile is now drawn as an overlay INSIDE the price panel growing
# leftward from the right edge (TradingView's "Volume Profile Visible
# Range"), so it no longer reserves any figure width of its own -- the old
# VOLUME_PROFILE_PANEL_WIDTH_FRAC/_GAP_FRAC pair that carved out a detached
# left panel (and, with it, a second duplicate price ladder) is gone.
VOLUME_PROFILE_OVERLAY_MAX_FRAC = 0.16

# Volume rides the bottom fraction of the price panel on its own hidden
# y-axis -- the matplotlib equivalent of chart-init.js:38's
# scaleMargins {top: 0.82, bottom: 0}.
VOLUME_OVERLAY_HEIGHT_FRAC = 0.18

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
# (see chart_geometry._pick_primary_source) -- most visually distinctive /
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
PATH_COLOR = THEME["text-faint"]

# Minimum vertical gap between two adjacent labels, as a fraction of the
# visible price range -- tuned so labels never visually touch at the
# fontsize/figure size used below, regardless of how close the actual
# price levels are to each other.
MIN_LABEL_GAP_FRAC = 0.07
