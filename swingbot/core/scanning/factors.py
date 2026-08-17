"""Factor registry for the unified confidence score (v32).

One pure function per factor: (FactorContext) -> FactorResult | None.
Returning None means "this factor had no input to read" and the factor is
omitted from the breakdown entirely -- an absent reading must never render
as a real one that scored zero (the rule quality.py:107-111 already states).

Weights live in the FactorResult each function returns, so re-weighting on
TRAIN evidence never edits control flow.

The kept factor set and the reasoning behind every drop is
docs/superpowers/plans/v32-factor-reconciliation.md (Task 1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class FactorResult:
    name: str
    points: int
    line: str


@dataclass
class FactorContext:
    """Everything any factor may read. All optional: a factor whose inputs
    are missing returns None rather than inventing a neutral value."""
    scenario: object = None
    df: object = None
    regime_trend: str | None = None
    htf_bias: str | None = None
    rs_percentile: float | None = None
    mtf: int | None = None
    breadth: float | None = None
    volume_ratio: float | None = None
    atr_pct: float | None = None
    trigger_distance_pct: float | None = None
    badge_status: str | None = None
    gap_fragile: bool = False
    target_count: int = 0
    target_families: list = field(default_factory=list)
    stop_count: int = 0
    stop_families: list = field(default_factory=list)


Factor = Callable[[FactorContext], "FactorResult | None"]

FACTORS: list[Factor] = []


def run_factors(factors: list[Factor], ctx: FactorContext) -> tuple[int, dict]:
    """Returns (total_points, {name: line}). Factors returning None are
    omitted from both."""
    total = 0
    breakdown: dict[str, str] = {}
    for fn in factors:
        result = fn(ctx)
        if result is None:
            continue
        total += result.points
        breakdown[result.name] = result.line
    return total, breakdown
