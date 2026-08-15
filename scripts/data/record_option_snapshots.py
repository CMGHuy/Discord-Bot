"""Daily option-chain archive -- P3 of the market-context spec.

WHY THIS EXISTS
---------------
dsgex.ai's headline features (dealer net GEX by strike, call/put walls, gamma
flip) are all derived from option open interest by strike. yfinance will serve
today's chain but keeps no history, so those features cannot be backtested --
which under this repo's evidence rules means they cannot ship. Every day we
don't record is a day of history that can never be recovered. This script
exists purely to start that clock; it gates nothing and improves nothing today.

RECORD RAW, DERIVE NOTHING
--------------------------
We store the chain as fetched, never a computed GEX number. The dealer sign
convention, the gamma model and the spot multiplier are all guesses right now;
an archive of today's guess is worth exactly today's guess, whereas raw chains
can be recomputed forever as the model improves.

The snapshot timestamp is recorded for the same reason: dealer positioning at
15:55 ET and at 09:35 ET are different animals, and a file without a timestamp
cannot tell you which one it holds.

NOT IMPORTED BY THE BOT. Nothing under swingbot/ may import this module -- it
must not be able to affect the live path.

Usage:
    python scripts/data/record_option_snapshots.py                 # default symbols
    python scripts/data/record_option_snapshots.py --symbols SPY,QQQ
    python scripts/data/record_option_snapshots.py --max-dte 45 --out market_data/options
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

import pandas as pd

log = logging.getLogger("record_option_snapshots")

# Capped on purpose. At ~100-300 KB per symbol-day, ten symbols is ~0.5 GB/yr;
# the full watchlist would be an unmanaged disk commitment for data whose
# payoff is a year away.
DEFAULT_SYMBOLS = ("SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA")

DEFAULT_MAX_DTE = 90          # near-dated chains carry the dealer-relevant OI
DEFAULT_OUT = Path("market_data") / "options"

# Columns yfinance gives us. Kept explicit so a silent upstream schema change
# shows up as a missing column in the archive rather than as a shape surprise
# months later when we finally compute GEX.
_WANTED = ("contractSymbol", "strike", "lastPrice", "bid", "ask", "volume",
           "openInterest", "impliedVolatility", "inTheMoney")


def _chain_frame(tk, symbol: str, expiry: str, side: str) -> pd.DataFrame | None:
    chain = tk.option_chain(expiry)
    raw = chain.calls if side == "call" else chain.puts
    if raw is None or raw.empty:
        return None

    out = raw.reindex(columns=[c for c in _WANTED if c in raw.columns]).copy()
    for missing in (c for c in _WANTED if c not in out.columns):
        out[missing] = pd.NA
    out["side"] = side
    out["expiry"] = expiry
    return out


def fetch_symbol(symbol: str, *, max_dte: int, now: dt.datetime) -> pd.DataFrame | None:
    """One symbol's full near-dated chain, calls and puts, as a flat frame."""
    import yfinance as yf

    tk = yf.Ticker(symbol)
    expiries = list(getattr(tk, "options", ()) or ())
    if not expiries:
        log.warning("%s: no expiries returned", symbol)
        return None

    horizon = (now + dt.timedelta(days=max_dte)).date()
    frames = []
    for expiry in expiries:
        try:
            if dt.date.fromisoformat(expiry) > horizon:
                continue
        except ValueError:
            log.warning("%s: unparseable expiry %r, skipping", symbol, expiry)
            continue
        for side in ("call", "put"):
            try:
                frame = _chain_frame(tk, symbol, expiry, side)
            except Exception:
                # One bad expiry must not cost us the rest of the chain.
                log.exception("%s %s %s: chain fetch failed", symbol, expiry, side)
                continue
            if frame is not None:
                frames.append(frame)

    if not frames:
        log.warning("%s: no chains within %d DTE", symbol, max_dte)
        return None

    out = pd.concat(frames, ignore_index=True)
    out["symbol"] = symbol
    out["snapshot_ts"] = pd.Timestamp(now)
    try:
        out["spot"] = float(tk.fast_info["last_price"])
    except Exception:
        # Spot is recoverable later from the OHLCV cache; its absence must not
        # cost us the chain itself.
        out["spot"] = pd.NA
        log.warning("%s: spot unavailable, archiving chain without it", symbol)
    return out


def write_snapshot(frame: pd.DataFrame, *, out_root: Path, symbol: str,
                   day: dt.date) -> Path:
    """Idempotent write -- re-running a date overwrites that date's file."""
    target_dir = out_root / f"{day:%Y/%m/%d}"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{symbol}.parquet"
    try:
        frame.to_parquet(target, index=False)
    except Exception:
        # pyarrow/fastparquet may be absent; a compressed CSV keeps the day
        # rather than losing it to a packaging detail.
        target = target.with_suffix(".csv.gz")
        frame.to_csv(target, index=False, compression="gzip")
    return target


def run(symbols, *, max_dte: int, out_root: Path, now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now()
    day = now.date()
    ok = 0

    for i, symbol in enumerate(symbols, 1):
        # One flushed line per symbol: this is the repo's rule for anything
        # that runs unattended, so a stalled run is visible immediately.
        print(f"[{i}/{len(symbols)}] {symbol} ...", end=" ", flush=True)
        try:
            frame = fetch_symbol(symbol, max_dte=max_dte, now=now)
        except Exception:
            log.exception("%s: fetch failed", symbol)
            print("FAILED", flush=True)
            continue
        if frame is None or frame.empty:
            print("no data", flush=True)
            continue

        target = write_snapshot(frame, out_root=out_root, symbol=symbol, day=day)
        ok += 1
        print(f"{len(frame):5d} rows -> {target}", flush=True)

    print(f"\n{ok}/{len(symbols)} symbols archived for {day}", flush=True)
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS),
                   help="comma-separated; default is the capped 10-symbol set")
    p.add_argument("--max-dte", type=int, default=DEFAULT_MAX_DTE)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    return run(symbols, max_dte=args.max_dte, out_root=args.out)


if __name__ == "__main__":
    sys.exit(main())
