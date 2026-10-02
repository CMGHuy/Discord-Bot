"""Weakness-mode selection for the SHORT extra-universe lane (bearish only).

Pure: never reads or writes ``rs_cache.json`` and never touches base breadth.
The bar it may see is the last completed bar common to stock, SPY and (for
isolated weakness) the sector ETF.
"""
from __future__ import annotations

import numpy as np

from swingbot import config
from swingbot.core.scanning.short_reference import (align_completed,
                                                    completed_frame, return_63)

MIN_PANEL_SYMBOLS = 5


def _has_bars(frame) -> bool:
    return frame is not None and len(frame) > 0


def _rel(stock, spy) -> float:
    return return_63(stock) - return_63(spy)


def build_reference_rels(frames: dict, spy, now) -> list[float]:
    """Stock-minus-SPY 63d returns over aligned windows; invalid symbols skipped."""
    rels = []
    for frame in frames.values():
        aligned = align_completed(frame, spy, None, now)
        if aligned is not None:
            rels.append(_rel(aligned[0], aligned[1]))
    return rels


def _alignment_failure(stock, spy, sector, need_sector: bool, now) -> str | None:
    """Named reason the three frames cannot share one completed window."""
    stock_c, spy_c = completed_frame(stock, now), completed_frame(spy, now)
    if not _has_bars(stock_c):
        return "missing_stock"
    if not _has_bars(spy_c):
        return "missing_spy"
    if stock_c.index[-1].date() != spy_c.index[-1].date():
        return "unaligned_spy"
    if need_sector and not _has_bars(sector):
        return "missing_sector"
    return None


def _sector_failure(stock, sector, now) -> str | None:
    sector_c = completed_frame(sector, now)
    if not _has_bars(sector_c):
        return "missing_sector"
    if sector_c.index[-1].date() != completed_frame(stock, now).index[-1].date():
        return "unaligned_sector"
    return None


def _percentile(rel: float, reference_rels) -> float:
    return 100.0 * float(np.mean([rel >= r for r in reference_rels]))


def _broad(stock, spy, reference_rels):
    if len(reference_rels) < MIN_PANEL_SYMBOLS:
        return None, "empty_panel"
    pct = _percentile(_rel(stock, spy), reference_rels)
    if pct <= config.RS_LAGGARD_PERCENTILE:
        return "broad", None
    return None, "not_laggard"


def _isolated(stock, sector):
    if return_63(stock) < return_63(sector):
        return "isolated", None
    return None, "not_laggard"


def select_mode(stock, spy, sector, *, spy_regime, reference_rels, now=None):
    """('broad'|'isolated', None) or (None, stable_rejection_reason)."""
    bearish = spy_regime.trend == "bearish"
    reason = _alignment_failure(stock, spy, sector, not bearish, now)
    if reason is None and not bearish:
        reason = _sector_failure(stock, sector, now)
    if reason is not None:
        return None, reason
    aligned = align_completed(stock, spy, None if bearish else sector, now)
    if aligned is None:
        return None, "short_history"
    stock_a, spy_a, sector_a = aligned
    if bearish:
        return _broad(stock_a, spy_a, reference_rels)
    return _isolated(stock_a, sector_a)
