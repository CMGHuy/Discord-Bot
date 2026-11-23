#!/usr/bin/env python3
"""v239 V239-1: one-time SPY + ^VIX daily cache for the bear-regime base-rate
study (scripts/research/regime_base_rates.py).

Fetches adjusted daily bars (yfinance, auto_adjust=True: the same adjusted
series the live scan's daily frames carry) from START through the study's
fixed END into data/backtest_cache_regime/, one CSV per symbol with LF line
endings, plus manifest.json holding each file's SHA-256, row count and first
and last dates. The study refuses to run when a file's hash differs from the
manifest, so this script refuses to overwrite an existing cache unless
--force is passed. Nothing is written unless both symbols pass their checks.

    python scripts/data/fetch_regime_data.py
    python scripts/data/fetch_regime_data.py --force          # refetch on purpose

^VIX is not Alpaca-eligible (the caret fails the US-symbol shape), so the
live engine also reads it from yfinance through get_daily_data; SPY goes to
the Alpaca router first there. This cache is yfinance for both, which is the
gap the v239 parity check (scripts/reports/regime_parity.py) measures."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.marketdata.backtest_cache import normalize_ohlcv  # noqa: E402

CACHE_DIR = ROOT / "data" / "backtest_cache_regime"
START = "1993-01-01"
END = "2026-11-20"
SYMBOLS = ("SPY", "^VIX")
MANIFEST = "manifest.json"
LATEST_FIRST_BAR = "1993-02-01"  # SPY lists 1993-01-29; ^VIX history starts in 1990
_OHLC = ["Open", "High", "Low", "Close"]


def csv_path(cache_dir: Path, symbol: str) -> Path:
    """One CSV per symbol; the caret stays (``^VIX.csv``)."""
    return Path(cache_dir) / f"{symbol}.csv"


def _download(symbol: str, start: str, end: str) -> pd.DataFrame | None:
    """Adjusted daily bars [start, end) from yfinance (``end`` is exclusive)."""
    import yfinance as yf  # local import: the tests never reach the network

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = yf.download(symbol, start=start, end=end, interval="1d",
                          auto_adjust=True, progress=False)
    return normalize_ohlcv(raw)


def _clean(frame: pd.DataFrame, end: str) -> pd.DataFrame:
    frame = frame[_OHLC + ["Volume"]].dropna(subset=_OHLC).copy()
    frame["Volume"] = frame["Volume"].fillna(0.0)
    index = pd.DatetimeIndex(frame.index)
    frame.index = (index.tz_localize(None) if index.tz is not None else index).normalize()
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    frame = frame[frame.index <= pd.Timestamp(end)]
    frame.index.name = "Date"
    return frame


def _problem(symbol: str, frame: pd.DataFrame | None) -> str | None:
    if frame is None or frame.empty:
        return f"{symbol}: the fetch returned no rows"
    first, last = frame.index[0].date().isoformat(), frame.index[-1].date().isoformat()
    if first > LATEST_FIRST_BAR:
        return f"{symbol}: first bar {first} is later than {LATEST_FIRST_BAR}"
    if last != END:
        return f"{symbol}: last bar {last} is not the study end {END}"
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(cache_dir: Path, frames: dict[str, pd.DataFrame], command: str) -> dict:
    """Hash the CSVs already on disk and write manifest.json next to them."""
    symbols = {}
    for symbol, frame in frames.items():
        symbols[symbol] = {"sha256": sha256_file(csv_path(cache_dir, symbol)),
                           "rows": int(len(frame)),
                           "first": frame.index[0].date().isoformat(),
                           "last": frame.index[-1].date().isoformat()}
    manifest = {"symbols": symbols, "command": command,
                "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    with open(Path(cache_dir) / MANIFEST, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return manifest


def _fetch_all(end_exclusive: str) -> tuple[dict[str, pd.DataFrame], str | None]:
    frames = {}
    for symbol in SYMBOLS:
        raw = _download(symbol, START, end_exclusive)
        frame = None if raw is None or raw.empty else _clean(raw, END)
        problem = _problem(symbol, frame)
        if problem is not None:
            return {}, problem
        frames[symbol] = frame
    return frames, None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(description="Fetch SPY + ^VIX daily for the v239 base-rate study")
    ap.add_argument("--cache-dir", default=str(CACHE_DIR))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    cache_dir = Path(args.cache_dir)
    if (cache_dir / MANIFEST).exists() and not args.force:
        print(f"refusing: {cache_dir / MANIFEST} exists; the study is pinned to it "
              "(pass --force to refetch on purpose)")
        return 2
    end_exclusive = (pd.Timestamp(END) + pd.Timedelta(days=1)).date().isoformat()
    frames, problem = _fetch_all(end_exclusive)
    if problem is not None:
        print(f"error: {problem}; nothing written")
        return 2
    cache_dir.mkdir(parents=True, exist_ok=True)
    for symbol, frame in frames.items():
        frame.to_csv(csv_path(cache_dir, symbol), lineterminator="\n")
    command = " ".join(["python", "scripts/data/fetch_regime_data.py", *argv])
    manifest = write_manifest(cache_dir, frames, command)
    for symbol, entry in manifest["symbols"].items():
        print(f"+ {symbol}: {entry['rows']} bars ({entry['first']} -> {entry['last']}) "
              f"sha256 {entry['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
