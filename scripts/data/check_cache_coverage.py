#!/usr/bin/env python3
"""List every point-in-time member whose cached history misses the warm-up.

    BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/data/check_cache_coverage.py --instrument v2
    python scripts/data/check_cache_coverage.py --instrument v2 --cache-dir data/backtest_cache_ext --out report.md

v136 spec section 1, "Data precondition" (v158 WC2). Reads the research span,
universe and warm-up start from the instrument contract (this script defines
no date) and the BACKTEST cache (`--cache-dir`, default
`backtest_cache.CACHE_DIR`), never market_data/. Lists gaps, drops nothing.
Exit 0 = every member covered, 1 = gaps listed, 2 = nothing to check.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.instrument import contract, coverage  # noqa: E402
from swingbot.core.marketdata import backtest_cache  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--instrument", choices=contract.VERSIONS, default="v2",
                    help="instrument whose universe, research span and warm-up are checked")
    ap.add_argument("--cache-dir", default=None,
                    help="backtest cache to read (default: backtest_cache.CACHE_DIR)")
    ap.add_argument("--out", default=None, help="write the markdown report here, else stdout")
    return ap


def _gap_symbols(report) -> list[str]:
    return [sym for sym, _ in report.late] + list(report.missing)


def _report_text(spec, cache_dir: Path) -> tuple[str, int]:
    symbols = coverage.research_members(spec)
    report = coverage.check_coverage(symbols, spec.warmup_start, cache_dir)
    start, end = spec.research_span
    head = [f"Instrument: {spec.version} (universe {spec.universe}, research {start}..{end})",
            f"Cache: `{cache_dir}`", f"Members checked: {len(symbols)}", ""]
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
    cache_dir = Path(args.cache_dir) if args.cache_dir else backtest_cache.CACHE_DIR
    text, gaps = _report_text(spec, cache_dir)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    print(f"COVERAGE: {'GAPS' if gaps else 'OK'}  {gaps} gap(s), cache {cache_dir}", file=sys.stderr)
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(run())
