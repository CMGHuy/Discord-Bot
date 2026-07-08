"""
Ticker symbol resolution.

Yahoo Finance uses specific, non-obvious formats for indices, metals, and
forex that don't match how people normally write them:
  - S&P 500 index is "^GSPC", not "SPX"
  - Gold spot is best fetched as "GC=F" (COMEX futures); "XAUUSD" alone
    isn't a valid Yahoo symbol
  - Silver spot is "SI=F"; "XAGUSD" alone isn't valid either
  - Forex pairs need a "=X" suffix, e.g. "EURUSD=X"

This module maps common aliases and provides sensible fallback guesses so
`!watchlist add SPX` or `!watchlist add XAUUSD` work instead of silently
failing with a Yahoo 404.
"""
import re

ALIASES = {
    "SPX": "^GSPC", "US500": "^GSPC", "SP500": "^GSPC", "S&P500": "^GSPC",
    "NDX": "^NDX", "US100": "^NDX", "NASDAQ100": "^NDX",
    "DJI": "^DJI", "US30": "^DJI", "DOWJONES": "^DJI",
    "VIX": "^VIX",
    "XAUUSD": "GC=F", "GOLD": "GC=F", "XAU": "GC=F", "GC": "GC=F",
    "XAGUSD": "SI=F", "SILVER": "SI=F", "XAG": "SI=F", "SI": "SI=F",
    "WTI": "CL=F", "USOIL": "CL=F", "OIL": "CL=F",
    "BRENT": "BZ=F", "UKOIL": "BZ=F",
    "BTC": "BTC-USD", "BTCUSD": "BTC-USD",
    "ETH": "ETH-USD", "ETHUSD": "ETH-USD",
}

_FX_PATTERN = re.compile(r"^[A-Z]{6}$")


def candidate_symbols(ticker: str) -> list[str]:
    """
    Returns an ordered list of Yahoo Finance symbols to try for a
    user-provided ticker, most-likely-correct first: the symbol as given,
    then a known alias if one exists, then an "=X" forex guess if the
    symbol looks like a 6-letter currency pair.
    """
    ticker = ticker.upper().strip()
    candidates = [ticker]

    alias = ALIASES.get(ticker)
    if alias and alias not in candidates:
        candidates.append(alias)

    if _FX_PATTERN.match(ticker) and not ticker.endswith("=X"):
        fx = f"{ticker}=X"
        if fx not in candidates:
            candidates.append(fx)

    return candidates
