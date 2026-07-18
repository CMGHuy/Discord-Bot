#!/usr/bin/env python3
"""Crawl all available FMP data for one or more stocks.

Reads the API key from the FMP_API_KEY environment variable (works on the
free tier -- gated endpoints are reported, not fatal). Writes one JSON per
endpoint under data/fmp/<SYMBOL>/, and CSVs for the tabular price/statement
endpoints. Use --probe to just print what your tier can reach without writing.

Examples:
    export FMP_API_KEY=xxxx           # (PowerShell: $env:FMP_API_KEY="xxxx")
    python scripts/fmp_crawl.py --probe AAPL
    python scripts/fmp_crawl.py AAPL MSFT
    python scripts/fmp_crawl.py --watchlist --intervals 1hour,15min
"""
import argparse
import csv
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.fmp_client import FMPClient, VALID_INTERVALS, FMPResult  # noqa: E402

OUT_ROOT = ROOT / "data" / "fmp"

# Endpoints worth also flattening into CSV when they return a list of flat dicts.
CSV_WORTHY = {
    "historical_eod", "dividends", "splits", "historical_market_cap",
    "income_statement", "balance_sheet", "cash_flow", "ratios", "key_metrics",
    "financial_growth", "enterprise_values", "earnings", "analyst_estimates",
}


def load_watchlist() -> list[str]:
    return json.loads((ROOT / "data" / "watchlist.json").read_text())


def _write_csv(path: Path, rows: list[dict]):
    # union of keys across rows, preserving first-seen order
    cols: list[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                cols.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _write_results(symbol: str, results: dict[str, FMPResult]):
    out = OUT_ROOT / symbol
    out.mkdir(parents=True, exist_ok=True)
    for name, r in results.items():
        if r.status not in ("ok", "empty"):
            continue
        (out / f"{name}.json").write_text(json.dumps(r.data, indent=2))
        if name in CSV_WORTHY and isinstance(r.data, list) and r.data \
                and all(isinstance(x, dict) for x in r.data):
            # intraday/eod come newest-first from FMP; write as-is
            _write_csv(out / f"{name}.csv", r.data)


ICON = {"ok": "+", "empty": ".", "gated": "L", "ratelimited": "~", "error": "x"}


def _print_table(symbol: str, results: dict[str, FMPResult]):
    print(f"\n== {symbol} ==")
    width = max(len(n) for n in results) if results else 20
    for name, r in results.items():
        tail = f"  {r.detail}" if r.detail else ""
        print(f"  [{ICON.get(r.status, '?')}] {name.ljust(width)}  {r.status:<11} n={r.n}{tail}")
    counts: dict[str, int] = {}
    for r in results.values():
        counts[r.status] = counts.get(r.status, 0) + 1
    print("  summary:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbols", nargs="*", help="ticker symbols to crawl")
    ap.add_argument("--watchlist", action="store_true", help="crawl every watchlist ticker")
    ap.add_argument("--probe", action="store_true", help="print tier/endpoint status only, write nothing")
    ap.add_argument("--intervals", default=",".join(("1hour", "15min")),
                    help=f"comma list of intraday intervals from {VALID_INTERVALS}")
    ap.add_argument("--period", default="annual", choices=["annual", "quarter"],
                    help="statement period (default annual; quarter is deeper but paid on FMP)")
    args = ap.parse_args()

    symbols = [s.upper() for s in args.symbols]
    if args.watchlist:
        symbols = sorted(set(symbols) | set(load_watchlist()))
    if not symbols:
        ap.error("give at least one symbol or --watchlist")

    intervals = tuple(i.strip() for i in args.intervals.split(",") if i.strip())
    bad = [i for i in intervals if i not in VALID_INTERVALS]
    if bad:
        ap.error(f"invalid interval(s) {bad}; valid: {VALID_INTERVALS}")

    client = FMPClient()
    if not client.api_key:
        print("WARNING: no FMP_API_KEY set -- every endpoint will report 'gated'.\n"
              "Set it: PowerShell  $env:FMP_API_KEY=\"yourkey\"   bash  export FMP_API_KEY=yourkey")

    for sym in symbols:
        results = client.crawl_all(sym, intervals=intervals, period=args.period)
        _print_table(sym, results)
        if not args.probe:
            _write_results(sym, results)
            print(f"  written -> {OUT_ROOT / sym}")


if __name__ == "__main__":
    main()
