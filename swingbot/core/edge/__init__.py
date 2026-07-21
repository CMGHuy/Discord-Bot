"""Edge package: growth math, sizing, portfolio risk, regime v2, factors.

Everything in this package is transparent arithmetic -- no ML, no fitted
black boxes -- so the walk-forward harness (backtest_wf.py) can audit any
component before it is allowed to touch live behavior.
"""
