#!/usr/bin/env python3
"""Build data/universe/sp500.json from a manually refreshed constituent CSV.

Refresh procedure (documented, no scraping dependency): copy the current
S&P 500 constituent table from any public source (e.g. the "List of S&P 500
companies" Wikipedia article's constituent table) into
data/universe/sp500_raw.csv with the header `Symbol,Name,Sector`
(GICS sector names). Then:

    python scripts/data/build_universe.py --raw data/universe/sp500_raw.csv
    python scripts/data/build_universe.py --raw data/universe/sp500_raw.csv --top 150

--top N ranks by 20-day average dollar volume using the local OHLCV cache
(fetch it first: python scripts/data/fetch_backtest_data.py --universe sp500).

NOTE (Task E13): the --top path is implemented and ready to use, but was NOT
run as part of E13 -- `fetch_backtest_data.py` has no `--universe` flag today
(only the ~78-ticker watchlist is cached under data/backtest_cache/), so
there is no local OHLCV cache for the full S&P 500 to rank against yet.
Wiring that fetch is separate scope. Until it lands, `--top N` will rank
every symbol as a 0.0 dollar-volume tie (whatever cache rows happen to
exist win arbitrarily) -- don't rely on its output before the prerequisite
fetch is run.
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot.core.universe import UNIVERSE_DIR  # noqa: E402


def build(raw_csv: str, top: int | None) -> str:
    rows = []
    with open(raw_csv, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            sym = r["Symbol"].strip().upper().replace(".", "-")  # BRK.B -> BRK-B (yfinance)
            rows.append({"symbol": sym, "name": r["Name"].strip(),
                         "sector": r["Sector"].strip(), "etf": False})
    seen, deduped = set(), []
    for r in rows:
        if r["symbol"] not in seen:
            seen.add(r["symbol"]); deduped.append(r)

    name = "sp500"
    if top:
        from swingbot.core.data_store import load_from_disk
        def dollar_vol(sym):
            df = load_from_disk(sym, "1d")
            if df is None or len(df) < 20:
                return 0.0
            t = df.tail(20)
            return float((t["Close"] * t["Volume"]).mean())
        deduped.sort(key=lambda r: dollar_vol(r["symbol"]), reverse=True)
        deduped = deduped[:top]
        name = f"sp500_top{top}"

    os.makedirs(UNIVERSE_DIR, exist_ok=True)
    out = os.path.join(UNIVERSE_DIR, f"{name}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(deduped, f, indent=1)
    print(f"wrote {out}: {len(deduped)} symbols")
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--raw", default="data/universe/sp500_raw.csv")
    p.add_argument("--top", type=int, default=None)
    a = p.parse_args()
    build(a.raw, a.top)
