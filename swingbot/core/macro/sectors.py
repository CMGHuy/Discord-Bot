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


def _window_return_pct(df, w) -> float:
    c = df["Close"]
    return float(c.iloc[-1] / c.iloc[-1 - w] - 1.0) * 100.0


def sector_rs(bars: dict, windows=(21, 63, 126)) -> list[dict]:
    """Per sector: return-over-window minus SPY's, composite = mean of
    per-window z-scores, rank 1..11 (1 = strongest)."""
    spy = bars.get(BENCHMARK)
    need = max(windows) + 1
    if spy is None or len(spy) < need:
        return []
    rows = []
    for etf, name in SECTOR_ETFS.items():
        df = bars.get(etf)
        if df is None or len(df) < need:
            continue
        rows.append({"etf": etf, "sector": name,
                     **{f"rs_{w}": round(_window_return_pct(df, w)
                                         - _window_return_pct(spy, w), 2)
                        for w in windows}})
    if not rows:
        return []
    for w in windows:
        vals = [r[f"rs_{w}"] for r in rows]
        mu = sum(vals) / len(vals)
        sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5 or 1.0
        for r in rows:
            r[f"z_{w}"] = (r[f"rs_{w}"] - mu) / sd
    for r in rows:
        r["composite"] = sum(r[f"z_{w}"] for w in windows) / len(windows)
    rows.sort(key=lambda r: r["composite"], reverse=True)
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows


def leaders(rs_rows: list[dict], n=3) -> list[dict]:
    return rs_rows[:n]


def laggards(rs_rows: list[dict], n=3) -> list[dict]:
    return rs_rows[-n:]
