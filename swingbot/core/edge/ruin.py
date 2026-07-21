"""Bootstrap Monte Carlo over the realized R distribution.

Resamples the bot's OWN closed-trade R multiples (no distributional
assumptions -- fat tails included exactly as observed), compounds
`n_paths` equity paths of `n_trades` each, and reports the percentiles
that matter for survival. `ruin` is deliberately conservative: halving
the account (equity < 0.5x start at ANY point) is treated as ruin,
because in practice the operator intervenes/abandons long before zero.
"""
from __future__ import annotations

import numpy as np

RUIN_THRESHOLD = 0.5   # equity multiple below which a path counts as ruined
TARGET_MULTIPLE = 10.0


def simulate(r_multiples: list[float], *, risk_pct: float,
             n_trades: int = 1000, n_paths: int = 2000, seed: int = 42) -> dict:
    r = np.asarray(list(r_multiples), dtype=float)
    if r.size == 0:
        raise ValueError("need at least one closed trade to bootstrap from")

    rng = np.random.default_rng(seed)
    draws = rng.choice(r, size=(n_paths, n_trades), replace=True)
    growth = 1.0 + (risk_pct / 100.0) * draws
    # A single trade can't lose more than 100% of equity even at absurd risk.
    np.clip(growth, 0.0, None, out=growth)
    equity = np.cumprod(growth, axis=1)

    peaks = np.maximum.accumulate(equity, axis=1)
    max_dd = 1.0 - (equity / peaks).min(axis=1)          # per-path max drawdown, fraction
    final = equity[:, -1]

    return {
        "p50_final_multiple": float(np.percentile(final, 50)),
        "p05_final_multiple": float(np.percentile(final, 5)),
        "max_dd_p50": float(np.percentile(max_dd, 50)),
        "max_dd_p95": float(np.percentile(max_dd, 95)),
        "p_ruin": float((equity.min(axis=1) < RUIN_THRESHOLD).mean()),
        "p_10x": float((equity.max(axis=1) >= TARGET_MULTIPLE).mean()),
    }
