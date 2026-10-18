"""Cache-coverage check: the v136 phase-3 data precondition (spec section 1).

Before any v2 run, every point-in-time member of the research span must have
cached history back to the instrument's ``warmup_start`` (2009-06-01: the
indicator warm-up before the 2010 research start). This module lists the
members that do not -- it never drops one -- so a gap is a visible decision,
not a silently shrunken universe.

It reads the BACKTEST cache only (``data/backtest_cache[_ext]/``, see
``swingbot.core.marketdata.backtest_cache``), never ``market_data/``, and only
the first dated row of each CSV. ``cache_dir`` is always passed in:
``BACKTEST_CACHE_DIR`` is read once at import, so callers decide.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from swingbot.core.marketdata import backtest_cache, pit_membership

_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class CoverageReport:
    """Every checked symbol lands in exactly one of covered / late / missing."""

    required_start: str
    covered: tuple[str, ...]
    late: tuple[tuple[str, str], ...]   # (symbol, first cached bar)
    missing: tuple[str, ...]            # no CSV, or a CSV with no dated row

    @property
    def gaps(self) -> int:
        return len(self.late) + len(self.missing)


def first_bar_date(path: Path) -> str | None:
    """ISO day of the first dated row of a cache CSV (rows are ascending), or
    None when the file is absent or holds no dated row. Undated header rows
    (yfinance's 'Ticker,...' / 'Date,,,') are skipped."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                cell = line.split(",", 1)[0].strip()
                if _ISO_DAY.match(cell):
                    return cell[:10]
    except OSError:
        return None
    return None


def _intervals(spec) -> dict[str, list[tuple[str, str]]]:
    path = pit_membership.membership_file_for(spec.universe)
    if path is None:
        raise ValueError(f"instrument {spec.version!r} has no point-in-time universe "
                         f"(universe={spec.universe!r})")
    intervals = pit_membership.load_intervals(path)
    if not intervals:
        raise FileNotFoundError(f"membership file missing or empty: {path}")
    return intervals


def research_members(spec) -> list[str]:
    """Every symbol that was a member at any point in the research span, sorted."""
    return pit_membership.members_between(_intervals(spec), *spec.research_span)


def first_membership(spec, symbols) -> dict[str, str]:
    """{symbol: start of its earliest membership span touching the research
    span}; symbols with no such span are left out."""
    intervals = _intervals(spec)
    start, end = spec.research_span
    out = {}
    for sym in symbols:
        starts = [s for s, e in intervals.get(sym, []) if s <= end and e > start]
        if starts:
            out[sym] = min(starts)
    return out


def check_coverage(symbols, required_start: str, cache_dir: Path) -> CoverageReport:
    """Classify each distinct symbol by its cached first bar against `required_start`."""
    covered, late, missing = [], [], []
    for sym in sorted(set(symbols)):
        first = first_bar_date(Path(cache_dir) / backtest_cache.cache_path(sym).name)
        if first is None:
            missing.append(sym)
        elif first > required_start:
            late.append((sym, first))
        else:
            covered.append(sym)
    return CoverageReport(required_start, tuple(covered), tuple(late), tuple(missing))


def _summary_lines(report: CoverageReport) -> list[str]:
    return [
        f"Required first bar: {report.required_start}",
        "",
        "| Status | Symbols |",
        "|---|---|",
        f"| Covered | {len(report.covered)} |",
        f"| Late | {len(report.late)} |",
        f"| Missing | {len(report.missing)} |",
        f"| Gaps | {report.gaps} |",
    ]


def _gap_lines(report: CoverageReport, first_membership: dict[str, str]) -> list[str]:
    lines = []
    if report.late:
        lines += ["", "## Late (first cached bar after the required day)", "",
                  "| Symbol | First cached bar | First PIT membership |", "|---|---|---|"]
        lines += [f"| {sym} | {first} | {first_membership.get(sym, '?')} |"
                  for sym, first in report.late]
    if report.missing:
        lines += ["", "## Missing (no cached CSV or no dated row)", "",
                  "| Symbol | First PIT membership |", "|---|---|"]
        lines += [f"| {sym} | {first_membership.get(sym, '?')} |" for sym in report.missing]
    return lines


def render_markdown(report: CoverageReport, first_membership: dict[str, str]) -> str:
    """The summary table plus one row per gap, each with its first membership."""
    lines = _summary_lines(report)
    lines += _gap_lines(report, first_membership) or ["", "No gaps."]
    return "\n".join(lines) + "\n"
