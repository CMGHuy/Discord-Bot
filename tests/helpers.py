"""Synthetic OHLCV builder with per-bar High/Low control.

Complements conftest.make_ohlcv (float-only, spread-derived High/Low):
this variant accepts (open, high, low, close) tuples so exit-model tests
can place highs/lows exactly on stop/target/trigger levels.
"""
import pandas as pd


def make_ohlcv(closes, *, start="2024-01-02", spread=0.01, volume=1_000_000):
    """Build a daily OHLCV frame from floats or (open, high, low, close) tuples."""
    rows = []
    for c in closes:
        if isinstance(c, (tuple, list)):
            o, h, l, cl = (float(x) for x in c)
        else:
            o = cl = float(c)
            h, l = cl * (1 + spread), cl * (1 - spread)
        rows.append((o, h, l, cl, float(volume)))
    idx = pd.bdate_range(start=start, periods=len(rows))
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=idx)
