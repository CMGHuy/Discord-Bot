"""
One-off helper: dumps full daily OHLCV history (same source/resolution the
bot itself uses) for every watchlist ticker to CSV files, so the data can be
analyzed outside this environment (e.g. by Claude in Cowork, which can't
reach Yahoo Finance directly from its sandbox).

Usage (run from the project root, same place you'd run bot.py):
    python export_2024_data.py

Output:
    data/historical_2024/<TICKER>.csv   (one file per watchlist ticker)
    data/historical_2024/_manifest.json (bar counts / errors summary)

Uses swingbot.core.data.get_daily_data(ticker, period="max") -- the exact
same function and ticker-resolution logic (candidate_symbols) the live bot
and !backtest command use, so the data lines up with what the bot actually
sees. period="max" is used (rather than just 2024) so indicators that need
long lookbacks (e.g. 200-day EMA/SMA for the 6-month horizon) have proper
warmup before 2024-01-01.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from swingbot.core.data import get_daily_data
from swingbot.core.watchlist import load_watchlist

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "historical_2024")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    tickers = load_watchlist()
    print(f"Exporting {len(tickers)} tickers to {OUT_DIR} ...")

    manifest = {"tickers": {}, "errors": {}}
    for i, ticker in enumerate(tickers, 1):
        safe_name = ticker.replace("=", "_").replace("^", "_")
        try:
            df = get_daily_data(ticker, period="max")
            out_path = os.path.join(OUT_DIR, f"{safe_name}.csv")
            df.to_csv(out_path)
            manifest["tickers"][ticker] = {
                "bars": len(df),
                "first_date": str(df.index[0].date()) if len(df) else None,
                "last_date": str(df.index[-1].date()) if len(df) else None,
            }
            print(f"[{i}/{len(tickers)}] OK   {ticker}: {len(df)} bars "
                  f"({manifest['tickers'][ticker]['first_date']} -> {manifest['tickers'][ticker]['last_date']})")
        except Exception as e:
            manifest["errors"][ticker] = str(e)
            print(f"[{i}/{len(tickers)}] FAIL {ticker}: {e}")

    with open(os.path.join(OUT_DIR, "_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDone. {len(manifest['tickers'])} succeeded, {len(manifest['errors'])} failed.")
    print(f"CSV files + _manifest.json written to: {OUT_DIR}")


if __name__ == "__main__":
    main()
