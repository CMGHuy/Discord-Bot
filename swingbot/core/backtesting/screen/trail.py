"""The v163 trail race: a chandelier 3 ATR trailing stop, no target. Long only.

Event on bar t (known at t's close). Entry = open of t+1; 1R = 1.5 x
ATR14[t]; initial stop = entry - 1R; no target. The stop in force on bar j
(j >= t+1) is

    stop_j = max(entry - 1R, max(High[t+1 .. j-1]) - 3 x ATR14[t])

so bar j's own high never raises bar j's stop (a daily bar does not say
whether its high came before its low), the stop never moves down, and ATR is
frozen at t. On each bar, in order, with raised_j = stop_j > entry - 1R
(strictly): an open at/below stop_j exits at the open (gap_stop, or
gap_trail when raised: a gap through a raised stop can be a gain); else a
low at/below stop_j exits at stop_j (stop, or trail when raised). After bar
t+cap, exit at its close (timeout). r is always in the initial 1R. Costs as
the fixed race: both fills worsened by SLIPPAGE_BPS, then commission_r().
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen import race as race_mod
from swingbot.core.edge.frictions import apply_frictions, commission_r

TRAIL_ATR = 3.0
_GAP_STOP, _STOP, _TIMEOUT, _TRAIL, _GAP_TRAIL = (
    race_mod.OUTCOMES.index(name)
    for name in ("gap_stop", "stop", "timeout", "trail", "gap_trail"))


def trail_stops(h: np.ndarray, entry: np.ndarray, risk: np.ndarray) -> np.ndarray:
    """The stop in force on every bar column: ``h`` is rows x cap (column 0 is
    bar t+1). Column j reads the highs of columns 0..j-1 only; column 0's
    high term is -inf (never NaN, which would switch the stop off)."""
    prior = np.empty_like(h, dtype=float)
    prior[:, 0] = -np.inf
    prior[:, 1:] = h[:, :-1]
    running = np.maximum.accumulate(prior, axis=1)
    trail = running - (TRAIL_ATR / race_mod.STOP_ATR * risk)[:, None]
    return np.maximum((entry - risk)[:, None], trail)


def _first_exit_trail(O, H, L, C, stops, initial):
    """Exit price, outcome code (index into race.OUTCOMES) and bar column.
    ``stops`` is per row and per bar; the exit prices at ``stops[row, j]``."""
    del H  # the bar's own high never decides its exit (see trail_stops)
    gap = O <= stops
    hit = gap | (L <= stops)
    any_hit = hit.any(axis=1)
    rows = np.arange(len(O))
    j = np.where(any_hit, hit.argmax(axis=1), O.shape[1] - 1)
    gapped = gap[rows, j]
    raised = stops[rows, j] > initial
    code = np.where(gapped, np.where(raised, _GAP_TRAIL, _GAP_STOP),
                    np.where(raised, _TRAIL, _STOP))
    code = np.where(any_hit, code, _TIMEOUT)
    price = np.where(gapped, O[rows, j], stops[rows, j])
    price = np.where(any_hit, price, C[rows, j])
    return price, code, j


def race_trail(df: pd.DataFrame, event_pos, cap: int, *, atr=None,
               slippage_bps=None, commission=None) -> race_mod.RaceResult:
    """Race every event in ``event_pos`` (bar positions) at once."""
    event_pos = np.asarray(event_pos, dtype=int)
    race_mod._check_positions(event_pos, cap, len(df))
    if event_pos.size == 0:
        return race_mod.RaceResult.empty()
    atr_v = (indicators.atr(df) if atr is None else pd.Series(atr)).to_numpy(dtype=float)
    o, h, l, c = (df[col].to_numpy(dtype=float) for col in ("Open", "High", "Low", "Close"))
    bars = event_pos[:, None] + 1 + np.arange(cap)[None, :]
    entry = o[event_pos + 1]
    risk = race_mod.STOP_ATR * atr_v[event_pos]
    stops = trail_stops(h[bars], entry, risk)
    price, code, offset = _first_exit_trail(o[bars], h[bars], l[bars], c[bars],
                                            stops, entry - risk)
    cost = commission_r() if commission is None else commission
    net = (apply_frictions(price, "sell", slippage_bps)
           - apply_frictions(entry, "buy", slippage_bps)) / risk - cost
    return race_mod.RaceResult(event_pos, event_pos + 1 + offset, entry, risk,
                               (price - entry) / risk, net,
                               np.asarray(race_mod.OUTCOMES)[code])
