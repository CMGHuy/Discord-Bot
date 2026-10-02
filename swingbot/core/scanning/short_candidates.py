"""Weakness-mode selection for the SHORT extra-universe lane (bearish only).

Pure: never reads or writes ``rs_cache.json`` and never touches base breadth.
The bar it may see is the last completed bar common to stock, SPY and (for
isolated weakness) the sector ETF.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

import numpy as np

from swingbot import config
from swingbot.core.marketdata.universe import ShortSnapshot
from swingbot.core.scanning.short_reference import (align_completed,
                                                    completed_frame,
                                                    etf_for_sector, return_63)

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


# --- V118-3: candidate contract ------------------------------------------------
SOURCE = "short_universe"


@dataclass(frozen=True)
class ShortCandidate:
    ticker: str
    mode: Literal["broad", "isolated"]
    source: str
    decision_bar_date: str
    membership_asof: str
    reference_id: str


@dataclass(frozen=True)
class ShortReference:
    """Everything the extra lane reads, frozen at scan start.

    `frames` holds the extra symbols' completed-bar frames only; the base
    frames dict is never merged into it or mutated.
    """
    frames: Mapping[str, object]
    spy: object
    sector_frames: Mapping[str, object]
    spy_regime: object | None
    reference_rels: tuple[float, ...]
    now: object
    reference_id: str


def extra_symbols(snapshot: ShortSnapshot, base_tickers: Sequence[str]) -> tuple[str, ...]:
    """Snapshot members not already scanned by the base lane (base wins ties)."""
    base = set(base_tickers)
    return tuple(symbol for symbol in snapshot.symbols if symbol not in base)


def _input_failure(snapshot, reference) -> str | None:
    if snapshot is None:
        return "no_snapshot"
    if reference is None or reference.spy is None:
        return "no_reference"
    if reference.spy_regime is None:
        return "missing_regime"
    return None


def _candidate_for(symbol, snapshot, reference, rejected=None) -> ShortCandidate | None:
    frame = reference.frames.get(symbol)
    sector_etf = etf_for_sector(snapshot.sector_of.get(symbol))
    mode, reason = select_mode(
        frame, reference.spy, reference.sector_frames.get(sector_etf),
        spy_regime=reference.spy_regime, reference_rels=reference.reference_rels,
        now=reference.now)
    if mode is None:
        if rejected is not None:
            rejected.append((symbol, reason))   # V118-5: the reason is the funnel's, not discarded
        return None
    bar_date = completed_frame(frame, reference.now).index[-1].date().isoformat()
    return ShortCandidate(symbol, mode, SOURCE, bar_date, snapshot.membership_asof,
                          reference.reference_id)


def extra_candidates(base_tickers, snapshot, reference, rejected=None):
    """([ShortCandidate, ...], None) or ([], stable_reason).

    `rejected`, when given, collects (symbol, stable_reason) for every symbol
    select_mode turned down."""
    reason = _input_failure(snapshot, reference)
    if reason is not None:
        return [], reason
    found = (_candidate_for(s, snapshot, reference, rejected)
             for s in extra_symbols(snapshot, base_tickers))
    return [c for c in found if c is not None], None
