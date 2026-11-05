#!/usr/bin/env python3
"""List every point-in-time member whose cached history misses the warm-up.

    BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/data/check_cache_coverage.py --instrument v2
    python scripts/data/check_cache_coverage.py --instrument v2 --cache-dir data/backtest_cache_ext --out report.md
    python scripts/data/check_cache_coverage.py --instrument v3 [--store-root data/market_data_pit]

v136 spec section 1, "Data precondition" (v158 WC2). Reads the research span,
universe and warm-up start from the instrument contract (this script defines
no date) and the BACKTEST cache (`--cache-dir`, default
`backtest_cache.CACHE_DIR`), never market_data/. Lists gaps, drops nothing.
An instrument with a ``store`` (v3) is checked against that store's daily
files, default ``history_store.store_root(store)``.
Exit 0 = every member covered, 1 = gaps listed, 2 = nothing to check or wrong flags.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.instrument import contract, coverage  # noqa: E402
from swingbot.core.marketdata import backtest_cache, history_store  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--instrument", choices=contract.VERSIONS, default="v2",
                    help="instrument whose universe, research span and warm-up are checked")
    ap.add_argument("--cache-dir", default=None,
                    help="backtest cache to read (default: backtest_cache.CACHE_DIR)")
    ap.add_argument("--store-root", default=None,
                    help="v190: the store an instrument with store='pit' (v3) is checked "
                         "against (default: history_store.store_root('pit'))")
    ap.add_argument("--out", default=None, help="write the markdown report here, else stdout")
    return ap


def _gap_symbols(report) -> list[str]:
    return [sym for sym, _ in report.late] + list(report.missing)


_CHECKS = {"Cache": coverage.check_coverage, "Store": coverage.check_store_coverage}


def _source(args, spec) -> tuple[Path, str]:
    """(directory, label) the check reads: the instrument's store when it names
    one (v3), else the backtest cache, exactly as before. ValueError on a flag
    that belongs to the other kind."""
    if spec.store is None:
        if args.store_root:
            raise ValueError(f"--instrument {spec.version} reads the backtest cache; "
                             f"use --cache-dir, not --store-root")
        return (Path(args.cache_dir) if args.cache_dir else backtest_cache.CACHE_DIR), "Cache"
    if args.cache_dir:
        raise ValueError(f"--instrument {spec.version} reads the {spec.store} store; "
                         f"use --store-root, not --cache-dir")
    root = Path(args.store_root) if args.store_root else history_store.store_root(spec.store)
    return root, "Store"


def _report_text(spec, source: Path, label: str) -> tuple[str, int]:
    symbols = coverage.research_members(spec)
    report = _CHECKS[label](symbols, spec.warmup_start, source)
    start, end = spec.research_span
    head = [f"Instrument: {spec.version} (universe {spec.universe}, research {start}..{end})",
            f"{label}: `{source}`", f"Members checked: {len(symbols)}", ""]
    firsts = coverage.first_membership(spec, _gap_symbols(report))
    body = coverage.render_markdown(report, firsts)
    return "\n".join(head) + body, report.gaps


def run(argv=None) -> int:
    args = _parser().parse_args(argv)
    spec = contract.resolve(args.instrument)
    if spec.warmup_start is None or spec.universe is None:
        print(f"instrument {spec.version} defines no warm-up start or point-in-time universe: "
              "nothing to check", file=sys.stderr)
        return 2
    try:
        source, label = _source(args, spec)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    text, gaps = _report_text(spec, source, label)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    print(f"COVERAGE: {'GAPS' if gaps else 'OK'}  {gaps} gap(s), {label.lower()} {source}", file=sys.stderr)
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(run())
