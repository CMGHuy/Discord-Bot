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
v211: a level-context idea counts with its context loaded and checked like the
real run, and the report ends with the outcome-blind preflight (shock days, ISO
shock weeks and events per year).
v182: a short or level idea's results doc ends with the short-side blocks
(event overlap with its family partner, the trend-only control, the SPY
200-day regime split, and for a level idea the fill depths, null_unfilled and
the 3 x repricing) -- all printed, none gating; such a run refuses before
screening when SPY.csv cannot load.
v211: an idea may declare CONTEXT_KIND = "level" (its context files load without
the z-coverage floor); --pin-context adds newly registered context files to the
hash pin, never rewriting a pinned one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
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
from swingbot.core.backtesting.screen.errors import IdeaError  # noqa: E402
from swingbot.core.backtesting.screen import context as screen_context  # noqa: E402
from swingbot.core.backtesting.screen import context as pit  # noqa: E402
from swingbot.core.backtesting.screen import descriptive, diagnostics  # noqa: E402
from swingbot.core.backtesting.screen import shock_readouts  # noqa: E402
from swingbot.core.backtesting.screen.ideas import _shock_breakdown as sb  # noqa: E402
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
    shock: dict | None = None   # v211: level only, shock-day null, 3 x book, gap/episode tags
    avoid: dict | None = None   # v214: avoid only, control-arm rows and read-out counts


#: v182: bars from the event bar to the entry bar, per entry mode.
_ENTRY_OFFSET = {"next_open": 1, "level": 0}

#: v214 G1: the control arm's own seed stream, null_seed(idea + ":control", ticker).
CONTROL_SEED_SUFFIX = ":control"


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
    bars from the pool only.
    v214: an avoid idea's condition bars never enter the pool."""
    eligible = null.eligible_mask(ctx["raw"], ctx["member"], ctx["warm"], idea.time_cap_bars)
    for mask in (exclude, ctx.get("condition")):
        if mask is not None:
            eligible = eligible & ~mask
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


#: v211: the shock-day null's seed is null_seed(idea + tag, ticker), a stream of its own, so the standard draw is untouched.
_SHOCK_NULL_TAG = "#shock-null"


def _shock_rows(ticker, index, kept, null_mean_r, entry: str) -> list:
    """The (entry_date, r_event, r_null) projection `_stressed` uses."""
    return [{"entry_date": row["entry_date"], "r_event": row["r_event"], "r_null": row["r_null"]}
            for row in _event_rows(ticker, index, kept, null_mean_r,
                                   entry_offset=_ENTRY_OFFSET[entry])]


def _shock_report(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict,
                  kept) -> dict | None:
    """v211, level ideas only (spec § Printed alongside each verdict): the shock-day null, the 3 x slippage book and the per-event gap and episode-day tags. Printed, never gating; the standard book is not touched."""
    if idea.context_kind != "level":
        return None
    context = ctx["context"]
    state = sb.ticker_state(df, context)
    # SHOCK bars minus every raw event bar: shock_null does not exclude events itself.
    pool = (_null_pool(idea, ctx) & state["shock"].to_numpy(dtype=bool)
            & ~np.asarray(ctx["raw"], dtype=bool))
    draw2 = shock_readouts.shock_null(
        df, kept.event_pos, pool, null.K,
        null.null_seed(idea.name + _SHOCK_NULL_TAG, ticker), cap=idea.time_cap_bars,
        atr=ctx["atr"], shape=idea.race_shape, direction=idea.direction, **costs)
    null2 = _shock_rows(ticker, df.index, kept.take(np.isin(kept.event_pos, draw2.event_pos)),
                        draw2.null_mean_r, idea.entry)
    stress = {"slippage_bps": shock_readouts.SHOCK_STRESS_SLIPPAGE_FACTOR
              * base_slippage(costs["slippage_bps"]), "commission": costs["commission"]}
    kept3, _, draw3 = _books(idea, ticker, df, ctx, stress)
    stress3 = _shock_rows(ticker, df.index, kept3, draw3.null_mean_r, idea.entry)
    tags = shock_readouts.event_tags(df, state, context[sb.BREADTH]["Close"], kept.event_pos)
    return {"null2": null2, "null2_dropped": draw2.dropped, "stress3": stress3, "tags": tags}


def _restricted(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict):
    """Context ideas only (v174 § 5.2): every event raced again against a
    null pool without the bars closer than CAP sessions to any shock day.
    For a context idea the raw mask IS the shock-day mask on this ticker's
    dates. Same seed, K and cap; printed, never gating.
    v211: a level idea's raw mask is a stock trigger, not a shock-day mask, so the restricted null does not apply."""
    if not idea.context or idea.context_kind == "level":
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


def _avoid_context(idea: Idea, df: pd.DataFrame) -> dict:
    """v214: an avoid idea's states(df), read once and put on the ticker's own
    index -- raw events, the control and exclusion masks and the gap bottom.
    An edge idea gets ``{}``."""
    if idea.mode != "avoid":
        return {}
    states = idea.states(df).reindex(df.index)
    flags = {key: states[key].fillna(False).to_numpy(dtype=bool)
             for key in ("event", "control_condition", "condition")}
    return {"raw": flags["event"], "control_condition": flags["control_condition"],
            "condition": flags["condition"],
            "bottom": states["bottom"].to_numpy(dtype=float)}


def ticker_context(idea: Idea, df: pd.DataFrame, spans, context: Mapping | None = None) -> dict:
    """Per-ticker inputs every screen path shares: raw events, membership, warm-up, ATR14 and the null's trend state (v182: moved out of screen_ticker so --count-only reads the same ones).
    v214: an avoid idea's raw events come from its states(df), whose masks and bottom follow the edge keys."""
    atr = indicators.atr(df)
    sma200 = indicators.sma(df["Close"], 200)
    member = null.member_mask(df.index, spans)
    warm = race.warm_mask(atr, sma200) & (df.index >= pd.Timestamp(EVENT_START))
    avoid = _avoid_context(idea, df)
    raw = avoid.pop("raw") if avoid else np.asarray(raw_events(idea, df, context), dtype=bool)
    return {"raw": raw,
            "member": member, "warm": warm, "atr": atr,
            "trend": null.trend_state(df, sma200), "levels": raw_levels(idea, df),
            "context": context, **avoid}


def _family_partner(idea: Idea) -> Idea | None:
    """v182: the first registered idea named in ``idea.family`` other than itself."""
    for name in idea.family:
        if name != idea.name and name in IDEAS:
            return IDEAS[name]
    return None


def _overlap(idea: Idea, df: pd.DataFrame, ctx: dict) -> dict | None:
    """v182: raw event bars shared with the family partner, member and warm bars only.
    v211: the partner gets the same context frames (a level family shares CONTEXT); a partner without context ignores them."""
    partner = _family_partner(idea)
    if partner is None:
        return None
    population = np.asarray(ctx["member"], dtype=bool) & np.asarray(ctx["warm"], dtype=bool)
    other = np.asarray(raw_events(partner, df, ctx.get("context")), dtype=bool)
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


def _overnight(df: pd.DataFrame, event_pos, bottom: np.ndarray) -> int:
    """v214: events whose next open is at or above the gap bottom (bar t's
    bottom, bar t + 1's open). A booked next-open event always has bar t + 1."""
    pos = np.asarray(event_pos, dtype=int)
    if len(pos) == 0:
        return 0
    opens = df["Open"].to_numpy(dtype=float)
    return int(np.count_nonzero(opens[pos + 1] >= bottom[pos]))


def _avoid_arm(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict,
               kept) -> dict | None:
    """v214, avoid ideas only: the control arm -- every kept event matched
    against control_condition bars (condition bars already out of the pool)
    on its own seed stream -- and the read-out counts. Events below the
    control floor (null.MIN_CANDIDATES, inside matched_null) stay in the
    null-paired book; they are counted in ``below_floor``."""
    if idea.mode != "avoid":
        return None
    pool = _null_pool(idea, ctx) & ctx["control_condition"]
    draw = null.matched_null(df, kept.event_pos, pool, null.K,
                             null.null_seed(idea.name + CONTROL_SEED_SUFFIX, ticker),
                             cap=idea.time_cap_bars, atr=ctx["atr"], trend=ctx["trend"],
                             shape=idea.race_shape, direction=idea.direction, **costs)
    matched = kept.take(np.isin(kept.event_pos, draw.event_pos))
    population = ctx["member"] & ctx["warm"]
    return {"control": _event_rows(ticker, df.index, matched, draw.null_mean_r,
                                   entry_offset=_ENTRY_OFFSET[idea.entry]),
            "below_floor": int(draw.dropped_no_match),
            "kept": len(kept.event_pos),
            "excluded": int((ctx["condition"] & population).sum()),
            "population": int(population.sum()),
            "overnight": _overnight(df, kept.event_pos, ctx["bottom"])}


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
        shock=_shock_report(idea, ticker, df, ctx, costs, kept),
        avoid=_avoid_arm(idea, ticker, df, ctx, costs, kept),
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


def _check_z(frame: pd.DataFrame, sessions: pd.DatetimeIndex, ticker: str) -> None:
    screen_context.check_z_coverage(screen_context.trailing_z(frame["Close"]), sessions,
                                    ticker, event_start=EVENT_START)


def _check_level(frame: pd.DataFrame, sessions: pd.DatetimeIndex, ticker: str) -> None:
    """v211: a level context (a fraction that is 0.0 on calm days) is never
    z-scored, so the z-coverage floor does not apply; raw index and session
    contiguity were already checked."""


_KIND_CHECKS: dict[str, Callable] = {"z": _check_z, "level": _check_level}


def _context_frame(cache_dir, ticker: str, sessions: pd.DatetimeIndex, end: str,
                   kind: str = "z"):
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
    _KIND_CHECKS[kind](frame, sessions, ticker)
    return frame, record


def load_context(cache_dir, tickers: tuple[str, ...], *, end: str = WINDOW_END,
                 kind: str = "z") -> screen_context.ContextData:
    """Every context frame an idea names, checked, from CONTEXT_START to end."""
    calendar = _spy_calendar(cache_dir, end)
    frames, records = {}, {}
    for ticker in tickers:
        frames[ticker], records[ticker] = _context_frame(cache_dir, ticker, calendar.index, end, kind)
    return screen_context.ContextData(frames=frames, calendar=calendar, records=records)


def _universe_context(idea: Idea, cache_dir, end: str, context):
    """A context idea run without frames loads them here, once per universe."""
    if idea.context and context is None:
        return load_context(cache_dir, idea.context, end=end,
                            kind=idea.context_kind).frames
    return context


CHECKPOINT_MANIFEST = "manifest.json"
_EMPTY = object()      # the empty-frame marker (None is a legal monkeypatched result)


def _json_sha256(value) -> str:
    text = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _context_sha256(context) -> str | None:
    """sha256 over every context series' records, in ticker order; None without one."""
    if not context:
        return None
    digest = hashlib.sha256()
    for ticker in sorted(context):
        digest.update(ticker.encode("utf-8"))
        digest.update(pd.util.hash_pandas_object(context[ticker], index=True).values.tobytes())
    return digest.hexdigest()


def _checkpoint_manifest(idea: Idea, start: str, end: str, names: list[str],
                         context=None, intervals=None) -> dict:
    return {"idea": idea.name, "start": start, "end": end,
            "tickers_sha256": hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest(),
            "context_sha256": _context_sha256(context),
            "intervals_sha256": _json_sha256(intervals or {}),
            "params_sha256": _json_sha256(dict(idea.params))}


class _Checkpoint:
    """v211: one pickle per finished ticker; a no-op without a directory."""

    def __init__(self, directory: Path | None):
        self.directory = directory

    def load(self, ticker: str):
        if self.directory is None:
            return None
        path = self.directory / f"{ticker}.pkl"
        # pickle is safe here: local scratch files this same script wrote, never shared input
        return pickle.loads(path.read_bytes()) if path.exists() else None

    def save(self, screen) -> None:
        if self.directory is None:
            return
        final = self.directory / f"{screen.ticker}.pkl"
        tmp = final.with_name(final.name + ".tmp")
        tmp.write_bytes(pickle.dumps(screen, protocol=pickle.HIGHEST_PROTOCOL))
        os.replace(tmp, final)


def _open_checkpoint(directory: Path | None, manifest: dict, out) -> _Checkpoint:
    if directory is None:
        return _Checkpoint(None)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / CHECKPOINT_MANIFEST
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved != manifest:
            raise ValueError(f"checkpoint {directory} belongs to another run: "
                             f"{saved} != {manifest}")
    else:
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    done = len(list(directory.glob("*.pkl")))
    out(f"[{manifest['idea']}] checkpoint {directory}: {done} ticker(s) already screened",
        flush=True)
    return _Checkpoint(directory)


def _screen_or_resume(idea, ticker, universe, cache_dir, start, end, context, checkpoint):
    resumed = checkpoint.load(ticker)
    if resumed is not None:
        return resumed
    df = load_frame(Path(cache_dir) / f"{ticker}.csv", start, end)
    if df is None:
        return _EMPTY
    screen = screen_ticker(idea, ticker, df, universe.intervals.get(ticker, []),
                           context=context)
    checkpoint.save(screen)
    return screen


def _guarded_errors(idea: Idea) -> tuple:
    """v214: the errors one ticker may raise without stopping the run --
    IdeaError for an avoid idea, none for an edge idea (``except ()`` catches nothing)."""
    return (IdeaError,) if idea.mode == "avoid" else ()


def _screen_guarded(idea: Idea, ticker: str, skipped: Counter, out, call):
    """v214: ``call()``, or ``None`` after counting and printing a guarded
    idea error -- that ticker is skipped and never checkpointed."""
    try:
        return call()
    except _guarded_errors(idea) as exc:
        skipped["idea_error"] += 1
        skipped[f"idea_error:{ticker}"] = 1
        out(f"[{idea.name}] {ticker}: idea error: {exc}", flush=True)
        return None


def screen_universe(idea: Idea, universe: Universe, cache_dir, *,
                    start: str = WINDOW_START, end: str = WINDOW_END,
                    tickers=None, out=print, context: Mapping | None = None,
                    checkpoint_dir: Path | None = None):
    """Every cached member, one at a time, with flushed percent progress.
    ``context`` (v174) is handed unchanged to every screen_ticker call.
    ``checkpoint_dir`` (v211) persists each finished ticker and resumes from it."""
    context = _universe_context(idea, cache_dir, end, context)
    names = universe.cached if tickers is None else [t for t in tickers if t in universe.cached]
    checkpoint = _open_checkpoint(checkpoint_dir,
                                  _checkpoint_manifest(idea, start, end, names, context,
                                                      universe.intervals), out)
    screens, skipped = [], Counter()
    for i, ticker in enumerate(names, start=1):
        result = _screen_guarded(
            idea, ticker, skipped, out,
            lambda: _screen_or_resume(idea, ticker, universe, cache_dir, start, end,
                                      context, checkpoint))
        if result is _EMPTY:
            skipped["empty_frame"] += 1
        elif result is not None:
            screens.append(result)
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


def count_ticker(idea: Idea, ticker: str, df: pd.DataFrame, spans,
                 context: Mapping | None = None) -> dict:
    """v182 --count-only for one ticker: the real run's events, drops and
    null draw, with a race-free exit bound (every trade lasts the full cap).
    Nothing is raced; no R is computed. v211: ``event_dates`` lists the ISO
    signal date of every counted event, ascending."""
    ctx = ticker_context(idea, df, spans, context)
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
            "event_dates": [d.strftime("%Y-%m-%d") for d in df.index[booked[matched]]],
            "event_depths": [] if depth is None else [float(d) for d in depth[matched]],
            "null_depths": [float(d) for d in groups.null_depths],
            "null_slots": int(groups.null_slots), "null_unfilled": int(groups.null_unfilled)}


_COUNT_SUMS = ("raw", "events", "null_slots", "null_unfilled")
_COUNT_LISTS = ("event_dates", "event_depths", "null_depths")


def _add_count(total: dict, one: dict) -> None:
    """Fold one count_ticker result into the universe total."""
    total["tickers"] += 1
    total["counters"].update(one["counters"])
    for key in _COUNT_SUMS:
        total[key] += one[key]
    for key in _COUNT_LISTS:
        total[key].extend(one[key])


def count_universe(idea: Idea, universe: Universe, cache_dir, *,
                   start: str = WINDOW_START, end: str = WINDOW_END, out=print,
                   context: Mapping | None = None) -> dict:
    """v182 --count-only over every cached member, the screen_universe loop
    and progress line, summed into one dict. ``context`` (v211) is handed
    unchanged to every count_ticker call."""
    total = {"tickers": 0, "members": len(universe.members), "missing": len(universe.missing),
             "skipped": Counter(), "counters": Counter(), "raw": 0, "events": 0,
             "event_dates": [], "event_depths": [], "null_depths": [], "null_slots": 0, "null_unfilled": 0}
    names = universe.cached
    for i, ticker in enumerate(names, start=1):
        df = load_frame(Path(cache_dir) / f"{ticker}.csv", start, end)
        if df is None:
            total["skipped"]["empty_frame"] += 1
        else:
            one = _screen_guarded(idea, ticker, total["skipped"], out,
                                  lambda: count_ticker(idea, ticker, df,
                                                       universe.intervals.get(ticker, []),
                                                       context=context))
            if one is not None:
                _add_count(total, one)
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


#: v211: the outcome-blind preflight's table header (spec § Track 2).
PREFLIGHT_HEADER = "| year | shock days | shock weeks | events |"


def _preflight_block(table: dict[int, dict]) -> list[str]:
    """v211 (spec § Track 2, Outcome-blind preflight): shock days, ISO shock
    weeks (the bootstrap's clusters) and counted events per year, then the
    totals. Printed only."""
    empty = sum(1 for row in table.values() if row["shock_days"] == 0)
    totals = {key: sum(row[key] for row in table.values())
              for key in ("shock_days", "shock_weeks", "events")}
    return (["", "## Preflight — shock days, weeks and events per year (outcome-blind)", "",
             "Printed before the shot from the context and the counted events only; it never "
             "decides whether the shot runs (the shot runs as registered). A shock week is an "
             "ISO week; a week spanning New Year counts once in each year.",
             f"Years without a shock day: {empty} of {len(table)}.", "",
             PREFLIGHT_HEADER, "|---:|---:|---:|---:|"]
            + [f"| {year} | {row['shock_days']} | {row['shock_weeks']} | {row['events']} |"
               for year, row in table.items()]
            + [f"| **total** | **{totals['shock_days']}** | **{totals['shock_weeks']}** | "
               f"**{totals['events']}** |"])


def _count_preflight(idea: Idea, data, counts: dict) -> dict | None:
    """v211: the per-year preflight table for a level-context idea, from the
    market-wide SHOCK state on the context calendar (not any ticker's) and the
    counted events' signal dates; None for every other idea, before reading
    anything."""
    if idea.context_kind != "level":
        return None
    frames = data.frames
    state = sb.shock_state(frames[sb.BREADTH]["Close"], frames[sb.VIX]["Close"])
    return shock_readouts.preflight_years(state, counts["event_dates"])


def render_counts(idea: Idea, counts: dict, args, *, preflight: dict | None = None) -> str:
    """The --count-only report: counts, the N gate, (level ideas) check 5 and
    (v211 level-context ideas) the preflight table."""
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
    if preflight is not None:
        lines += _preflight_block(preflight)
    return "\n".join(lines) + "\n"


def count_refusal(args, idea: Idea) -> str | None:
    """Why this count must not happen, or None. Checked before any data is
    read; never reads the ledger. v211: a level-context idea is counted (its
    context loads in run_count); a z idea is still refused."""
    if args.end > WINDOW_END:
        return f"window end {args.end} is after {WINDOW_END}; the screen never reads 2020+"
    if (args.start, args.end) != (WINDOW_START, WINDOW_END):
        return (f"--count-only counts the pre-registered window {WINDOW_START}..{WINDOW_END} "
                f"only, not {args.start}..{args.end}")
    if args.tickers:
        return ("--count-only counts the whole universe; --tickers belongs to a --dry-run "
                "smoke test")
    if idea.context and idea.context_kind == "z":
        return (f"--count-only counts ideas without context series; {idea.name} reads "
                f"{', '.join(idea.context)}")
    return None


def run_count(args) -> int:
    """v182 --count-only: refuse, or print the count report. Writes nothing.
    v211: a context idea's series load and are checked (SHA pin included)
    exactly as the real run; nothing is pinned or written."""
    idea = IDEAS[args.idea]
    data = None
    reason = count_refusal(args, idea)
    if reason is None:
        try:
            universe = load_universe(args.cache_dir, args.membership, args.start, args.end)
        except ValueError as exc:
            reason = str(exc)
    if reason is None:
        data, reason = _context_step(args, idea)
    if reason:
        print(f"refused: {reason}", file=sys.stderr)
        return 2
    context = None if data is None else data.frames
    counts = count_universe(idea, universe, args.cache_dir, start=args.start, end=args.end,
                            context=context)
    print(render_counts(idea, counts, args, preflight=_count_preflight(idea, data, counts)))
    return 0


RESULTS_DIR =ROOT / "docs" / "superpowers" / "results"
INSTRUMENT = "screen-v1"

#: v214 G1: the closed screens a sign flip alone would clear (calibration only, never re-run)
CALIBRATION_IDS = ("screen-high52w", "screen-gap_volume", "screen-sweep_reclaim_bos",
                   "screen-range_breakdown_close")
#: the ledger keeps the edge p (share of resamples <= 0), not the interval; p >= 0.975
#: means the upper 95% bound sits at or below 0
CALIBRATION_P = 0.975
#: the v211 shots that share the ledger's BH family (spec § Constraints, ledger order)
V211_SHOT_IDS = ("screen-shock_support_break_short", "screen-shock_failed_bounce_short")
#: the per-ticker avoid counts that sum across the universe
AVOID_COUNTS = ("below_floor", "kept", "excluded", "population", "overnight")

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


def add_context_hashes(records: Mapping[str, dict], path) -> list[str]:
    """v211: pin context files not yet pinned; a pinned SHA is never rewritten."""
    path = Path(path)
    pinned = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    added = {}
    for ticker, record in sorted(records.items()):
        sha = record["sha256"]
        if ticker not in pinned:
            added[ticker] = sha
        elif pinned[ticker] != sha:
            raise screen_context.ContextError(
                f"{ticker}.csv SHA-256 {sha[:12]} differs from {pinned[ticker][:12]} "
                f"pinned in {path}; a pin is never rewritten")
    if not added:
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({**pinned, **added}, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")
    return sorted(added)


def run_pin_context(args) -> int:
    try:
        records = _hash_records(args.cache_dir)
        added = add_context_hashes(records, args.context_hashes)
    except screen_context.ContextError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    for ticker in added:
        print(f"pinned {ticker} {records[ticker]['sha256']} -> {args.context_hashes}")
    if not added:
        print(f"nothing to pin: every context file is already pinned in {args.context_hashes}")
    return 0


def _mode_runner(args) -> Callable[[argparse.Namespace], int] | None:
    """The one-shot modes that replace a screen; later modes are added here."""
    if args.count_only:
        return run_count
    if args.pin_context:
        return run_pin_context
    return None


def _context_step(args, idea: Idea) -> tuple[screen_context.ContextData | None, str | None]:
    """(ContextData, None), or (None, reason) to refuse; (None, None) for an
    idea without context. Runs for dry and real runs alike."""
    if not idea.context:
        return None, None
    try:
        records = _hash_records(args.cache_dir)
        data = load_context(args.cache_dir, idea.context, end=args.end,
                            kind=idea.context_kind)
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
    p.add_argument("--checkpoint-dir", type=Path, default=None,
                   help="v211: persist each finished ticker's screen here; a restart skips "
                        "them (refuses another run's checkpoint)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the doc, write nothing")
    mode.add_argument("--count-only", action="store_true",
                      help="v182: count events, drops and full-cap non-overlap (and check 5 "
                           "for a level idea); no race, no R, writes nothing")
    mode.add_argument("--pin-context", action="store_true",
                      help="v211: add the SHA-256 of every registered context file missing "
                           "from --context-hashes; never rewrites a pinned one, screens "
                           "nothing, writes nothing else")
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


def _avoid_pairs(screens) -> list:
    """v214: every screen's avoid control-arm rows, pooled in screen order."""
    return [verdict.PairedEvent(r["entry_date"], r["r_event"] - r["r_null"])
            for s in screens if s.avoid for r in s.avoid["control"]]


def _decide_kwargs(mode: str, screens=()) -> dict:
    """v214: the extra ``verdict.decide`` arguments for ``mode``. Edge gives
    none, so every edge call stays the literal ``verdict.decide(paired)``."""
    if mode == "edge":
        return {}
    return {"mode": "avoid", "control": _avoid_pairs(screens)}


def _stress(screens, mode: str = "edge"):
    """The 2 x slippage verdict over the trail pairs; None for a fixed idea."""
    if all(screen.stressed is None for screen in screens):
        return None
    rows = [row for screen in screens if screen.stressed is not None
            for row in screen.stressed]
    return verdict.decide([verdict.PairedEvent(row["entry_date"], row["r_event"] - row["r_null"])
                           for row in rows], **_decide_kwargs(mode))


def summarise(screens, skipped=None, *, mode: str = "edge") -> dict:
    events = [row for screen in screens for row in screen.events]
    paired = [verdict.PairedEvent(row["entry_date"], row["r_event"] - row["r_null"])
              for row in events]
    return {"verdict": verdict.decide(paired, **_decide_kwargs(mode, screens)), "events": events,
            "counters": _sum_counters(screen.counters for screen in screens),
            "skipped": Counter(skipped or {}),
            "event_outcomes": Counter(row["outcome"] for row in events),
            "null_outcomes": _sum_counters(screen.null_outcomes for screen in screens),
            "mean_r_event": _mean([row["r_event"] for row in events]),
            "mean_r_null": _mean([row["r_null"] for row in events]),
            "drift": _drift(screens), "rank": _rank(screens),
            "timeouts": _timeouts(screens, events), "stress": _stress(screens)}


def with_avoid_blocks(summary: dict, screens, idea: Idea) -> dict:
    """v214: an avoid idea's summed read-out counts and idea-error tickers;
    any other idea's summary comes back untouched."""
    if idea.mode != "avoid":
        return summary
    blocks = [s.avoid for s in screens if s.avoid]
    prefix = "idea_error:"
    errors = sorted(key[len(prefix):] for key in summary["skipped"] if key.startswith(prefix))
    avoid = {name: sum(block[name] for block in blocks) for name in AVOID_COUNTS}
    return {**summary, "avoid": {**avoid, "errors": {ticker: 1 for ticker in errors}}}


def _calibration(rows) -> list:
    """v214: the four closed screens read against the avoid clauses (printout only)."""
    by_id = {row["id"]: row for row in rows}
    out = []
    for row_id in CALIBRATION_IDS:
        name = row_id.removeprefix("screen-")
        row = by_id.get(row_id, {})
        exp_r, p = row.get("exp_r"), row.get("p")
        out.append({"id": row_id, "direction": IDEAS[name].direction if name in IDEAS else "n/a",
                    "exp_r": exp_r, "p": p,
                    "clause_1": verdict.avoid_mean_clause(exp_r),
                    "clause_2": p is not None and p >= CALIBRATION_P})
    return out


def _avoid_run(run: dict, idea: Idea, rows, row: dict) -> dict:
    """An avoid idea's run dict also carries the calibration and the ledger order."""
    if idea.mode != "avoid":
        return run
    return {**run, "calibration": _calibration(rows),
            "ledger_order": {"position": len(rows) + 1,
                             "preceding_v211": [r["id"] for r in rows
                                                if r["id"] in V211_SHOT_IDS]}}


def _restricted_pairs(screens):
    """Every ticker's restricted-null pairs, pooled; None for an old idea."""
    if all(screen.restricted is None for screen in screens):
        return None
    return [row for screen in screens if screen.restricted for row in screen.restricted]


def with_diagnostics(summary: dict, screens, idea: Idea, data, *, end: str) -> dict:
    """The summary plus ``"context"`` (v174 § 5) for a context idea; the same
    dict, untouched, for any other. The verdict object is never rebuilt."""
    if not idea.context or idea.context_kind == "level" or data is None:
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


def _decide(rows, mode: str = "edge") -> verdict.Verdict | None:
    if rows is None:
        return None
    return verdict.decide([verdict.PairedEvent(r["entry_date"], r["r_event"] - r["r_null"])
                           for r in rows], **_decide_kwargs(mode))


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


def _shock_split(pairs: list, key: str, labels: tuple) -> dict:
    """Per label: n, mean r_event and mean paired excess; ``missing`` counts unlabelled tags."""
    out = {}
    for label in labels:
        rows = [row for row, tag in pairs if tag[key] == label]
        out[label] = {"n": len(rows), "exp_r_event": _mean([r["r_event"] for r in rows]),
                      "delta_exp_r": _mean([r["r_event"] - r["r_null"] for r in rows])}
    out["missing"] = sum(tag[key] is None for _, tag in pairs)
    return out


def with_shock_blocks(summary: dict, screens, idea: Idea) -> dict:
    """v211: the summary plus ``"shock"`` for a level idea; the same dict, untouched, for any other. The verdict object is never rebuilt."""
    if idea.context_kind != "level":
        return summary
    shocked = [s for s in screens if s.shock is not None]
    pairs = [(row, tag) for s in shocked for row, tag in zip(s.events, s.shock["tags"])]
    block = {"null2": _decide([r for s in shocked for r in s.shock["null2"]]),
             "null2_dropped": sum(s.shock["null2_dropped"] for s in shocked),
             "stress3": _decide([r for s in shocked for r in s.shock["stress3"]]),
             "gap": _shock_split(pairs, "gap_bucket", shock_readouts.GAP_BUCKETS),
             "episode_day": _shock_split(pairs, "episode_day", shock_readouts.EPISODE_DAYS),
             "skipped_overlap": summary["counters"].get("skipped_overlap", 0)}
    return {**summary, "shock": block}


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
             "control": _decide(_pooled(screens, "control"), idea.mode),
             "regime": regime,
             "repriced": _decide(_pooled(screens, "repriced"), idea.mode),
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
    """The verdict table for ``v.mode`` (v214)."""
    return _VERDICT_RENDERERS[v.mode](v)


def _render_edge_verdict(v) -> list:
    return [f"## Verdict: {v.verdict}", "",
            "| Clause | Measured | Rule | Holds |", "|---|---|---|---|",
            f"| ΔExpR = mean(R_event − mean R_null) | {_fmt(v.delta_exp_r)}R | ≥ {verdict.PASS_EXP_R:+.2f}R | {_yes(v.clauses['exp_r'])} |",
            f"| lower 95% bound, week-clustered bootstrap | {_fmt(v.ci_low)}R (upper {_fmt(v.ci_high)}R) | > 0 | {_yes(v.clauses['ci'])} |",
            f"| years with mean(d) > 0 | {v.years_positive} of {len(verdict.YEARS)} | ≥ {verdict.MIN_POSITIVE_YEARS} | {_yes(v.clauses['years'])} |",
            f"| kept events N | {v.n} | ≥ {verdict.MIN_N} | {_yes(v.clauses['n'])} |", "",
            f"One-sided bootstrap p (share of resamples ≤ 0): {_fmt(v.p, '.4f')}. "
            f"N < {verdict.MIN_N} is `SCREEN-UNDERPOWERED` whatever the other clauses say."]


def _render_avoid_verdict(v) -> list:
    """v214: the avoid table -- every clause mirrored below zero, plus the control arm."""
    c, rule = v.control, f"≤ {-verdict.PASS_EXP_R:+.2f}R"
    return [f"## Verdict: {v.verdict}", "",
            "| Clause | Measured | Rule | Holds |", "|---|---|---|---|",
            f"| ΔExpR = mean(R_event − mean R_null) | {_fmt(v.delta_exp_r)}R | {rule} | {_yes(v.clauses['exp_r'])} |",
            f"| upper 95% bound, week-clustered bootstrap | {_fmt(v.ci_high)}R (lower {_fmt(v.ci_low)}R) | < 0 | {_yes(v.clauses['ci'])} |",
            f"| years with mean(d) < 0 | {v.years_negative} of {len(verdict.YEARS)} | ≥ {verdict.MIN_POSITIVE_YEARS} | {_yes(v.clauses['years'])} |",
            f"| kept events N | {v.n} | ≥ {verdict.MIN_N} | {_yes(v.clauses['n'])} |",
            f"| control arm ΔExpR = mean(R_event − mean R_control) | {_fmt(c.delta_exp_r)}R | {rule} | {_yes(v.clauses['control_exp_r'])} |",
            f"| control arm upper 95% bound | {_fmt(c.ci_high)}R (lower {_fmt(c.ci_low)}R) | < 0 | {_yes(v.clauses['control_ci'])} |",
            f"| control arm events N_c | {c.n} | ≥ {verdict.MIN_N} | {_yes(v.clauses['control_n'])} |", "",
            f"One-sided bootstrap p (share of resamples ≥ 0): {_fmt(v.p, '.4f')}. "
            f"N < {verdict.MIN_N} or N_c < {verdict.MIN_N} is `SCREEN-UNDERPOWERED` whatever "
            "the other clauses say; the control arm is drawn from bars where the idea's "
            "control condition holds (G1), so a sign flip alone never passes."]


_VERDICT_RENDERERS = {"edge": _render_edge_verdict, "avoid": _render_avoid_verdict}


def _years_text(v) -> str:
    """The publish line's year count: positive years (edge), negative years (avoid)."""
    if v.mode == "avoid":
        return f"{v.years_negative}/{len(verdict.YEARS)} years negative"
    return f"{v.years_positive}/{len(verdict.YEARS)} years"


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


def _render_shock_control(summary, block) -> list:
    """v211: the unconditional control, the same trigger with the shock state ignored."""
    c = block["control"]
    margin = _minus(summary["verdict"].delta_exp_r, c.delta_exp_r)
    return ["**Unconditional control** (`control_events`: the same trigger with the shock "
            "state ignored; same race, same matched null): "
            f"N = {c.n}, ΔExpR {_fmt(c.delta_exp_r)}R, 95% week-clustered interval "
            f"{_fmt(c.ci_low)}R to {_fmt(c.ci_high)}R. The idea's ΔExpR minus the control's: "
            f"{_fmt(margin)}R. A pass whose ΔExpR is not clearly above the control is not "
            "credited to the shock condition."]


_CONTROL_TEXT: dict[str, Callable] = {"z": _render_control, "level": _render_shock_control}

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
        parts.append(_CONTROL_TEXT[idea.context_kind](summary, block))
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


def _render_split(title: str, column: str, split: dict, labels: tuple,
                  missing_label: str) -> list:
    """v211: one labelled split table and its missing-count line."""
    lines = [title, "", f"| {column} | N | mean R_event | ΔExpR (standard null) |",
             "|---|---:|---:|---:|"]
    for label in labels:
        cell = split[label]
        lines.append(f"| {label} | {cell['n']} | {_fmt(cell['exp_r_event'])}R | "
                     f"{_fmt(cell['delta_exp_r'])}R |")
    return lines + ["", f"{missing_label}: {split['missing']}."]


def _render_shock_blocks(idea, summary, run) -> list:
    """v211: the shock read-outs, descriptive and never gating."""
    b, v = summary["shock"], summary["verdict"]
    n2, s3 = b["null2"], b["stress3"]
    factor = shock_readouts.SHOCK_STRESS_SLIPPAGE_FACTOR
    parts = [
        [f"Kept events N = {v.n}; skipped as overlapping an open race (`skipped_overlap`) "
         f"= {b['skipped_overlap']}."],
        [f"**Shock-day null** (K = {null.K} bars drawn only from this ticker's SHOCK days, "
         "no month or trend match; its own seeded stream): "
         f"N = {n2.n}, ΔExpR {_fmt(n2.delta_exp_r)}R, 95% week-clustered interval "
         f"{_fmt(n2.ci_low)}R to {_fmt(n2.ci_high)}R; events dropped for fewer than "
         f"{null.MIN_CANDIDATES} SHOCK-day candidates: {b['null2_dropped']}. "
         f"The standard ΔExpR minus this one: {_fmt(_minus(v.delta_exp_r, n2.delta_exp_r))}R. "
         "An edge that vanishes against this null is the market's drift after a shock day, "
         "not the stock trigger."],
        [f"**Re-priced at {factor} x slippage** ({factor * run['slippage_bps']} bps a side, "
         "both fills, events and standard null; shock-day spreads widen 2-5x): "
         f"ΔExpR {_fmt(s3.delta_exp_r)}R, 95% week-clustered interval "
         f"{_fmt(s3.ci_low)}R to {_fmt(s3.ci_high)}R; change vs the base book "
         f"{_fmt(_minus(s3.delta_exp_r, v.delta_exp_r))}R. Printed, never gating."],
        _render_split("**Gap split** (next open vs the signal close; the race fills the "
                      "entry at that open, gap included, and a gap through the stop at the "
                      "open):", "gap", b["gap"], shock_readouts.GAP_BUCKETS,
                      "Events with no next open"),
        _render_split("**Day of the episode** (`peak`: the signal close is the episode's "
                      "highest BREADTH_ATR1 so far, so the entry is the session after the "
                      "breadth peak; `later`: any other SHOCK day of the episode):",
                      "day", b["episode_day"], shock_readouts.EPISODE_DAYS,
                      "Events on a NORMAL day"),
    ]
    lines = ["## Shock read-outs (v211; descriptive, never gating)"]
    for part in parts:
        lines += [""] + part
    return lines


def _render_level_context(idea, summary, run) -> list:
    """v211: the level idea's context series and the short-family BH q."""
    lines = ["## Context series (v211 level)", "", diagnostics.scope_sentence(idea), "",
             "| series | rows | first | last | SHA-256 |", "|---|---:|---|---|---|"]
    for _, r in sorted(run["context"].records.items()):
        lines.append(f"| {r['ticker']} | {r['rows']} | {r['first']} | {r['last']} | "
                     f"`{r['sha256'][:12]}` |")
    lines += ["", "**Short-family BH q** (every short idea screened so far, "
              "`SHORT_SCREEN_IDS`, this run's row included; reported, never gating):",
              "", "| ledger id | q |", "|---|---:|"]
    lines += [f"| `{i}` | {_fmt(q, '.4f')} |" for i, q in run["short_q"].items()] \
        or ["| (no short idea in the ledger yet) | n/a |"]
    return lines


_CONTEXT_SECTIONS: dict[str, Callable] = {"z": _render_context,
                                          "level": _render_level_context}


def _render_calibration(rows) -> list:
    lines = ["### Calibration: four closed screens (never re-run)", "",
             f"Clause 1 is ΔExpR ≤ {-verdict.PASS_EXP_R:+.2f}R. Clause 2 (upper 95% bound < 0) is "
             f"read from the ledger's edge p as p ≥ {CALIBRATION_P}, because the ledger stores no "
             "interval. A screen passing both shows what a sign flip alone would clear; the "
             "control arm is what it never faced.", "",
             "| Ledger id | Direction | ΔExpR | edge p | Clause 1 | Clause 2 |",
             "|---|---|---|---|---|---|"]
    lines += [f"| `{c['id']}` | {c['direction']} | {_fmt(c['exp_r'])}R | {_fmt(c['p'], '.4f')} "
              f"| {_yes(c['clause_1'])} | {_yes(c['clause_2'])} |" for c in rows]
    return lines


def _render_avoid(summary, run) -> list:
    """v214: the avoid read-outs (never gating), the control arm per year, the
    calibration printout and the ledger order."""
    a, c = summary["avoid"], summary["verdict"].control
    order = run["ledger_order"]
    return [
        "## Avoid mode (read-outs, never gating)", "",
        "**Seeds:** the matched null draws with `null_seed(idea, ticker)` = [42, crc32(idea), "
        "crc32(ticker)]; the control arm with `null_seed(idea + \":control\", ticker)`, from bars "
        "where the idea's control condition holds, at least "
        f"{null.MIN_CANDIDATES} candidates per event. Every bar where the idea's condition holds "
        "is excluded from both pools.", "",
        "| Read-out | Count | Share |", "|---|---|---|",
        f"| member and warm bars | {a['population']} | |",
        f"| condition bars excluded from both pools | {a['excluded']} | "
        f"{_share(_ratio(a['excluded'], a['population']))} of member and warm bars |",
        f"| kept events below the control floor | {a['below_floor']} | "
        f"{_share(_ratio(a['below_floor'], a['kept']))} of kept events |",
        "| kept events whose next open reached the gap bottom (overnight) | "
        f"{a['overnight']} | {_share(_ratio(a['overnight'], a['kept']))} of kept events |",
        f"| tickers aborted by an idea error | {len(a['errors'])} | |", "",
        "Idea errors per ticker: "
        f"{', '.join(f'{t} 1' for t in a['errors']) or 'none'}.", "",
        "### Control arm per year", "",
        "| Year | N_c | mean(d_c) |", "|---|---|---|",
        *[f"| {year} | {n} | {_fmt(mean)}R |" for year, (n, mean) in c.per_year.items()], "",
        *_render_calibration(run["calibration"]), "",
        "### Ledger order", "",
        f"This row is ledger row {order['position']}; v211 shots already in the ledger: "
        f"{', '.join(order['preceding_v211']) or 'none'}. The BH q in the header is computed "
        "across the whole ledger in this order (spec § Constraints)."]


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
    if "shock" in summary:
        sections.append(_render_shock_blocks(idea, summary, run))
    if idea.context:
        sections.append(_CONTEXT_SECTIONS[idea.context_kind](idea, summary, run))
    if idea.mode == "avoid":
        sections.append(_render_avoid(summary, run))
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


def _level_hypothesis(idea) -> str:
    """v211: the short text, the level context series, then the frozen scope
    (the ledger has no note field)."""
    return (_short_hypothesis(idea)
            + f", context {', '.join(idea.context)} levels from {CONTEXT_START} "
              "(v211 shock screen). " + diagnostics.scope_sentence(idea))


def _avoid_hypothesis(idea) -> str:
    """v214: the avoid ledger hypothesis, naming both baselines and the margin."""
    return (f"{idea.name}: {idea.summary}; AVOID mode (v214): fixed {race.STOP_ATR}/"
            f"{race.STOP_ATR * race.REWARD_RISK} ATR race, {idea.direction}, entry next open, "
            f"cap {idea.time_cap_bars}, must trail both a K={null.K} matched null and a "
            f"K={null.K} control arm by >= {verdict.PASS_EXP_R:.2f}R, condition bars excluded "
            "from both pools, PIT S&P 500 2010-2019, after costs (v214 avoid screen)")


def hypothesis(idea) -> str:
    """The ledger hypothesis, naming the shape and cap; the fixed text is
    today's, byte for byte."""
    if idea.mode == "avoid":
        return _avoid_hypothesis(idea)
    if idea.context_kind == "level":
        return _level_hypothesis(idea)
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


#: v211 (spec § Track 2): every short idea screened so far; the results doc
#: prints BH q across them. range_breakdown_stop is unspent and simply absent
#: from q until it runs.
SHORT_SCREEN_IDS = ("v104-b-short-mechanisms", "screen-range_breakdown_close",
                    "screen-range_breakdown_stop", "screen-shock_support_break_short",
                    "screen-shock_failed_bounce_short")


def short_family_q(rows: list[dict], row: dict) -> dict[str, float | None]:
    """BH q over the short ideas in the ledger plus this run's row, in
    SHORT_SCREEN_IDS order; a row with p = None maps to None."""
    family = {r["id"]: r for r in [*rows, row] if r["id"] in SHORT_SCREEN_IDS}
    q = stats.ledger_qvalues(list(family.values()))
    return {i: q[i] for i in SHORT_SCREEN_IDS if i in q}


def _context_run(run: dict, idea, rows, row: dict, data) -> dict:
    """A context idea's run dict also carries its ContextData and the
    screen-family BH q (§ 5.5); any other idea's run dict is returned as is.
    v211: a level idea carries the short-family q instead (§ Track 2)."""
    if not idea.context:
        return run
    if idea.context_kind == "level":
        return {**run, "context": data, "short_q": short_family_q(rows, row)}
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
    run = _avoid_run(_context_run(_run_info(args, q), idea, rows, row, data), idea, rows, row)
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
          f"lower95={_fmt(v.ci_low)}R, {_years_text(v)} -> {row['record']}")
    return 0


def _utf8_stdout() -> None:
    """The results doc carries Δ and ≥; a redirected Windows stdout is cp1252."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass    # a capture stream that cannot be reconfigured is already safe


def _run_screens(args, idea: Idea, universe: Universe, data, spy) -> dict:
    """The summary ``main`` publishes (screen, diagnostics, short blocks)."""
    tickers = args.tickers.split(",") if args.tickers else None
    screens, skipped = screen_universe(idea, universe, args.cache_dir, start=args.start,
                                       end=args.end, tickers=tickers,
                                       context=None if data is None else data.frames,
                                       checkpoint_dir=args.checkpoint_dir)
    summary = with_diagnostics(summarise(screens, skipped, mode=idea.mode), screens, idea,
                               data, end=args.end)
    summary = with_short_blocks(summary, screens, idea, spy)
    summary = with_shock_blocks(summary, screens, idea)
    return with_avoid_blocks(summary, screens, idea)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    _utf8_stdout()
    runner = _mode_runner(args)
    if runner is not None:
        return runner(args)
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
    return publish(args, idea, universe, _run_screens(args, idea, universe, data, spy),
                   rows, data=data)


if __name__ == "__main__":
    sys.exit(main())
