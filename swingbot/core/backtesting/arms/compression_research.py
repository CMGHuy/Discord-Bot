"""v119-10: the compression short's research cohort and its explicit offline as-of inputs.

`offline_context()` is what `StrategyEngine` reads under ``COMPRESSION_SHORT_RESEARCH_MODE``
when no context was injected: cached SPY, point-in-time S&P 500 membership
(`data/universe/sp500_membership.csv`), the dated sector mapping
(`data/universe/sp500_sector_history.csv`, mapped to its SPDR ETF through the live
sector->ETF table) and observed-as-of earnings snapshots. Every missing input rejects the
candidate with a recorded reason; none is filled from today's facts.

NO-LOOKAHEAD: no historical archive of earnings calendars *as they were observed* exists.
The `market_data/earnings` CSVs hold final report dates, which is what became known later,
not what was on the calendar at the signal date -- so `snapshot_of` returns None and the
shared decision excludes the candidate as `earnings_unknown`. It never reads those CSVs.

`measure_compression_short()` runs one mode's cohort through the same `StrategyEngine`
the producer stamps and returns the supplemental diagnostics (signal/entry dates, mode,
exclusion totals, exit reasons, the `daily_close_proxy` label) beside the unchanged
`ArmTrade` rows.
"""
from __future__ import annotations

import datetime as dt
import os
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

import pandas as pd

from swingbot.core.backtesting.arms.knobs import apply_knobs
from swingbot.core.backtesting.arms.strategy_engine import (RESEARCH_KNOB, CompressionResearchContext,
                                                           StrategyEngine)
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.planning.time_exit import PROXY_BASIS

MEASURED_MODES = ("broad", "isolated")
MEMBERSHIP_FILE = "sp500_membership.csv"
SECTOR_HISTORY_FILE = "sp500_sector_history.csv"


@dataclass
class CompressionMeasurement:
    """One research mode's cohort. `trades` are the stamped-shape rows; the rest is supplemental."""

    mode: str
    trades: list
    signal_diagnostics: list
    diagnostics: Counter
    diagnostics_by_mode: Counter
    exit_reasons: Counter
    close_price_basis: str = PROXY_BASIS
    notes: list = field(default_factory=list)

    def break_even_borrow_fee(self) -> float | None:
        """Annual borrow fee (fraction of entry value) at which the cohort's summed R is zero.

        f = sum(r) / sum(entry / |entry - stop| * calendar_days_held / 365), min one day per trade;
        0.0 when the summed R is already <= 0, None with no filled trade. No borrow history is implied.
        """
        rows = [r for r in self.signal_diagnostics if r["r_multiple"] is not None]
        exposure = sum(_fee_exposure(r) for r in rows)
        if not rows or exposure <= 0:
            return None
        return max(0.0, sum(r["r_multiple"] for r in rows) / exposure)


def _fee_exposure(row: dict) -> float:
    risk = abs(row["entry_price"] - row["stop_loss"])
    if risk <= 0:
        return 0.0
    days = (dt.date.fromisoformat(row["exit_date"]) - dt.date.fromisoformat(row["entry_date"])).days
    return row["entry_price"] / risk * max(1, days) / 365.0


def measure_compression_short(frames: dict, window: tuple[str, str], *, mode: str,
                              context: CompressionResearchContext, horizons=("2w",)) -> CompressionMeasurement:
    """Replay one mode's cohort over `frames` with the research knob set to `mode`."""
    if mode not in MEASURED_MODES:
        raise ValueError(f"mode must be one of {MEASURED_MODES}, got {mode!r}")
    from swingbot.scan_params import ScanParams
    with apply_knobs({RESEARCH_KNOB: mode}):
        params = ScanParams.from_config()
        engine = StrategyEngine((COMPRESSION_SHORT,), compression_context=context)
        trades = [trade for ticker in sorted(frames)
                  for trade in engine.run_ticker(ticker, frames[ticker], horizons, window, params)]
    return CompressionMeasurement(
        mode=mode, trades=trades, signal_diagnostics=list(engine.compression_signals),
        diagnostics=Counter(engine.compression_reasons),
        diagnostics_by_mode=Counter(engine.compression_reasons_by_mode),
        exit_reasons=Counter(engine.compression_exit_reasons))


# --- the explicit offline as-of loader ------------------------------------------------------

def _cached_frame(symbol: str) -> pd.DataFrame | None:
    """A symbol's frame from the backtest CSV cache, or None (offline only, never a fetch)."""
    from swingbot.core.marketdata.backtest_cache import cache_path
    path = cache_path(symbol)
    if not path.exists():
        return None
    frame = pd.read_csv(path, index_col="Date", parse_dates=True)
    return frame if len(frame) else None


@lru_cache(maxsize=1)
def _membership() -> dict:
    from swingbot.core.marketdata import universe
    from swingbot.core.marketdata.pit_membership import load_intervals
    return load_intervals(os.path.join(universe.UNIVERSE_DIR, MEMBERSHIP_FILE))


@lru_cache(maxsize=1)
def _sector_spans() -> dict:
    from swingbot.core.marketdata import universe
    return universe._load_sector_intervals(os.path.join(universe.UNIVERSE_DIR, SECTOR_HISTORY_FILE))


@lru_cache(maxsize=1)
def _etf_of_sector() -> dict:
    from swingbot.core.scanning.fetch import _etf_symbol_of_sector
    return _etf_symbol_of_sector()


@lru_cache(maxsize=64)
def _frame(symbol: str):
    return _cached_frame(symbol)


def clear_offline_caches() -> None:
    for cached in (_membership, _sector_spans, _etf_of_sector, _frame):
        cached.cache_clear()


def member_on(ticker: str, day: dt.date) -> bool:
    """Index member on `day` by the dated intervals; a ticker with no interval is not a member."""
    from swingbot.core.marketdata.pit_membership import is_member
    spans = _membership().get(ticker)
    return bool(spans) and is_member(day.isoformat(), spans)


def sector_on(ticker: str, day: dt.date):
    """The ETF frame of the sector `ticker` was mapped to on `day`, or None when unmapped/uncached."""
    from swingbot.core.marketdata.universe import _sector_on
    sector = _sector_on(day.isoformat(), _sector_spans().get(ticker, []))
    etf = _etf_of_sector().get(sector) if sector else None
    return _frame(etf) if etf else None


def no_asof_snapshot(ticker: str, decided_at: dt.datetime):
    """No observed-as-of earnings archive exists: unknown, never assumed clear."""
    return None


def offline_context() -> CompressionResearchContext:
    """The research engine's explicit as-of inputs, read from local files only."""
    from swingbot import config
    spy = _frame(config.MARKET_REGIME_TICKER)
    return CompressionResearchContext(
        spy=spy if spy is not None else pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"]),
        sector_of=lambda ticker: None, snapshot_of=no_asof_snapshot,
        member_on=member_on, sector_on=sector_on)
