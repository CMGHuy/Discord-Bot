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

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot import config  # noqa: E402
from swingbot.core.backtesting.screen import forward, indicators, null, race, verdict  # noqa: E402,F401
from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS, Idea  # noqa: E402
from swingbot.core.edge.frictions import commission_r  # noqa: E402
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


RESULTS_DIR = ROOT / "docs" / "superpowers" / "results"
INSTRUMENT = "screen-v1"


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
    p.add_argument("--tickers", default=None, help="comma list; smoke test, needs --dry-run")
    p.add_argument("--dry-run", action="store_true", help="print the doc, write nothing")
    return p


def refusal(args, rows) -> str | None:
    """Why this run must not happen, or None. Checked before any data is read."""
    if args.end > WINDOW_END:
        return f"window end {args.end} is after {WINDOW_END}; the screen never reads 2020+"
    if args.start > args.end:
        return f"window start {args.start} is after its end {args.end}"
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
            "drift": _drift(screens), "rank": _rank(screens)}


def _fmt(value, spec: str = "+.4f") -> str:
    return "n/a" if value is None else format(value, spec)


def _yes(ok: bool) -> str:
    return "yes" if ok else "**no**"


def _render_head(idea, v, run) -> list:
    params = ", ".join(f"{key}={value}" for key, value in idea.params.items())
    return [
        f"# v140 screen: `{idea.name}` -> {v.verdict}", "",
        f"**Ledger id:** `{run['ledger_id']}` (instrument `{INSTRUMENT}`); BH q = "
        f"{_fmt(run['q'], '.4f')} across the ledger (reported, never gating).", "",
        f"**Run:** {run['date']}; window {run['start']}..{run['end']}; "
        f"`python scripts/backtest/screen_idea.py --idea {idea.name}`; null K = {null.K}, "
        f"seed 42 per (idea, ticker); bootstrap {stats.WEEK_BOOTSTRAP_RESAMPLES:,} "
        f"week resamples, seed {stats.WEEK_BOOTSTRAP_SEED}.", "",
        f"**Trigger:** {idea.summary} ({idea.source}); params {params}; time cap "
        f"{idea.time_cap_bars} bars; {idea.direction} only.", "",
        f"**Trade:** entry next open; stop {race.STOP_ATR} x ATR14; target "
        f"{race.STOP_ATR * race.REWARD_RISK} x ATR14; a gap through either level "
        f"fills at the open; stop first on a bar touching both; costs "
        f"{run['slippage_bps']} bps a side + {run['commission']:.4f}R commission.", "",
        "**Spec:** `docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md`",
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
            f"| ΔExpR = mean(R_event − mean R_null) | {_fmt(v.delta_exp_r)}R | ≥ +0.10R | {_yes(v.clauses['exp_r'])} |",
            f"| lower 95% bound, week-clustered bootstrap | {_fmt(v.ci_low)}R (upper {_fmt(v.ci_high)}R) | > 0 | {_yes(v.clauses['ci'])} |",
            f"| years with mean(d) > 0 | {v.years_positive} of {len(verdict.YEARS)} | ≥ 7 | {_yes(v.clauses['years'])} |",
            f"| kept events N | {v.n} | ≥ 300 | {_yes(v.clauses['n'])} |", "",
            f"One-sided bootstrap p (share of resamples ≤ 0): {_fmt(v.p, '.4f')}. "
            "N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say."]


def _mix(outcomes: Counter) -> list:
    total = sum(outcomes.values())
    return [f"{outcomes.get(name, 0)} ({100.0 * outcomes.get(name, 0) / total:.1f}%)"
            if total else "0" for name in race.OUTCOMES]


def _render_arms(summary) -> list:
    lines = ["## Both arms", "",
             f"Mean R_event {_fmt(summary['mean_r_event'])}R; mean R_null (each event's "
             f"null mean, averaged) {_fmt(summary['mean_r_null'])}R. Both after costs.", "",
             "| Exit | event arm | null arm |", "|---|---|---|"]
    lines += [f"| {name} | {e} | {n} |" for name, e, n in
              zip(race.OUTCOMES, _mix(summary["event_outcomes"]), _mix(summary["null_outcomes"]))]
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


def render_results(idea, summary, universe, run) -> str:
    v = summary["verdict"]
    sections = [_render_head(idea, v, run), _render_universe(universe, summary),
                _render_verdict(v), _render_arms(summary), _render_years(v),
                _render_drift(summary)]
    return "\n\n".join("\n".join(lines) for lines in sections) + "\n"


def record_path(path) -> str:
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def ledger_row(idea, v, record: str, day: str) -> dict:
    return {"id": ledger_id(idea.name), "date": day,
            "hypothesis": (f"{idea.name}: {idea.summary}; fixed 1.5/3 ATR race vs K=20 "
                           f"matched null, cap {idea.time_cap_bars}, PIT S&P 500 "
                           "2010-2019, after costs (v140 screen)"),
            "instrument": INSTRUMENT, "n": v.n,
            "exp_r": None if v.delta_exp_r is None else round(v.delta_exp_r, 4),
            "p": None if v.p is None else round(v.p, 4),
            "verdict": v.verdict, "record": record}


def _run_info(args, q) -> dict:
    return {"ledger_id": ledger_id(args.idea), "q": q, "date": args.date,
            "start": args.start, "end": args.end,
            "slippage_bps": getattr(config, "SLIPPAGE_BPS", 5.0),
            "commission": commission_r()}


def publish(args, idea, universe, summary, rows) -> int:
    """Write the results doc, then append the ledger row (so the ledger never
    points at a missing doc). --dry-run prints and writes nothing."""
    v = summary["verdict"]
    path = Path(args.results_dir) / f"{args.date}-screen-{idea.name}.md"
    row = ledger_row(idea, v, record_path(path), args.date)
    stats.validate_ledger_row(row)
    q = stats.ledger_qvalues(rows + [row])[row["id"]]
    text = render_results(idea, summary, universe, _run_info(args, q))
    if args.dry_run:
        print(text)
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
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
    rows = stats.load_ledger(args.ledger)
    reason = refusal(args, rows)
    if reason is None:
        try:
            universe = load_universe(args.cache_dir, args.membership, args.start, args.end)
        except ValueError as exc:
            reason = str(exc)
    if reason:
        print(f"refused: {reason}", file=sys.stderr)
        return 2
    idea = IDEAS[args.idea]
    tickers = args.tickers.split(",") if args.tickers else None
    screens, skipped = screen_universe(idea, universe, args.cache_dir, start=args.start,
                                       end=args.end, tickers=tickers)
    return publish(args, idea, universe, summarise(screens, skipped), rows)


if __name__ == "__main__":
    sys.exit(main())
