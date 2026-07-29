"""VIX level, trailing-1y percentile, regime bands, term structure."""
from __future__ import annotations

from swingbot.core.macro import fred

_REGIME_BANDS = ((16.0, "calm"), (24.0, "normal"), (32.0, "elevated"))


def _regime(level: float) -> str:
    for cut, name in _REGIME_BANDS:
        if level < cut:
            return name
    return "stress"


def vix_state(loader=None) -> dict | None:
    """loader (optional): ticker -> daily OHLCV frame; used as a ^VIX
    cached-bars fallback when FRED's VIXCLS is unavailable."""
    series = fred.fred_series("VIXCLS")
    if not series and loader is not None:
        bars = loader("^VIX")
        if bars is not None and len(bars):
            series = [(str(idx.date()), float(v))
                      for idx, v in bars["Close"].items()]
    if not series:
        return None
    closes = [v for _, v in series]
    level = closes[-1]
    window = closes[-252:]
    percentile = 100.0 * sum(v <= level for v in window) / len(window)
    vix3m = fred.fred_series("VXVCLS")
    term = None
    if vix3m:
        term = "backwardation" if level > vix3m[-1][1] else "contango"
    return {"level": round(level, 2), "percentile_1y": round(percentile, 1),
            "regime": _regime(level), "term_structure": term}
