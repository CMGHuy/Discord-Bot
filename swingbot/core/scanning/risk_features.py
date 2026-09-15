"""Candidate discriminators stamped on every plan at issuance (v86 spec §4).

These are NOT scored, weighted or combined -- deliberately. v32 and v33 both
regressed folding signals into one number. This module only RECORDS what was
knowable at the creating bar, so scripts/reports/cohort_separation_report.py
can later measure which of these actually separates winners from losers,
before anyone spends a pre-registration on a richer key.

NO-LOOKAHEAD: every argument is a reading from the creating bar or earlier.
Nothing in here reads a dataframe, so there is no bar index to get wrong --
the caller passes scalars it already holds in scope.
"""
from __future__ import annotations

import datetime as dt
import math

# ET (US market-hours) RTH buckets. Boundaries are deliberately coarse: the
# point is to find out whether time-of-day matters at all (median live hold
# is ~2h against horizons labelled 2w-9m), not to slice it finely on 782
# trades.
_OPEN_UNTIL = dt.time(11, 0)
_CLOSE_FROM = dt.time(15, 30)


def _bad_atr(atr_val) -> bool:
    """True for a falsy/zero/None atr_val OR a NaN one -- ``not float('nan')``
    is False in Python, so ``if not atr_val`` alone lets a NaN reading slip
    through and produce a garbage ratio (final-review Fix 8)."""
    return not atr_val or (isinstance(atr_val, float) and math.isnan(atr_val))


def _ratio(numerator: float, atr_val: float) -> float | None:
    if _bad_atr(atr_val):
        return None
    return round(abs(float(numerator)) / float(atr_val), 4)


def session_bucket(now: dt.datetime) -> str:
    t = now.time()
    if t < _OPEN_UNTIL:
        return "open"
    if t >= _CLOSE_FROM:
        return "close"
    return "midday"


def build(*, regime2_state, confidence_level, htf_bias, direction,
          confluence_count, entry, stop_loss, atr_val, close,
          rs_percentile, now, days_to_earnings=None) -> dict:
    return {
        "regime2_state": regime2_state,
        "confidence_level": confidence_level,
        # None, not False, when there is no bias reading -- "we did not know"
        # and "it disagreed" are different facts and must not pool.
        "htf_agree": None if htf_bias is None else bool(htf_bias == direction),
        "confluence_count": confluence_count,
        "stop_width_atr": _ratio(entry - stop_loss, atr_val),
        "atr_pct": (round(100.0 * float(atr_val) / float(close), 4)
                    if not _bad_atr(atr_val) and close else None),
        "rs_percentile": rs_percentile,
        "session_bucket": session_bucket(now),
        # Opportunistic: null unless v82's calendar is merged and wired. This
        # plan does not depend on v82 and must never block on it.
        "days_to_earnings": days_to_earnings,
    }
