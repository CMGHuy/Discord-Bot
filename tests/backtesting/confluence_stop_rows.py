"""Synthetic v139 arm S rows (the confluence_stop_replay shapes) for the
funnel and driver tests."""
from tests.backtesting.acceptance_rows import record

KEYS = ("c3", "c4", "c5")


def s_record(ticker, date, outcome, r, **kw):
    return {**record(ticker, date, outcome, r, **kw), "fill_beyond_ceiling": False}


def s_row(baseline, cells, *, d=3.0, changed=None, rollback=None):
    """`baseline` and each `cells` value are s_record() dicts or None."""
    anchor = baseline or next(c for c in cells.values() if c is not None)
    return {"arm": "S", "ticker": anchor["ticker"], "horizon_key": anchor["horizon_key"],
            "entry_date": anchor["entry_date"], "direction": anchor["direction"],
            "clamped": d is not None, "d": d,
            "changed": changed if changed is not None else {key: True for key in cells},
            "rollback": rollback if rollback is not None else {key: False for key in cells},
            "baseline": baseline, "cells": cells}


def lifted_s_rows(lifts, *, jitter=0.0, n_tickers=20, per_ticker=4, year=2021):
    """n_tickers * per_ticker paired rows. The baseline alternates win (+2R)
    and loss (-1R); each cell keeps the outcome and adds lifts[key], plus
    +jitter on even trades and -jitter on odd ones."""
    rows = []
    for t in range(n_tickers):
        for k in range(per_ticker):
            ticker, date = f"T{t:02d}", f"{year}-{k + 1:02d}-15"
            outcome, base_r = ("win", 2.0) if k % 2 == 0 else ("loss", -1.0)
            wobble = jitter if k % 2 == 0 else -jitter
            cells = {key: s_record(ticker, date, outcome, base_r + lift + wobble)
                     for key, lift in lifts.items()}
            rows.append(s_row(s_record(ticker, date, outcome, base_r), cells))
    return rows


def census_row(d, changed=(False, False, False), *, ticker="T00", date="2021-01-15",
               horizon="4w", direction="bullish", rollback=(False, False, False)):
    return {"ticker": ticker, "horizon_key": horizon, "entry_date": date,
            "direction": direction, "clamped": d is not None, "d": d,
            "changed": dict(zip(KEYS, changed)), "rollback": dict(zip(KEYS, rollback))}
