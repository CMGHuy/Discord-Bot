"""Checklist score 0-100 + tier ladder. Pure functions — cuts arrive as
arguments (resolved from config Fields by the G75 orchestrator)."""
from __future__ import annotations

import dataclasses
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


def _enforce_verdict(result, min_tier: str) -> str:
    """What enforce WOULD do: hard block or below-min-tier -> block; the
    min tier itself -> WEAK-style downgrade (cockpit rule 6) unless the
    bar is already A+."""
    if result.hard_blocks:
        return "block"
    tier_rank = TIER_ORDER.index(result.tier)
    min_rank = TIER_ORDER.index(min_tier)
    if tier_rank > min_rank:
        return "block"
    if tier_rank == min_rank and min_tier != "A+":
        return "downgrade"
    return "pass"


def decide(result, mode: str, min_tier: str) -> str:
    """Shadow and inform ALWAYS return "pass" — only opt-in enforce may
    block or downgrade. The would-be verdict is exposed via with_advisory."""
    return _enforce_verdict(result, min_tier) if mode == "enforce" else "pass"


def with_advisory(result, mode: str, min_tier: str):
    """(decision, result) where result.advisory_decision carries the
    enforce verdict regardless of mode — inform renders it as information
    ("enforce would block this"), G123."""
    advisory = _enforce_verdict(result, min_tier)
    decision = advisory if mode == "enforce" else "pass"
    return decision, dataclasses.replace(result, advisory_decision=advisory)
