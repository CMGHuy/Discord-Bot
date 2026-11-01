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

    python scripts/data/check_history_store.py --pit --root data/market_data_pit --backtest-dir data/backtest_cache_ext

v190 section 2: --pit builds and freezes <root>/_integrity.json (coverage
cuts, vendor identity re-derived against backtest_cache_ext only, reused-symbol
trims and context symbols) plus a Markdown summary. It reads files directly:
history_store.load(store="pit") refuses until this report exists. Freeze the
report before any strategy result is read; a later manifest rewrite makes it stale.
"""
import argparse
import hashlib
import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_SCRIPTS = ROOT / "scripts" / "data"
if str(DATA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DATA_SCRIPTS))

import pandas as pd  # noqa: E402

from alpaca_history import identity, pit_coverage, reuse, store_io  # noqa: E402
from swingbot import config  # noqa: E402

from swingbot.core.marketdata import history_store, pit_integrity, pit_membership, universe  # noqa: E402
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



# --- PIT integrity freeze --------------------------------------------------------------

DETECTORS = ("scripts/data/alpaca_history/reuse.py", "scripts/data/alpaca_history/pit_coverage.py")
REFERENCE_SOURCE = "backtest_cache_ext"
NO_BARS = "skipped: no Alpaca bars"
NOT_FETCHED = "not fetched"
NO_WINDOW_BARS = "no daily bars in the store window"
TRIM_EMPTY = "integrity trim leaves no bars"
PIT_ADMITTED = ("ok", "flagged: no-reference")
SUMMARY_NAME = "{month}-v190-pit-integrity-report.md"


@dataclass
class _PitRun:
    root: Path
    sessions: pd.DatetimeIndex
    entries: dict
    intervals: dict[str, list[tuple[str, str]]]
    backtest_dir: Path
    thresholds: reuse.Thresholds


def detector_blob(path: Path) -> str:
    """Git's blob id, normalising the checkout's CRLF line endings."""
    raw = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def context_symbols() -> list[str]:
    return sorted({CALENDAR_TICKER, config.MARKET_REGIME_TICKER, *universe.sector_map("etfs")})


def _blank_entry(manifest: dict | None) -> dict:
    return {"admitted": False, "reason": None, "identity": None,
            "identity_manifest": manifest.get("status") if manifest else None,
            "reference": {"source": None, "sha256": None}, "dropped_before": 0,
            "first_bar": None, "last_bar": None, "coverage": [], "signal_cuts": [],
            "trim": None, "breaks": [], "gaps": []}


def _reference_part(ticker: str, frame: pd.DataFrame, entry: dict, run: _PitRun):
    path = identity.reference_path(ticker, backtest_dir=run.backtest_dir, market_dir=None)
    ref = identity.reference_frame(ticker, backtest_dir=run.backtest_dir, market_dir=None)
    if path is not None:
        entry["reference"] = {"source": REFERENCE_SOURCE, "sha256": store_io.sha256_file(path)}
    entry["identity"] = identity.identity_check(frame, ref)[0].status
    manifest_identity = run.entries[ticker].get("identity") or {}
    dropped = manifest_identity.get("dropped_before")
    if dropped:
        entry["dropped_before"] = int(((run.sessions >= pit_coverage.STORE_START)
                                        & (run.sessions < dropped)).sum())
    return ref


def _coverage_part(frame: pd.DataFrame, spans: list, entry: dict, run: _PitRun) -> None:
    measured = spans or [(pit_coverage.STORE_START, pit_coverage.STORE_END_EXCL)]
    coverage, cuts = pit_coverage.coverage_entry(frame.index, run.sessions, measured)
    entry.update(coverage=coverage, signal_cuts=[list(cut) for cut in cuts])


def _reuse_part(frame: pd.DataFrame, ref, spans: list, entry: dict, run: _PitRun) -> None:
    last_reference = _label(ref.index.max()) if ref is not None else None
    gaps = reuse.series_gaps(frame, spans, last_reference, run.sessions, run.thresholds)
    priority = [g["from"] for g in gaps if g["kind"] in ("end", "reference-end")]
    breaks = reuse.find_breaks(frame, run.thresholds, sessions_from=min(priority, default=None))
    entry.update(reuse.resolve(breaks, spans, frame, run.thresholds), gaps=gaps)


def _break_refusal(entry: dict, resolution: str) -> str | None:
    for brk in entry["breaks"]:
        if brk["resolution"] == resolution:
            label = f"{brk['date']} ({brk['kind']})"
            if resolution == reuse.UNRESOLVED:
                return f"unresolved break {label}"
            return f"in-span break {label}: resolve by hand"
    return None


def _admission(frame: pd.DataFrame, entry: dict) -> None:
    if entry["identity"] not in PIT_ADMITTED:
        entry["reason"] = f"identity re-derived: {entry['identity']}"
        return
    refusal = _break_refusal(entry, reuse.UNRESOLVED) or _break_refusal(entry, reuse.IN_SPAN)
    if refusal:
        entry["reason"] = refusal
        return
    trim = entry["trim"]
    if trim and pit_integrity.apply_trim(frame, (trim["keep_from"], trim["keep_before"])) is None:
        entry["reason"] = TRIM_EMPTY
        return
    entry["admitted"] = True


def _ticker_entry(ticker: str, run: _PitRun) -> dict:
    manifest = run.entries.get(ticker)
    entry = _blank_entry(manifest)
    if manifest is None:
        entry["reason"] = NOT_FETCHED
        return entry
    status = manifest.get("status") or ""
    if status.startswith("skipped:"):
        entry["reason"] = status
        return entry
    frame = read_frame(run.root, ticker, "daily")
    if frame is not None:
        frame = frame[frame.index <= pd.Timestamp(pit_coverage.STORE_END)]
    if frame is None or frame.empty:
        entry["reason"] = NO_WINDOW_BARS
        return entry
    ref = _reference_part(ticker, frame, entry, run)
    entry.update(first_bar=_label(frame.index.min()), last_bar=_label(frame.index.max()))
    spans = run.intervals.get(ticker, [])
    _coverage_part(frame, spans, entry, run)
    _reuse_part(frame, ref, spans, entry, run)
    _admission(frame, entry)
    return entry


def _manifest_hashes(root: Path) -> dict:
    paths = {tf: root / tf / "_manifest.json" for tf in history_store.TIMEFRAMES}
    return {tf: store_io.sha256_file(path) if path.exists() else None for tf, path in paths.items()}


def build_integrity(root: Path, *, intervals: dict[str, list[tuple[str, str]]],
                    backtest_dir: Path, thresholds: reuse.Thresholds, now: datetime) -> dict:
    """Assemble a frozen data verdict from raw files, without admitting via the reader."""
    root = Path(root)
    sessions = pit_coverage.expected_sessions(read_frame(root, CALENDAR_TICKER, "daily"))
    entries = (_manifest(root, "daily") or {}).get("tickers", {})
    no_bars = sorted(t for t, entry in entries.items() if entry.get("status") == NO_BARS)
    members = {t for t, spans in intervals.items() if any(pit_coverage.clip_span(s) for s in spans)}
    tickers = sorted((members | set(entries) | set(context_symbols())) - set(no_bars))
    run = _PitRun(root, sessions, entries, intervals, backtest_dir, thresholds)
    doc = _integrity_header(root, thresholds, now)
    doc.update(aliases={t: entry["alias"] for t, entry in entries.items() if entry.get("alias")},
               no_bars=no_bars, tickers={t: _ticker_entry(t, run) for t in tickers})
    return doc


def _integrity_header(root: Path, thresholds: reuse.Thresholds, now: datetime) -> dict:
    return {"schema": pit_integrity.SCHEMA_VERSION,
            "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "store_start": pit_coverage.STORE_START, "store_end": pit_coverage.STORE_END,
            "thresholds": {"max_missing_run": pit_coverage.MAX_MISSING_RUN,
                           "trailing_sessions": pit_coverage.TRAILING_SESSIONS,
                           "min_trailing_share": pit_coverage.MIN_TRAILING_SHARE, **asdict(thresholds)},
            "detector_sha": {rel: detector_blob(ROOT / rel) for rel in DETECTORS},
            "manifest_sha256": _manifest_hashes(root)}



def write_integrity(root: Path, doc: dict) -> Path:
    path = pit_integrity.integrity_path(root)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)
    return path


def _table(title: str, columns: tuple, rows: list) -> str:
    if not rows:
        return f"## {title}\n\nnone\n"
    header = " | ".join(columns)
    rule = " | ".join("---" for _ in columns)
    body = [" | ".join(str(value).replace("|", "\\|") for value in row) for row in rows]
    return f"## {title}\n\n| {header} |\n| {rule} |\n" + "\n".join(f"| {row} |" for row in body) + "\n"


def _counts(doc: dict) -> tuple[int, int, int]:
    total = len(doc["tickers"])
    admitted = sum(bool(entry["admitted"]) for entry in doc["tickers"].values())
    return admitted, total - admitted, len(doc["no_bars"])


def _summary_title(doc: dict) -> str:
    return ("# v190 PIT store integrity report\n\n"
            f"Generated: {doc['generated_at']}\n\n"
            "This report is frozen before any strategy result is read. Running --mode update "
            "on the store afterwards makes every v3 run stop with StaleIntegrityError.\n")


def _summary_counts(doc: dict) -> str:
    admitted, excluded, no_bars = _counts(doc)
    return (f"## Counts\n\nTickers: {len(doc['tickers'])}; admitted: {admitted}; "
            f"excluded: {excluded}; no bars: {no_bars}; aliases: {len(doc['aliases'])}.\n")


def _summary_thresholds(doc: dict) -> str:
    return _table("Thresholds", ("Threshold", "Value"), list(doc["thresholds"].items()))


def _summary_hashes(doc: dict) -> str:
    return _table("Manifest sha256", ("Timeframe", "sha256"), list(doc["manifest_sha256"].items()))


def _summary_detectors(doc: dict) -> str:
    return _table("Detector sha", ("Path", "Blob"), list(doc["detector_sha"].items()))


def _summary_excluded(doc: dict) -> str:
    rows = [(t, e["reason"]) for t, e in doc["tickers"].items() if not e["admitted"]]
    return _table("Excluded", ("Ticker", "Reason"), rows)


def _summary_trims(doc: dict) -> str:
    rows = [(t, e["trim"]["keep_from"], e["trim"]["keep_before"], e["trim"]["reason"])
            for t, e in doc["tickers"].items() if e["trim"]]
    return _table("Trims", ("Ticker", "keep_from", "keep_before", "Reason"), rows)


def _summary_breaks(doc: dict) -> str:
    rows = [(t, b["date"], b["kind"], b["resolution"])
            for t, e in doc["tickers"].items() for b in e["breaks"]]
    return _table("Breaks", ("Ticker", "Date", "Kind", "Resolution"), rows)


def _summary_cuts(doc: dict) -> str:
    rows = [(t, *cut) for t, e in doc["tickers"].items() for cut in e["signal_cuts"]]
    return _table("Signal cuts", ("Ticker", "Start", "end_excl", "Reason"), rows)


def _summary_dropped(doc: dict) -> str:
    rows = [(t, e["dropped_before"]) for t, e in doc["tickers"].items() if e["dropped_before"]]
    return _table("Bars dropped before the reference", ("Ticker", "Count"), rows)


def _summary_sources(doc: dict) -> str:
    counts = Counter(e["reference"]["source"] or "none" for e in doc["tickers"].values())
    return _table("Reference sources", ("Source", "Count"), sorted(counts.items()))


def _summary_no_bars(doc: dict) -> str:
    names = ", ".join(doc["no_bars"]) or "none"
    aliases = _table("Aliases", ("Member", "Alpaca"), sorted(doc["aliases"].items()))
    return f"## No bars\n\n{names}\n\n{aliases}"


def render_integrity_md(doc: dict) -> str:
    sections = (_summary_title, _summary_counts, _summary_thresholds, _summary_hashes,
                _summary_detectors, _summary_excluded, _summary_trims, _summary_breaks,
                _summary_cuts, _summary_dropped, _summary_sources, _summary_no_bars)
    return "\n".join(section(doc) for section in sections)


def run_pit(args: argparse.Namespace) -> int:
    if args.tickers:
        print("refused: --pit reads the whole store; --tickers does not apply")
        return 2
    root = args.root or history_store.store_root(history_store.PIT)
    problems = verify_hashes(root)
    if problems:
        for problem in problems:
            print(f"HASH {problem}")
        print("refused: hash problems -- no integrity report written")
        return 1
    intervals = pit_membership.load_intervals(pit_membership.membership_file_for("sp500_pit"))
    if not intervals:
        print("refused: no sp500 membership file")
        return 1
    now = datetime.now(timezone.utc)
    try:
        doc = build_integrity(root, intervals=intervals,
                              backtest_dir=args.backtest_dir or history_store.resolve_data_root("backtest_cache_ext"),
                              thresholds=reuse.THRESHOLDS, now=now)
    except ValueError as exc:
        print(f"refused: {exc}")
        return 1
    path = write_integrity(root, doc)
    results = args.results_dir
    results.mkdir(parents=True, exist_ok=True)
    summary = results / SUMMARY_NAME.format(month=now.strftime("%Y-%m"))
    summary.write_text(render_integrity_md(doc), encoding="utf-8", newline="\n")
    admitted, excluded, no_bars = _counts(doc)
    print(f"integrity: {admitted} admitted, {excluded} excluded, {no_bars} no bars -- "
          f"{path} sha256 {store_io.sha256_file(path)[:12]} -- summary {summary}")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None,
                    help="store root (default: HISTORY_STORE_DIR or data/market_data)")
    ap.add_argument("--tickers", default=None, help="comma list (default: every stored ticker)")
    ap.add_argument("--verify-hashes", action="store_true",
                    help="also check every file against its manifest SHA-256")
    ap.add_argument("--pit", action="store_true", help="freeze the whole PIT store integrity report")
    ap.add_argument("--backtest-dir", type=Path, default=None,
                    help="PIT reference cache (default: data/backtest_cache_ext)")
    ap.add_argument("--results-dir", type=Path, default=ROOT / "docs" / "superpowers" / "results",
                    help="PIT Markdown summary directory")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.pit:
        return run_pit(args)
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
