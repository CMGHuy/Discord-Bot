"""v162 §5: freeze a yfinance daily cache into a hashed snapshot.

The §5 re-baseline must be reproducible, and data/backtest_cache/ is refreshed
by the live bot. So the yfinance legs read a copy whose every file is hashed:

  python scripts/data/snapshot_backtest_cache.py --src data/backtest_cache \\
      --out data/backtest_cache_snapshot_v162 --tickers-file T.txt          # leg a
  python scripts/data/snapshot_backtest_cache.py --src data/backtest_cache \\
      --out data/backtest_cache_snapshot_v162_from2016 --tickers-file T.txt \\
      --start 2016-01-01                                                    # leg b
  python scripts/data/snapshot_backtest_cache.py --verify data/backtest_cache_snapshot_v162
  python scripts/data/snapshot_backtest_cache.py --intersect-out T.txt \\
      --watchlist-file W.txt --src data/backtest_cache                      # the §5 ticker set

With --tickers-file the benchmark (config.MARKET_REGIME_TICKER) is always
copied too: every backtest reads it for market context. A snapshot is never
overwritten; <out>/_hashes.json holds a SHA-256 per file and one over all.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HASHES_FILE = "_hashes.json"


def read_tickers_file(path) -> list[str]:
    """One ticker per line; '#' starts a comment. Upper-cased, de-duplicated, sorted."""
    found = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        text = line.split("#", 1)[0].strip().upper()
        if text:
            found.add(text)
    return sorted(found)


def csv_name(ticker: str) -> str:
    """The CSV file name the yfinance cache uses for a ticker."""
    from swingbot.core.marketdata.backtest_cache import cache_path
    return cache_path(ticker).name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def combined_hash(files: dict[str, str]) -> str:
    text = "\n".join(f"{name}:{sha}" for name, sha in sorted(files.items()))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sources(src: Path, tickers) -> list[Path]:
    if tickers is None:
        return sorted(src.glob("*.csv"))
    paths = [src / csv_name(t) for t in tickers]
    missing = [p.name for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"not in {src}: {', '.join(missing)}")
    return paths


def _copy(path: Path, target: Path, start: str | None) -> None:
    if start is None:
        shutil.copyfile(path, target)
        return
    # Byte for byte: the header plus every line whose leading ISO date is >= start,
    # so a truncated file is an exact line subset of its source (no float re-format).
    lines = path.read_bytes().splitlines(keepends=True)
    keep = [line for line in lines[1:] if line.split(b",", 1)[0].decode("ascii", "replace") >= start]
    target.write_bytes(b"".join(lines[:1] + keep))


def snapshot(src, out, *, start: str | None = None, tickers=None,
             now: datetime | None = None) -> dict:
    """Copy the cache (all CSVs, or exactly `tickers`) into `out` and hash it."""
    src, out = Path(src), Path(out)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} exists and is not empty; a snapshot is never overwritten")
    paths = _sources(src, tickers)
    out.mkdir(parents=True, exist_ok=True)
    for path in paths:
        _copy(path, out / path.name, start)
    files = {p.name: _sha256(out / p.name) for p in paths}
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {"src": str(src), "start": start, "created_at": stamp,
                "files": files, "hash": combined_hash(files)}
    (out / HASHES_FILE).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n",
                                   encoding="utf-8")
    return manifest


def verify(out) -> list[str]:
    """One problem line per changed, missing or extra file; [] when intact."""
    out = Path(out)
    hashes = out / HASHES_FILE
    if not hashes.is_file():
        return [f"MISSING {HASHES_FILE}"]
    manifest = json.loads(hashes.read_text(encoding="utf-8"))
    problems = []
    for name, sha in sorted(manifest["files"].items()):
        path = out / name
        if not path.is_file():
            problems.append(f"MISSING {name}")
        elif _sha256(path) != sha:
            problems.append(f"CHANGED {name}")
    problems += [f"EXTRA {p.name}" for p in sorted(out.glob("*.csv"))
                 if p.name not in manifest["files"]]
    if combined_hash(manifest["files"]) != manifest.get("hash"):
        problems.append("HASH top-level hash does not match the file list")
    return problems


def _ok_tickers(manifest: dict | None) -> set[str]:
    entries = (manifest or {}).get("tickers") or {}
    return {t for t, e in entries.items() if (e or {}).get("status") == "ok"}


def intersection_tickers(watchlist, manifest: dict | None, cache_dir) -> list[str]:
    """Watchlist tickers that are 'ok' in the store's daily manifest AND cached."""
    ok = _ok_tickers(manifest)
    wanted = {w.strip().upper() for w in watchlist if w.strip()}
    return sorted(t for t in wanted
                  if t in ok and (Path(cache_dir) / csv_name(t)).is_file())


def _iso_date(text: str) -> str:
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {text!r}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=None, help="the yfinance cache to copy")
    ap.add_argument("--out", type=Path, default=None, help="the snapshot directory (must not exist)")
    ap.add_argument("--start", type=_iso_date, default=None, help="drop rows before this date")
    ap.add_argument("--tickers-file", type=Path, default=None,
                    help="copy exactly these tickers (plus the market benchmark)")
    ap.add_argument("--verify", type=Path, default=None, metavar="DIR",
                    help="check a snapshot against its _hashes.json")
    ap.add_argument("--intersect-out", type=Path, default=None, metavar="PATH",
                    help="write the §5 ticker set (needs --watchlist-file and --src)")
    ap.add_argument("--watchlist-file", type=Path, default=None)
    return ap.parse_args(argv)


def _run_verify(args) -> int:
    problems = verify(args.verify)
    for line in problems:
        print(line)
    print(f"verify: {len(problems)} problem(s) in {args.verify}")
    return 1 if problems else 0


def _run_intersect(args) -> int:
    if not (args.src and args.watchlist_file):
        raise ValueError("--intersect-out needs --watchlist-file and --src")
    from swingbot.core.marketdata import history_store
    tickers = intersection_tickers(read_tickers_file(args.watchlist_file),
                                   history_store.require_manifest("daily"), args.src)
    if not tickers:
        raise ValueError("the intersection is empty")
    args.intersect_out.write_text("\n".join(tickers) + "\n", encoding="utf-8")
    print(f"intersection: {len(tickers)} ticker(s) -> {args.intersect_out}")
    return 0


def _run_snapshot(args) -> int:
    if not (args.src and args.out):
        raise ValueError("a snapshot needs --src and --out")
    tickers = None
    if args.tickers_file:
        from swingbot import config
        tickers = sorted(set(read_tickers_file(args.tickers_file))
                         | {str(config.MARKET_REGIME_TICKER).upper()})
    manifest = snapshot(args.src, args.out, start=args.start, tickers=tickers)
    print(f"snapshot: {len(manifest['files'])} file(s) -> {args.out} hash {manifest['hash']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.verify:
            return _run_verify(args)
        if args.intersect_out:
            return _run_intersect(args)
        return _run_snapshot(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
