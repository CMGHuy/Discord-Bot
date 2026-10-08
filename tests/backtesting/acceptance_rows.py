"""Synthetic v129 replay rows (the acceptance_replay.entry_row shape) for the
funnel tests and the driver-script tests."""


def record(ticker, date, outcome, r, *, horizon="4w", rr=2.0, mix=None, gap=False):
    return {"ticker": ticker, "strategy": "S", "horizon_key": horizon,
            "entry_date": date, "outcome": outcome, "r_multiple": r,
            "planned_rr": rr, "source": "confluence", "direction": "bullish",
            "exit_mix": mix or ("tp1" if outcome == "win" else "stop"),
            "gap_through": gap}


def row(baseline, cells, *, arm="Z", eligible=True):
    """`baseline` and each `cells` value are record() dicts or None."""
    anchor = baseline or next(c for c in cells.values() if c is not None)
    return {"arm": arm, "ticker": anchor["ticker"], "horizon_key": anchor["horizon_key"],
            "entry_date": anchor["entry_date"], "direction": anchor["direction"],
            "eligible": eligible, "baseline": baseline, "cells": cells}


def lifted_rows(arm, lifts, *, jitter=0.0, n_tickers=20, per_ticker=4, year=2021):
    """n_tickers * per_ticker paired rows. The baseline alternates win (+2R)
    and loss (-1R); each cell keeps the outcome and adds lifts[key], plus
    +jitter on even trades and -jitter on odd ones."""
    rows = []
    for t in range(n_tickers):
        for k in range(per_ticker):
            ticker, date = f"T{t:02d}", f"{year}-{k + 1:02d}-15"
            outcome, base_r = ("win", 2.0) if k % 2 == 0 else ("loss", -1.0)
            wobble = jitter if k % 2 == 0 else -jitter
            cells = {key: record(ticker, date, outcome, base_r + lift + wobble)
                     for key, lift in lifts.items()}
            rows.append(row(record(ticker, date, outcome, base_r), cells, arm=arm))
    return rows
