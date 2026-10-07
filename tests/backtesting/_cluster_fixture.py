"""Shared pinned arms for the v138 cluster-unit tests (not a test module).

12 tickers x 15 trades over 120 calendar days (14 ISO weeks), win R varying
by ticker so neither clustering unit is degenerate. The component drops the
trades where (t * k) % 7 == 0 and flips some losses to wins."""
from datetime import date, timedelta

from swingbot.core.backtesting.acceptance import ArmTrade

FAST = dict(n_resamples=300, seed=42)


def _arm(t, day, win):
    entry = date(2021, 1, 4) + timedelta(days=day)
    return ArmTrade(ticker=f"T{t}", strategy="MACD", horizon_key="3m",
                    entry_date=entry.isoformat(), outcome="win" if win else "loss",
                    r_multiple=(1.0 + 0.5 * (t % 4)) if win else -1.0,
                    planned_rr=2.0, direction="bullish")


def pinned_arms():
    base, comp = [], []
    for t in range(12):
        for k in range(15):
            day = (t * 5 + k * 3) % 120
            base.append(_arm(t, day, (t + k) % 3 == 0))
            if (t * k) % 7 != 0:
                comp.append(_arm(t, day, (t + k) % 3 == 0 or k % 5 == 1))
    return base, comp
