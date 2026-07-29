#!/usr/bin/env python3
"""Backfill data/macro/history/{key}.json for the surviving macro series.

Post-audit scope (win-rate audit, 2026-07-29): the FRED series registry
(CPI/PPI/PCE, labor, yields, curve) was cut, so this backfills VIX from FRED
plus the series derived from cached daily bars:

    vix.json             FRED VIXCLS, 2017-01 -> present
    vix_percentile.json  trailing-252-observation percentile of VIX
    breadth_50dma.json   % of the cached universe above its 50 DMA
    breadth_200dma.json  ... above its 200 DMA

2017 start gives yoy headroom for 2018 backtests.

Usage (NETWORK for the VIX pull):
    FRED_API_KEY=... python scripts/backfill_macro.py
    python scripts/backfill_macro.py --only breadth_50dma,breadth_200dma

Progress is printed per series (one flushed line per completed unit), per
the repo's long-running-script rule in CLAUDE.md.
"""
import argparse
import os
import sys

sys.path.insert(0, ".")

import pandas as pd

from swingbot.core.backtest_cache import CACHE_DIR
from swingbot.core.jsonio import atomic_write_json
from swingbot.core.macro import fred
from swingbot.core.macro.history import HISTORY_DIR

START = "2017-01-01"


def _load_universe() -> dict:
    """Every ticker in the backtest cache — the same universe breadth is
    measured over at scan time."""
    frames = {}
    if not CACHE_DIR.exists():
        return frames
    for path in sorted(CACHE_DIR.glob("*.csv")):
        try:
            frames[path.stem] = pd.read_csv(path, index_col=0, parse_dates=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {path.stem}: unreadable ({type(exc).__name__})", flush=True)
    return frames


def build_vix() -> list[list]:
    series = fred.fred_series("VIXCLS", start=START)
    if not series:
        raise SystemExit("no VIX series — check FRED_API_KEY (or use --only)")
    return [[d, v] for d, v in series]


def build_vix_percentile(vix_rows: list[list]) -> list[list]:
    out = []
    values = [v for _, v in vix_rows]
    for i, (date, _) in enumerate(vix_rows):
        window = values[max(0, i - 251):i + 1]
        pct = 100.0 * sum(v <= values[i] for v in window) / len(window)
        out.append([date, round(pct, 1)])
    return out


def build_breadth(frames: dict, window: int) -> list[list]:
    """Daily % of the universe above its `window`-day SMA. Computed
    vectorised per ticker, then aligned — one pass over the cache."""
    above, counted = None, None
    for df in frames.values():
        closes = df["Close"]
        if len(closes) < window:
            continue
        sma = closes.rolling(window).mean()
        flag = (closes > sma).astype(float).where(sma.notna())
        above = flag if above is None else above.add(flag, fill_value=0.0)
        ones = flag.notna().astype(float)
        counted = ones if counted is None else counted.add(ones, fill_value=0.0)
    if above is None:
        return []
    pct = (100.0 * above / counted).dropna()
    pct = pct[pct.index >= pd.Timestamp(START)]
    return [[d.strftime("%Y-%m-%d"), round(float(v), 1)] for d, v in pct.items()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", default="", help="comma-separated subset of series keys")
    args = ap.parse_args()
    wanted = {k.strip() for k in args.only.split(",") if k.strip()}

    def want(key: str) -> bool:
        return not wanted or key in wanted

    os.makedirs(HISTORY_DIR, exist_ok=True)
    written = {}

    if want("vix") or want("vix_percentile"):
        print("fetching VIX from FRED ...", flush=True)
        vix_rows = build_vix()
        if want("vix"):
            written["vix"] = vix_rows
        if want("vix_percentile"):
            written["vix_percentile"] = build_vix_percentile(vix_rows)
        print(f"  + vix: {len(vix_rows)} observations", flush=True)

    if want("breadth_50dma") or want("breadth_200dma"):
        print("loading cached universe ...", flush=True)
        frames = _load_universe()
        print(f"  loaded {len(frames)} tickers", flush=True)
        if want("breadth_50dma"):
            written["breadth_50dma"] = build_breadth(frames, 50)
            print(f"  + breadth_50dma: {len(written['breadth_50dma'])} days", flush=True)
        if want("breadth_200dma"):
            written["breadth_200dma"] = build_breadth(frames, 200)
            print(f"  + breadth_200dma: {len(written['breadth_200dma'])} days", flush=True)

    for key, rows in written.items():
        atomic_write_json(os.path.join(HISTORY_DIR, f"{key}.json"), rows)
    print(f"wrote {len(written)} series -> {HISTORY_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
