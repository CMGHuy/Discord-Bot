"""VIX curve calm (frozen 2026-11-07): long the stock the next open on any
day the VIX term structure is NOT in its stress state.

The stress state turns on when VIX / VIX3M closes above 1.0 (curve
inverted) and stays on until the ratio closes below 0.95 (hysteresis).
Events are the calm days, so the matched null is the stressed days of the
same ticker, month and trend state: a pass says longs taken in calm
curve months beat longs taken while the curve is inverted by >= +0.10R —
exactly the claim a "no new longs while inverted" gate needs
(docs/strategy/vix-and-the-index.md § 7, candidate 1). Months with no
stressed day have no null and drop out, so the comparison is made only
inside months that saw both states. A fail closes exactly this definition.
"""
from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import context as pit

CONTEXT = ("^VIX", "^VIX3M")
CAP = 10
RACE = "fixed"
PARAMS = {"near": "^VIX", "far": "^VIX3M", "stress_on_above": 1.0,
          "stress_off_below": 0.95, "events": "calm (not stressed)", "side": "long"}
SUMMARY = ("VIX/VIX3M stress state (on > 1.0, off < 0.95) is off; "
           "null = stressed days, same month and trend")
SOURCE = ("VIX term-structure regime (Simon & Campasano 2014; Johnson 2017), "
          "see docs/strategy/vix-and-the-index.md § 4")


def stress_state(ratio: pd.Series, on_above: float, off_below: float) -> pd.Series:
    """True while stressed. The state at t reads ratios dated <= t only; an
    undefined ratio leaves the state unchanged (and the start is calm)."""
    values = ratio.to_numpy(dtype=float)
    out = np.zeros(len(values), dtype=bool)
    stressed = False
    for i, r in enumerate(values):
        if r > on_above:
            stressed = True
        elif r < off_below:
            stressed = False
        out[i] = stressed                      # NaN compares False: unchanged
    return pd.Series(out, index=ratio.index)


def events(df: pd.DataFrame, context: Mapping[str, pd.DataFrame]) -> pd.Series:
    """True on every stock date whose own VIX/VIX3M bar is calm. A stock
    date without both context bars, or with an undefined ratio, is False."""
    near = context[PARAMS["near"]]["Close"]
    far = context[PARAMS["far"]]["Close"]
    ratio = (near / far).where(far > 0)
    stressed = stress_state(ratio, PARAMS["stress_on_above"], PARAMS["stress_off_below"])
    calm = (~stressed) & ratio.notna()
    return pit.context_on(df.index, calm).rename("vix_curve_calm")
