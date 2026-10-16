#!/usr/bin/env python3
"""v162: row-count and hash check for the Alpaca history store (spec
Acceptance 1-2, §4).

    python scripts/data/check_history_store.py                    # every stored ticker
    python scripts/data/check_history_store.py --tickers AAPL,MSFT
    python scripts/data/check_history_store.py --verify-hashes    # also every file vs its manifest

Counts each ticker's bars per session against SPY's own bars in the same
timeframe (15min over regular hours: 26 a full session, 14 a 13:00 half-day;
hourly 7 and 4; daily 1). Holidays, half-days and dates before a listing are
explained; thin names with missing bars are reported as sparse. A missing
session, an extra one or a ticker that stops early is unexplained.
Exit code 1 on any unexplained gap or hash problem.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from swingbot.core.marketdata import history_store  # noqa: E402
from swingbot.core.marketdata.data_store import safe_symbol  # noqa: E402

RTH_15MIN_FULL = 26
RTH_15MIN_HALF = 14
HOURLY_FULL = 7
HOURLY_HALF = 4
CALENDAR_TICKER = "SPY"
EXPECTED = {"15min": (RTH_15MIN_FULL, RTH_15MIN_HALF), "hourly": (HOURLY_FULL, HOURLY_HALF),
            "daily": (1, 1)}
MAX_LINES_PER_PAIR = 20


def _path(root: Path, ticker: str, timeframe: str) -> Path:
    return Path(root) / timeframe / f"{safe_symbol(ticker)}.csv"


def read_frame(root: Path, ticker: str, timeframe: str) -> pd.DataFrame | None:
    """The stored frame; 15min cut to bars starting 09:30-15:45. None when absent."""
    path = _path(root, ticker, timeframe)
    if not path.exists():
        return None
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    if timeframe == "15min":
        frame = frame.between_time("09:30", "15:45")
    return frame if len(frame) else None


def session_counts(frame: pd.DataFrame) -> pd.Series:
    """Bars per date, indexed by the naive midnight of each date."""
    return frame.groupby(frame.index.normalize()).size()


def _label(day: pd.Timestamp) -> str:
    return day.strftime("%Y-%m-%d")


def _classify_days(calendar_days: pd.Series, counts: pd.Series, expected, result: dict) -> None:
    full, half = expected
    for day, want in calendar_days.items():
        have = int(counts.get(day, 0))
        if want not in (full, half):
            result["unexplained"].append(f"{_label(day)}: calendar has {want} bars")
        elif have == want:
            result["full" if want == full else "half_day"] += 1
        elif 0 < have < want:
            result["sparse"] += 1
        else:
            result["unexplained"].append(f"{_label(day)}: {have} of {want} bars")


def _edges(counts: pd.Series, calendar: pd.Series, result: dict) -> None:
    first, last = counts.index.min(), counts.index.max()
    result["pre_listing"] = int((calendar.index < first).sum())
    weekdays = pd.bdate_range(first, last)
    result["holiday"] = int((~weekdays.isin(calendar.index)).sum())
    for day in counts.index.difference(calendar.index):
        result["unexplained"].append(f"{_label(day)}: bars on a day {CALENDAR_TICKER} did not trade")
    after = int((calendar.index > last).sum())
    if after > 1:
        result["unexplained"].append(
            f"ends {_label(last)}, {after} sessions before {CALENDAR_TICKER}")


def check_ticker(ticker: str, timeframe: str, *, root: Path, calendar: pd.Series) -> dict:
    result = {"ticker": ticker, "timeframe": timeframe, "sessions": 0, "full": 0,
              "half_day": 0, "holiday": 0, "pre_listing": 0, "sparse": 0, "unexplained": []}
    frame = read_frame(root, ticker, timeframe)
    if frame is None:
        result["unexplained"].append("no file or no rows")
        return result
    counts = session_counts(frame)
    first, last = counts.index.min(), counts.index.max()
    in_range = calendar[(calendar.index >= first) & (calendar.index <= last)]
    result["sessions"] = len(in_range)
    _classify_days(in_range, counts, EXPECTED[timeframe], result)
    _edges(counts, calendar, result)
    return result


def _manifest(root: Path, timeframe: str) -> dict | None:
    path = Path(root) / timeframe / "_manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _hash_problem(root: Path, timeframe: str, ticker: str, entry: dict) -> list[str]:
    want = entry.get("sha256")
    if not want:
        return []
    path = _path(root, ticker, timeframe)
    if not path.exists():
        return [f"{timeframe}/{ticker}: file missing ({path})"]
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    return [] if got == want else [f"{timeframe}/{ticker}: sha256 {got[:12]} != manifest {want[:12]}"]


def verify_hashes(root: Path) -> list[str]:
    """One line per manifest entry whose file is missing or differs."""
    problems = []
    for tf in history_store.TIMEFRAMES:
        manifest = _manifest(root, tf)
        if manifest is None:
            problems.append(f"{tf}: no manifest at {Path(root) / tf / '_manifest.json'}")
            continue
        for ticker, entry in sorted(manifest.get("tickers", {}).items()):
            problems += _hash_problem(root, tf, ticker, entry)
    return problems


def _pairs(root: Path, tickers: list[str] | None, timeframe: str):
    """(stored tickers, skipped {ticker: status}) for one timeframe."""
    entries = (_manifest(root, timeframe) or {}).get("tickers", {})
    wanted = tickers or sorted(entries)
    stored = [t for t in wanted if (entries.get(t) or {}).get("sha256")]
    skipped = {t: (entries.get(t) or {}).get("status", "not in manifest")
               for t in wanted if t not in stored}
    return stored, skipped


def _print_result(res: dict) -> None:
    print(f"{res['ticker']:<8} {res['timeframe']:<6} sessions={res['sessions']} "
          f"full={res['full']} half={res['half_day']} holiday={res['holiday']} "
          f"pre_listing={res['pre_listing']} sparse={res['sparse']} "
          f"unexplained={len(res['unexplained'])}")
    for line in res["unexplained"][:MAX_LINES_PER_PAIR]:
        print(f"    {line}")


def _check_timeframe(root: Path, tickers: list[str] | None, timeframe: str) -> int:
    """Unexplained-gap count for one timeframe (1 when SPY has no file)."""
    stored, skipped = _pairs(root, tickers, timeframe)
    for ticker, status in sorted(skipped.items()):
        print(f"SKIP {ticker} {timeframe}: {status}")
    spy = read_frame(root, CALENDAR_TICKER, timeframe)
    if spy is None:
        print(f"{timeframe}: no {CALENDAR_TICKER} calendar under {Path(root) / timeframe}")
        return 1
    calendar = session_counts(spy)
    bad = 0
    for ticker in stored:
        res = check_ticker(ticker, timeframe, root=root, calendar=calendar)
        _print_result(res)
        bad += len(res["unexplained"])
    return bad


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None,
                    help="store root (default: HISTORY_STORE_DIR or data/market_data)")
    ap.add_argument("--tickers", default=None, help="comma list (default: every stored ticker)")
    ap.add_argument("--verify-hashes", action="store_true",
                    help="also check every file against its manifest SHA-256")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root or history_store.store_root()
    tickers = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else None
    problems = verify_hashes(root) if args.verify_hashes else []
    for line in problems:
        print(f"HASH {line}")
    unexplained = sum(_check_timeframe(root, tickers, tf) for tf in history_store.TIMEFRAMES)
    print(f"check: {unexplained} unexplained gap(s), {len(problems)} hash problem(s)")
    return 1 if unexplained or problems else 0


if __name__ == "__main__":
    sys.exit(main())
