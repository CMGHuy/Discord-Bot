"""Per-bar market context, carried as namespaced columns on the ticker frame.

WHY COLUMNS AND NOT A PARAMETER
-------------------------------
`entries_for()` has accepted an optional `regimes` series since E24, but
nothing ever passed one: neither `run_backtest -> _vectorized_entries` nor
live `evaluate_all(ticker, df)` has a market dataframe anywhere in its call
chain. That left `apply_regime_gate` built, tested and permanently inert.

Threading a market series through ~15 signatures was the obvious fix and is
the one E24 deferred. It was rejected here on a technical ground rather than
a diff-size one: a separate series must be reindexed onto `df.index` at every
use, and a market-regime gate is precisely the feature where one off-by-one
leaks tomorrow's regime into today's entry -- the backtest looks excellent,
live underperforms, and nothing fails anywhere.

Attaching context as columns makes the alignment happen exactly once, here,
and makes it index-aligned to `df` *by construction*. The existing
NO-LOOKAHEAD discipline in entry_filters (`shift(+n)`, trailing `rolling`,
`.fillna(False)`) then covers context for free and is auditable the same way.
`tests/test_market_context.py::test_attach_is_truncation_invariant` is the
structural proof.

The cost of that choice is real: `df` is copied and sliced in several places,
and any path that rebuilds a frame without calling `attach` loses the block.
`get()` is what makes that survivable -- with the gate flag on, a missing
column raises instead of quietly opening the gate.

FAIL-CLOSED
-----------
`get()` returns None when the gate flag is off, which `apply_regime_gate`
already treats as "leave entries untouched". With the flag ON it raises
rather than degrading to None. A context gate that silently opens when its
data is missing is strictly worse than no gate at all, because it invites
trust in alerts that were never actually filtered.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.edge.regime2 import VOL_HISTORY, VOL_WINDOW, regime_series

# The full context block. `has_context()` is all-or-nothing over this tuple:
# a frame carrying only some of it is treated as carrying none, so a partial
# rebuild can never be mistaken for a complete one.
CTX_COLUMNS: tuple[str, ...] = ("ctx_regime", "ctx_rv_pct", "ctx_cot_z")

# Reserved for P2b (CFTC Traders in Financial Futures positioning). Declared
# now so adding it later never reshapes the block. Populated with NaN, which
# reads as "no data" everywhere downstream.
_RESERVED: tuple[str, ...] = ("ctx_cot_z",)


class MissingContextError(RuntimeError):
    """Raised when a gate is enabled but its context column is absent."""


def _rv_percentile(spy_df: pd.DataFrame) -> pd.Series:
    """SPY realized vol as its own trailing percentile (0..1).

    The continuous form of regime2's binary quiet/volatile split, reusing that
    module's windows so the two can never drift apart. Rank is over the
    trailing VOL_HISTORY bars *inclusive of the current one* -- a trailing
    window, so no lookahead.
    """
    rv = spy_df["Close"].pct_change().rolling(VOL_WINDOW).std()
    return rv.rolling(VOL_HISTORY, min_periods=VOL_WINDOW * 3).rank(pct=True)


def attach(df: pd.DataFrame, *, spy_df: pd.DataFrame,
           cot_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return a copy of `df` carrying the context block.

    Alignment is **ffill only** -- never bfill, never interpolate. SPY is the
    calendar; a ticker's index has holes (halts, late listings) and may start
    before SPY's history. Bars with no prior SPY observation stay NaN, and NaN
    blocks downstream, matching entry_filters' `.fillna(False)` convention.
    """
    if "Close" not in spy_df.columns:
        raise ValueError("spy_df must carry a 'Close' column to derive context from")
    if cot_df is not None:      # P2b; the parameter exists so the seam is stable
        raise NotImplementedError("ctx_cot_z is reserved for P2b (see spec section 6)")

    out = df.copy()
    for col, series in (("ctx_regime", regime_series(spy_df)),
                        ("ctx_rv_pct", _rv_percentile(spy_df))):
        out[col] = series.reindex(out.index, method="ffill")

    for col in _RESERVED:
        out[col] = np.nan

    return out


def attach_all(frames: dict, *, spy_df: pd.DataFrame) -> dict:
    """Stamp a whole {ticker: df} mapping -- the backtest half of the channel.

    Returns a new mapping; the input is not mutated. A frame that cannot be
    stamped is passed through unstamped rather than dropped, so a single odd
    ticker never silently shrinks a backtest universe. With the gate flag on,
    that ticker then raises at entries_for() instead of quietly trading
    ungated, which is the intended fail-closed behaviour.
    """
    out = {}
    for ticker, df in frames.items():
        if df is None or getattr(df, "empty", True):
            out[ticker] = df
            continue
        try:
            out[ticker] = attach(df, spy_df=spy_df)
        except Exception:
            out[ticker] = df
    return out


def has_context(df: pd.DataFrame) -> bool:
    """True only when the *entire* block is present -- see CTX_COLUMNS."""
    return all(col in df.columns for col in CTX_COLUMNS)


def get(df: pd.DataFrame, name: str) -> pd.Series | None:
    """Fetch one context column, failing closed.

    Returns None when the gate flag is off (`apply_regime_gate` short-circuits
    on None). Raises MissingContextError when the flag is on and the column is
    absent -- never degrades to None, which would silently open the gate.
    """
    if name not in CTX_COLUMNS:
        raise ValueError(f"{name!r} is not a declared context column; expected one of {CTX_COLUMNS}")

    from swingbot import config

    if not getattr(config, "REGIME_GATES_ENABLED", False):
        return None

    if name not in df.columns:
        raise MissingContextError(
            f"{name!r} is missing but REGIME_GATES_ENABLED is on. The frame reached "
            "the entry logic without market_context.attach() -- fix the caller rather "
            "than disabling the flag; a gate that opens when its data is missing is "
            "worse than no gate."
        )
    return df[name]
