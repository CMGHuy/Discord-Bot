"""Entry gates driven by distributions, not vibes: overnight gap noise
(this task), earnings blackout (E18). Each is a pure function; wiring is
always flag-gated and fold-validated before it can touch live behavior."""
from __future__ import annotations

import numpy as np
import pandas as pd


def gap_stats(df: pd.DataFrame, lookback: int = 250) -> dict:
    """Distribution of overnight gaps |Open / prev Close - 1| in percent."""
    tail = df.tail(lookback + 1)
    gaps = (tail["Open"] / tail["Close"].shift(1) - 1.0).abs().dropna() * 100.0
    if gaps.empty:
        return {"p90_gap_pct": 0.0, "p99_gap_pct": 0.0, "n": 0}
    return {"p90_gap_pct": float(np.percentile(gaps, 90)),
            "p99_gap_pct": float(np.percentile(gaps, 99)),
            "n": int(len(gaps))}


def stop_beyond_gap_noise(stop_distance_pct: float, gap_p90_pct: float,
                          cushion: float = 1.0) -> bool:
    """A stop inside the ticker's routine overnight gap is decided by the
    open print, not by the setup. True = the stop clears the noise."""
    return stop_distance_pct >= cushion * gap_p90_pct
