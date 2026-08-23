"""Effective confluence count: how many INDEPENDENT votes a set of confirming
strategy families actually represents.

`levels.count_confirming_strategies` counts families. EMA, VWAP, AVWAP,
Bollinger Bands, Donchian Channel and Rolling S/R are all moving-window
derivations of the same close series; Fibonacci, Zigzag Pivot and Floor Pivot
are all swing-extreme derivations of the same pivots. Several co-locate by
construction rather than by corroboration, so a raw count of 5 can be two
observations wearing five hats.

The reduction is the participation ratio -- the effective number of
independent bets:

    N_eff = N^2 / sum_{i,j in F} R[i][j]

R is a symmetric matrix of measured co-occurrence probabilities with a unit
diagonal (Task 4). Independent families give N_eff = N; perfectly redundant
ones give N_eff = 1; and 1 <= N_eff <= N always, which is why wiring this in
can only ever TIGHTEN the gate.

Transparent arithmetic, no fitted object at runtime: the matrix is a frozen
constant measured once on TRAIN, so the fold harness can audit it.
"""
from __future__ import annotations

import math
from typing import Sequence

from swingbot.core.market.levels import ALL_STRATEGY_FAMILIES

FAMILY_ORDER: tuple[str, ...] = tuple(ALL_STRATEGY_FAMILIES)
_INDEX = {name: i for i, name in enumerate(FAMILY_ORDER)}

# measured-on: 4e04251 TRAIN 2020-01-01..2023-12-31
# scripts/backtest/measure_confluence_redundancy.py over the 78-ticker
# watchlist x {4w,2m,3m,4m,6m}, every 20th bar: 707,655 candidate prices,
# 75/78 tickers contributing (CRWV/SNDK/SPCX have no cached history).
# R[i][j] = (C[i][j]/C[i][i] + C[j][i]/C[j][j]) / 2 -- the symmetrised
# probability that family j also lands on a price family i landed on.
# Row/column order is FAMILY_ORDER above, which is levels.ALL_STRATEGY_FAMILIES;
# tests/edge/test_confluence_matrix.py asserts that element for element.
REDUNDANCY = [
    [1.0000, 0.7941, 0.8268, 0.7417, 0.3109, 0.6246, 0.6088, 0.6003, 0.7808, 0.5045, 0.6891, 0.6696],   # EMA
    [0.7941, 1.0000, 0.7434, 0.6918, 0.2354, 0.5903, 0.5516, 0.5443, 0.6534, 0.4387, 0.6193, 0.6905],   # VWAP
    [0.8268, 0.7434, 1.0000, 0.8290, 0.4592, 0.7159, 0.6981, 0.6956, 0.8091, 0.5916, 0.7526, 0.6855],   # AVWAP
    [0.7417, 0.6918, 0.8290, 1.0000, 0.6939, 0.8376, 0.7587, 0.7702, 0.7740, 0.6676, 0.7558, 0.6655],   # Fibonacci
    [0.3109, 0.2354, 0.4592, 0.6939, 1.0000, 0.5733, 0.5913, 0.6459, 0.4986, 0.4876, 0.3971, 0.2881],   # Rolling S/R
    [0.6246, 0.5903, 0.7159, 0.8376, 0.5733, 1.0000, 0.6397, 0.6457, 0.6497, 0.5765, 0.6570, 0.5824],   # Zigzag Pivot
    [0.6088, 0.5516, 0.6981, 0.7587, 0.5913, 0.6397, 1.0000, 0.8871, 0.7249, 0.5826, 0.5922, 0.5341],   # Bollinger Bands
    [0.6003, 0.5443, 0.6956, 0.7702, 0.6459, 0.6457, 0.8871, 1.0000, 0.7161, 0.5920, 0.5982, 0.5310],   # Donchian Channel
    [0.7808, 0.6534, 0.8091, 0.7740, 0.4986, 0.6497, 0.7249, 0.7161, 1.0000, 0.5935, 0.6741, 0.6069],   # Floor Pivot
    [0.5045, 0.4387, 0.5916, 0.6676, 0.4876, 0.5765, 0.5826, 0.5920, 0.5935, 1.0000, 0.4946, 0.4474],   # Trendline
    [0.6891, 0.6193, 0.7526, 0.7558, 0.3971, 0.6570, 0.5922, 0.5982, 0.6741, 0.4946, 1.0000, 0.5611],   # FVG
    [0.6696, 0.6905, 0.6855, 0.6655, 0.2881, 0.5824, 0.5341, 0.5310, 0.6069, 0.4474, 0.5611, 1.0000],   # Volume Profile
]



def effective_count(families: Sequence[str],
                    matrix: Sequence[Sequence[float]] | None = None) -> float:
    """Effective (redundancy-discounted) number of confirming families.

    `matrix` defaults to the frozen `REDUNDANCY` constant once Task 4 lands.
    Passing None before then raises -- an implicit identity default would turn
    this whole component into a silent no-op.
    """
    if matrix is None:
        matrix = globals().get("REDUNDANCY")
    if matrix is None:
        raise ValueError("no redundancy matrix available")

    seen: list[int] = []
    for name in families:
        if name not in _INDEX:
            raise ValueError(f"unknown family: {name!r}")
        idx = _INDEX[name]
        if idx not in seen:
            seen.append(idx)

    n = len(seen)
    if n <= 1:
        return float(n)

    total = 0.0
    for i in seen:
        for j in seen:
            total += float(matrix[i][j])
    if total <= 0.0:
        raise ValueError("redundancy matrix produced a non-positive denominator")
    return (n * n) / total


def effective_count_int(families: Sequence[str],
                        matrix: Sequence[Sequence[float]] | None = None) -> int:
    """`effective_count` floored to the integer the scan pipeline consumes.

    FLOOR, not round, and pre-registered as such: the gate fails closed, so a
    scenario at 2.9 effective votes has not earned a 3.
    """
    return int(math.floor(effective_count(families, matrix) + 1e-9))
