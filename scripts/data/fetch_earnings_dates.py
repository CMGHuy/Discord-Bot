#!/usr/bin/env python3
"""Fetch frozen Yahoo earnings-date CSVs for cached non-ETF symbols."""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import pandas as pd
from swingbot.core.market.earnings_calendar import CSV_FIELDS, EARNINGS_CSV_DIR, UNCONFIRMED, report_from_timestamp
from swingbot.core.market.session import US_MARKET_TZ

CACHE_DIR, DEFAULT_LIMIT = ROOT / "data" / "backtest_cache", 60

def rows_from_frame(frame):
    rows = {}
    for value in frame.index:
        stamp = pd.Timestamp(value)
        stamp = stamp.tz_localize(US_MARKET_TZ) if stamp.tzinfo is None else stamp.tz_convert(US_MARKET_TZ)
        report = report_from_timestamp(stamp.to_pydatetime())
        rows[report.date] = {"report_date": report.date.isoformat(), "timing": report.timing, "report_ts_et": stamp.isoformat()}
    return [rows[date] for date in sorted(rows)]

def write_csv(path, rows):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS); writer.writeheader(); writer.writerows(rows)

def fetch_frame(symbol, limit):
    import yfinance as yf
    from swingbot.core.marketdata.ticker_utils import candidate_symbols
    for candidate in candidate_symbols(symbol):
        try: frame = yf.Ticker(candidate).get_earnings_dates(limit=limit)
        except Exception as exc:
            print(f"    {candidate}: fetch failed: {exc}", flush=True); continue
        if frame is not None and not frame.empty: return frame
    return None

def cached_symbols(cache_dir): return sorted(path.stem for path in Path(cache_dir).glob("*.csv"))

def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument("--tickers"); parser.add_argument("--cache-dir", default=str(CACHE_DIR)); parser.add_argument("--out-dir", default=str(EARNINGS_CSV_DIR)); parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT); parser.add_argument("--force", action="store_true")
    args=parser.parse_args(argv)
    from swingbot.core.marketdata.universe import is_etf
    symbols=args.tickers.split(",") if args.tickers else cached_symbols(args.cache_dir); missing=0
    for index, symbol in enumerate(symbols, 1):
        out=Path(args.out_dir) / f"{symbol.upper()}.csv"; prefix=f"[{index}/{len(symbols)}] {symbol}"
        if is_etf(symbol): print(f"{prefix}: ETF, no earnings", flush=True); continue
        if out.exists() and not args.force: print(f"{prefix}: exists, skipped", flush=True); continue
        frame=fetch_frame(symbol, args.limit); rows=rows_from_frame(frame) if frame is not None else []
        if not rows: missing += 1; print(f"{prefix}: NO DATA", flush=True); continue
        write_csv(out, rows); print(f"{prefix}: {len(rows)} reports (unconfirmed {sum(row['timing'] == UNCONFIRMED for row in rows)})", flush=True)
    return int(bool(missing))

if __name__ == "__main__": raise SystemExit(main())
