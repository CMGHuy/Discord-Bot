"""11 SPDR sector ETFs: data plumbing, RS ranks (G24), rotation (G25)."""
from __future__ import annotations

import logging

log = logging.getLogger("swing-bot.macro.sectors")

SECTOR_ETFS = {
    "XLK": "Technology", "XLF": "Financials", "XLV": "Health Care",
    "XLY": "Cons. Discretionary", "XLP": "Cons. Staples", "XLE": "Energy",
    "XLI": "Industrials", "XLB": "Materials", "XLU": "Utilities",
    "XLRE": "Real Estate", "XLC": "Comm. Services",
}
BENCHMARK = "SPY"


def _default_loader(ticker):
    """Read one ticker from data/backtest_cache/ (the cache every backtest
    script reads — NOT market_data/, see docs/claude/known-traps.md).

    The plan specified swingbot.core.data.load_cached_daily; no such
    function exists. There is no shared single-ticker loader in the repo —
    scripts go through backtest_cache.cache_path + pd.read_csv — so this
    mirrors that pattern and degrades to None instead of raising.
    """
    try:
        import pandas as pd

        from swingbot.core.backtest_cache import cache_path
        path = cache_path(ticker)
        if not path.exists():
            return None
        return pd.read_csv(path, index_col=0, parse_dates=True)
    except Exception:  # noqa: BLE001 — a cold/corrupt cache must not stop a scan
        return None


def sector_bars(loader=None) -> dict:
    """{ticker: df} for the 11 sectors + SPY; missing tickers are skipped
    with a WARN — never a raise (a scan must survive a cold cache)."""
    loader = loader or _default_loader
    bars = {}
    for ticker in list(SECTOR_ETFS) + [BENCHMARK]:
        df = loader(ticker)
        if df is None or not len(df):
            log.warning("sectors: no cached bars for %s — skipped", ticker)
            continue
        bars[ticker] = df
    return bars
