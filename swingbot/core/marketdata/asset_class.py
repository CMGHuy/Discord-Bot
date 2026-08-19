"""Asset-class classification for RS eligibility (v34).

Relative strength versus SPY is only meaningful for things that are, loosely,
equity risk. FX, futures and indices are exempt from the RS gate -- an
exemption that is logged distinctly from a pass, so a scan never reports a
gold future as having 'passed' a comparison that was never run.

Classification is by RESOLVED Yahoo symbol shape, because that is what was
actually fetched: XAUUSD resolves to GC=F, and GC=F is what must be judged.
"""
from __future__ import annotations

_OVERRIDES: dict[str, str] = {
    # Symbols the suffix heuristic gets wrong. Keep small and justified.
}

_RS_ELIGIBLE = {"equity", "etf"}


def classify(symbol: str) -> str:
    if not symbol:
        return "equity"
    sym = symbol.strip().upper()
    if sym in _OVERRIDES:
        return _OVERRIDES[sym]
    if sym.startswith("^"):
        return "index"
    if sym.endswith("=X"):
        return "fx"
    if sym.endswith("=F"):
        return "future"
    from swingbot.core.marketdata.universe import is_etf
    return "etf" if is_etf(sym) else "equity"


def is_rs_eligible(symbol: str) -> bool:
    """False means exempt from the RS gate -- never 'failed' it."""
    return classify(symbol) in _RS_ELIGIBLE
