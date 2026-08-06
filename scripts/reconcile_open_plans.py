#!/usr/bin/env python3
"""Catch-up reconciliation for open plans -- replay the bars a poll gap missed.

WHY THIS EXISTS. Both live close paths compare a single SPOT price against the
level and never read bars:

    performance.TradeLog.close_if_live_price_hit()  -> get_current_price()
    plan_manager.PlanManager.poll() -> _price_fn    -> get_current_price()

So a TP/SL touch that happens between two polls -- or while the bot is down --
is invisible and never recovered. Proven on 2026-08-03: the bot was OOM-killed
for 4h20m and 23 of 28 open plans touched TP1 during the gap. None was booked,
and the next poll sees the NEXT price, not the high that was missed.

WHAT THIS DOES. For every open plan it fetches the bars covering the gap and
feeds them through `PlanManager._step` / `._on_event` -- the manager's OWN state
machine and trade-log hooks, not a reimplementation. Whatever the live bot would
have done had it been polling, this does.

INTRABAR ORDERING is the conservative convention the backtest walk already uses
(`plan_engine._single_leg_exit_walk` checks the stop before the target): within
each bar the ADVERSE extreme is presented first, then the favourable one, then
the close. A bar that spans both the stop and the target therefore resolves as
the stop -- pessimistic, never flattering.

Dry-run by default. `--apply` is the only thing that writes.

    python scripts/reconcile_open_plans.py                       # dry run
    python scripts/reconcile_open_plans.py --since 2026-08-03T16:50:59Z --apply

Run it with the bot STOPPED. The manager writes plans.json and trades.json, and
a concurrent live poll would race this.
"""
import argparse
import datetime as dt
import sys
import warnings
from collections import Counter
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd


def _bars(ticker: str, since: dt.datetime, interval: str):
    """Intraday bars covering the gap, tz-aware UTC, oldest first."""
    import yfinance as yf
    lookback = max(2, (dt.datetime.now(dt.timezone.utc) - since).days + 2)
    df = yf.download(ticker, period=f"{lookback}d", interval=interval,
                     progress=False, auto_adjust=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    idx = df.index
    if idx.tz is None:
        df.index = idx.tz_localize("UTC")
    else:
        df.index = idx.tz_convert("UTC")
    return df[df.index >= since]


def _price_sequence(row, is_bull: bool):
    """Adverse extreme first, then favourable, then close -- the same
    pessimistic ordering the backtest exit walk uses."""
    lo, hi, close = float(row["Low"]), float(row["High"]), float(row["Close"])
    return [lo, hi, close] if is_bull else [hi, lo, close]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None,
                    help="ISO8601 UTC start of the gap; default = the plan's "
                         "own last transition time, per plan")
    ap.add_argument("--interval", default="5m",
                    help="yfinance bar interval for the replay (default 5m)")
    ap.add_argument("--apply", action="store_true",
                    help="actually write plans.json / trades.json")
    args = ap.parse_args()

    from swingbot.core.plan_manager import PlanManager, _bars_since, _live_atr
    from swingbot.core.plan_store import PlanStore
    from swingbot.core.performance import TradeLog

    since_arg = None
    if args.since:
        since_arg = dt.datetime.fromisoformat(args.since.replace("Z", "+00:00"))

    store = PlanStore()
    if not args.apply:
        # `_step_active`/`_step_partial` call store.update(), which calls
        # _save() unconditionally -- so a "dry run" would still rewrite
        # plans.json. Neuter the persistence, not the state machine: the
        # in-memory plan objects still mutate, so the replay is identical,
        # it just never reaches disk.
        store.update = lambda plan: None
        store.set_extra = lambda *a, **k: False
    mgr = PlanManager(store, lambda t: 0.0, atr_fn=_live_atr,
                      bar_count_fn=_bars_since,
                      trade_log=TradeLog() if args.apply else None)

    plans = store.open_plans()
    print(f"{len(plans)} open plan(s) | interval={args.interval} | "
          f"{'APPLY -- WILL WRITE' if args.apply else 'DRY RUN -- no writes'}\n",
          flush=True)

    tally = Counter()
    for plan in plans:
        since = since_arg
        if since is None:
            hist = getattr(plan, "status_history", None) or []
            stamp = hist[-1].get("at") if hist else getattr(plan, "created_at", None)
            if not stamp:
                print(f"  {plan.ticker:<6} {plan.plan_id[:8]}  SKIP (no timestamp)")
                continue
            since = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if since.tzinfo is None:
                since = since.replace(tzinfo=dt.timezone.utc)

        df = _bars(plan.ticker, since, args.interval)
        if df is None or df.empty:
            print(f"  {plan.ticker:<6} {plan.plan_id[:8]}  no bars since {since:%Y-%m-%d %H:%M}")
            tally["no_bars"] += 1
            continue

        is_bull = plan.direction == "bullish"
        fired = []
        for _, row in df.iterrows():
            for price in _price_sequence(row, is_bull):
                try:
                    evs = mgr._step(plan, price)
                except Exception as exc:
                    print(f"  {plan.ticker:<6} step failed: {exc}")
                    evs = []
                for ev in evs:
                    if args.apply:
                        mgr._on_event(plan, ev)
                    fired.append(ev)
                if evs and str(getattr(plan, "status", "")).endswith("CLOSED"):
                    break
            if str(getattr(plan, "status", "")).endswith("CLOSED"):
                break

        if not fired:
            tally["unchanged"] += 1
            continue
        for ev in fired:
            tally[ev.transition] += 1
        summary = " -> ".join(
            f"{ev.transition}@{ev.detail.get('exit_price', ev.detail.get('exit_price') or ev.detail.get('working_stop') or '')}"
            if ev.detail.get("exit_price") or ev.detail.get("working_stop")
            else ev.transition for ev in fired)
        print(f"  {plan.ticker:<6} {plan.direction:<8} {plan.plan_id[:8]}  "
              f"bars={len(df):<4} {summary}", flush=True)

    print("\nSummary:", dict(tally))
    if not args.apply:
        print("\nDRY RUN -- nothing written. Re-run with --apply (bot stopped) "
              "to commit these transitions.")
    return 0


if __name__ == "__main__":
    # V29: label every close this replay books as `close_source="reconcile"`.
    # A reconciled close resolves a bar spanning both levels AS THE STOP, so
    # its loss is the full gap move rather than a managed stop-out -- pooling
    # the two into one expectancy makes an outage look like strategy decay.
    # Measured on the live book: -1.041R reconciled (n=32) vs -0.342R
    # live-polled (n=30) over the same days. Wrapping the entry point rather
    # than the loop is deliberate: everything this script writes is a
    # reconciled close, and that stays true if the internals move.
    from swingbot.core.performance import close_attribution

    with close_attribution("reconcile"):
        sys.exit(main())
