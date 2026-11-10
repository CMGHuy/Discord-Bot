#!/usr/bin/env python3
"""One-time OHLCV cache for the redesign backtests. Downloads every
watchlist ticker over a date range (default 2018-06-01 -> 2025-12-31, giving
>=18 months warm-up before the 2020 train window: the regime gate needs a
200-SMA + a 120-bar shift) and saves one CSV per ticker under
data/backtest_cache/. Re-running skips tickers already cached; pass --force
(or delete the folder) to overwrite and re-fetch.

v162: `load_cached` (imported by most backtest scripts) no longer reads this
cache directly. It returns `training_data.load_daily`, which reads the
selected training data: the Alpaca history store (data/market_data/, the
default) or this cache (`--data-source yfinance`, TRAINING_DATA_SOURCE=yfinance,
or BACKTEST_CACHE_DIR set). This script still writes only
data/backtest_cache/ (or BACKTEST_CACHE_DIR); the history store has its own
writer, scripts/data/fetch_alpaca_history.py.

Range is configurable:
    python scripts/data/fetch_backtest_data.py --start 2010-01-01 --end today --force
'today' / 'now' for --end resolves to the current date. yfinance daily bars
go back decades; intraday (1h/1m) history is NOT available this far back.

--universe NAME (Task E15) is a SEPARATE, additive mode: it incrementally
updates market_data/ (watchlist + named universe, e.g. sp500) via
swingbot.core.marketdata.data_store.update_cache -- fetching only new bars since each
symbol's last cached date, nightly-safe for 500+ symbols. This is a
DIFFERENT cache location from the default data/backtest_cache/ path above
(owned by swingbot.core.marketdata.backtest_cache) and the two are NOT unified: today's
run_backtest_range.py / backtest_scenarios.py / this script's default mode
still only read data/backtest_cache/, not market_data/.
    python scripts/data/fetch_backtest_data.py --universe sp500

--training-universe NAME (v112) widens the DEFAULT mode instead: it caches
watchlist + benchmark + the named universe into data/backtest_cache/ (or
BACKTEST_CACHE_DIR), the cache every backtest script reads, so a later
`run_backtest_range.py --universe NAME` finds the frames. Tickers Yahoo no
longer serves (delisted names in `sp500_pit`) are listed in a coverage file
next to the cache -- that list IS the residual survivorship bias.
    BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/data/fetch_backtest_data.py \
        --start 2010-01-01 --end 2026-09-25 --training-universe sp500_pit

--vix-context (v211) is its own mode: it fetches daily ^VIX 2009-01-01 ->
2019-12-31 into <cache-dir>/^VIX.csv (the screen's context loader reads
<stem>.csv literally, so not cache_path's _VIX.csv) and refuses a calendar
that differs from <cache-dir>/SPY.csv's sessions from 2009-06-01.
    python scripts/data/fetch_backtest_data.py --vix-context --cache-dir data/backtest_cache_ext"""
import argparse
import datetime as dt
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import yfinance as yf

# Cache location, filename scheme, and CSV shape are owned by the core module
# so this bulk populator and the auto-cache-on-add path can never drift.
from swingbot.core.marketdata.backtest_cache import CACHE_DIR, cache_path, normalize_ohlcv
from swingbot.core.marketdata import training_data
from swingbot import config
from swingbot.core.backtesting.instrument import contract
from swingbot.core.backtesting.screen import context as screen_context

START, END = "2018-06-01", "2025-12-31"


def load_universe_symbols(name: str) -> list[str]:
    """Watchlist ticker + named universe (e.g. sp500), deduped, sorted.
    Import kept local so the default no-flag path never touches this module."""
    from swingbot.core.marketdata import universe
    symbols = set(load_watchlist()) | set(universe.universe_symbols(name))
    return sorted(symbols)


def load_watchlist() -> list[str]:
    """The watchlist table: Postgres is the only store."""
    from swingbot.core.marketdata.watchlist import load_watchlist as repo_watchlist
    return repo_watchlist()


def load_cached(ticker: str) -> pd.DataFrame | None:
    """Daily training bars for one ticker from the selected source (v162):
    TRAINING_DATA_SOURCE, a script's --data-source, or yfinance when
    BACKTEST_CACHE_DIR is set. Every backtest script that imports this reads
    through swingbot.core.marketdata.training_data."""
    return training_data.load_daily(ticker)


def add_data_source_arg(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--data-source", choices=training_data.DATA_SOURCES, default=None,
                    help="training bars: 'alpaca' (data/market_data/ history store) or "
                         "'yfinance' (data/backtest_cache/); default TRAINING_DATA_SOURCE"
                         "; --instrument v3 always reads the PIT store (data/market_data_pit/)")


def instrument_store_spec(args: argparse.Namespace) -> contract.InstrumentSpec | None:
    """Resolve a store-bearing instrument, leaving legacy selections alone."""
    version = getattr(args, "instrument", None)
    if not version:
        return None
    spec = contract.resolve(version)
    return spec if spec.store is not None else None


def require_context_frames() -> None:
    """Refuse a PIT run without every context frame after its integrity trim and cut."""
    from swingbot.core.marketdata.universe import sector_map

    symbols = dict.fromkeys([config.MARKET_REGIME_TICKER, *sector_map("etfs")])
    missing = [symbol for symbol in symbols if training_data.load_daily(symbol) is None]
    if not missing:
        return
    exclusions = training_data.excluded()

    def _described(symbol: str) -> str:
        reason = exclusions.get(symbol)
        return f"{symbol} ({reason})" if reason else symbol

    raise SystemExit(
        "error: --instrument v3 needs every context frame in the PIT store, missing: "
        + ", ".join(_described(symbol) for symbol in missing)
        + " -- run the context pass (scripts/data/fetch_alpaca_history.py --root "
          "data/market_data_pit --tickers ...) and rebuild the integrity report")


def _select_instrument_store(args: argparse.Namespace, spec: contract.InstrumentSpec) -> str:
    """Select the instrument's store and ensure its context is usable."""
    if getattr(args, "data_source", None) not in (None, "alpaca"):
        raise SystemExit(
            f"error: --instrument {spec.version} reads the {spec.store} Alpaca store; "
            f"--data-source {args.data_source} cannot be combined with it")
    training_data.select("alpaca", spec.store, spec.research_end)
    require_context_frames()
    print(f"training data: alpaca, PIT store cut at {spec.research_end} "
          f"({len(training_data.excluded())} excluded)")
    return "alpaca"


def apply_data_source(args: argparse.Namespace) -> str:
    """Select the run's training source and say which one, before any bar is read.
    An instrument with a store (v3) selects it here -- one call, every script
    (spec section 3); no universe name and no environment variable does."""
    spec = instrument_store_spec(args)
    if spec is not None:
        return _select_instrument_store(args, spec)
    source = training_data.select(getattr(args, "data_source", None))
    print(f"training data: {source} ({len(training_data.excluded())} excluded)")
    return source


def fetch(ticker: str, start: str, end: str) -> pd.DataFrame | None:
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df is None or df.empty or len(df) < 260:
        return None
    return normalize_ohlcv(df)


VIX_CONTEXT = "^VIX"
VIX_START, VIX_END = "2009-01-01", "2019-12-31"
_OHLC = ["Open", "High", "Low", "Close"]


def vix_context_path(cache_dir: Path) -> Path:
    """The loader reads <stem>.csv literally, so the caret stays."""
    return Path(cache_dir) / f"{VIX_CONTEXT}.csv"


def check_vix_sessions(vix_index: pd.DatetimeIndex, spy_index: pd.DatetimeIndex, *,
                       start: str = screen_context.CONTEXT_START,
                       end: str = VIX_END) -> None:
    """Refuse a ^VIX calendar that differs from SPY's sessions in [start, end]."""
    screen_context.check_raw_index(vix_index, VIX_CONTEXT)
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    vix_slice = vix_index[(vix_index >= lo) & (vix_index <= hi)]
    spy_slice = spy_index[(spy_index >= lo) & (spy_index <= hi)]
    if len(spy_slice) == 0:
        raise screen_context.ContextError(
            f"{VIX_CONTEXT}: no SPY session between {start} and {end}")
    screen_context.check_contiguous(vix_slice, spy_slice, VIX_CONTEXT)


def _clean_vix_frame(frame: pd.DataFrame, end: str) -> pd.DataFrame:
    frame = frame[_OHLC + ["Volume"]].dropna(subset=_OHLC).copy()
    frame["Volume"] = frame["Volume"].fillna(0.0)
    frame = frame[frame.index <= pd.Timestamp(end)]
    frame.index.name = "Date"
    return frame


def fetch_vix_context(cache_dir: Path, *, start: str = VIX_START, end: str = VIX_END,
                      fetcher=fetch) -> Path:
    """Fetch ^VIX, check it against SPY's sessions, and only then write it."""
    spy_path = Path(cache_dir) / "SPY.csv"
    if not spy_path.exists():
        raise screen_context.ContextError(
            f"{VIX_CONTEXT}: {spy_path} is missing; the session check needs SPY")
    spy = pd.read_csv(spy_path, parse_dates=["Date"], index_col="Date")
    stop = (pd.Timestamp(end) + pd.Timedelta(days=1)).date().isoformat()  # yfinance end is exclusive
    raw = fetcher(VIX_CONTEXT, start, stop)
    if raw is None or raw.empty:
        raise screen_context.ContextError(f"{VIX_CONTEXT}: the fetch returned no data")
    frame = _clean_vix_frame(raw, end)
    check_vix_sessions(frame.index, spy.index, end=end)
    path = vix_context_path(cache_dir)
    frame.to_csv(path)
    return path


def vix_context_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch ^VIX context aligned to SPY sessions")
    ap.add_argument("--vix-context", action="store_true", required=True)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--start", default=VIX_START)
    ap.add_argument("--end", default=VIX_END)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    target = vix_context_path(Path(args.cache_dir))
    if target.exists() and not args.force:
        print(f"refusing: {target} exists; pass --force to refetch "
              "(a pinned context file is never refetched)")
        return 2
    try:
        path = fetch_vix_context(Path(args.cache_dir), start=args.start, end=args.end,
                                 fetcher=fetch)
    except screen_context.ContextError as exc:
        print(f"error: {exc}")
        return 2
    written = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    print(f"+ {VIX_CONTEXT}: {len(written)} bars "
          f"({written.index[0].date()} -> {written.index[-1].date()}) -> {path}")
    return 0


def training_tickers(watchlist: list[str], benchmark: str | None,
                     training_universe: str | None) -> list[str]:
    """Default-mode fetch list: watchlist, plus the regime benchmark, plus
    every symbol of --training-universe when given. Deduped, sorted."""
    tickers = set(watchlist)
    if benchmark:
        tickers.add(benchmark)
    if training_universe:
        from swingbot.core.marketdata import universe
        tickers |= set(universe.universe_symbols(training_universe))
    return sorted(tickers)


def write_coverage(name: str, requested: list[str], failed: list[str]) -> Path:
    """Record which universe symbols have no cached history. For a `_pit`
    universe these are mostly delisted names Yahoo dropped -- the part of
    the survivorship bias free data cannot remove, so it is written down
    rather than silently shrinking N."""
    from swingbot.core.marketdata.universe import universe_symbols
    members = set(universe_symbols(name))
    missing = sorted(t for t in failed if t in members)
    have = sum(1 for t in members if cache_path(t).exists())
    out = CACHE_DIR / f"_coverage_{name}.json"
    out.write_text(json.dumps({"universe": name, "members": len(members), "cached": have,
                               "missing": missing, "requested": len(requested)}, indent=1))
    print(f"coverage: {have}/{len(members)} '{name}' symbols cached, "
          f"{len(missing)} unavailable -> {out}")
    return out


def _resolve_end(end: str) -> str:
    if end.lower() in ("today", "now"):
        # yfinance end is exclusive; +1 day to include the latest complete bar
        return (dt.date.today() + dt.timedelta(days=1)).isoformat()
    return end


def _tickers(args) -> list[str]:
    """--tickers wins outright (v113: the four inverse ETFs, never the
    watchlist or benchmark). Otherwise the watchlist plus the market-context
    benchmark (P0) -- not necessarily on the watchlist, but every backtest that
    gates on regime needs its history cached -- plus --training-universe."""
    if args.tickers:
        return [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    from swingbot import config
    return training_tickers(load_watchlist(), config.MARKET_REGIME_TICKER,
                            getattr(args, "training_universe", None))


def main():
    ap =argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default=START, help=f"start date YYYY-MM-DD (default {START})")
    ap.add_argument("--end", default=END, help=f"end date YYYY-MM-DD, or 'today' (default {END})")
    ap.add_argument("--force", action="store_true", help="re-fetch and overwrite already-cached tickers")
    ap.add_argument("--tickers", default=None,
                    help="comma-separated tickers to fetch INSTEAD of the watchlist "
                         "(the market-context benchmark is not added)")
    # --universe is a SEPARATE, additive code path (Task E15). It does NOT
    # touch data/backtest_cache/ (owned by swingbot.core.marketdata.backtest_cache and
    # read by run_backtest_range.py / backtest_scenarios.py / this script's
    # default no-flag mode above) -- it writes to market_data/ via
    # swingbot.core.marketdata.data_store's incremental cache instead. The two caches
    # are NOT unified: today's grid/backtest scripts only read the former,
    # so --universe output isn't yet usable by them. This mirrors that gap
    # honestly rather than silently building an orphaned feature.
    ap.add_argument("--universe", metavar="NAME", default=None,
                     help="incrementally update market_data/ for watchlist + "
                          "named universe (e.g. 'sp500') via swingbot.core.marketdata.data_store."
                          "update_cache -- a SEPARATE cache from the default "
                          "data/backtest_cache/ path above; not read by "
                          "run_backtest_range.py or other grid scripts yet")
    ap.add_argument("--training-universe", metavar="NAME", default=None,
                    help="default mode: also cache every symbol of this named universe "
                         "(e.g. 'sp500', 'sp500_pit', 'sp500+etfs') into the backtest "
                         "cache and write a coverage report of unavailable symbols")
    args = ap.parse_args()

    if args.universe:
        from swingbot.core.marketdata.data_store import update_cache
        symbols = load_universe_symbols(args.universe)
        print(f"Incrementally updating market_data/ for {len(symbols)} symbols "
              f"(watchlist + universe='{args.universe}')\n"
              f"NOTE: this populates market_data/, a separate cache from "
              f"data/backtest_cache/ -- run_backtest_range.py and other grid "
              f"scripts do not read it yet.\n")
        result = update_cache(symbols)
        updated = sum(1 for n in result.values() if n > 0)
        total_new = sum(result.values())
        for sym, n in sorted(result.items()):
            if n:
                print(f"  + {sym}: {n} new bars")
        print(f"\nDone: {updated}/{len(symbols)} symbols updated, {total_new} new bars total")
        return

    start, end = args.start, _resolve_end(args.end)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    tickers = _tickers(args)

    print(f"Fetching {len(tickers)} tickers | {start} -> {end} | force={args.force}\n")
    ok, skipped, failed = 0, 0, []
    for t in sorted(tickers):
        if cache_path(t).exists() and not args.force:
            skipped += 1
            continue
        df = fetch(t, start, end)
        if df is None:
            print(f"  x {t}: no data (<260 bars or empty)")
            failed.append(t)
            continue
        df.to_csv(cache_path(t))
        ok += 1
        print(f"  + {t}: {len(df)} bars ({df.index[0].date()} -> {df.index[-1].date()})")
    print(f"\nDone: {ok} fetched, {skipped} already cached, {len(failed)} failed {failed or ''}")
    if args.training_universe:
        write_coverage(args.training_universe, tickers, failed)


def _entry(argv: list[str]) -> int | None:
    if "--vix-context" in argv:
        return vix_context_main(argv)
    return main()


if __name__ == "__main__":
    sys.exit(_entry(sys.argv[1:]))
