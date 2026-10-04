"""v119 market-mode selector for the masked short compression-release strategy.

Broad (SPY bearish) and isolated (SPY not bearish, stock lagging its sector ETF)
are separate arms; a ticker is in at most one. Pure: the live caller passes only
data, the research caller reconstructs the same as-of frames and dated sector
mapping, never today's static sector map.

NO-LOOKAHEAD: each frame is cut to completed bars, then to dates <= the stock's
last completed date. A later sector/SPY bar can never change today's mode.
"""
from __future__ import annotations

import pandas as pd

from swingbot.core.scanning.strategy_pass import completed_frame

RETURN_WINDOW = 63


def _upto(frame, last):
    return frame[frame.index <= last]


def _return_63(frame) -> float:
    close = frame["Close"]
    return float(close.iloc[-1] / close.iloc[-1 - RETURN_WINDOW] - 1.0)


def _aligned(frame, last, reason):
    """Frame trimmed to `last`, or the rejection reason if it does not end there."""
    if frame is None or len(frame) == 0:
        return None, reason.replace("unaligned", "missing")
    trimmed = _upto(frame, last)
    if len(trimmed) == 0 or trimmed.index[-1] != last:
        return None, reason
    return trimmed, None


def compression_mode(stock, spy, sector, *, now, spy_regime) -> tuple[str | None, str | None]:
    """Return ("broad"|"isolated", None) or (None, rejection_reason) for the last completed bar."""
    stock = completed_frame(stock, now)
    if stock is None or len(stock) == 0:
        return None, "missing_stock"
    last = stock.index[-1]
    spy_ok, reason = _aligned(completed_frame(spy, now), last, "unaligned_spy")
    if reason:
        return None, reason
    if spy_regime.trend == "bearish":
        return "broad", None
    sector_ok, reason = _aligned(completed_frame(sector, now), last, "unaligned_sector")
    if reason:
        return None, reason
    if min(len(stock), len(sector_ok)) <= RETURN_WINDOW:
        return None, "short_history"
    if _return_63(stock) < _return_63(sector_ok):
        return "isolated", None
    return None, "not_sector_laggard"
