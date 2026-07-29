"""% of the scan universe above its 50/200 DMA.

Capability check performed 2026-07-29 (the task told us to wrap edge-engine
E28 if it had landed): `swingbot.core.edge.factors.breadth_pct_above_50ema`
does exist, but it is a *different statistic* — % above the 50-**EMA**, with
a 60-bar minimum and a BREADTH_MIN_TICKERS floor. This module needs the
50/200 **SMA** pair with a 200-bar minimum, so wrapping E28 would silently
change what the number means. Deliberately computed here instead; if the two
ever need to agree, that is a decision to make explicitly, not by import.
"""
from __future__ import annotations


def breadth(bars: dict) -> dict:
    above50 = above200 = n = 0
    for df in bars.values():
        closes = df["Close"]
        if len(closes) < 200:
            continue
        n += 1
        above50 += bool(closes.iloc[-1] > closes.rolling(50).mean().iloc[-1])
        above200 += bool(closes.iloc[-1] > closes.rolling(200).mean().iloc[-1])
    if n == 0:
        return {"pct_above_50dma": None, "pct_above_200dma": None, "n": 0}
    return {"pct_above_50dma": round(100.0 * above50 / n, 1),
            "pct_above_200dma": round(100.0 * above200 / n, 1), "n": n}


def breadth_state(b: dict) -> str:
    pct = b.get("pct_above_50dma")
    if pct is None:
        return "unknown"
    if pct >= 60:
        return "healthy"
    if pct <= 40:
        return "weak"
    return "mixed"
