#!/usr/bin/env python3
"""v140 idea screen: one idea, one shot, PIT S&P 500 daily bars 2010-2019.

    python scripts/backtest/screen_idea.py --idea high52w \
        --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext

Every event races the idea's frozen shape (v163): ``fixed`` (entry next
open, stop 1.5 x ATR14, target 3 x ATR14, idea-specific time cap, costs) or
``trail`` (same entry and initial stop, no target, a chandelier stop
3 x ATR14[t] under the highest high of the bars before, cap >= 60 bars)
against K = 20 matched random bars raced the same way (same ticker, month
and trend state). verdict.decide applies the four-clause pass rule, the
same for both shapes; the script writes
docs/superpowers/results/<date>-screen-<idea>.md and appends ledger row
screen-<idea>. It refuses an idea already in the
ledger (one shot per idea) and a window end after 2019-12-31. --dry-run
prints the results doc and writes nothing; --tickers needs --dry-run.
--count-only (v182) prints the event count before the shot (the real events,
drops and null draw, full-cap non-overlap) and, for a level idea, check 5; it
races nothing, writes nothing and never reads the ledger.
v182: a short or level idea's results doc ends with the short-side blocks
(event overlap with its family partner, the trend-only control, the SPY
200-day regime split, and for a level idea the fill depths, null_unfilled and
the 3 x repricing) -- all printed, none gating; such a run refuses before
screening when SPY.csv cannot load.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Callable, Mapping

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot import config  # noqa: E402
from swingbot.core.backtesting.screen import forward, indicators, null, race, trail, verdict  # noqa: E402,F401
from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS, Idea  # noqa: E402
from swingbot.core.backtesting.screen import context as screen_context  # noqa: E402
from swingbot.core.backtesting.screen import context as pit  # noqa: E402
from swingbot.core.backtesting.screen import descriptive, diagnostics  # noqa: E402
from swingbot.core.backtesting.screen.context import CONTEXT_START  # noqa: E402,F401
from swingbot.core.edge.frictions import BORROW_RATE_ANNUAL, commission_r  # noqa: E402
from swingbot.core.marketdata import pit_membership  # noqa: E402

WINDOW_START = "2010-01-01"
EVENT_START = "2011-01-01"  # 2010 primes ATR14/SMA200/252-bar max only (v140 F14)
WINDOW_END = "2019-12-31"
OHLCV = ["Open", "High", "Low", "Close", "Volume"]
DEFAULT_CACHE = Path(config.DATA_DIR) / "backtest_cache_ext"
DEFAULT_MEMBERSHIP = Path(config.DATA_DIR) / "universe" / "sp500_membership.csv"
PROGRESS_EVERY = 25
COUNTER_ORDER = ("dropped_nonmember", "dropped_warmup", "dropped_window",
                 "skipped_overlap", "dropped_no_match")
STRESS_SLIPPAGE_FACTOR = 2   # v163: the trail book re-priced at 2 x slippage; printed, never gating


def base_slippage(slippage_bps=None):
    """The slippage a run is priced at: the passed value, else config's.
    Never cast: the results doc prints it as config holds it."""
    return getattr(config, "SLIPPAGE_BPS", 5.0) if slippage_bps is None else slippage_bps


def load_frame(path, start: str = WINDOW_START, end: str = WINDOW_END):
    """One cached CSV cut to [start, end]. A bar after ``end`` never leaves
    this function, so nothing downstream can read 2020+."""
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    inside = (df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))
    df = df.loc[inside, OHLCV].dropna()
    return df if len(df) else None


@dataclass(frozen=True)
class Universe:
    intervals: dict
    members: list
    cached: list
    missing: list


def load_universe(cache_dir, membership_path, start: str = WINDOW_START,
                  end: str = WINDOW_END) -> Universe:
    intervals = pit_membership.load_intervals(str(membership_path))
    if not intervals:
        raise ValueError(f"no membership rows in {membership_path}")
    members = pit_membership.members_between(intervals, start, end)
    cached = [s for s in members if (Path(cache_dir) / f"{s}.csv").is_file()]
    have = set(cached)
    return Universe(intervals, members, cached, [s for s in members if s not in have])


@dataclass
class TickerScreen:
    ticker: str
    counters: Counter
    events: list
    null_outcomes: Counter
    excess: dict
    rank: pd.DataFrame
    null_timeout_r: list = field(default_factory=list)   # v163: trail only, net R per null timeout
    stressed: list | None = None                          # v163: trail only, 2 x slippage pairs
    restricted: list | None = None                        # v174: context only, null pool off shock windows
    null_slots: int = 0                                   # v182: null bars drawn
    null_unfilled: int = 0                                # v182: null bars whose order never filled
    depths: dict | None = None                            # v182: level only, {"event": [...], "null": [...]}
    repriced: list | None = None                          # v182: level only, 3 x slippage pairs
    control: list | None = None                           # v182: rows of the trend-only control book
    overlap: dict | None = None                           # v182: raw-bar overlap with the family partner


#: v182: bars from the event bar to the entry bar, per entry mode.
_ENTRY_OFFSET = {"next_open": 1, "level": 0}


def _event_rows(ticker, index, kept, null_mean_r, entry_offset: int = 1) -> list:
    return [{"ticker": ticker,
             "entry_date": index[pos + entry_offset].strftime("%Y-%m-%d"),
             "exit_date": index[out].strftime("%Y-%m-%d"),
             "r_event": float(r), "r_null": float(m), "outcome": str(o)}
            for pos, out, r, m, o in zip(kept.event_pos, kept.exit_pos, kept.r,
                                         null_mean_r, kept.outcome)]


def _rank_frame(index, raw, population, fwd) -> pd.DataFrame:
    """Member and warm bars, raw event indicator, forward returns (F10)."""
    columns = {"year": np.asarray(index.year)[population],
               "event": raw[population].astype(int)}
    columns.update({f"fwd_{h}": values[population] for h, values in fwd.items()})
    return pd.DataFrame(columns)


def _event_depths(df: pd.DataFrame, event_pos, ctx: dict, direction: str) -> np.ndarray:
    """v182: each event's fill depth in ATR14[t-1]; empty for no events."""
    if len(event_pos) == 0:
        return np.array([], dtype=float)
    return race.level_fills(df, event_pos, ctx["levels"], ctx["atr"], direction)[1]


def _null_pool(idea: Idea, ctx: dict, exclude: np.ndarray | None = None) -> np.ndarray:
    """The bars the matched null may draw from; ``exclude`` (v174) removes
    bars from the pool only."""
    eligible = null.eligible_mask(ctx["raw"], ctx["member"], ctx["warm"], idea.time_cap_bars)
    if exclude is not None:
        eligible = eligible & ~exclude
    return eligible


def _books(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict,
           exclude: np.ndarray | None = None,
           level_factor: float = race.LEVEL_SLIPPAGE_FACTOR):
    """The kept event book, its counters and its matched null at one cost
    setting, both raced under the idea's own shape (v163). ``exclude`` drops
    bars from the null pool only (v174 restricted null); the event book and
    the seed are the same either way.
    v182: a level idea (ctx["levels"]) books and nulls in level mode at level_factor x base entry slippage."""
    cap, shape = idea.time_cap_bars, idea.race_shape
    levels = ctx.get("levels")
    book_kw = {} if levels is None else {"levels": levels, "level_factor": level_factor}
    booked, counts = race.run_book(df, ctx["raw"], cap, member=ctx["member"],
                                   warm=ctx["warm"], atr=ctx["atr"], shape=shape,
                                   direction=idea.direction, **costs, **book_kw)
    eligible = _null_pool(idea, ctx, exclude)
    null_kw = {} if levels is None else {
        "depth": _event_depths(df, booked.event_pos, ctx, idea.direction),
        "level_factor": level_factor}
    draw = null.matched_null(df, booked.event_pos, eligible,
                             null.K, null.null_seed(idea.name, ticker), cap=cap,
                             atr=ctx["atr"], trend=ctx["trend"], shape=shape,
                             direction=idea.direction, **costs, **null_kw)
    counts["dropped_no_match"] = draw.dropped_no_match
    return booked.take(np.isin(booked.event_pos, draw.event_pos)), counts, draw


def _null_timeout_r(idea: Idea, draw) -> list:
    """Trail only: net R of every null race that ran to its cap."""
    if idea.race_shape != "trail":
        return []
    raced = draw.null_race
    return [float(r) for r in raced.r[raced.outcome == "timeout"]]


def _stressed(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict):
    """Trail only: every kept event and its null mean re-raced at
    STRESS_SLIPPAGE_FACTOR x the base slippage. Slippage never moves an exit
    bar, so the overlap rule and the null draw (same seed) keep the same
    events; only the R changes."""
    if idea.race_shape != "trail":
        return None
    stress = {"slippage_bps": STRESS_SLIPPAGE_FACTOR * base_slippage(costs["slippage_bps"]),
              "commission": costs["commission"]}
    kept, _, draw = _books(idea, ticker, df, ctx, stress)
    return [{"entry_date": row["entry_date"], "r_event": row["r_event"], "r_null": row["r_null"]}
            for row in _event_rows(ticker, df.index, kept, draw.null_mean_r)]


def _repriced(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict):
    """Level only (v182): the same events -- exits, overlap and the seeded
    draw do not depend on slippage -- repriced at REPRICE_SLIPPAGE_FACTOR x
    base entry slippage. Printed, never gating."""
    if idea.entry != "level":
        return None
    kept, _, draw = _books(idea, ticker, df, ctx, costs,
                           level_factor=race.REPRICE_SLIPPAGE_FACTOR)
    return [{"entry_date": row["entry_date"], "r_event": row["r_event"], "r_null": row["r_null"]}
            for row in _event_rows(ticker, df.index, kept, draw.null_mean_r, entry_offset=0)]


def _level_report(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict,
                  kept, draw) -> dict:
    """v182: null slot and unfilled counts; depths and the 3 x book for a level idea."""
    depths = None
    if idea.entry == "level":
        depths = {"event": [float(x) for x in
                            _event_depths(df, kept.event_pos, ctx, idea.direction)],
                  "null": [float(x) for x in draw.null_depths]}
    return {"null_slots": draw.null_slots, "null_unfilled": draw.null_unfilled,
            "depths": depths, "repriced": _repriced(idea, ticker, df, ctx, costs)}


def _restricted(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict):
    """Context ideas only (v174 § 5.2): every event raced again against a
    null pool without the bars closer than CAP sessions to any shock day.
    For a context idea the raw mask IS the shock-day mask on this ticker's
    dates. Same seed, K and cap; printed, never gating."""
    if not idea.context:
        return None
    near = pit.near_mask(ctx["raw"], idea.time_cap_bars)
    kept, _, draw = _books(idea, ticker, df, ctx, costs, exclude=near)
    return [{"entry_date": row["entry_date"], "r_event": row["r_event"], "r_null": row["r_null"]}
            for row in _event_rows(ticker, df.index, kept, draw.null_mean_r)]


def _events_plain(idea: Idea, df: pd.DataFrame, context) -> pd.Series:
    """An idea without CONTEXT: one argument, exactly as since v140."""
    return idea.events(df)


def _events_with_context(idea: Idea, df: pd.DataFrame, context) -> pd.Series:
    """A v174 context idea: its own named frames, nothing else."""
    if context is None:
        raise ValueError(f"{idea.name} reads context {idea.context}; none was loaded")
    return idea.events(df, {name: context[name] for name in idea.context})


#: Keyed on bool(idea.context), so screen_ticker grows no branch (v174 § 1).
_EVENT_CALLS: dict[bool, Callable] = {False: _events_plain, True: _events_with_context}


def raw_events(idea: Idea, df: pd.DataFrame, context: Mapping | None) -> pd.Series:
    """The idea's raw event flags on the ticker's own index."""
    return _EVENT_CALLS[bool(idea.context)](idea, df, context).reindex(df.index, fill_value=False)


def raw_levels(idea: Idea, df: pd.DataFrame) -> np.ndarray | None:
    """v182: the idea's resting-order levels on the ticker's own index (NaN
    where it has none); ``None`` for a next-open idea."""
    if idea.entry != "level":
        return None
    return idea.levels(df).reindex(df.index).to_numpy(dtype=float)


def ticker_context(idea: Idea, df: pd.DataFrame, spans, context: Mapping | None = None) -> dict:
    """Per-ticker inputs every screen path shares: raw events, membership, warm-up, ATR14 and the null's trend state (v182: moved out of screen_ticker so --count-only reads the same ones)."""
    atr = indicators.atr(df)
    sma200 = indicators.sma(df["Close"], 200)
    member = null.member_mask(df.index, spans)
    warm = race.warm_mask(atr, sma200) & (df.index >= pd.Timestamp(EVENT_START))
    return {"raw": np.asarray(raw_events(idea, df, context), dtype=bool),
            "member": member, "warm": warm, "atr": atr,
            "trend": null.trend_state(df, sma200), "levels": raw_levels(idea, df)}


def _family_partner(idea: Idea) -> Idea | None:
    """v182: the first registered idea named in ``idea.family`` other than itself."""
    for name in idea.family:
        if name != idea.name and name in IDEAS:
            return IDEAS[name]
    return None


def _overlap(idea: Idea, df: pd.DataFrame, ctx: dict) -> dict | None:
    """v182: raw event bars shared with the family partner, member and warm bars only."""
    partner = _family_partner(idea)
    if partner is None:
        return None
    population = np.asarray(ctx["member"], dtype=bool) & np.asarray(ctx["warm"], dtype=bool)
    other = np.asarray(raw_events(partner, df, None), dtype=bool)
    return descriptive.event_overlap(ctx["raw"] & population, other & population)


def _control(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict) -> list | None:
    """v182: the trend-only control -- the same book (race, direction, entry
    mode, levels, matched null and seed) over idea.control(df). Never gating."""
    if idea.control is None:
        return None
    flags = idea.control(df).reindex(df.index, fill_value=False).to_numpy(dtype=bool)
    kept, _, draw = _books(idea, ticker, df, {**ctx, "raw": flags}, costs)
    return _event_rows(ticker, df.index, kept, draw.null_mean_r,
                       entry_offset=_ENTRY_OFFSET[idea.entry])


def screen_ticker(idea: Idea, ticker: str, df: pd.DataFrame, spans, *,
                  slippage_bps=None, commission=None,
                  context: Mapping | None = None) -> TickerScreen:
    costs = {"slippage_bps": slippage_bps, "commission": commission}
    ctx = ticker_context(idea, df, spans, context)
    kept, counts, draw = _books(idea, ticker, df, ctx, costs)
    fwd = {h: forward.forward_atr(df, ctx["atr"], h, direction=idea.direction)
           for h in forward.HORIZONS}
    return TickerScreen(
        ticker=ticker, counters=Counter(counts),
        events=_event_rows(ticker, df.index, kept, draw.null_mean_r,
                           entry_offset=_ENTRY_OFFSET[idea.entry]),
        null_outcomes=Counter(draw.null_race.outcome.tolist()),
        excess={h: forward.excess_drift(fwd[h], draw.event_pos, draw.groups)
                for h in forward.HORIZONS},
        rank=_rank_frame(df.index, ctx["raw"], ctx["member"] & ctx["warm"], fwd),
        null_timeout_r=_null_timeout_r(idea, draw),
        stressed=_stressed(idea, ticker, df, ctx, costs),
        restricted=_restricted(idea, ticker, df, ctx, costs),
        control=_control(idea, ticker, df, ctx, costs), overlap=_overlap(idea, df, ctx),
        **_level_report(idea, ticker, df, ctx, costs, kept, draw))


def _spy_calendar(cache_dir, end: str) -> pd.DataFrame:
    """SPY sessions in [CONTEXT_START, end]: the calendar every context file
    must cover (v174 load check 3)."""
    path = Path(cache_dir) / "SPY.csv"
    if not path.is_file():
        raise screen_context.ContextError(f"SPY calendar {path} is missing")
    calendar = load_frame(path, CONTEXT_START, end)
    if calendar is None:
        raise screen_context.ContextError(f"SPY calendar has no bar in {CONTEXT_START}..{end}")
    return calendar


def _context_frame(cache_dir, ticker: str, sessions: pd.DatetimeIndex, end: str):
    """One context CSV through the v174 load checks, the raw index first
    (load_frame silently repairs tz, order and duplicates)."""
    path = Path(cache_dir) / f"{ticker}.csv"
    record = screen_context.file_record(path)
    raw = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    screen_context.check_raw_index(raw.index, ticker)
    frame = load_frame(path, CONTEXT_START, end)
    if frame is None:
        raise screen_context.ContextError(f"{ticker}: no bar in {CONTEXT_START}..{end}")
    screen_context.check_contiguous(frame.index, sessions, ticker)
    screen_context.check_z_coverage(screen_context.trailing_z(frame["Close"]), sessions,
                                    ticker, event_start=EVENT_START)
    return frame, record


def load_context(cache_dir, tickers: tuple[str, ...], *, end: str = WINDOW_END) -> screen_context.ContextData:
    """Every context frame an idea names, checked, from CONTEXT_START to end."""
    calendar = _spy_calendar(cache_dir, end)
    frames, records = {}, {}
    for ticker in tickers:
        frames[ticker], records[ticker] = _context_frame(cache_dir, ticker, calendar.index, end)
    return screen_context.ContextData(frames=frames, calendar=calendar, records=records)


def _universe_context(idea: Idea, cache_dir, end: str, context):
    """A context idea run without frames loads them here, once per universe."""
    if idea.context and context is None:
        return load_context(cache_dir, idea.context, end=end).frames
    return context


def screen_universe(idea: Idea, universe: Universe, cache_dir, *,
                    start: str = WINDOW_START, end: str = WINDOW_END,
                    tickers=None, out=print, context: Mapping | None = None):
    """Every cached member, one at a time, with flushed percent progress.
    ``context`` (v174) is handed unchanged to every screen_ticker call."""
    context = _universe_context(idea, cache_dir, end, context)
    names = universe.cached if tickers is None else [t for t in tickers if t in universe.cached]
    screens, skipped = [], Counter()
    for i, ticker in enumerate(names, start=1):
        df = load_frame(Path(cache_dir) / f"{ticker}.csv", start, end)
        if df is None:
            skipped["empty_frame"] += 1
        else:
            screens.append(screen_ticker(idea, ticker, df,
                                         universe.intervals.get(ticker, []),
                                         context=context))
        if i % PROGRESS_EVERY == 0 or i == len(names):
            out(f"[{idea.name}] {i}/{len(names)} tickers ({100.0 * i / len(names):.0f}%)",
                flush=True)
    return screens, skipped


def _count_depths(idea: Idea, df: pd.DataFrame, ctx: dict, booked: np.ndarray):
    """Level ideas: each booked event's fill depth in ATR14[t-1], from the
    function the real run fills with (race.level_fills); None for next_open."""
    if ctx["levels"] is None:
        return None
    return np.asarray(_event_depths(df, booked, ctx, idea.direction), dtype=float)


def count_ticker(idea: Idea, ticker: str, df: pd.DataFrame, spans) -> dict:
    """v182 --count-only for one ticker: the real run's events, drops and
    null draw, with a race-free exit bound (every trade lasts the full cap).
    Nothing is raced; no R is computed."""
    ctx = ticker_context(idea, df, spans)
    cap = idea.time_cap_bars
    cand, counts = race.candidate_events(ctx["raw"], ctx["member"], ctx["warm"], cap,
                                         entry=idea.entry)
    keep = race.non_overlapping(cand, cand + cap)
    counts["skipped_overlap"] = int((~keep).sum())
    booked = cand[keep]
    depth = _count_depths(idea, df, ctx, booked)
    groups = null.draw_groups(df, booked, _null_pool(idea, ctx), null.K,
                              null.null_seed(idea.name, ticker), atr=ctx["atr"],
                              trend=ctx["trend"], direction=idea.direction, depth=depth)
    counts["dropped_no_match"] = groups.dropped_no_match
    matched = np.isin(booked, groups.event_pos)
    return {"ticker": ticker, "counters": Counter(counts),
            "raw": int(np.count_nonzero(ctx["raw"])), "events": int(matched.sum()),
            "event_depths": [] if depth is None else [float(d) for d in depth[matched]],
            "null_depths": [float(d) for d in groups.null_depths],
            "null_slots": int(groups.null_slots), "null_unfilled": int(groups.null_unfilled)}


_COUNT_SUMS = ("raw", "events", "null_slots", "null_unfilled")
_COUNT_LISTS = ("event_depths", "null_depths")


def _add_count(total: dict, one: dict) -> None:
    """Fold one count_ticker result into the universe total."""
    total["tickers"] += 1
    total["counters"].update(one["counters"])
    for key in _COUNT_SUMS:
        total[key] += one[key]
    for key in _COUNT_LISTS:
        total[key].extend(one[key])


def count_universe(idea: Idea, universe: Universe, cache_dir, *,
                   start: str = WINDOW_START, end: str = WINDOW_END, out=print) -> dict:
    """v182 --count-only over every cached member, the screen_universe loop
    and progress line, summed into one dict."""
    total = {"tickers": 0, "members": len(universe.members), "missing": len(universe.missing),
             "skipped": Counter(), "counters": Counter(), "raw": 0, "events": 0,
             "event_depths": [], "null_depths": [], "null_slots": 0, "null_unfilled": 0}
    names = universe.cached
    for i, ticker in enumerate(names, start=1):
        df = load_frame(Path(cache_dir) / f"{ticker}.csv", start, end)
        if df is None:
            total["skipped"]["empty_frame"] += 1
        else:
            _add_count(total, count_ticker(idea, ticker, df, universe.intervals.get(ticker, [])))
        if i % PROGRESS_EVERY == 0 or i == len(names):
            out(f"[{idea.name}] {i}/{len(names)} tickers ({100.0 * i / len(names):.0f}%)",
                flush=True)
    return total


def _count_table(counts: dict) -> list[str]:
    """The count steps, raw events down to the count N."""
    counters = counts["counters"]
    return (["| step | events |", "|---|---:|", f"| raw events | {counts['raw']} |"]
            + [f"| {name} | {counters.get(name, 0)} |" for name in COUNTER_ORDER[:3]]
            + [f"| skipped_overlap (full-cap bound) | {counters.get('skipped_overlap', 0)} |",
               f"| dropped_no_match | {counters.get('dropped_no_match', 0)} |",
               f"| **count N** | **{counts['events']}** |"])


def _count_gate(n: int) -> str:
    if n >= verdict.MIN_N:
        return f"**Gate:** N = {n} ≥ {verdict.MIN_N}: the one shot may run."
    return (f"**Gate:** N = {n} < {verdict.MIN_N}: no run, no ledger row; "
            "report to the partner.")


def _cell(value) -> str:
    return "–" if value is None else f"{value:.3f}"


def _depth_row(label: str, summary: dict) -> str:
    share = "–" if summary["gap_share"] is None else f"{100 * summary['gap_share']:.1f}%"
    return (f"| {label} | {summary['n']} | {_cell(summary['q1'])} | "
            f"{_cell(summary['median'])} | {_cell(summary['q3'])} | {share} |")


def _check5_block(idea: Idea, counts: dict) -> list[str]:
    """Check 5 (spec Part B): the fill-depth table, both clauses, the verdict."""
    ok, lines = descriptive.check_fill_depth(counts["event_depths"], counts["null_depths"],
                                             counts["null_slots"], counts["null_unfilled"])
    verdict_line = (f"**Check 5:** PASS -- {idea.name} may run." if ok else
                    f"**Check 5:** FAIL -- {idea.name} is not run; tell the partner.")
    return (["", "## Check 5 — fill depth (outcome-blind)", "",
             "| depth (ATR14[t−1]) | n | q1 | median | q3 | gap fills |",
             "|---|---:|---:|---:|---:|---:|",
             _depth_row("events", descriptive.depth_summary(counts["event_depths"])),
             _depth_row("null fills", descriptive.depth_summary(counts["null_depths"])), ""]
            + [f"- {line}" for line in lines] + ["", verdict_line])


def render_counts(idea: Idea, counts: dict, args) -> str:
    """The --count-only report: counts, the N gate and (level ideas) check 5."""
    cap = idea.time_cap_bars
    lines = [f"# v182 count: `{idea.name}` (outcome-blind: no race, no R)", "",
             f"**Window:** {args.start}..{args.end} (events from {EVENT_START}). "
             f"**Universe:** {counts['members']} PIT S&P 500 members, {counts['tickers']} "
             f"counted, {counts['missing']} missing from the cache, "
             f"{sum(counts['skipped'].values())} empty frames.",
             f"**Idea:** {idea.direction}, entry {idea.entry}, {idea.race_shape} race, "
             f"cap {cap} bars.",
             f"**Command:** `python scripts/backtest/screen_idea.py --idea {idea.name} "
             "--count-only`", ""]
    lines += _count_table(counts)
    lines += ["", f"Non-overlap here assumes every trade lasts the full {cap}-bar cap, so "
              "the real run books at least as many events before the null match.", "",
              _count_gate(counts["events"])]
    if idea.entry == "level":
        lines += _check5_block(idea, counts)
    return "\n".join(lines) + "\n"


def count_refusal(args, idea: Idea) -> str | None:
    """Why this count must not happen, or None. Checked before any data is
    read; never reads the ledger."""
    if args.end > WINDOW_END:
        return f"window end {args.end} is after {WINDOW_END}; the screen never reads 2020+"
    if (args.start, args.end) != (WINDOW_START, WINDOW_END):
        return (f"--count-only counts the pre-registered window {WINDOW_START}..{WINDOW_END} "
                f"only, not {args.start}..{args.end}")
    if args.tickers:
        return ("--count-only counts the whole universe; --tickers belongs to a --dry-run "
                "smoke test")
    if idea.context:
        return (f"--count-only counts ideas without context series; {idea.name} reads "
                f"{', '.join(idea.context)}")
    return None


def run_count(args) -> int:
    """v182 --count-only: refuse, or print the count report. Writes nothing."""
    idea = IDEAS[args.idea]
    reason = count_refusal(args, idea)
    if reason is None:
        try:
            universe = load_universe(args.cache_dir, args.membership, args.start, args.end)
        except ValueError as exc:
            reason = str(exc)
    if reason:
        print(f"refused: {reason}", file=sys.stderr)
        return 2
    counts = count_universe(idea, universe, args.cache_dir, start=args.start, end=args.end)
    print(render_counts(idea, counts, args))
    return 0


RESULTS_DIR =ROOT / "docs" / "superpowers" / "results"
INSTRUMENT = "screen-v1"

#: {ticker: sha256} of every registered context CSV, written by the first
#: real run of a context idea; backtest_cache_ext is gitignored (v174 § 2).
CONTEXT_HASHES = RESULTS_DIR / "2026-10-18-v174-context-hashes.json"


def context_tickers() -> tuple[str, ...]:
    return tuple(sorted({name for idea in IDEAS.values() for name in idea.context}))


def _hash_records(cache_dir) -> dict:
    return {t: screen_context.file_record(Path(cache_dir) / f"{t}.csv")
            for t in context_tickers()}


def hash_refusal(records: Mapping[str, dict], path) -> str | None:
    """Why the context bytes differ from the pinned ones, or None (no pin yet,
    or every ticker matches)."""
    path = Path(path)
    if not path.is_file():
        return None
    pinned = json.loads(path.read_text(encoding="utf-8"))
    for ticker, record in sorted(records.items()):
        if ticker not in pinned:
            return f"{ticker} has no SHA-256 in {path}; the pinned context set changed"
        if pinned[ticker] != record["sha256"]:
            return (f"{ticker}.csv SHA-256 {record['sha256'][:12]} differs from "
                    f"{pinned[ticker][:12]} pinned in {path}; the context data changed "
                    f"after the first shot (never refetch)")
    return None


def write_hashes(records: Mapping[str, dict], path) -> bool:
    """Pin the context bytes once; never overwrite a pin."""
    path = Path(path)
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({t: r["sha256"] for t, r in records.items()}, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")
    return True


def _context_step(args, idea: Idea) -> tuple[screen_context.ContextData | None, str | None]:
    """(ContextData, None), or (None, reason) to refuse; (None, None) for an
    idea without context. Runs for dry and real runs alike."""
    if not idea.context:
        return None, None
    try:
        records = _hash_records(args.cache_dir)
        data = load_context(args.cache_dir, idea.context, end=args.end)
        data = replace(data, checked_records=records)
        reason = _context_hash_refusal(args, data)
    except screen_context.ContextError as exc:
        return None, str(exc)
    return (None, reason) if reason else (data, None)


def _spy_step(args, idea: Idea) -> tuple[pd.DataFrame | None, str | None]:
    """v182: a short or level idea's doc splits ΔExpR by SPY's 200-day
    regime, so SPY must load before the one shot; (None, None) otherwise."""
    if not _needs_short_blocks(idea):
        return None, None
    try:
        return _spy_calendar(args.cache_dir, args.end), None
    except screen_context.ContextError as exc:
        return None, f"SPY regime split (v182) cannot load SPY: {exc}"


def _context_hash_refusal(args, data) -> str | None:
    """Bind loaded frames and publication to the union checked before screening."""
    if data is None:
        return None
    try:
        for ticker, record in sorted(data.checked_records.items()):
            path = Path(args.cache_dir) / f"{ticker}.csv"
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            loaded = data.records.get(ticker, record)["sha256"]
            if digest != record["sha256"] or loaded != record["sha256"]:
                return (f"{ticker}.csv SHA-256 differs from the checked bytes before "
                        "screening; the context data changed")
    except OSError as exc:
        return f"cannot verify checked context bytes: {exc}"
    return hash_refusal(data.checked_records, args.context_hashes)


def _pin_context_hashes(args, data) -> None:
    if data is not None and write_hashes(data.checked_records, args.context_hashes):
        print(f"pinned context SHA-256 -> {args.context_hashes}")


def ledger_id(name: str) -> str:
    return f"screen-{name}"


def _iso_day(text: str) -> str:
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an ISO date: {text!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--idea", required=True, choices=list(IDEAS))
    p.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--membership", type=Path, default=DEFAULT_MEMBERSHIP)
    p.add_argument("--start", type=_iso_day, default=WINDOW_START)
    p.add_argument("--end", type=_iso_day, default=WINDOW_END)
    p.add_argument("--date", type=_iso_day, default=date.today().isoformat(),
                   help="results-doc and ledger date; default today")
    p.add_argument("--ledger", type=Path, default=stats.LEDGER_PATH)
    p.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--context-hashes", type=Path, default=CONTEXT_HASHES,
                   help="v174 pinned SHA-256 of the context CSVs")
    p.add_argument("--tickers", default=None, help="comma list; smoke test, needs --dry-run")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the doc, write nothing")
    mode.add_argument("--count-only", action="store_true",
                      help="v182: count events, drops and full-cap non-overlap (and check 5 "
                           "for a level idea); no race, no R, writes nothing")
    return p


def refusal(args, rows) -> str | None:
    """Why this run must not happen, or None. Checked before any data is read."""
    if args.end > WINDOW_END:
        return f"window end {args.end} is after {WINDOW_END}; the screen never reads 2020+"
    if args.start > args.end:
        return f"window start {args.start} is after its end {args.end}"
    if not args.dry_run and (args.start, args.end) != (WINDOW_START, WINDOW_END):
        return (f"window {args.start}..{args.end} is not the pre-registered window "
                f"{WINDOW_START}..{WINDOW_END}; a real run cannot spend the one shot on it")
    if args.tickers and not args.dry_run:
        return "--tickers is a smoke test and needs --dry-run, so it cannot spend the one shot"
    if any(row["id"] == ledger_id(args.idea) for row in rows):
        return (f"{ledger_id(args.idea)} is already in the ledger: one shot per idea; "
                "a changed parameter is a new idea with a new name")
    return None


def _mean(values) -> float | None:
    return float(np.mean(values)) if len(values) else None


def _sum_counters(counters) -> Counter:
    total = Counter()
    for counter in counters:
        total.update(counter)
    return total


def _drift(screens) -> dict:
    out = {}
    for h in forward.HORIZONS:
        values = [v for screen in screens for v in screen.excess[h]]
        out[h] = (len(values), _mean(values))
    return out


def _rank(screens) -> dict:
    frames = [screen.rank for screen in screens if len(screen.rank)]
    if not frames:
        return {}
    pooled = pd.concat(frames, ignore_index=True)
    return {h: forward.yearly_rank_corr(pooled["year"], pooled["event"], pooled[f"fwd_{h}"])
            for h in forward.HORIZONS}


def _book_timeouts(count: int, total: int, values) -> tuple:
    return (count, count / total if total else None, _mean(values))


def _timeouts(screens, events) -> dict:
    """(count, share of the book, mean net R) of timeouts, event and null
    books. The null mean is trail only: fixed screens keep no null R."""
    event_r = [row["r_event"] for row in events if row["outcome"] == "timeout"]
    null_mix = _sum_counters(screen.null_outcomes for screen in screens)
    null_r = [r for screen in screens for r in screen.null_timeout_r]
    return {"event": _book_timeouts(len(event_r), len(events), event_r),
            "null": _book_timeouts(null_mix["timeout"], sum(null_mix.values()), null_r)}


def _stress(screens):
    """The 2 x slippage verdict over the trail pairs; None for a fixed idea."""
    if all(screen.stressed is None for screen in screens):
        return None
    rows = [row for screen in screens if screen.stressed is not None
            for row in screen.stressed]
    return verdict.decide([verdict.PairedEvent(row["entry_date"], row["r_event"] - row["r_null"])
                           for row in rows])


def summarise(screens, skipped=None) -> dict:
    events = [row for screen in screens for row in screen.events]
    paired = [verdict.PairedEvent(row["entry_date"], row["r_event"] - row["r_null"])
              for row in events]
    return {"verdict": verdict.decide(paired), "events": events,
            "counters": _sum_counters(screen.counters for screen in screens),
            "skipped": Counter(skipped or {}),
            "event_outcomes": Counter(row["outcome"] for row in events),
            "null_outcomes": _sum_counters(screen.null_outcomes for screen in screens),
            "mean_r_event": _mean([row["r_event"] for row in events]),
            "mean_r_null": _mean([row["r_null"] for row in events]),
            "drift": _drift(screens), "rank": _rank(screens),
            "timeouts": _timeouts(screens, events), "stress": _stress(screens)}


def _restricted_pairs(screens):
    """Every ticker's restricted-null pairs, pooled; None for an old idea."""
    if all(screen.restricted is None for screen in screens):
        return None
    return [row for screen in screens if screen.restricted for row in screen.restricted]


def with_diagnostics(summary: dict, screens, idea: Idea, data, *, end: str) -> dict:
    """The summary plus ``"context"`` (v174 § 5) for a context idea; the same
    dict, untouched, for any other. The verdict object is never rebuilt."""
    if not idea.context or data is None:
        return summary
    diag = diagnostics.compute(idea, summary["events"], _restricted_pairs(screens), data,
                               event_start=EVENT_START, event_end=end)
    return {**summary, "context": diag}


def _needs_short_blocks(idea: Idea) -> bool:
    """v182: a short or level idea's results doc carries the short-side blocks."""
    return idea.direction == "short" or idea.entry == "level"


def _pooled(screens, name: str) -> list | None:
    """Every ticker's rows of one TickerScreen field, pooled; None if no screen has it."""
    if all(getattr(screen, name) is None for screen in screens):
        return None
    return [row for screen in screens if getattr(screen, name) for row in getattr(screen, name)]


def _decide(rows) -> verdict.Verdict | None:
    if rows is None:
        return None
    return verdict.decide([verdict.PairedEvent(r["entry_date"], r["r_event"] - r["r_null"])
                           for r in rows])


def _overlap_total(screens) -> dict | None:
    """The family-partner overlap counts summed over the screens that have them."""
    counted = [screen.overlap for screen in screens if screen.overlap is not None]
    if not counted:
        return None
    return {key: sum(one[key] for one in counted) for key in ("own", "other", "both")}


def _level_blocks(screens) -> dict:
    """Level only: pooled fill depths and the null slot counts."""
    if all(screen.depths is None for screen in screens):
        return {"depths": None, "slots": None}
    with_depths = [screen for screen in screens if screen.depths is not None]
    return {"depths": {side: descriptive.depth_summary(
                [d for screen in with_depths for d in screen.depths[side]])
                for side in ("event", "null")},
            "slots": (sum(screen.null_slots for screen in screens),
                      sum(screen.null_unfilled for screen in screens))}


def with_short_blocks(summary: dict, screens, idea: Idea, spy) -> dict:
    """v182: the summary plus ``"short"`` -- overlap, trend-only control, SPY
    regime split and the level blocks -- for a short or level idea; the same
    dict, untouched, for any other. The verdict object is never rebuilt."""
    if not _needs_short_blocks(idea):
        return summary
    partner = _family_partner(idea)
    regime = (None if spy is None else
              descriptive.regime_split(summary["events"], descriptive.spy_above_200(spy)))
    block = {"partner": None if partner is None else partner.name,
             "overlap": _overlap_total(screens),
             "control": _decide(_pooled(screens, "control")),
             "regime": regime,
             "repriced": _decide(_pooled(screens, "repriced")),
             **_level_blocks(screens)}
    return {**summary, "short": block}


def _fmt(value, spec: str = "+.4f") -> str:
    return "n/a" if value is None else format(value, spec)


def _yes(ok: bool) -> str:
    return "yes" if ok else "**no**"


def _short_borrow() -> str:
    return f"borrow {BORROW_RATE_ANNUAL:.1%} a year on calendar days held; "


def _short_level_line(costs: str) -> str:
    """v182: the short sell-stop (level entry) trade line."""
    return ("**Trade:** short; sell-stop resting at the level (known from bars <= t-1), "
            "placed before bar t opens, valid one bar; fills at the lower of the open and "
            f"the level, entry slippage {race.LEVEL_SLIPPAGE_FACTOR} x base; stop "
            f"{race.STOP_ATR} x ATR14[t-1] above; target "
            f"{race.STOP_ATR * race.REWARD_RISK} x ATR14[t-1] below; on the fill bar only "
            "the stop counts (a high at or above it exits at the stop); from bar t+1 a gap "
            "through either level fills at the open; stop first on a bar touching both; "
            + _short_borrow() + costs)


def _short_trade_line(idea, costs: str) -> str:
    """v182: the short trade line, the exact mirror of the long one plus borrow."""
    if idea.entry == "level":
        return _short_level_line(costs)
    if idea.race_shape == "trail":
        return ("**Trade:** short; entry next open (sell); initial stop "
                f"{race.STOP_ATR} x ATR14[t] above (1R); no target; chandelier trail: "
                "the stop on bar j is the lower of the initial stop and the lowest low "
                f"of bars t+1..j-1 plus {trail.TRAIL_ATR} x ATR14[t], never raised, ATR "
                "frozen at the signal bar; a gap through the stop fills at the open; no "
                f"exit after {idea.time_cap_bars} bars -> out at that close; R in the "
                "initial 1R; " + _short_borrow() + costs)
    return (f"**Trade:** short; entry next open (sell); stop {race.STOP_ATR} x ATR14 above; "
            f"target {race.STOP_ATR * race.REWARD_RISK} x ATR14 below; a gap through "
            "either level fills at the open; stop first on a bar touching both; "
            + _short_borrow() + costs)


def _render_trade(idea, run) -> str:
    """The trade line for the idea's shape; the fixed text is today's, byte for byte."""
    costs = (f"costs {run['slippage_bps']} bps a side + {run['commission']:.4f}R "
             "commission.")
    if idea.direction == "short":
        return _short_trade_line(idea, costs)
    if idea.race_shape == "trail":
        return (f"**Trade:** entry next open; initial stop {race.STOP_ATR} x ATR14[t] (1R); "
                "no target; chandelier trail: the stop on bar j is the higher of the "
                "initial stop and the highest high of bars t+1..j-1 minus "
                f"{trail.TRAIL_ATR} x ATR14[t], never lowered, ATR frozen at the signal "
                "bar; a gap through the stop fills at the open; no exit after "
                f"{idea.time_cap_bars} bars -> out at that close; R in the initial 1R; "
                + costs)
    return (f"**Trade:** entry next open; stop {race.STOP_ATR} x ATR14; target "
            f"{race.STOP_ATR * race.REWARD_RISK} x ATR14; a gap through either level "
            "fills at the open; stop first on a bar touching both; " + costs)


def _render_head(idea, v, run) -> list:
    params = ", ".join(f"{key}={value}" for key, value in idea.params.items())
    return [
        f"# v140 screen: `{idea.name}` -> {v.verdict}", "",
        f"**Ledger id:** `{run['ledger_id']}` (instrument `{INSTRUMENT}`); BH q = "
        f"{_fmt(run['q'], '.4f')} across the ledger (reported, never gating).", "",
        f"**Run:** {run['date']}; window {run['start']}..{run['end']}; "
        f"events count from {EVENT_START} (earlier bars only prime the indicators); the "
        f"year rule is {verdict.MIN_POSITIVE_YEARS} of {len(verdict.YEARS)} calendar years "
        f"({verdict.YEARS[0]}-{verdict.YEARS[-1]}); "
        f"`python scripts/backtest/screen_idea.py --idea {idea.name}`; null K = {null.K}, "
        f"seed {null.SEED_BASE} per (idea, ticker); bootstrap {stats.WEEK_BOOTSTRAP_RESAMPLES:,} "
        f"week resamples, seed {stats.WEEK_BOOTSTRAP_SEED}.", "",
        f"**Trigger:** {idea.summary} ({idea.source}); params {params}; time cap "
        f"{idea.time_cap_bars} bars; {idea.direction} only.", "",
        _render_trade(idea, run), "",
        "**Spec:** `docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md`",
    ]


def _render_universe(universe, summary) -> list:
    counters, v = summary["counters"], summary["verdict"]
    raw = sum(counters[name] for name in COUNTER_ORDER) + v.n
    lines = ["## Universe and counters", "", "| | count |", "|---|---|",
             f"| point-in-time S&P 500 members in the window | {len(universe.members)} |",
             f"| cached and screened | {len(universe.cached)} |",
             f"| missing from the cache (survivorship that remains) | {len(universe.missing)} |",
             f"| cached but empty inside the window | {summary['skipped'].get('empty_frame', 0)} |",
             f"| raw events | {raw} |"]
    lines += [f"| `{name}` | {counters[name]} |" for name in COUNTER_ORDER]
    lines += [f"| **kept events (N)** | **{v.n}** |", "",
              "PIT members missing from the cache: "
              + (", ".join(universe.missing) or "none") + "."]
    return lines


def _render_verdict(v) -> list:
    return [f"## Verdict: {v.verdict}", "",
            "| Clause | Measured | Rule | Holds |", "|---|---|---|---|",
            f"| ΔExpR = mean(R_event − mean R_null) | {_fmt(v.delta_exp_r)}R | ≥ {verdict.PASS_EXP_R:+.2f}R | {_yes(v.clauses['exp_r'])} |",
            f"| lower 95% bound, week-clustered bootstrap | {_fmt(v.ci_low)}R (upper {_fmt(v.ci_high)}R) | > 0 | {_yes(v.clauses['ci'])} |",
            f"| years with mean(d) > 0 | {v.years_positive} of {len(verdict.YEARS)} | ≥ {verdict.MIN_POSITIVE_YEARS} | {_yes(v.clauses['years'])} |",
            f"| kept events N | {v.n} | ≥ {verdict.MIN_N} | {_yes(v.clauses['n'])} |", "",
            f"One-sided bootstrap p (share of resamples ≤ 0): {_fmt(v.p, '.4f')}. "
            f"N < {verdict.MIN_N} is `SCREEN-UNDERPOWERED` whatever the other clauses say."]


def _mix(outcomes: Counter, names: tuple) -> list:
    total = sum(outcomes.values())
    return [f"{outcomes.get(name, 0)} ({100.0 * outcomes.get(name, 0) / total:.1f}%)"
            if total else "0" for name in names]


def _render_arms(summary, names: tuple) -> list:
    """``names``: the idea's own outcomes (race.SHAPE_OUTCOMES[shape])."""
    lines = ["## Both arms", "",
             f"Mean R_event {_fmt(summary['mean_r_event'])}R; mean R_null (each event's "
             f"null mean, averaged) {_fmt(summary['mean_r_null'])}R. Both after costs.", "",
             "| Exit | event arm | null arm |", "|---|---|---|"]
    lines += [f"| {name} | {e} | {n} |" for name, e, n in
              zip(names, _mix(summary["event_outcomes"], names),
                  _mix(summary["null_outcomes"], names))]
    return lines


def _share(share) -> str:
    return "n/a" if share is None else f"{100.0 * share:.1f}%"


def _render_stress(summary, run) -> str:
    """The trail book re-priced at STRESS_SLIPPAGE_FACTOR x slippage (spec
    § Costs): printed beside the verdict, never a clause of it."""
    stressed, base = summary["stress"], summary["verdict"]
    bps = STRESS_SLIPPAGE_FACTOR * run["slippage_bps"]
    if stressed is None or stressed.delta_exp_r is None:
        return f"At {bps} bps a side ({STRESS_SLIPPAGE_FACTOR} x slippage): no stressed pairs."
    change = None if base.delta_exp_r is None else stressed.delta_exp_r - base.delta_exp_r
    return (f"At {bps} bps a side ({STRESS_SLIPPAGE_FACTOR} x slippage, both fills): "
            f"ΔExpR {_fmt(stressed.delta_exp_r)}R, 95% week-clustered interval "
            f"{_fmt(stressed.ci_low)}R to {_fmt(stressed.ci_high)}R; change vs the base "
            f"book {_fmt(change)}R. Printed, never gating.")


def _render_trail(summary, run) -> list:
    """Trail ideas only: N beside the overlap skips, timeouts per book (the cap
    is the trail's main free parameter), and the 2 x slippage line."""
    v, t = summary["verdict"], summary["timeouts"]
    null_n = sum(summary["null_outcomes"].values())
    return ["## Trail race (reported, never gating)", "",
            f"Kept events N = {v.n}; skipped as overlapping an open race "
            f"(`skipped_overlap`) = {summary['counters']['skipped_overlap']}.", "",
            "| | event book | null book |", "|---|---|---|",
            f"| races | {v.n} | {null_n} |",
            f"| timeouts (share) | {t['event'][0]} ({_share(t['event'][1])}) | "
            f"{t['null'][0]} ({_share(t['null'][1])}) |",
            f"| mean timeout R, after costs | {_fmt(t['event'][2])}R | {_fmt(t['null'][2])}R |",
            "", _render_stress(summary, run)]


def _ratio(a, b):
    return a / b if b else None


def _minus(a, b):
    return None if a is None or b is None else a - b


def _render_overlap(idea, block) -> list:
    """v182: raw-bar overlap with the family partner, both shares."""
    o, own, partner = block["overlap"], idea.name, block["partner"]
    return [f"**Event overlap** with `{partner}` (raw event bars on member, warm bars): "
            f"{o['both']} of {o['own']} `{own}` bars ({_share(_ratio(o['both'], o['own']))}) "
            f"are also `{partner}` bars; {o['both']} of {o['other']} `{partner}` bars "
            f"({_share(_ratio(o['both'], o['other']))}) are also `{own}` bars. "
            "Nested ideas are two looks at one hypothesis: read both results docs together "
            "(family of two, BH q above)."]


def _render_control(summary, block) -> list:
    """v182: the trend-only control book and the idea's margin over it."""
    c = block["control"]
    margin = _minus(summary["verdict"].delta_exp_r, c.delta_exp_r)
    return ["**Trend-only control** (`control_events`: the idea's trend and first-break "
            "clauses, no range clauses; same race, same matched null): "
            f"N = {c.n}, ΔExpR {_fmt(c.delta_exp_r)}R, 95% week-clustered interval "
            f"{_fmt(c.ci_low)}R to {_fmt(c.ci_high)}R. The idea's ΔExpR minus the control's: "
            f"{_fmt(margin)}R. A pass whose ΔExpR is not clearly above the control is not "
            "credited to the range."]


_REGIME_ROWS = (("above", "above its 200-day average"), ("below", "below its 200-day average"))


def _render_regime(block) -> list:
    """v182: ΔExpR split by SPY's close against its 200-day SMA before entry."""
    regime = block["regime"]
    if regime is None:
        return ["**SPY regime split:** not computed (no SPY frame)."]
    lines = ["**SPY regime split** (SPY close vs its 200-day average at the last close "
             "before entry):", "", "| SPY | N | ΔExpR |", "|---|---|---|"]
    lines += [f"| {label} | {regime[key][0]} | {_fmt(regime[key][1])}R |"
              for key, label in _REGIME_ROWS]
    return lines + ["", f"Events with no SPY average before entry: {regime['unknown']}."]


def _render_repriced(summary, block, run) -> str:
    """v182: the level book at REPRICE_SLIPPAGE_FACTOR x base entry slippage."""
    r = block["repriced"]
    delta, low, high = (None, None, None) if r is None else (r.delta_exp_r, r.ci_low, r.ci_high)
    bps = race.REPRICE_SLIPPAGE_FACTOR * run["slippage_bps"]
    return (f"**Repriced at {race.REPRICE_SLIPPAGE_FACTOR} x base entry slippage** "
            f"({bps} bps on the entry fill, events and null): ΔExpR {_fmt(delta)}R, "
            f"95% week-clustered interval {_fmt(low)}R to {_fmt(high)}R; change vs the "
            f"{race.LEVEL_SLIPPAGE_FACTOR} x book "
            f"{_fmt(_minus(delta, summary['verdict'].delta_exp_r))}R. Printed, never gating.")


def _render_level(summary, block, run) -> list:
    """v182: fill depths, null slots and null_unfilled, the 3 x repricing."""
    slots, unfilled = block["slots"]
    return ["**Fill depth** (ATR14[t−1] below the bar's open; 0 = a gap fill at the open):",
            "", "| depth (ATR14[t−1]) | n | q1 | median | q3 | gap fills |",
            "|---|---:|---:|---:|---:|---:|",
            _depth_row("events", block["depths"]["event"]),
            _depth_row("null fills", block["depths"]["null"]), "",
            f"**Null slots:** {slots}; unfilled {unfilled} ({_share(_ratio(unfilled, slots))}); "
            "an event with no filled null is dropped as `dropped_no_match`.", "",
            _render_repriced(summary, block, run)]


def _render_short_blocks(idea, summary, run) -> list:
    """v182: the short-side blocks, descriptive and never gating."""
    block = summary["short"]
    parts = []
    if block["overlap"] is not None:
        parts.append(_render_overlap(idea, block))
    if block["control"] is not None:
        parts.append(_render_control(summary, block))
    parts.append(_render_regime(block))
    if block["depths"] is not None:
        parts.append(_render_level(summary, block, run))
    lines = ["## Short-side blocks (descriptive, never gating)"]
    for part in parts:
        lines += [""] + part
    return lines


def _render_years(v) -> list:
    lines = ["## Per year", "", "| Year | N | mean(d) |", "|---|---|---|"]
    lines += [f"| {year} | {n} | {_fmt(mean)}R |" for year, (n, mean) in v.per_year.items()]
    return lines


def _render_rank(rank) -> list:
    if not rank:
        return ["(no eligible bars)"]
    years = sorted({year for table in rank.values() for year in table})
    lines = ["| Year | " + " | ".join(f"h={h}" for h in rank) + " |",
             "|---|" + "---|" * len(rank)]
    lines += [f"| {year} | " + " | ".join(_fmt(rank[h].get(year)) for h in rank) + " |"
              for year in years]
    return lines


def _render_drift(summary) -> list:
    lines = ["## Forward drift (reported, never gating)", "",
             "Mean excess forward return in ATR14 units from the signal close, "
             "event minus its matched null.", "",
             "| h (bars) | events | mean excess (ATR) |", "|---|---|---|"]
    lines += [f"| {h} | {n} | {_fmt(mean)} |" for h, (n, mean) in summary["drift"].items()]
    lines += ["", "Spearman rank correlation, raw event indicator vs h-bar forward "
              "return, member and warm bars pooled across tickers per year:", ""]
    return lines + _render_rank(summary["rank"])


def _render_context(idea, summary, run) -> list:
    """v174 § 5, the last section of a context idea's doc."""
    return diagnostics.render(summary["context"], run["context"],
                              context_start=CONTEXT_START, window_start=run["start"],
                              screen_q=run["screen_q"],
                              scope=diagnostics.scope_sentence(idea))


def render_results(idea, summary, universe, run) -> str:
    v = summary["verdict"]
    sections = [_render_head(idea, v, run), _render_universe(universe, summary),
                _render_verdict(v),
                _render_arms(summary, race.SHAPE_OUTCOMES[idea.race_shape])]
    if idea.race_shape == "trail":
        sections.append(_render_trail(summary, run))
    sections += [_render_years(v), _render_drift(summary)]
    if "short" in summary:
        sections.append(_render_short_blocks(idea, summary, run))
    if idea.context:
        sections.append(_render_context(idea, summary, run))
    return "\n\n".join("\n".join(lines) for lines in sections) + "\n"


def record_path(path) -> str:
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _context_hypothesis(idea) -> str:
    """v174: the fixed-race text naming the context series, then the scope
    sentence (the ledger has no note field; validate_ledger_row rejects one)."""
    return (f"{idea.name}: {idea.summary}; fixed {race.STOP_ATR}/{race.STOP_ATR * race.REWARD_RISK} "
            f"ATR race vs K={null.K} matched null, cap {idea.time_cap_bars}, PIT S&P 500 "
            f"2010-2019, context {', '.join(idea.context)} adjusted closes from "
            f"{CONTEXT_START}, after costs (v174 intermarket screen). "
            + diagnostics.scope_sentence(idea))


_SHORT_ENTRY_TEXT = {"next_open": "entry next open",
                     "level": "sell-stop at the level, filled on the event bar"}
_SHORT_RACE_TEXT = {
    "fixed": lambda: f"fixed {race.STOP_ATR}/{race.STOP_ATR * race.REWARD_RISK} ATR race",
    "trail": lambda: (f"chandelier {trail.TRAIL_ATR} ATR trail race, initial stop "
                      f"{race.STOP_ATR} ATR"),
}


def _short_hypothesis(idea) -> str:
    """v182: the short ledger hypothesis, naming direction, entry, shape and borrow."""
    entry = _SHORT_ENTRY_TEXT[idea.entry]
    shape = _SHORT_RACE_TEXT[idea.race_shape]()
    return (f"{idea.name}: {idea.summary}; SHORT, {entry}, {shape} vs K={null.K} matched "
            f"null raced short, cap {idea.time_cap_bars}, borrow {BORROW_RATE_ANNUAL:.1%} "
            "a year, PIT S&P 500 2010-2019, after costs (v182 short screen)")


def hypothesis(idea) -> str:
    """The ledger hypothesis, naming the shape and cap; the fixed text is
    today's, byte for byte."""
    if idea.context:
        return _context_hypothesis(idea)
    if idea.direction == "short":
        return _short_hypothesis(idea)
    if idea.race_shape == "trail":
        return (f"{idea.name}: {idea.summary}; chandelier {trail.TRAIL_ATR} ATR trail race, "
                f"initial stop {race.STOP_ATR} ATR, cap {idea.time_cap_bars} vs K={null.K} "
                "matched null, PIT S&P 500 2010-2019, after costs (v163 trail screen)")
    return (f"{idea.name}: {idea.summary}; fixed {race.STOP_ATR}/{race.STOP_ATR * race.REWARD_RISK} ATR race vs K={null.K} "
            f"matched null, cap {idea.time_cap_bars}, PIT S&P 500 "
            "2010-2019, after costs (v140 screen)")


def ledger_row(idea, v, record: str, day: str) -> dict:
    return {"id": ledger_id(idea.name), "date": day,
            "hypothesis": hypothesis(idea),
            "instrument": INSTRUMENT, "n": v.n,
            "exp_r": None if v.delta_exp_r is None else round(v.delta_exp_r, 4),
            "p": None if v.p is None else round(v.p, 4),
            "verdict": v.verdict, "record": record,
            "data_source": "yfinance"}   # the Stage -2 screen reads backtest_cache_ext (v162 leaves it)


def _run_info(args, q) -> dict:
    return {"ledger_id": ledger_id(args.idea), "q": q, "date": args.date,
            "start": args.start, "end": args.end,
            "slippage_bps": base_slippage(None),
            "commission": commission_r()}


def _context_run(run: dict, idea, rows, row: dict, data) -> dict:
    """A context idea's run dict also carries its ContextData and the
    screen-family BH q (§ 5.5); any other idea's run dict is returned as is."""
    if not idea.context:
        return run
    return {**run, "context": data,
            "screen_q": diagnostics.screen_family_q(rows, row, INSTRUMENT)}


def publish(args, idea, universe, summary, rows, data=None) -> int:
    """Write the results doc, then append the ledger row (so the ledger never
    points at a missing doc). --dry-run prints and writes nothing."""
    v = summary["verdict"]
    path = Path(args.results_dir) / f"{args.date}-screen-{idea.name}.md"
    row = ledger_row(idea, v, record_path(path), args.date)
    stats.validate_ledger_row(row)
    q = stats.ledger_qvalues(rows + [row])[row["id"]]
    run = _context_run(_run_info(args, q), idea, rows, row, data)
    text = render_results(idea, summary, universe, run)
    reason = _context_hash_refusal(args, data)
    if reason:
        print(f"refused: {reason}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(text)
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    _pin_context_hashes(args, data)
    stats.append_ledger_row(row, path=args.ledger)
    print(f"{row['id']}: {v.verdict}, N={v.n}, dExpR={_fmt(v.delta_exp_r)}R, "
          f"lower95={_fmt(v.ci_low)}R, {v.years_positive}/{len(verdict.YEARS)} years -> {row['record']}")
    return 0


def _utf8_stdout() -> None:
    """The results doc carries Δ and ≥; a redirected Windows stdout is cp1252."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass    # a capture stream that cannot be reconfigured is already safe


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    _utf8_stdout()
    if args.count_only:
        return run_count(args)
    rows = stats.load_ledger(args.ledger)
    reason = refusal(args, rows)
    if reason is None:
        try:
            universe = load_universe(args.cache_dir, args.membership, args.start, args.end)
        except ValueError as exc:
            reason = str(exc)
    data = None
    if reason is None:
        data, reason = _context_step(args, IDEAS[args.idea])
    spy = None
    if reason is None:
        spy, reason = _spy_step(args, IDEAS[args.idea])
    if reason:
        print(f"refused: {reason}", file=sys.stderr)
        return 2
    idea = IDEAS[args.idea]
    tickers = args.tickers.split(",") if args.tickers else None
    screens, skipped = screen_universe(idea, universe, args.cache_dir, start=args.start,
                                       end=args.end, tickers=tickers,
                                       context=None if data is None else data.frames)
    summary = with_diagnostics(summarise(screens, skipped), screens, idea, data, end=args.end)
    summary = with_short_blocks(summary, screens, idea, spy)
    return publish(args, idea, universe, summary, rows, data=data)


if __name__ == "__main__":
    sys.exit(main())
