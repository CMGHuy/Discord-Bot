#!/usr/bin/env python3
"""v140 idea screen: one idea, one shot, PIT S&P 500 daily bars 2010-2019.

    python scripts/backtest/screen_idea.py --idea high52w \
        --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext

Every event races a fixed trade (entry next open, stop 1.5 x ATR14, target
3 x ATR14, idea-specific time cap, costs) against K = 20 matched random bars
(same ticker, month and trend state). verdict.decide applies the four-clause
pass rule; the script writes docs/superpowers/results/<date>-screen-<idea>.md
and appends ledger row screen-<idea>. It refuses an idea already in the
ledger (one shot per idea) and a window end after 2019-12-31. --dry-run
prints the results doc and writes nothing; --tickers needs --dry-run.
"""
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot import config  # noqa: E402
from swingbot.core.backtesting.screen import forward, indicators, null, race, verdict  # noqa: E402,F401
from swingbot.core.backtesting.screen.ideas import Idea  # noqa: E402
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


def _event_rows(ticker, index, kept, null_mean_r) -> list:
    return [{"ticker": ticker,
             "entry_date": index[pos + 1].strftime("%Y-%m-%d"),
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


def screen_ticker(idea: Idea, ticker: str, df: pd.DataFrame, spans, *,
                  slippage_bps=None, commission=None) -> TickerScreen:
    costs = {"slippage_bps": slippage_bps, "commission": commission}
    cap = idea.time_cap_bars
    atr = indicators.atr(df)
    sma200 = indicators.sma(df["Close"], 200)
    raw = np.asarray(idea.events(df).reindex(df.index, fill_value=False), dtype=bool)
    member = null.member_mask(df.index, spans)
    warm = race.warm_mask(atr, sma200) & (df.index >= pd.Timestamp(EVENT_START))
    booked, counts = race.run_book(df, raw, cap, member=member, warm=warm,
                                   atr=atr, **costs)
    draw = null.matched_null(df, booked.event_pos,
                             null.eligible_mask(raw, member, warm, cap), null.K,
                             null.null_seed(idea.name, ticker), cap=cap, atr=atr,
                             trend=null.trend_state(df, sma200), **costs)
    counts["dropped_no_match"] = draw.dropped_no_match
    kept = booked.take(np.isin(booked.event_pos, draw.event_pos))
    fwd = {h: forward.forward_atr(df, atr, h) for h in forward.HORIZONS}
    return TickerScreen(
        ticker=ticker, counters=Counter(counts),
        events=_event_rows(ticker, df.index, kept, draw.null_mean_r),
        null_outcomes=Counter(draw.null_race.outcome.tolist()),
        excess={h: forward.excess_drift(fwd[h], draw.event_pos, draw.groups)
                for h in forward.HORIZONS},
        rank=_rank_frame(df.index, raw, member & warm, fwd))


def screen_universe(idea: Idea, universe: Universe, cache_dir, *,
                    start: str = WINDOW_START, end: str = WINDOW_END,
                    tickers=None, out=print):
    """Every cached member, one at a time, with flushed percent progress."""
    names = universe.cached if tickers is None else [t for t in tickers if t in universe.cached]
    screens, skipped = [], Counter()
    for i, ticker in enumerate(names, start=1):
        df = load_frame(Path(cache_dir) / f"{ticker}.csv", start, end)
        if df is None:
            skipped["empty_frame"] += 1
        else:
            screens.append(screen_ticker(idea, ticker, df,
                                         universe.intervals.get(ticker, [])))
        if i % PROGRESS_EVERY == 0 or i == len(names):
            out(f"[{idea.name}] {i}/{len(names)} tickers ({100.0 * i / len(names):.0f}%)",
                flush=True)
    return screens, skipped
