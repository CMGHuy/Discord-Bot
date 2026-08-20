"""Asset-class classification for RS eligibility (v34).

Relative strength versus SPY is only meaningful for things that are, loosely,
equity risk. FX, futures, indices and crypto are exempt from the RS gate --
an exemption that is logged distinctly from a pass, so a scan never reports a
gold future as having 'passed' a comparison that was never run.

Classification is by RESOLVED Yahoo symbol shape (XAUUSD resolves to GC=F,
and GC=F is what must be judged) -- but `classify()` does not require its
caller to have already done that resolution. Final-review fix: the real
gate call site (`scanning/engine.py`) passes the raw watchlist string
straight through (`item.result.ticker`), never the resolved symbol, so a
classifier that only understood already-resolved shapes silently misjudged
every unresolved alias -- XAUUSD, SPX, BTC, etc. all read as "equity" and
so were never exempted. `classify()` now walks
`ticker_utils.candidate_symbols()` itself and returns the first non-equity
verdict among the candidates it produces (the symbol as given, its known
alias, and an "=X" FX guess, in that order) -- so it is correct whether it's
handed a raw watchlist entry or an already-resolved Yahoo symbol.
"""
from __future__ import annotations

_OVERRIDES: dict[str, str] = {
    # ALIASES keys (ticker_utils.py) that are ALSO real, fetchable Yahoo
    # tickers in their own right. data.py's get_daily_data() tries the bare
    # symbol FIRST and only falls back to ALIASES's mapping if that fetch
    # fails -- so for these specific keys, the bare symbol is what actually
    # gets analyzed, never the alias. Without this override, classify()'s
    # walk-all-candidates search finds the alias's non-equity classification
    # (e.g. "GOLD" -> GC=F -> "future") and wrongly exempts a symbol whose
    # real fetched data is an ordinary equity/ETF. Keep small and justified.
    "GOLD": "equity",  # NYSE: Barrick Gold Corp. ALIASES maps GOLD -> GC=F,
                       # but that fallback is unreachable -- GOLD itself is a
                       # valid, liquid Yahoo ticker.
    "OIL": "etf",      # iPath S&P GSCI Crude Oil ETN, historically traded as
                       # "OIL" on Yahoo. ALIASES's CL=F fallback never fires
                       # if the bare symbol still resolves.
}

_RS_ELIGIBLE = {"equity", "etf"}

# Resolved crypto shapes this codebase actually produces (see
# ticker_utils.ALIASES -- BTC/BTCUSD -> BTC-USD, ETH/ETHUSD -> ETH-USD).
# "-USDT" is included for any future alias using a stablecoin quote pair;
# no such alias exists yet, but the suffix is cheap to recognize now rather
# than adding a crypto class later that only covers the two live pairs.
_CRYPTO_SUFFIXES = ("-USD", "-EUR", "-USDT")


def _classify_resolved(sym: str) -> str:
    """Classify a symbol that is assumed to already be in resolved Yahoo
    shape (or at least not require further alias lookup). Never called
    directly from outside this module -- see classify()."""
    if sym in _OVERRIDES:
        return _OVERRIDES[sym]
    if sym.startswith("^"):
        return "index"
    if sym.endswith("=X"):
        return "fx"
    if sym.endswith("=F"):
        return "future"
    if sym.endswith(_CRYPTO_SUFFIXES):
        return "crypto"
    from swingbot.core.marketdata.universe import is_etf
    return "etf" if is_etf(sym) else "equity"


def classify(symbol: str) -> str:
    """Classify `symbol` by asset class, accepting either an unresolved
    watchlist string (e.g. "XAUUSD", "SPX", "BTC") or an already-resolved
    Yahoo symbol (e.g. "GC=F", "^GSPC", "BTC-USD").

    Walks swingbot.core.marketdata.ticker_utils.candidate_symbols(symbol)
    -- the same candidate list the data layer tries when fetching -- and
    returns the first candidate's classification that isn't "equity". This
    means a symbol is only ever left classified as "equity" if every
    candidate the fetch layer would have tried also reads as equity/unknown;
    any candidate that resolves to fx/future/index/crypto is enough to
    exempt the whole symbol.

    Exception: a bare symbol listed in _OVERRIDES short-circuits the walk
    entirely (see that dict's comment) -- these are ALIASES keys that are
    themselves real, fetchable tickers, so the walk-for-a-non-equity-verdict
    logic above would otherwise wrongly exempt them via their alias's
    classification, which data.py's actual fetch order never reaches.
    """
    if not symbol:
        return "equity"
    sym = symbol.strip().upper()

    if sym in _OVERRIDES:
        return _OVERRIDES[sym]

    from swingbot.core.marketdata.ticker_utils import candidate_symbols
    for candidate in candidate_symbols(sym):
        verdict = _classify_resolved(candidate)
        if verdict != "equity":
            return verdict
    return "equity"


def is_rs_eligible(symbol: str) -> bool:
    """False means exempt from the RS gate -- never 'failed' it."""
    return classify(symbol) in _RS_ELIGIBLE
