"""v182: trade direction for the screen races.

A short race is the long race on negated prices (O, H, L, C -> -O, -L, -H,
-C): stop above, target below, gap stop on Open >= stop, the high checked
first. So the mirror identity is a property of the code. ``oriented`` hands
a long its own arrays back, untouched, and ``net_r`` keeps the long net-R
expression with its operand order, so every long float is computed exactly
as before v182 (partner rule 2026-10-21).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.edge.frictions import apply_frictions, borrow_r, commission_r

DIRECTIONS = ("long", "short")


def _check(direction: str) -> None:
    if direction not in DIRECTIONS:
        raise ValueError(f"unknown direction {direction!r}; expected one of {DIRECTIONS}")


def oriented(o, h, l, c, direction: str):
    """The four price arrays as the long race reads them: a long gets the
    very same objects back; a short gets (-O, -L, -H, -C)."""
    _check(direction)
    if direction == "long":
        return o, h, l, c
    return -o, -l, -h, -c


def holding_days(index: pd.DatetimeIndex, entry_pos, exit_pos) -> np.ndarray:
    """Calendar days from the entry bar's date to the exit bar's date."""
    return (index[np.asarray(exit_pos)] - index[np.asarray(entry_pos)]).days.to_numpy(dtype=float)


def net_r(entry, price, risk, *, direction: str, days, slippage_bps=None,
          entry_bps=None, commission=None) -> np.ndarray:
    """Net R per trade from real (un-negated) entry and exit prices.
    ``entry_bps=None`` fills the entry at ``slippage_bps``; a long never
    reads ``days`` and is never charged borrow."""
    _check(direction)
    eb = slippage_bps if entry_bps is None else entry_bps
    cost = commission_r() if commission is None else commission
    if direction == "long":
        return (apply_frictions(price, "sell", slippage_bps)
                - apply_frictions(entry, "buy", eb)) / risk - cost
    return ((apply_frictions(entry, "sell", eb) - apply_frictions(price, "buy", slippage_bps))
            / risk - cost - borrow_r(entry, risk, days))
