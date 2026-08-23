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
