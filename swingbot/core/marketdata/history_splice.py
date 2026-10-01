"""Give a shallow live daily frame the deep history the on-disk cache holds.

A cold ticker is fetched live (Alpaca reaches back only to 2016, yfinance
only `period`), while its stale cache file keeps the full archive. The
scanner builds levels and the long-horizon strategies from long history, so a
live-only frame finds far fewer setups. This returns cached-older-rows + live.

NO-LOOKAHEAD: only cached bars strictly BEFORE the live frame's first bar are
used, so nothing is ever placed after the live frame's last bar -- the
(possibly partial) today bar stays the last row, and live wins on overlap.
"""
import logging

import pandas as pd

from swingbot.core.marketdata.adjustments import (
    _ADJUSTMENT_MISMATCH_TOLERANCE, _MIN_OVERLAP_BARS)

log = logging.getLogger(__name__)

_NOTHING_OLDER = "cache holds nothing older than the live frame"


def _comparable(live, cached) -> bool:
    """Same column set and the same index tz-ness -- never splice across."""
    return (set(live.columns) == set(cached.columns)
            and live.index.tz == cached.index.tz)


def _bases_agree(live, cached) -> bool:
    """True only when >= _MIN_OVERLAP_BARS shared bars have closes within the
    corporate-action tolerance (median ratio): a split/dividend rescales the
    whole history, so an unproven or disagreeing basis must not be spliced."""
    common = live.index.intersection(cached.index)
    if len(common) < _MIN_OVERLAP_BARS:
        return False
    ratios = (live.loc[common, "Close"] / cached.loc[common, "Close"]).dropna()
    ratios = ratios[ratios > 0]
    if ratios.empty:
        return False
    return abs(float(ratios.median()) - 1.0) <= _ADJUSTMENT_MISMATCH_TOLERANCE + 1e-9


def _refusal(live, cached) -> str | None:
    """Why the splice must not happen, or None when it may."""
    if not _comparable(live, cached):
        return "column set or index tz differs"
    if cached.index.min() >= live.index.min():
        return _NOTHING_OLDER
    if not _bases_agree(live, cached):
        return "overlap closes disagree or overlap too short (adjustment basis unproven)"
    return None


def splice_cached_history(live, cached, symbol: str):
    """`live` (wins on overlap) extended backwards with `cached`'s older bars;
    `live` itself, unchanged, whenever the splice is not provably safe."""
    if live is None or live.empty or cached is None or cached.empty:
        return live
    reason = _refusal(live, cached)
    if reason is not None:
        if reason == _NOTHING_OLDER:
            return live                  # the common warm case: nothing to say
        log.info("%s: not splicing cached history under the live frame (%s)", symbol, reason)
        return live
    older = cached.loc[cached.index < live.index.min(), list(live.columns)]
    out = pd.concat([older, live])
    out.index.name = live.index.name
    out.attrs = dict(live.attrs)
    return out
