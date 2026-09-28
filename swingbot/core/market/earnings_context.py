"""v104: per-bar earnings columns for the short strategies (spec §3.3, §3.4).

evt_reaction      1.0 on a reaction session (the first session that trades on
                  the report), else 0.0.
evt_bars_to_next  bars from this bar to the next reaction session (0 = this bar
                  is one); NaN when no later report is known.

Reaction mapping follows earnings_calendar.reaction_session on the frame's OWN
bar grid -- before_open reacts on the report date's bar, after_close and
unconfirmed on the next bar -- so it needs no exchange calendar and runs
offline. A report after the last bar is placed by business days past it.

LOOKAHEAD NOTE (deliberate, spec §3.4 / v82 precedent): evt_bars_to_next reads
the next SCHEDULED report date. Companies announce dates weeks ahead, so the
date is knowable at the bar; the report's CONTENT is never read. evt_reaction
looks at the current bar only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.market import earnings_calendar as ec

EVT_COLUMNS = ("evt_reaction", "evt_bars_to_next")


def _position(days: pd.DatetimeIndex, report) -> int:
    ts = pd.Timestamp(report.date)
    side = "left" if report.timing == ec.BEFORE_OPEN else "right"
    pos = int(days.searchsorted(ts, side=side))
    if pos < len(days):
        return pos
    first_after = days[-1] + pd.offsets.BDay(1)
    reaction = ts if report.timing == ec.BEFORE_OPEN else ts + pd.offsets.BDay(1)
    return len(days) - 1 + len(pd.bdate_range(first_after, reaction))


def reaction_positions(index: pd.DatetimeIndex, reports) -> list[int]:
    days = pd.DatetimeIndex(index).normalize()
    if len(days) == 0:
        return []
    return sorted({_position(days, report) for report in reports})


def attach(df: pd.DataFrame, ticker: str, *, source=None) -> pd.DataFrame:
    """Return a copy of `df` carrying EVT_COLUMNS for `ticker`."""
    source = source if source is not None else ec.CsvSource()
    out = df.copy()
    n = len(out)
    positions = np.asarray(reaction_positions(out.index, source.reports(ticker)), dtype=int)
    reaction = np.zeros(n)
    reaction[positions[positions < n]] = 1.0
    bars = np.full(n, np.nan)
    if len(positions):
        here = np.arange(n)
        nxt = np.searchsorted(positions, here, side="left")
        known = nxt < len(positions)
        bars[known] = positions[nxt[known]] - here[known]
    out["evt_reaction"] = reaction
    out["evt_bars_to_next"] = bars
    return out
