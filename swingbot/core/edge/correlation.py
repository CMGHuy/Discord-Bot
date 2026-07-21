"""Correlation-aware exposure: three 'different' trades that are 0.9-
correlated are one trade at 3x size. Positions whose 90-day daily-returns
correlation with a candidate exceeds THRESHOLD count their heat against
the candidate's cluster budget (CORRELATED_HEAT_CAP_PCT). When price
history is too thin to correlate, same-sector membership (universe file
tags, E13) is the conservative fallback."""
from __future__ import annotations

import pandas as pd

from swingbot import config
from swingbot.core.edge.heat import trade_risk_pct

MIN_OVERLAP_BARS = 30
DEFAULT_THRESHOLD = 0.75


def returns_corr(df_a: pd.DataFrame, df_b: pd.DataFrame, window: int = 90) -> float | None:
    ra = df_a["Close"].pct_change().dropna().tail(window)
    rb = df_b["Close"].pct_change().dropna().tail(window)
    joined = pd.concat([ra, rb], axis=1, join="inner").dropna()
    if len(joined) < MIN_OVERLAP_BARS:
        return None
    return float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))


def cluster_exposure(open_trades: list, candidate_ticker: str,
                     dfs: dict, balance: float, *, window: int = 90,
                     threshold: float = DEFAULT_THRESHOLD,
                     sectors: dict | None = None) -> dict:
    cand_df = dfs.get(candidate_ticker)
    cluster, correlated_heat, max_corr = [], 0.0, 0.0
    for t in open_trades:
        tick = t.get("ticker")
        corr = None
        if cand_df is not None and tick in dfs:
            corr = returns_corr(cand_df, dfs[tick], window)
        in_cluster = corr is not None and corr > threshold
        if corr is None and sectors:
            # thin data -> conservative sector fallback
            in_cluster = (sectors.get(tick) is not None
                          and sectors.get(tick) == sectors.get(candidate_ticker))
        if corr is not None:
            max_corr = max(max_corr, corr)
        if in_cluster:
            cluster.append(tick)
            correlated_heat += trade_risk_pct(t, balance)
    return {"cluster": cluster, "correlated_heat": round(correlated_heat, 3),
            "max_corr": round(max_corr, 3)}


def cluster_check(exposure: dict, candidate_risk_pct: float,
                  cap_pct: float | None = None) -> dict:
    cap = cap_pct if cap_pct is not None else getattr(config, "CORRELATED_HEAT_CAP_PCT", 3.0)
    remaining = max(0.0, cap - exposure["correlated_heat"])
    return {"allowed": candidate_risk_pct <= remaining + 1e-9,
            "remaining": round(remaining, 3), "cap": cap, **exposure}
