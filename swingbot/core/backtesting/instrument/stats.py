"""Instrument v2 statistics (v136 spec §4).

The week-clustered bootstrap: trades are grouped by the ISO week of their
entry date across every ticker and whole weeks are resampled. Trades on one
symbol share a price path (why v1 clusters by ticker), but trades on
different symbols in one week share the market's move, which the ticker
bootstrap counts as independent. The week is the unit that prices both.

numpy only: scipy is NOT in requirements.txt. This module imports nothing
from ``acceptance``, so ``acceptance.cluster_bootstrap`` can import it lazily
for ``cluster="week"`` without an import cycle.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

import numpy as np

#: Pre-registered (spec §4): 10,000 replicates, seeded.
WEEK_BOOTSTRAP_RESAMPLES = 10_000
WEEK_BOOTSTRAP_SEED = 42


def iso_week_key(entry_date) -> str:
    """``"YYYY-Www"`` for an entry date (str, ``str(Timestamp)`` or date).

    A trade with no entry date cannot be placed in a week; refusing is the
    only honest answer, since a catch-all week would invent a cluster."""
    if entry_date is None or not str(entry_date).strip():
        raise ValueError("trade has no entry_date; it cannot be assigned an "
                         "ISO-week cluster")
    year, week, _ = date.fromisoformat(str(entry_date)[:10]).isocalendar()
    return f"{year}-W{week:02d}"


def group_by_week(trades) -> dict:
    """Trades keyed by ISO week of entry, pooled across every ticker."""
    out = defaultdict(list)
    for trade in trades:
        out[iso_week_key(getattr(trade, "entry_date", None))].append(trade)
    return out


def _draw(b_by, c_by, weeks, row):
    """Both arms' populations for one resample row of week indices."""
    b_draw, c_draw = [], []
    for j in row:
        b_draw.extend(b_by.get(weeks[j], ()))
        c_draw.extend(c_by.get(weeks[j], ()))
    return b_draw, c_draw


def week_cluster_bootstrap(baseline, component, statistic, *,
                           n_resamples: int = WEEK_BOOTSTRAP_RESAMPLES,
                           seed: int = WEEK_BOOTSTRAP_SEED) -> np.ndarray:
    """Resample WEEKS with replacement, recomputing ``statistic`` per draw.

    Same contract as ``acceptance.cluster_bootstrap``: both arms are
    resampled with the SAME week draw, so pairing survives; a draw where the
    statistic is undefined is dropped, never zero-filled."""
    b_by, c_by = group_by_week(baseline), group_by_week(component)
    weeks = sorted(set(b_by) | set(c_by))
    if not weeks:
        return np.array([])
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(weeks), size=(n_resamples, len(weeks)))
    out = []
    for row in picks:
        value = statistic(*_draw(b_by, c_by, weeks, row))
        if value is not None:
            out.append(value)
    return np.asarray(out, dtype=float)


def _checked_p(value) -> float:
    p = float(value)
    if not 0.0 <= p <= 1.0:   # also refuses NaN: every comparison is False
        raise ValueError(f"p-value must lie in [0, 1], got {value!r}")
    return p


def bh_qvalues(pvalues) -> list:
    """Benjamini-Hochberg step-up q-values, aligned with the input.

    ``q_(k) = min over j >= k of (m * p_(j) / j)``, capped at 1. ``None``
    (a pre-registration with no recorded p) passes through as ``None`` and
    does not count toward ``m``. Reported, never gating (v136 §4)."""
    values = list(pvalues)
    present = sorted(((i, _checked_p(p)) for i, p in enumerate(values)
                      if p is not None), key=lambda item: item[1])
    out = [None] * len(values)
    m = len(present)
    running = 1.0
    for rank in range(m, 0, -1):
        index, p = present[rank - 1]
        running = min(running, p * m / rank)
        out[index] = running
    return out
