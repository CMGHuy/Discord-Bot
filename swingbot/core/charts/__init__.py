"""
Everything involved in rendering a trade chart PNG, grouped into one
subpackage: the shared dark-theme visual constants (chart_style.py), small
drawing/geometry helpers (chart_drawing.py), the confirmed-strategy overlay
dispatcher (chart_strategy_overlay.py), the left-side Volume Profile panel
(chart_volume_profile.py), and the top-level chart-assembly entry points
(trade_chart.py: generate_trade_chart, generate_all_strategy_charts).

These five modules were previously flat siblings directly under
swingbot/core/ alongside ~25 unrelated modules (levels, signals, backtest,
account, watchlist, ...); their own docstrings already described them as
one cohesive "chart_*.py sibling module" unit, so they're grouped here as
an actual Python subpackage instead of just a naming convention.

External call sites should import from here, e.g.:
    from swingbot.core.charts.trade_chart import generate_trade_chart
    from swingbot.core.charts.chart_drawing import _pick_primary_source
"""
