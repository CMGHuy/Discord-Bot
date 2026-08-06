#!/usr/bin/env python3
"""Extend `data/backtest_cache/` forward in time WITHOUT rewriting history.

Why this exists (plan v8, Task V24 Step 5). The only way to refresh this cache
was `fetch_backtest_data.py --force`, which is all-or-nothing across every
ticker and writes with a bare `df.to_csv(path)` -- it bypasses
`backtest_cache.save_to_disk`, so V43's `CacheShrinkError` guard never fires on
that path. Run with the script's default `--start 2018-06-01` it would silently
truncate ~20 years off the deep-history files. This script only ever appends.

Two failure modes it is built to prevent, both measured on 2026-08-05:

1. **Adjustment-basis seams.** yfinance's `auto_adjust=True` back-adjusts the
   whole series relative to *today*, so refetching an already-cached bar can
   return a different price than when it was written -- SPY's overlap came back
   a uniform -0.5286% lower. Blindly appending today's-basis bars onto an older
   basis splices in a gap that never happened. So every ticker's overlap is
   re-measured before anything is written, and a ticker whose existing rows do
   not reproduce is SKIPPED, never merged.

2. **Mixed conventions in one cache.** This cache is not uniform: 94 of 95
   files are dividend-adjusted, but **SPY is raw/unadjusted** (its adjusted
   spread is 37.5pp back to 1999, its raw spread 0.000pp). Fetching everything
   adjusted would rewrite SPY's entire history onto a different basis -- a
   methodology change wearing a cache-refresh costume. Each file's convention
   is therefore detected from its own overlap and preserved.

Existing rows are never modified: the output is byte-identical for every bar
already on disk, plus strictly-newer bars appended. Writes are atomic
(temp file + `os.replace`) and refuse to shrink a file.

    python scripts/extend_backtest_cache.py                  # dry run (default)
    python scripts/extend_backtest_cache.py --apply
    python scripts/extend_backtest_cache.py --apply --end 2026-08-04 --only SPY,QQQ

`--end` is INCLUSIVE (unlike yfinance's exclusive end). Requires network.
"""
import argparse
import datetime as dt
import json
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import yfinance as yf

from swingbot.core.backtest_cache import CACHE_DIR, cache_path, normalize_ohlcv

# An overlapping bar must reproduce this closely for the convention to count as
# identified. Far below any real dividend/split step, far above float noise.
TOL_PP = 0.02


def load_known_tickers() -> dict[str, str]:
    """Map cache filename stem -> real yfinance symbol.

    `cache_path` mangles `^`/`=`/`/` into `_`, which is not reversible (`_VIX`
    could be `^VIX` or a literal). So the mapping is rebuilt forward from the
    symbols this repo actually caches rather than guessed from the filename.
    """
    from scripts.fetch_backtest_data import CONTEXT_TICKERS

    watchlist = json.loads((ROOT / "data" / "watchlist.json").read_text())
    out: dict[str, str] = {}
    for sym in set(watchlist) | set(CONTEXT_TICKERS):
        out[cache_path(sym).stem] = sym
    return out


def resolve_symbol(stem: str, known: dict[str, str]) -> str | None:
    """Real yfinance symbol for a cache file, or None if it can't be resolved.

    Some cached ETFs (DIA/GLD/IWM/QQQ/TLT) are in neither the watchlist nor
    CONTEXT_TICKERS. `cache_path` only ever mangles `^`/`=`/`/` INTO `_`, so a
    stem with no `_` cannot have been mangled and is its own symbol. A stem
    containing `_` is genuinely ambiguous (`_VIX` -> `^VIX`? `VIX=F`?) and is
    left unresolved rather than guessed.
    """
    if stem in known:
        return known[stem]
    return stem if "_" not in stem else None


def _flatten(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    df = normalize_ohlcv(df)
    if df is None:
        return None
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    return df


def fetch_full(symbol: str, adjusted: bool) -> pd.DataFrame | None:
    return _flatten(yf.download(symbol, period="max", auto_adjust=adjusted,
                                progress=False))


def overlap_spread(disk: pd.DataFrame, live: pd.DataFrame) -> tuple[float, int]:
    """Max-minus-min of live/disk close ratio over shared dates, in percentage
    points, plus the number of shared bars. A constant non-zero offset still
    shows as ~0 spread, so the caller also checks the level, not just the
    spread."""
    common = disk.index.intersection(live.index)
    if len(common) == 0:
        return float("inf"), 0
    ratio = live.loc[common, "Close"] / disk.loc[common, "Close"]
    return float((ratio.max() - ratio.min()) * 100), len(common)


def max_abs_offset(disk: pd.DataFrame, live: pd.DataFrame) -> float:
    common = disk.index.intersection(live.index)
    ratio = live.loc[common, "Close"] / disk.loc[common, "Close"]
    return float((ratio - 1).abs().max() * 100)


def _atomic_append(path: Path, new: pd.DataFrame, expect_rows: int) -> bool:
    """Append `new` while leaving every existing byte untouched.

    Round-tripping a CSV through pandas is not byte-stable -- `read_csv` +
    `to_csv` re-serializes `108.07000000000001` as `108.07`. Numerically that
    is a no-op, but rewriting the whole file turns a 3.5k-row extension into a
    191k-line diff on a git-tracked cache and puts 27 years of history through
    a formatter for no reason. Copying the original bytes and appending only
    the new rows makes "history is never modified" true by construction rather
    than by inspection.

    Still atomic: the copy is built as a temp file and swapped in with
    `os.replace`, and it is re-read at full length before the swap.
    """
    tmp = path.with_suffix(".csv.tmp")
    original = path.read_bytes()
    if not original.endswith(b"\n"):
        original += b"\n"
    tmp.write_bytes(original + new.to_csv(header=False).encode())
    try:
        check = pd.read_csv(tmp, index_col="Date", parse_dates=True)
    except Exception:  # noqa: BLE001 -- unreadable temp file is a failed write
        tmp.unlink(missing_ok=True)
        return False
    if len(check) != expect_rows or not check.index.is_monotonic_increasing \
            or check.index.has_duplicates:
        tmp.unlink(missing_ok=True)
        return False
    os.replace(tmp, path)
    return True


def _atomic_write(path: Path, df: pd.DataFrame) -> bool:
    """Write via temp file + os.replace, verifying the temp file reads back at
    full length first. A truncated or garbled write must never replace a good
    cache file."""
    tmp = path.with_suffix(".csv.tmp")
    df.to_csv(tmp)
    try:
        check = pd.read_csv(tmp, index_col="Date", parse_dates=True)
    except Exception:  # noqa: BLE001 -- unreadable temp file is a failed write
        tmp.unlink(missing_ok=True)
        return False
    if len(check) != len(df):
        tmp.unlink(missing_ok=True)
        return False
    os.replace(tmp, path)
    return True


def process(stem: str, symbol: str, end: pd.Timestamp, apply: bool,
            rebase: bool = False) -> dict:
    path = cache_path(symbol)
    r = {"ticker": stem, "status": "", "added": 0, "convention": "", "note": ""}

    disk = pd.read_csv(path, index_col="Date", parse_dates=True)
    if disk.empty:
        r["status"] = "SKIP"
        r["note"] = "empty cache file"
        return r
    disk.index = pd.to_datetime(disk.index)
    last = disk.index[-1]

    if last.normalize() >= end.normalize():
        r["status"] = "CURRENT"
        r["note"] = f"already through {last.date()}"
        return r

    # Identify the file's own convention by which fetch reproduces its history.
    chosen = None
    rescaled = None  # uniform-offset candidate, usable only via --rebase
    diag = []
    for adjusted in (True, False):
        live = fetch_full(symbol, adjusted)
        if live is None:
            diag.append(f"{'adj' if adjusted else 'raw'}=no-data")
            continue
        spread, n = overlap_spread(disk, live)
        offset = max_abs_offset(disk, live) if n else float("inf")
        diag.append(f"{'adj' if adjusted else 'raw'}={spread:.3f}pp/{offset:.3f}%")
        if n < 20:
            continue
        # Both the shape (spread) and the level (offset) must match: a uniform
        # offset has spread ~0 but is still a different basis.
        if spread <= TOL_PP and offset <= TOL_PP:
            chosen = (live, "adjusted" if adjusted else "raw")
            break
        # Shape matches, level does not: the ticker went ex-dividend since it
        # was cached, so the whole file is a constant multiple of today's
        # series. Appending would splice in a gap-down that never happened;
        # rebasing the file is exact, because a uniform rescale leaves every
        # percentage return -- and therefore every R-multiple -- unchanged.
        if rescaled is None and spread <= TOL_PP:
            rescaled = (live, "adjusted" if adjusted else "raw", offset)

    if chosen is None and rescaled is not None and rebase:
        live, convention, offset = rescaled
        if len(live) < len(disk) or live.index[0] > disk.index[0]:
            r["status"] = "SKIP"
            r["note"] = (f"rebase would lose history "
                         f"({len(live)} live vs {len(disk)} disk rows)")
            return r
        # Clamp to the file's existing start. A `period="max"` refetch reaches
        # back further than the cache deliberately does (PFE's live history
        # starts in the 1970s against a cache that starts 2000-01-03), and
        # prepending decades would quietly enlarge the TRAIN window for a
        # handful of tickers. Rebase rescales and extends forward -- nothing else.
        new_end = live[(live.index >= disk.index[0]) & (live.index <= end)]
        r["convention"] = convention
        r["added"] = len(new_end) - len(disk)
        r["note"] = (f"REBASED {offset:.3f}% (uniform; returns unchanged) "
                     f"{last.date()} -> {new_end.index[-1].date()}")
        if not apply:
            r["status"] = "WOULD-REBASE"
            return r
        if not _atomic_write(path, new_end):
            r["status"] = "SKIP"
            r["note"] = "verification read-back mismatch"
            return r
        r["status"] = "REBASED"
        return r

    if chosen is None:
        r["status"] = "SKIP"
        hint = "" if rescaled is None else " [uniform rescale -- rerun with --rebase]"
        r["note"] = "no convention reproduced history; " + " ".join(diag) + hint
        return r

    live, convention = chosen
    r["convention"] = convention

    new = live[(live.index > last) & (live.index <= end)]
    if new.empty:
        r["status"] = "NONE"
        r["note"] = f"no bars after {last.date()}"
        return r

    merged = pd.concat([disk, new])
    if not merged.index.is_monotonic_increasing or merged.index.has_duplicates:
        r["status"] = "SKIP"
        r["note"] = "merge produced duplicate/out-of-order index"
        return r
    if len(merged) < len(disk):  # cannot happen by construction; assert anyway
        r["status"] = "SKIP"
        r["note"] = "refusing to shrink"
        return r

    r["added"] = len(new)
    r["note"] = f"{last.date()} -> {new.index[-1].date()}"
    if not apply:
        r["status"] = "WOULD-ADD"
        return r

    if not _atomic_append(path, new, len(merged)):
        r["status"] = "SKIP"
        r["note"] = "verification read-back mismatch"
        return r
    r["status"] = "ADDED"
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--end", default="today",
                    help="last bar to include, INCLUSIVE (YYYY-MM-DD or 'today')")
    ap.add_argument("--only", default=None,
                    help="comma-separated ticker subset (cache filename stems)")
    ap.add_argument("--apply", action="store_true",
                    help="actually write; default is a dry run")
    ap.add_argument("--rebase", action="store_true",
                    help="for files that are a UNIFORM rescale of today's series "
                         "(went ex-dividend since caching), rewrite the whole file "
                         "onto today's basis instead of skipping. Exact: a uniform "
                         "rescale leaves every percentage return unchanged.")
    args = ap.parse_args()

    end = (pd.Timestamp(dt.date.today()) if args.end in ("today", "now")
           else pd.Timestamp(args.end))

    known = load_known_tickers()
    stems = sorted(p.stem for p in CACHE_DIR.glob("*.csv"))
    if args.only:
        want = {s.strip() for s in args.only.split(",") if s.strip()}
        stems = [s for s in stems if s in want]

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"[{mode}] extending {len(stems)} cached tickers through {end.date()} "
          f"(inclusive)\n", flush=True)

    results = []
    unknown = []
    for i, stem in enumerate(stems, 1):
        symbol = resolve_symbol(stem, known)
        if symbol is None:
            unknown.append(stem)
            print(f"  [{i:3}/{len(stems)}] {stem:8} SKIP    not in watchlist/context "
                  f"-- cannot resolve real symbol", flush=True)
            continue
        try:
            r = process(stem, symbol, end, args.apply, args.rebase)
        except Exception as exc:  # noqa: BLE001 -- one bad ticker must not abort the run
            r = {"ticker": stem, "status": "ERROR", "added": 0,
                 "convention": "", "note": repr(exc)[:120]}
        results.append(r)
        print(f"  [{i:3}/{len(stems)}] {stem:8} {r['status']:10} "
              f"{r['added']:4} bars  {r['convention']:8} {r['note']}", flush=True)

    added = [r for r in results if r["status"] in ("ADDED", "WOULD-ADD",
                                                   "REBASED", "WOULD-REBASE")]
    bad = [r for r in results if r["status"] in ("SKIP", "ERROR")]
    print(f"\nDone: {len(added)} extended ({sum(r['added'] for r in added)} bars), "
          f"{sum(1 for r in results if r['status'] == 'CURRENT')} already current, "
          f"{sum(1 for r in results if r['status'] == 'NONE')} no new bars, "
          f"{len(bad)} skipped/errored, {len(unknown)} unresolvable")
    conv = {}
    for r in added:
        conv[r["convention"]] = conv.get(r["convention"], 0) + 1
    if conv:
        print("Conventions preserved: " + ", ".join(f"{k}={v}" for k, v in sorted(conv.items())))
    for r in bad:
        print(f"  ! {r['ticker']}: {r['status']} -- {r['note']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
