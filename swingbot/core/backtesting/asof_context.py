"""v93 point-in-time cross-sectional inputs for entry-context snapshots."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from swingbot.core.edge.factors import RS_WINDOW
from swingbot.core.edge.regime2 import regime_series

COLUMNS = ("regime2_state", "rs_pctile", "sector_pctile", "rs_combined")


def _rel_series(df: pd.DataFrame, spy: pd.DataFrame, window: int) -> pd.Series:
    ticker_return = df["Close"] / df["Close"].shift(window) - 1.0
    spy_return = (spy["Close"] / spy["Close"].shift(window) - 1.0).reindex(df.index, method="ffill")
    return ticker_return - spy_return


def _pct_rank_rows(matrix: pd.DataFrame) -> pd.DataFrame:
    """Per-date percentile, matching ``factors.rs_percentile`` including ties."""
    return (matrix.rank(axis=1, method="max", pct=True) * 100.0).round(1)


def build_asof(frames: dict, spy_df: pd.DataFrame, *, sector_of_ticker: dict,
               sector_etf_frames: dict, sector_of_etf: dict,
               window: int = RS_WINDOW) -> dict:
    """Build no-lookahead cross-sectional values for each loaded symbol."""
    rels = pd.DataFrame({symbol: _rel_series(df, spy_df, window) for symbol, df in frames.items()})
    rs = _pct_rank_rows(rels)
    etf_rels = pd.DataFrame({symbol: _rel_series(df, spy_df, window)
                             for symbol, df in sector_etf_frames.items()})
    etf_rank = (_pct_rank_rows(etf_rels) if len(etf_rels.columns) >= 2
                else pd.DataFrame(index=etf_rels.index))
    etf_of_sector = {sector: etf for etf, sector in sector_of_etf.items()}
    regime = regime_series(spy_df)
    result = {}
    for symbol, df in frames.items():
        row = pd.DataFrame(index=df.index)
        row["regime2_state"] = regime.reindex(df.index, method="ffill")
        row["rs_pctile"] = rs[symbol].reindex(df.index)
        etf = etf_of_sector.get(sector_of_ticker.get(symbol))
        if etf in etf_rank.columns:
            row["sector_pctile"] = etf_rank[etf].reindex(df.index, method="ffill")
        else:
            row["sector_pctile"] = np.nan
        combined = 0.7 * row["rs_pctile"] + 0.3 * row["sector_pctile"]
        row["rs_combined"] = combined.where(row["sector_pctile"].notna(), row["rs_pctile"])
        result[symbol] = row
    return result


def asof_row(asof_df: pd.DataFrame | None, ts) -> dict:
    """Return a JSON-safe context row at ``ts``, or no values when absent."""
    if asof_df is None or ts not in asof_df.index:
        return {}
    row = asof_df.loc[ts]

    def clean(value):
        if isinstance(value, str):
            return value
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return None if math.isnan(value) else value

    return {key: clean(row[key]) for key in COLUMNS}
