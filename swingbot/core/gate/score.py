"""Checklist score 0-100 + tier ladder. Pure functions — cuts arrive as
arguments (resolved from config Fields by the G75 orchestrator)."""
from __future__ import annotations

from typing import Sequence

from swingbot.core.gate.types import CheckResult, scoreable

TIER_ORDER = ("A+", "A", "B", "C")
_STATUS_CREDIT = {"pass": 1.0, "warn": 0.5, "fail": 0.0}


def score(checks: Sequence[CheckResult]) -> float:
    """Weighted score: pass=1.0, warn=0.5, fail=0.0; unknown excluded from
    the denominator (types.scoreable). Nothing scoreable -> neutral 50.0;
    the caller carries macro_stale responsibility."""
    scored = [c for c in scoreable(checks) if c.weight > 0]
    denom = sum(c.weight for c in scored)
    if denom == 0:
        return 50.0
    got = sum(c.weight * _STATUS_CREDIT[c.status] for c in scored)
    return round(got / denom * 100.0, 2)


def assign_tier(score: float, hard_blocks: Sequence[str], *,
                aplus_cut: float, a_cut: float, b_cut: float) -> str:
    """Any hard block -> C regardless of score; otherwise inclusive cuts."""
    if hard_blocks:
        return "C"
    if score >= aplus_cut:
        return "A+"
    if score >= a_cut:
        return "A"
    if score >= b_cut:
        return "B"
    return "C"
