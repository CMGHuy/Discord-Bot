"""Frozen v122 clause-6 baseline partition and missing-ratio disclosure."""
from __future__ import annotations

import math

from swingbot.core.backtesting.acceptance import ClauseResult, expectancy_r, win_rate
from swingbot.core.edge import gates
from swingbot.core.market import structure


class NotADryupArm(ValueError):
    """The arm stamp does not identify an active dry-up component."""


def in_scope(trade, scope):
    """Keep the two registered components and the frozen strategy list separate."""
    if trade.source != scope:
        return False
    return scope == 'confluence' or (scope == 'strategy' and
                                    gates.strategy_in_dryup_scope(trade.strategy))


def scoped_ratios(trades, frame_for, scope, cache=None):
    """Read completed signal-date bars; caller-owned cache belongs to one dataset."""
    cache = {} if cache is None else cache
    ratios = cache.setdefault('ratios', {})
    frames = cache.setdefault('frames', {})
    result = {}
    for trade in trades:
        if not in_scope(trade, scope):
            continue
        if trade.key not in ratios:
            if trade.ticker not in frames:
                frames[trade.ticker] = frame_for(trade.ticker)
            frame = frames[trade.ticker]
            ratios[trade.key] = (None if frame is None else
                                 structure.pullback_vol_ratio(frame.loc[:trade.entry_date], trade.direction))
        result[trade.key] = ratios[trade.key]
    return result


def none_share(ratios, scope):
    """Disclose undefined ratios within this component, including empty scopes."""
    n = len(ratios)
    missing = sum(ratio is None for ratio in ratios.values())
    return {'scope': scope, 'n': n, 'none': missing,
            'share': missing / n if n else None}


def flagged_keys(ratios, d):
    """Use the live gate's strict comparison, including its None/NaN/off rules."""
    return {key for key, ratio in ratios.items() if gates.ratio_exceeds(ratio, d)}


def baseline_mechanism(baseline, flagged, scope):
    """Compare flagged vs unflagged in-scope baseline outcomes only."""
    scoped = [trade for trade in baseline if in_scope(trade, scope)]
    removed = [trade for trade in scoped if trade.key in flagged]
    retained = [trade for trade in scoped if trade.key not in flagged]
    return _mechanism_result(removed, retained, scope)


def _mechanism_result(removed, retained, scope):
    removed_wr, retained_wr = win_rate(removed), win_rate(retained)
    removed_exp = expectancy_r(removed)
    if removed_wr is None or retained_wr is None or removed_exp is None:
        return ClauseResult('mechanism', 'FAIL',
                            'in-scope baseline removed or retained population has no decided trades to compare')
    passed = removed_wr < retained_wr and removed_exp <= 0
    return ClauseResult('mechanism', 'PASS' if passed else 'FAIL',
                        f'{scope} baseline removed WR {removed_wr:.2f}% vs retained {retained_wr:.2f}%, '
                        f'removed ExpR {removed_exp:+.4f}R (must be <= 0)', removed_wr, retained_wr)


def knob_context(blob):
    """Return an active component only when both dry-up knobs are stamped."""
    delta = (blob.get('provenance') or {}).get('knob_delta') or {}
    scope = delta.get('PULLBACK_DRYUP_SCOPE')
    d = delta.get('PULLBACK_DRYUP_MAX_RATIO')
    if scope not in ('strategy', 'confluence') or isinstance(d, bool):
        return None
    if not isinstance(d, (int, float)) or not math.isfinite(d) or d <= 0:
        return None
    return scope, float(d)
