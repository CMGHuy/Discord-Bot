"""Offline audit of the quality score against realized TRAIN outcomes.
Part 1 (Task 52): decile table. Part 2 (Task 53): numpy logistic audit.
NEVER imported by swingbot/ -- tests enforce that."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swingbot.core import quality
from swingbot.core.backtest import ALL_STRATEGIES, run_backtest
from swingbot.core.plan_engine import build_strategy_plan
from swingbot.core.registry import get_badge
from swingbot.core.strategy_types import HORIZONS, MIN_BARS

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "backtest_cache"
TRAIN = ("2020-01-01", "2023-12-31")


def collect_scored_trades() -> list[dict]:
    """One row per TRAIN trade: the 7 quality component inputs (computed
    as-of the entry bar, no lookahead) + the realized outcome."""
    rows = []
    frames = {p.stem: pd.read_csv(p, index_col="Date", parse_dates=True)
              for p in sorted(CACHE_DIR.glob("*.csv"))}
    for ticker, df in frames.items():
        vol_ratio_series = df["Volume"] / df["Volume"].rolling(20).mean()
        for hk in HORIZONS:
            for strategy in ALL_STRATEGIES:
                s = run_backtest(ticker, df, strategy, hk, exit_model="v2",
                                 scale_out=True)
                date_to_idx = {str(d.date()): k for k, d in enumerate(df.index)}
                for t in s.trades:
                    if not (TRAIN[0] <= t.entry_date <= TRAIN[1]):
                        continue
                    i = date_to_idx[t.entry_date]
                    window = df.iloc[:i + 1]
                    badge = get_badge("strategy", strategy)
                    q = quality.score_plan(
                        direction=t.direction,
                        regime=None,                       # offline: no SPY regime feed
                        htf_bias=None,
                        confluence_count=0,                # strategy-source trades
                        volume_ratio=float(vol_ratio_series.iloc[i]),
                        atr_pct=quality.atr_percentile(window),
                        trigger_distance_pct=0.0,          # market entries
                        badge_status=badge.status)
                    rows.append({"score": q.score,
                                 "components": dict(q.breakdown),
                                 "outcome": t.outcome,
                                 "r": t.r_multiple})
    return rows


def decile_table(rows: list[dict]) -> None:
    print(f"{'decile':<8} {'N':>5} {'WR%':>6} {'ExpR':>7}")
    for lo in range(0, 100, 10):
        bucket = [r for r in rows if lo <= r["score"] < lo + 10 or
                  (lo == 90 and r["score"] == 100)]
        ev = [r for r in bucket if r["outcome"] in ("win", "loss")]
        wins = sum(1 for r in ev if r["outcome"] == "win")
        wr = wins / len(ev) * 100 if ev else float("nan")
        expr = np.mean([r["r"] for r in bucket]) if bucket else float("nan")
        print(f"{lo:>2}-{lo + 9:<5} {len(bucket):>5} {wr:>6.1f} {expr:>+7.3f}")


COMPONENT_NAMES = ["regime", "htf", "confluence", "volume",
                   "atr_percentile", "trigger_distance", "badge"]


def logistic_audit(rows: list[dict]) -> int:
    """Gradient-descent logistic regression, no sklearn. Returns exit code:
    1 when any component coefficient is significantly NEGATIVE (|z| > 2) --
    a component actively hurting the score."""
    ev = [r for r in rows if r["outcome"] in ("win", "loss")]
    X = np.array([[r["components"][c] for c in COMPONENT_NAMES] for r in ev],
                 dtype=float)
    y = np.array([1.0 if r["outcome"] == "win" else 0.0 for r in ev])
    # standardize so one learning rate fits all columns
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    Xs = np.c_[np.ones(len(X)), (X - mu) / sd]

    w = np.zeros(Xs.shape[1])
    for _ in range(20_000):
        p = 1 / (1 + np.exp(-Xs @ w))
        w -= 0.05 * (Xs.T @ (p - y)) / len(y)

    # standard errors from the Fisher information matrix
    p = 1 / (1 + np.exp(-Xs @ w))
    W = p * (1 - p)
    cov = np.linalg.pinv(Xs.T @ (Xs * W[:, None]))
    se = np.sqrt(np.diag(cov))
    z = w / np.where(se == 0, np.inf, se)

    bad = 0
    print(f"\n{'component':<18} {'coef':>8} {'z':>7}")
    for name, coef, zval in zip(["intercept"] + COMPONENT_NAMES, w, z):
        flag = ""
        if name != "intercept" and coef < 0 and abs(zval) > 2:
            flag, bad = "  << HURTING", bad + 1
        print(f"{name:<18} {coef:>8.3f} {zval:>7.2f}{flag}")
    return 1 if bad else 0


if __name__ == "__main__":
    rows = collect_scored_trades()
    decile_table(rows)
    sys.exit(logistic_audit(rows))
