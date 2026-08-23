"""Does expectancy vary with how many trades the scanner opens on one day?

Plan v51 (docs/superpowers/plans/2026-08-22-v51-alert-density-expectancy.md).
This measures a correlation over TRAIN and stops at the number. It ships no
trading behaviour, no config Field, no flag and no gate: any throttle it might
justify is a separate spec with its own pre-registered hypothesis.

THE DEFINITION, fixed before any data contact and not revisited: a trade's
density is the number of trades OPENED ON THE SAME CALENDAR DATE across the
whole universe, counted in the same backtest run, including itself. Entry date
comes from `opened_at`. This is a PROXY for alert count -- not every alert
becomes a trade -- and it must be described in those words wherever it is
reported, never as an alert count.

This module half (Task 1) is pure arithmetic over trade lists: no I/O, no
network, no cache reads. The sweep that feeds it (Task 2) wraps these
functions; it does not reimplement them.
"""
from __future__ import annotations

# Bucket edges mirror the source's quiet/busy split (HKUDS/Vibe-Trading's
# trade-journal skill: busy >=3 trades vs quiet <=1) widened for a ~75-ticker
# universe scanned across ten horizons. Frozen before any number was read;
# redefining them after seeing a null result is the exact failure the one-shot
# discipline exists to prevent.
DENSITY_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("quiet", 1, 1),
    ("normal", 2, 3),
    ("busy", 4, 7),
    ("flood", 8, 10_000),
)


def _entry_day(trade: dict) -> str | None:
    """Calendar date a trade was opened, or None if it carries no entry stamp.

    A missing `opened_at` is skipped rather than raised: a sweep over ten
    horizons should not die on one malformed record, and a silently dropped
    trade is visible in the reported `n`.
    """
    raw = trade.get("opened_at")
    if not raw:
        return None
    return str(raw)[:10]


def density_by_day(trades: list[dict]) -> dict[str, int]:
    """{entry date: trades opened that date}, counting every trade including
    itself. Intraday times never split a day."""
    out: dict[str, int] = {}
    for t in trades:
        day = _entry_day(t)
        if day is None:
            continue
        out[day] = out.get(day, 0) + 1
    return out


def _bucket_for(density: int) -> str | None:
    for name, lo, hi in DENSITY_BUCKETS:
        if lo <= density <= hi:
            return name
    return None


def _is_evaluated(trade: dict) -> bool:
    """Whether a trade counts toward win rate.

    Mirrors run_backtest_range.pool(): win rate is over win/loss only, so
    scratches and timeouts are excluded. Where a record carries no `outcome`
    (the pure-arithmetic case) any trade with an R-multiple is evaluated.
    """
    outcome = trade.get("outcome")
    if outcome is not None:
        return outcome in ("win", "loss")
    return trade.get("r_multiple") is not None


def _is_win(trade: dict) -> bool:
    outcome = trade.get("outcome")
    if outcome is not None:
        return outcome == "win"
    r = trade.get("r_multiple")
    return r is not None and r > 0


def _bucket_row(name: str, trades: list[dict], total: int) -> dict:
    rs = [t["r_multiple"] for t in trades if t.get("r_multiple") is not None]
    evaluated = [t for t in trades if _is_evaluated(t)]
    wins = [t for t in evaluated if _is_win(t)]
    return {
        "bucket": name,
        "n": len(trades),
        "n_eval": len(evaluated),
        "wins": len(wins),
        "losses": len(evaluated) - len(wins),
        # None, not 0.0, for an empty bucket: "no trades" must not read as
        # "no edge". Every bucket is reported even at n=0 -- the shape of the
        # answer is the point (holding_period_split's rule).
        "win_rate": len(wins) / len(evaluated) * 100 if evaluated else None,
        "expectancy_r": float(sum(rs) / len(rs)) if rs else None,
        "total_r": float(sum(rs)),
        "share_of_trades": len(trades) / total if total else 0.0,
    }


def bucket_trades(trades: list[dict]) -> list[dict]:
    """One row per density bucket, in DENSITY_BUCKETS order, always all of them.

    Expectancy is the mean R over every trade in the bucket (including
    scratches and timeouts, as pool() does); win rate is over win/loss only.
    An empty input returns an empty list -- there is no population to describe
    the shape of -- but a non-empty one always reports all four buckets.
    """
    if not trades:
        return []
    by_day = density_by_day(trades)
    groups: dict[str, list[dict]] = {name: [] for name, _, _ in DENSITY_BUCKETS}
    total = 0
    for t in trades:
        day = _entry_day(t)
        if day is None:
            continue
        bucket = _bucket_for(by_day[day])
        if bucket is None:
            continue
        groups[bucket].append(t)
        total += 1
    return [_bucket_row(name, groups[name], total) for name, _, _ in DENSITY_BUCKETS]


def density_profile(trades: list[dict]) -> dict:
    """How dense the days actually are, described rather than bucketed.

    Purely descriptive, and reported alongside the frozen buckets rather than
    instead of them. Without it a table showing (say) 95% of trades in `flood`
    reads as a bug when it is in fact a fact about a 78-ticker x 10-horizon
    universe: the bucket edges were frozen before data contact and are not
    revisited, but whether they discriminate anything on THIS population is
    something the reader must be able to see.
    """
    by_day = density_by_day(trades)
    if not by_day:
        return {"n_days": 0, "n_trades": 0, "min": None, "median": None,
                "mean": None, "max": None, "days_per_bucket": {}}
    counts = sorted(by_day.values())
    mid = len(counts) // 2
    median = (counts[mid] if len(counts) % 2
              else (counts[mid - 1] + counts[mid]) / 2)
    days_per_bucket: dict[str, int] = {name: 0 for name, _, _ in DENSITY_BUCKETS}
    for c in counts:
        bucket = _bucket_for(c)
        if bucket is not None:
            days_per_bucket[bucket] += 1
    return {
        "n_days": len(counts),
        "n_trades": sum(counts),
        "min": counts[0],
        "median": float(median),
        "mean": sum(counts) / len(counts),
        "max": counts[-1],
        "days_per_bucket": days_per_bucket,
    }


def per_day_rows(trades: list[dict]) -> list[dict]:
    """One row per entry date: how many trades, across how many DISTINCT
    tickers and horizons, and how they did.

    The distinct-ticker count is what separates the two things a raw trade
    count conflates, and the plan links them explicitly: twelve trades across
    twelve tickers is "many tickers alerting on one day" (the hypothesis),
    while twelve trades across two tickers at six horizons each is spec v49's
    pathology one level down -- one setup counted once per timeframe. A report
    that cannot tell them apart cannot honestly call either one a finding.
    """
    by_day: dict[str, list[dict]] = {}
    for t in trades:
        day = _entry_day(t)
        if day is None:
            continue
        by_day.setdefault(day, []).append(t)
    rows = []
    for day in sorted(by_day):
        group = by_day[day]
        rs = [t["r_multiple"] for t in group if t.get("r_multiple") is not None]
        evaluated = [t for t in group if _is_evaluated(t)]
        wins = [t for t in evaluated if _is_win(t)]
        rows.append({
            "date": day,
            "n_trades": len(group),
            "n_tickers": len({t.get("ticker") for t in group if t.get("ticker")}),
            "n_horizons": len({t.get("horizon") for t in group if t.get("horizon")}),
            "bucket": _bucket_for(len(group)),
            "mean_r": float(sum(rs) / len(rs)) if rs else None,
            "win_rate": len(wins) / len(evaluated) * 100 if evaluated else None,
        })
    return rows


# ---------------------------------------------------------------------------
# Task 2: the TRAIN sweep. Every line below this point does I/O; everything
# above it is pure. The heavy imports are deliberately lazy so the unit tests
# for the arithmetic above never pay for pandas + the whole swingbot import
# graph.
# ---------------------------------------------------------------------------

CONFLUENCE_SOURCE = "confluence"


def _bootstrap_path() -> None:
    """Put the repo root and the sibling script dirs on sys.path.

    Mirrors run_backtest_range.py's own preamble -- `scripts/` is not a
    package and its modules import each other bare.
    """
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    for p in (root, root / "scripts" / "data", root / "scripts" / "backtest"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def _plumbing():
    """The existing replay plumbing, imported once.

    Deliberately re-uses run_backtest_range's helpers (frame loading, market
    context, the TRAIN window, entry-date windowing) rather than restating
    them: a divergent second harness is how two answers to one question get
    produced. Importing that module is safe -- it guards main() behind
    __name__ == "__main__".
    """
    _bootstrap_path()
    import warnings

    warnings.filterwarnings("ignore")
    import run_backtest_range as rbr

    return rbr


def _entry_dates_for_ticker(ticker: str, df, horizons, date_from, date_to,
                            *, gates, scale_out, want_strategies, want_confluence,
                            strategies):
    """Both populations for ONE ticker, as flat trade dicts.

    Grouped per ticker (not per ticker-horizon) for the same reason
    backtest_scenarios._replay_ticker is: the OHLCV frame is the expensive
    thing to move across a process boundary, and a per-pair split would ship
    the same ~2MB frame once per horizon.

    `opened_at` is the SIGNAL bar's date in both populations. That is what
    BacktestTrade.entry_date already is (backtest.py stamps
    `df.index[i].date()` for signal index `i`), and it is what
    run_scenario_backtest windows confluence trades by ("start/end restrict
    SIGNAL dates"). It is the day the setup fired, which is the alert-density
    proxy this plan is about -- not necessarily the day a stop-entry order
    filled.
    """
    from swingbot.core.backtesting.backtest import run_backtest
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    from swingbot.core.planning.plan_engine import simulate_exit

    rows: list[dict] = []
    per_unit: list[tuple[str, str, int]] = []   # (horizon, population, n trades)

    for hk in horizons:
        if want_confluence:
            n_before = len(rows)
            for i, plan in replay_scenarios(ticker, df, hk, gates=gates):
                signal_date = str(df.index[i].date())
                if date_from and signal_date < date_from:
                    continue
                if date_to and signal_date > date_to:
                    continue
                res = simulate_exit(df, i, plan, scale_out=scale_out)
                # A plan that never triggered never opened a trade, so it
                # cannot contribute to a day's density. _aggregate() drops
                # these from `closed` for the same reason.
                if res.outcome == "not_triggered":
                    continue
                rows.append({
                    "opened_at": signal_date,
                    "ticker": ticker,
                    "horizon": hk,
                    "source": CONFLUENCE_SOURCE,
                    "strategy": CONFLUENCE_SOURCE,
                    "outcome": res.outcome,
                    "r_multiple": res.r_total,
                })
            per_unit.append((hk, CONFLUENCE_SOURCE, len(rows) - n_before))

        if want_strategies:
            n_before = len(rows)
            for strat in strategies:
                try:
                    summary = run_backtest(
                        ticker, df, strat, hk, one_at_a_time=True,
                        exit_model="v2", scale_out=scale_out,
                        tp2_mode="levels", frictions=True)
                except Exception as e:                      # one bad pair must not kill the sweep
                    print(f"    ! {ticker} {strat}/{hk}: {e}", flush=True)
                    continue
                for t in rbr_window_trades(summary, date_from, date_to):
                    rows.append({
                        "opened_at": t.entry_date,
                        "ticker": ticker,
                        "horizon": hk,
                        "source": "strategy",
                        "strategy": strat,
                        "outcome": t.outcome,
                        "r_multiple": t.r_multiple,
                    })
            per_unit.append((hk, "strategy", len(rows) - n_before))

    return rows, per_unit


def rbr_window_trades(summary, date_from, date_to):
    """run_backtest_range.window_trades, reached through the module so the
    entry-date windowing has exactly one definition."""
    return _plumbing().window_trades(summary, date_from, date_to)


def _worker(args):
    """Process-pool entry point: must be module-level and take one picklable
    argument. Returns (ticker, rows, per_unit)."""
    (ticker, df, horizons, date_from, date_to, gates, scale_out,
     want_strategies, want_confluence, strategies) = args
    _plumbing()          # sys.path + warnings inside the child (spawn on Windows)
    rows, per_unit = _entry_dates_for_ticker(
        ticker, df, horizons, date_from, date_to, gates=gates,
        scale_out=scale_out, want_strategies=want_strategies,
        want_confluence=want_confluence, strategies=strategies)
    return ticker, rows, per_unit


def load_frames(tickers, *, verbose=True):
    """{ticker: context-stamped frame} for every cached, liquid, clean ticker.

    Same exclusion sequence as run_backtest_range.run_scenario_mode, reached
    through that module so the two runs see the same universe.
    """
    rbr = _plumbing()
    from swingbot.core.marketdata.universe import data_quality_issues, liquidity_reason

    frames, excluded = {}, {"uncached": [], "illiquid": [], "bad_data": []}
    for ticker in tickers:
        df = rbr._with_context(rbr.load_cached(ticker))
        if df is None:
            excluded["uncached"].append((ticker, "not in backtest cache"))
            continue
        reason = liquidity_reason(df)
        if reason is not None:
            excluded["illiquid"].append((ticker, reason))
            continue
        issues = data_quality_issues(df, ticker)
        if issues:
            excluded["bad_data"].append((ticker, "; ".join(issues)))
            continue
        frames[ticker] = df
    if verbose:
        print(f"loaded {len(frames)}/{len(tickers)} cached tickers "
              f"({len(excluded['uncached'])} uncached, "
              f"{len(excluded['illiquid'])} illiquid, "
              f"{len(excluded['bad_data'])} bad data)", flush=True)
    return frames, excluded


def sweep(frames, date_from, date_to, *, horizons, gates, scale_out,
          strategies, want_strategies=True, want_confluence=True, workers=None):
    """Every trade both populations open in the window, as flat dicts.

    Prints one flushed line per ticker-horizon-population as each ticker
    lands, with elapsed seconds -- this is a multi-hour-shaped sweep and a
    silent process is indistinguishable from a stalled one.
    """
    import os
    import time
    from concurrent.futures import ProcessPoolExecutor, as_completed

    tasks = [
        (t, df, list(horizons), date_from, date_to, gates, scale_out,
         want_strategies, want_confluence, list(strategies))
        for t, df in frames.items()
    ]
    n_workers = max(1, int(workers)) if workers else max(1, (os.cpu_count() or 2) - 1)
    total_units = len(tasks) * len(horizons) * (int(want_strategies) + int(want_confluence))
    print(f"sweep: {len(tasks)} tickers x {len(horizons)} horizons "
          f"x {(int(want_strategies) + int(want_confluence))} population(s) "
          f"= {total_units} units, {n_workers} worker(s)", flush=True)

    rows: list[dict] = []
    t0 = time.time()
    done_units = 0
    done_tickers = 0

    def _report(ticker, per_unit):
        nonlocal done_units, done_tickers
        done_tickers += 1
        for hk, population, n in per_unit:
            done_units += 1
            print(f"[{done_units}/{total_units}] {ticker} {hk} {population} "
                  f"trades={n} ({time.time() - t0:.0f}s elapsed, "
                  f"ticker {done_tickers}/{len(tasks)})", flush=True)

    if n_workers <= 1 or len(tasks) <= 1:
        for task in tasks:
            ticker, r, per_unit = _worker(task)
            rows.extend(r)
            _report(ticker, per_unit)
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            futures = [pool.submit(_worker, task) for task in tasks]
            for fut in as_completed(futures):
                ticker, r, per_unit = fut.result()
                rows.extend(r)
                _report(ticker, per_unit)

    print(f"sweep done: {len(rows)} trades in {time.time() - t0:.0f}s", flush=True)
    return rows


def _table(title, trades) -> list[str]:
    """The bucket table for one population. Every bucket is printed even at
    n=0 -- the shape of the answer is the point."""
    rows = bucket_trades(trades)
    prof = density_profile(trades)
    out = [f"== {title} (n={len(trades)}) =="]
    if prof["n_days"]:
        out.append(f"   days={prof['n_days']}  trades/day: min={prof['min']} "
                   f"median={prof['median']:g} mean={prof['mean']:.1f} "
                   f"max={prof['max']}  "
                   f"days per bucket: " + " ".join(
                       f"{k}={v}" for k, v in prof["days_per_bucket"].items()))
    out.append(f"{'Bucket':8s} {'Range':>8s} {'N':>6s} {'Share':>7s} "
               f"{'Win%':>6s} {'ExpR':>8s} {'TotalR':>10s}")
    if not rows:
        out.append("  (no trades)")
        return out
    ranges = {name: (lo, hi) for name, lo, hi in DENSITY_BUCKETS}
    for r in rows:
        lo, hi = ranges[r["bucket"]]
        rng = f"{lo}" if lo == hi else (f"{lo}+" if hi >= 10_000 else f"{lo}-{hi}")
        wr = f"{r['win_rate']:.1f}" if r["win_rate"] is not None else "n/a"
        er = f"{r['expectancy_r']:+.3f}" if r["expectancy_r"] is not None else "n/a"
        out.append(f"{r['bucket']:8s} {rng:>8s} {r['n']:6d} "
                   f"{r['share_of_trades'] * 100:6.1f}% {wr:>6s} {er:>8s} "
                   f"{r['total_r']:+10.2f}")
    return out


def build_report(trades) -> tuple[list[str], dict]:
    """The three tables the plan asks for: everything pooled, then the
    confluence population on its own, then the rest.

    The split matters: confluence is the population the hypothesis is about
    (and the only negative one in the book), so pooling it with the validated
    strategies would dilute exactly the signal being looked for.
    """
    confluence = [t for t in trades if t.get("source") == CONFLUENCE_SOURCE]
    others = [t for t in trades if t.get("source") != CONFLUENCE_SOURCE]
    lines: list[str] = []
    payload = {}
    for title, pop, key in (
        ("ALL TRADES POOLED", trades, "all"),
        ("CONFLUENCE SCAN ONLY", confluence, "confluence"),
        ("NAMED STRATEGIES ONLY", others, "strategies"),
    ):
        lines.extend(_table(title, pop))
        lines.append("")
        payload[key] = {"n_trades": len(pop), "buckets": bucket_trades(pop),
                        "density_profile": density_profile(pop),
                        "per_day": per_day_rows(pop)}
    return lines, payload


def spy_returns(date_from, date_to) -> dict:
    """{date: close-to-close % change} for the benchmark over the window.

    Attached to the per-day rows so the "busy days are simply trending days
    where every setup works" reading -- Task 4's most likely artefact, which
    would make density a proxy for regime and the finding a restatement of the
    regime filter -- can actually be checked instead of speculated about.
    """
    rbr = _plumbing()
    df = rbr._market_frame()
    if df is None:
        return {}
    closes = df["Close"]
    pct = closes.pct_change() * 100.0
    out = {}
    for ts, val in pct.items():
        day = str(ts.date() if hasattr(ts, "date") else ts)[:10]
        if date_from and day < date_from:
            continue
        if date_to and day > date_to:
            continue
        if val == val:                      # skip NaN (first bar)
            out[day] = float(val)
    return out


def main():
    import argparse
    import json

    rbr = _plumbing()
    from swingbot.core.backtesting.backtest import ALL_STRATEGIES
    from swingbot.core.backtesting.backtest_scenarios import CONFLUENCE_GATES
    from swingbot.core.market.strategy_types import HORIZONS

    ap = argparse.ArgumentParser(
        description="Measure expectancy by entry-day trade density (plan v51).")
    ap.add_argument("--train", action="store_true",
                    help="2020-01-01..2023-12-31 (the only window this plan may read)")
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--universe", default=None,
                    help="named universe instead of the watchlist")
    ap.add_argument("--limit", type=int, default=None,
                    help="first N tickers only -- smoke runs, never the reported answer")
    ap.add_argument("--horizons", default=None,
                    help="comma-separated subset, e.g. 2w,4w (default: all ten)")
    ap.add_argument("--workers", type=int, default=None, help="0/1 = sequential")
    ap.add_argument("--no-strategies", dest="want_strategies", action="store_false",
                    help="confluence population only")
    ap.add_argument("--no-confluence", dest="want_confluence", action="store_false",
                    help="named-strategy population only")
    ap.add_argument("--no-scale-out", dest="scale_out", action="store_false",
                    help="single-leg v2 exits instead of the deployed scale-out")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--dump-trades", dest="dump_trades", default=None,
                    help="write every raw trade record here (provenance; kept "
                         "out of the committed summary, which would otherwise "
                         "be a multi-MB file in a repo that warns about them)")
    args = ap.parse_args()

    if args.train:
        date_from, date_to, label = *rbr.TRAIN, "TRAIN"
    elif args.date_from and args.date_to:
        date_from, date_to, label = args.date_from, args.date_to, "CUSTOM"
    else:
        ap.error("need --train or --from/--to")

    if label != "TRAIN":
        print("WARNING: this plan is pre-registered on TRAIN only. The 2024-25 "
              "window is tainted for any selection decision, and 'is there a "
              "density effect worth building on' is exactly a selection "
              "decision.", flush=True)

    horizons = ([h.strip() for h in args.horizons.split(",")]
                if args.horizons else list(HORIZONS))
    unknown = [h for h in horizons if h not in HORIZONS]
    if unknown:
        ap.error(f"unknown horizon(s): {unknown}; known: {list(HORIZONS)}")

    tickers = rbr._tickers_for_run(args.universe)
    if args.limit:
        tickers = tickers[:args.limit]
        print(f"SMOKE RUN: first {len(tickers)} ticker(s) only -- not a reportable "
              f"answer", flush=True)

    frames, excluded = load_frames(tickers)
    if not frames:
        raise SystemExit("no usable frames -- run scripts/data/fetch_backtest_data.py first")

    strategies = list(ALL_STRATEGIES)
    trades = sweep(frames, date_from, date_to, horizons=horizons,
                   gates=CONFLUENCE_GATES, scale_out=args.scale_out,
                   strategies=strategies, want_strategies=args.want_strategies,
                   want_confluence=args.want_confluence, workers=args.workers)

    lines, payload = build_report(trades)

    # Stamp the benchmark's own move onto every day, in every population, so
    # the regime-artefact reading is checkable from the saved artefact alone
    # and never needs a second sweep.
    spy = spy_returns(date_from, date_to)
    for key in ("all", "confluence", "strategies"):
        for row in payload[key]["per_day"]:
            row["spy_ret_pct"] = spy.get(row["date"])
    header = [
        f"== {label} {date_from} .. {date_to} | entry-day trade density ==",
        "density = trades opened on the same calendar date across the whole",
        "universe, including itself. A PROXY for alert count -- not every alert",
        "becomes a trade.",
        f"buckets: " + ", ".join(
            f"{n}={lo}" if lo == hi else (f"{n}={lo}+" if hi >= 10_000 else f"{n}={lo}-{hi}")
            for n, lo, hi in DENSITY_BUCKETS),
        f"exits: v2 + {'scale-out' if args.scale_out else 'single-leg'}; "
        f"frictions on; {len(frames)} tickers x {len(horizons)} horizons",
        "",
    ]
    report = "\n".join(header + lines)
    print("\n" + report)

    if args.json_out:
        payload["meta"] = {
            "plan": "v51-alert-density-expectancy",
            "window": {"label": label, "from": date_from, "to": date_to},
            "definition": ("trades opened on the same calendar date across the "
                           "whole universe, including itself; a proxy for alert "
                           "count, not an alert count"),
            "opened_at": "signal bar date (both populations)",
            "buckets": [list(b) for b in DENSITY_BUCKETS],
            "exit_model": "v2",
            "scale_out": bool(args.scale_out),
            "frictions": True,
            "tickers": sorted(frames),
            "n_tickers": len(frames),
            "horizons": horizons,
            "strategies": strategies if args.want_strategies else [],
            "confluence_gates": dict(CONFLUENCE_GATES),
            "excluded": {k: [list(x) for x in v] for k, v in excluded.items()},
            "smoke_run": bool(args.limit),
        }
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\nSaved {args.json_out}")

    if args.dump_trades:
        with open(args.dump_trades, "w", encoding="utf-8") as f:
            for t in trades:
                f.write(json.dumps(t) + "\n")
        print(f"Saved {args.dump_trades} ({len(trades)} raw trade records)")


if __name__ == "__main__":
    main()
