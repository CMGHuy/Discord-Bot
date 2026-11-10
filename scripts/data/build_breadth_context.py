"""Build the BREADTH_ATR1 context file (v211).

Run once, then pin it (V211-13):
    python scripts/data/build_breadth_context.py --cache-dir data/backtest_cache_ext

Writes <cache-dir>/BREADTH_ATR1.csv on SPY's sessions from CONTEXT_START, point
in time, and never rebuilds over an existing file. --membership defaults to the
tracked data/universe/sp500_membership.csv.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.screen import breadth  # noqa: E402
from swingbot.core.backtesting.screen import context as screen_context  # noqa: E402
from swingbot.core.marketdata import pit_membership  # noqa: E402
from swingbot.core.marketdata.backtest_cache import cache_path  # noqa: E402

_PRICE = ["Open", "High", "Low", "Close"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build the BREADTH_ATR1 context file.")
    p.add_argument("--cache-dir", required=True, type=Path)
    p.add_argument("--membership", type=Path,
                   default=ROOT / "data" / "universe" / "sp500_membership.csv")
    p.add_argument("--end", default="2019-12-31")
    p.add_argument("--out", type=Path, default=None)
    return p


def spy_sessions(cache_dir: Path, end: str) -> pd.DatetimeIndex:
    path = cache_dir / "SPY.csv"
    if not path.exists():
        raise screen_context.ContextError(f"{path} is missing")
    index = pd.read_csv(path, parse_dates=["Date"], index_col="Date").index
    keep = (index >= pd.Timestamp(screen_context.CONTEXT_START)) & (index <= pd.Timestamp(end))
    return index[keep]


def load_member(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df = df.dropna(subset=_PRICE)
    return df[~df.index.duplicated(keep="first")].sort_index()


def load_members(cache_dir: Path, symbols) -> tuple[dict[str, pd.DataFrame], list[str]]:
    frames: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for symbol in symbols:
        df = load_member(cache_dir / cache_path(symbol).name)
        if df is None:
            missing.append(symbol)
        else:
            frames[symbol] = df
    return frames, sorted(missing)


def coverage_lines(table: pd.DataFrame, intervals, sessions: pd.DatetimeIndex) -> list[str]:
    members = sum(breadth.member_mask(spans, sessions).astype(int) for spans in intervals.values())
    frame = pd.DataFrame({"members": members, "with_data": table["Volume"].to_numpy()},
                         index=sessions)
    lines = []
    for year, grp in frame.groupby(frame.index.year):
        m, w = grp["members"].mean(), grp["with_data"].mean()
        share = w / m if m else 0.0
        lines.append(f"{year}: {w:.1f} of {m:.1f} PIT members with a finite move "
                     f"per session ({share:.1%})")
    return lines


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = args.out or args.cache_dir / f"{breadth.NAME}.csv"
    if out.exists():
        print(f"refusing: {out} exists; {breadth.NAME} is built once and pinned")
        return 2
    intervals = pit_membership.load_intervals(str(args.membership))
    if not intervals:
        print(f"error: no membership rows in {args.membership}")
        return 2
    try:
        sessions = spy_sessions(args.cache_dir, args.end)
    except screen_context.ContextError as exc:
        print(f"error: {exc}")
        return 2
    symbols = pit_membership.members_between(intervals, screen_context.CONTEXT_START, args.end)
    frames, missing = load_members(args.cache_dir, symbols)
    table = breadth.breadth_atr1(frames, intervals, sessions)
    table.to_csv(out)
    print(f"{len(missing)} PIT member(s) without a cache file: {', '.join(missing[:10])}")
    for line in coverage_lines(table, intervals, sessions):
        print(line)
    print(f"+ {breadth.NAME}: {len(table)} sessions ({table.index[0].date()} -> "
          f"{table.index[-1].date()}) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
