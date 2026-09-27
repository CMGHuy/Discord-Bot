"""v106 provider parity report: Alpaca vs yfinance on the same symbols.

Calls both providers directly -- AlpacaProvider and data.py's yfinance
helpers -- never through the router, so a fallback cannot hide a
difference. Compares daily closes over the last N sessions (basis points),
Alpaca/yfinance volume, and the live last price (Alpaca's configured feed vs
yfinance's 1-minute last). Informational: exits 0 on a finished report, 2 if
the Alpaca keys are unset.

    python scripts/reports/provider_parity_report.py [--symbols A,B]
        [--sessions 60] [--json out.json]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

ACTION_BPS = 50          # a single-date close gap past this can move a level/trigger
CHUNK = 25


def _close_bps(alp: pd.DataFrame, yf: pd.DataFrame) -> pd.Series:
    common = alp.index.intersection(yf.index)
    a, y = alp.loc[common, "Close"].astype(float), yf.loc[common, "Close"].astype(float)
    return ((a / y - 1.0).abs() * 10_000).where(y > 0).dropna()


def _volume_ratios(alp: pd.DataFrame, yf: pd.DataFrame) -> list:
    if "Volume" not in alp or "Volume" not in yf:
        return []
    common = alp.index.intersection(yf.index)
    a, y = alp.loc[common, "Volume"].astype(float), yf.loc[common, "Volume"].astype(float)
    return list((a / y).where(y > 0).dropna())


def _pct(values: list, q: float):
    return round(float(np.percentile(values, q)), 2) if values else None


def compare_daily(alpaca: dict, yf: dict) -> dict:
    """Pure comparison of {symbol: daily frame} from each source."""
    empty = pd.DataFrame(columns=["Close", "Volume"])
    bps_all, ratios, mismatches = [], [], []
    missing_alpaca = missing_yf = 0
    symbols = sorted(set(alpaca) | set(yf))
    for sym in symbols:
        alp, y = alpaca.get(sym, empty), yf.get(sym, empty)
        missing_alpaca += len(y.index.difference(alp.index))
        missing_yf += len(alp.index.difference(y.index))
        bps = _close_bps(alp, y)
        bps_all.extend(bps.tolist())
        ratios.extend(_volume_ratios(alp, y))
        mismatches.extend({"symbol": sym, "date": str(pd.Timestamp(d).date()),
                           "bps": round(float(v), 2)}
                          for d, v in bps.items() if v > ACTION_BPS)
    return {
        "symbols": len(symbols),
        "close_bps_median": _pct(bps_all, 50),
        "close_bps_p95": _pct(bps_all, 95),
        "close_bps_max": round(float(max(bps_all)), 2) if bps_all else None,
        "missing_alpaca": missing_alpaca,
        "missing_yf": missing_yf,
        "action_mismatches": mismatches,
        "volume_ratio_median": _pct(ratios, 50),
    }


def compare_live(alpaca: dict, yf: dict) -> dict:
    """{symbol: bps} of Alpaca's last trade vs yfinance's 1-minute last."""
    return {s: round(abs(alpaca[s] / yf[s] - 1.0) * 10_000, 2)
            for s in sorted(set(alpaca) & set(yf)) if yf[s] > 0}


def _period_for(sessions: int) -> str:
    return "6mo" if sessions <= 100 else "1y" if sessions <= 240 else "2y"


def _last_sessions(frames: dict, sessions: int) -> dict:
    return {s: df.sort_index().iloc[-sessions:] for s, df in frames.items() if not df.empty}


def _symbols(arg: str | None) -> list:
    from swingbot.core.marketdata.providers.base import is_alpaca_eligible
    from swingbot.core.marketdata.watchlist import load_watchlist
    raw = arg.split(",") if arg else load_watchlist()
    return [s.strip().upper() for s in raw if is_alpaca_eligible(s.strip().upper())]


def _fetch(provider, symbols: list, sessions: int) -> tuple:
    from swingbot.core.marketdata import data
    period = _period_for(sessions)
    alp, yf, live_a, live_y = {}, {}, {}, {}
    for i in range(0, len(symbols), CHUNK):
        chunk = symbols[i:i + CHUNK]
        alp.update(provider.daily_bars(chunk, period))
        yf.update(data._yf_daily_batch(chunk, period))
        live_a.update(provider.latest_prices(chunk, 10 ** 9))
        live_y.update(data._yf_batch_prices(chunk))
        print(f"  fetched {min(i + CHUNK, len(symbols))}/{len(symbols)} "
              f"({chunk[0]}..{chunk[-1]})", flush=True)
    return _last_sessions(alp, sessions), _last_sessions(yf, sessions), live_a, live_y


def _print_report(daily: dict, live: dict, per_symbol: dict) -> None:
    print("\nDAILY CLOSE PARITY (bps, Alpaca vs yfinance)")
    for key in ("symbols", "close_bps_median", "close_bps_p95", "close_bps_max",
                "missing_alpaca", "missing_yf", "volume_ratio_median"):
        print(f"  {key:<22}{daily[key]}")
    print(f"  {'action_mismatches':<22}{len(daily['action_mismatches'])} (> {ACTION_BPS} bps)")
    for m in daily["action_mismatches"][:20]:
        print(f"    {m['symbol']:<8}{m['date']}  {m['bps']:>8.2f}")
    print("\nPER SYMBOL  max-close-bps  live-bps")
    for sym, stats in per_symbol.items():
        print(f"  {sym:<10}{str(stats['close_bps_max']):>13}  {str(live.get(sym, '-')):>8}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbols", help="comma-separated; default: eligible watchlist symbols")
    ap.add_argument("--sessions", type=int, default=60)
    ap.add_argument("--json", help="also write the report as JSON to this path")
    args = ap.parse_args(argv)

    from swingbot import config
    from swingbot.core.marketdata.providers.alpaca_provider import AlpacaProvider
    if not (config.ALPACA_API_KEY_ID and config.ALPACA_API_SECRET_KEY):
        print("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are unset in .env -- nothing to compare.")
        return 2
    provider = AlpacaProvider(config.ALPACA_API_KEY_ID, config.ALPACA_API_SECRET_KEY,
                              config.ALPACA_DATA_FEED_LIVE)
    symbols = _symbols(args.symbols)
    print(f"Comparing {len(symbols)} symbol(s) over the last {args.sessions} sessions", flush=True)
    alp, yf, live_a, live_y = _fetch(provider, symbols, args.sessions)

    daily = compare_daily(alp, yf)
    live = compare_live(live_a, live_y)
    per_symbol = {s: compare_daily({s: alp[s]} if s in alp else {}, {s: yf[s]} if s in yf else {})
                  for s in symbols}
    _print_report(daily, live, per_symbol)
    if args.json:
        Path(args.json).write_text(json.dumps(
            {"daily": daily, "live_bps": live, "per_symbol": per_symbol}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
