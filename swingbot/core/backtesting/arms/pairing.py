"""Pair baseline and component arms by :attr:`ArmTrade.key`.

A duplicate key inside one arm is a harness bug, not data: pairing would
silently keep the last row and every downstream delta would be wrong.
"""
from __future__ import annotations


class DuplicateKeyError(ValueError):
    """Raised when one arm contains more than one row for a pairing key."""


def index_by_key(trades) -> dict:
    """Return one trade per pairing key, refusing ambiguous input."""
    out: dict = {}
    for trade in trades:
        if trade.key in out:
            raise DuplicateKeyError(f"duplicate pairing key {trade.key}")
        out[trade.key] = trade
    return out


def _fingerprint(trade) -> tuple:
    r_multiple = None if trade.r_multiple is None else round(trade.r_multiple, 6)
    return trade.outcome, r_multiple


def changed_outcomes(baseline, component) -> int:
    """Count added, removed, or changed-outcome trades between two arms."""
    baseline_by_key = index_by_key(baseline)
    component_by_key = index_by_key(component)
    moved = len(baseline_by_key.keys() ^ component_by_key.keys())
    flipped = sum(
        _fingerprint(baseline_by_key[key]) != _fingerprint(component_by_key[key])
        for key in baseline_by_key.keys() & component_by_key.keys()
    )
    return moved + flipped


def overlap(baseline, component) -> int:
    """Count pairing keys shared by both arms."""
    return len({trade.key for trade in baseline} & {trade.key for trade in component})
