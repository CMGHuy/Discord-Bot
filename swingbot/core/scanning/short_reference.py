"""Strict date-aligned reference windows for the SHORT extra-universe lane.

Bar-knowledge rule: a value here may see only completed daily bars that share
one calendar date across stock, SPY and sector. The base lane's
``edge/factors.relative_return`` compares terminal positions even when dates
differ; this module never does.
"""
from __future__ import annotations

import pandas as pd

from swingbot.core.scanning.strategy_pass import completed_frame

WINDOW_BARS = 64      # 63-day return needs 64 closes


def etf_for_sector(sector: str | None) -> str | None:
    """Sector name -> SPDR ETF symbol, via the one existing mapping."""
    if not sector:
        return None
    from swingbot.core.scanning.fetch import _etf_symbol_of_sector
    return _etf_symbol_of_sector().get(sector)


def _usable(frame: pd.DataFrame | None) -> bool:
    return frame is not None and len(frame) > 0


def last_date_matches(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    return a.index[-1].date() == b.index[-1].date()


def align_completed(stock, spy, sector, now):
    """Completed, date-intersected (stock, spy, sector|None) or None."""
    stock, spy = completed_frame(stock, now), completed_frame(spy, now)
    if not _usable(stock) or not _usable(spy) or not last_date_matches(stock, spy):
        return None
    common = stock.index.intersection(spy.index)
    if sector is not None:
        sector = completed_frame(sector, now)
        if not _usable(sector) or not last_date_matches(stock, sector):
            return None
        common = common.intersection(sector.index)
    if len(common) < WINDOW_BARS:
        return None
    return (stock.loc[common], spy.loc[common],
            None if sector is None else sector.loc[common])


def return_63(frame: pd.DataFrame) -> float:
    close = frame["Close"]
    return float(close.iloc[-1] / close.iloc[-WINDOW_BARS] - 1.0)
