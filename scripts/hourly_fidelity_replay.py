#!/usr/bin/env python3
"""Daily-vs-hourly exit fidelity (plan v8 V51 Step 4, and the harness V23 Step 1
will reuse).

Every backtest in this repo walks DAILY bars, and a daily bar cannot say which
of the stop and the target was touched first when it spans both. The exit walk
resolves that ambiguity by always checking the stop first ("conservative:
stop first, exactly as single-leg"), which is a choice, not a measurement.
This replays the SAME trades against hourly bars, where the ordering is mostly
observable, and reports how often the two disagree.

That disagreement rate is the error bar V52 must carry on every number.

**Scope, deliberately.** `market_data/hourly/` starts 2023-08-25, so its overlap
with TRAIN (..2023-12-31) is ~612 bars/ticker -- about 87 trading days. Only
short horizons can resolve inside that, so the default is 2w/4w; a 3m trade
cannot complete and would be scored as a timeout by construction. Everything
after 2023-12-31 is the VALIDATION window V24's one-shot budget owns, so this
script does not go there by default and V23 must make that call deliberately.

Usage:
  python scripts/hourly_fidelity_replay.py [--from D] [--to D]
      [--horizons 2w,4w] [--strategies "RSI,MACD"] [--max-tickers N]
      [--json out.json]
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.backtest import ALL_STRATEGIES, run_backtest          # noqa: E402
from swingbot.core.plan_engine import (                                   # noqa: E402
    PlanStatus, TradePlanV2, exit_params_for, simulate_exit,
)
from swingbot.core.strategy_types import BREAKEVEN_TRIGGER_FRACTION, HORIZONS  # noqa: E402

DAILY = ROOT / "data" / "backtest_cache"
HOURLY = ROOT / "market_data" / "hourly"
# Enough daily history before the window for any indicator to warm up, without
# replaying 25 years per ticker just to score four months of trades.
WARMUP_BARS = 400


def _load_daily(t):
    p = DAILY / f"{t}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p, index_col=0, parse_dates=True)
    return df if {"Open", "High", "Low", "Close"} <= set(df.columns) else None


def _load_hourly(t):
    p = HOURLY / f"{t}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p, index_col=0, parse_dates=True)
    if not {"Open", "High", "Low", "Close"} <= set(df.columns):
        return None
    return df.sort_index()


def _trail_scale(daily, hourly_w, entry_date, plan_trail):
    """Scale the trail multiple so the hourly replay trails at the same PRICE
    distance the daily walk would.

    Without this the comparison is confounded and the confound is large: the
    walk trails by `trail_atr_mult x ATR(14)` computed on whatever df it is
    given, and ATR(14) on hourly bars is a fraction of ATR(14) on daily bars.
    A raw hourly replay therefore trails several times tighter and stops the
    runner out far sooner -- which is a DIFFERENT EXIT POLICY, not a finer view
    of the same one. Scaling by (daily ATR / hourly ATR) at entry holds the
    policy fixed so what is left is genuine intrabar path fidelity.
    """
    from swingbot.core.indicators import atr as atr_ind
    try:
        d_atr = float(atr_ind(daily, 14).loc[:entry_date].iloc[-1])
        h_atr = float(atr_ind(hourly_w, 14).iloc[:64].median())
        if d_atr > 0 and h_atr > 0:
            return plan_trail * (d_atr / h_atr)
    except Exception:
        pass
    return plan_trail


def _plan_from(trade, strategy, horizon_key):
    """Rebuild the minimal plan the exit walk needs from a recorded daily
    trade. Entry/stop/TP1 are copied verbatim -- this compares EXITS, so the
    entry decision must be held identical across both resolutions."""
    ep = exit_params_for(strategy)
    return TradePlanV2(
        plan_id="fid", ticker=trade.ticker if hasattr(trade, "ticker") else "T",
        created_at=trade.entry_date, source="strategy", strategy=strategy,
        horizon_key=horizon_key, direction=trade.direction, entry_type="market",
        trigger_price=trade.entry, entry_price=trade.entry, expiry_bars=1,
        stop_loss=trade.stop_loss, tp1=trade.take_profit, tp1_fraction=0.5,
        tp2=None, breakeven_trigger_fraction=BREAKEVEN_TRIGGER_FRACTION,
        trail_atr_mult=ep["trail_atr_mult"], quality_score=0,
        quality_breakdown=[], tier="C", badge="WEAK", badge_stats={},
        status=PlanStatus.ACTIVE, status_history=[],
    )


def _ambiguous(daily, trade):
    """Did any daily bar in the trade's life span BOTH barriers? That is the
    exact condition under which the daily walk had to guess."""
    seg = daily.loc[trade.entry_date:trade.exit_date]
    if seg.empty:
        return False
    lo, hi = seg["Low"].to_numpy(), seg["High"].to_numpy()
    if trade.direction == "bullish":
        return bool(((lo <= trade.stop_loss) & (hi >= trade.take_profit)).any())
    return bool(((hi >= trade.stop_loss) & (lo <= trade.take_profit)).any())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="lo", default="2023-08-25")
    ap.add_argument("--to", dest="hi", default="2023-12-31")
    ap.add_argument("--horizons", default="2w,4w")
    ap.add_argument("--strategies", default=None)
    ap.add_argument("--max-tickers", type=int, default=None)
    ap.add_argument("--raw-trail", action="store_true",
                    help="Do NOT rescale the trail to the daily ATR. Measures "
                         "'manage this position on hourly bars with an hourly-ATR "
                         "trail', which is a different exit policy -- not the "
                         "intrabar-fidelity question V51 Step 4 asks.")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    horizons = [h.strip() for h in args.horizons.split(",") if h.strip()]
    strategies = ([s.strip() for s in args.strategies.split(",")]
                  if args.strategies else list(ALL_STRATEGIES))
    tickers = sorted(p.stem for p in HOURLY.glob("*.csv")
                     if (DAILY / f"{p.stem}.csv").exists())
    if args.max_tickers:
        tickers = tickers[:args.max_tickers]

    print(f"{len(tickers)} tickers with both feeds | window {args.lo}..{args.hi} "
          f"| horizons {horizons} | {len(strategies)} strategies", flush=True)

    rows, agree, total, amb_total, amb_disagree = [], 0, 0, 0, 0
    flips = {}
    for n, t in enumerate(tickers, 1):
        daily, hourly = _load_daily(t), _load_hourly(t)
        if daily is None or hourly is None:
            print(f"[{n}/{len(tickers)}] {t}: SKIP (missing feed)", flush=True)
            continue
        hourly_w = hourly[(hourly.index >= args.lo) & (hourly.index <= f"{args.hi} 23:59")]
        if len(hourly_w) < 50:
            print(f"[{n}/{len(tickers)}] {t}: SKIP (only {len(hourly_w)} hourly bars)",
                  flush=True)
            continue
        # Warm-up slice: enough history for indicators, not 25 years of it.
        d_idx = daily.index
        start_i = max(0, int(d_idx.searchsorted(pd.Timestamp(args.lo))) - WARMUP_BARS)
        daily_w = daily.iloc[start_i:d_idx.searchsorted(pd.Timestamp(args.hi)) + 1]

        hour_dates = pd.Index([ts.date() for ts in hourly_w.index])
        t_total = t_agree = 0
        for strategy in strategies:
            for hk in horizons:
                try:
                    res = run_backtest(t, daily_w, strategy, hk,
                                       exit_model="v2", scale_out=True, tp2_mode="none")
                except Exception:
                    continue
                for tr in res.trades:
                    if not (args.lo <= tr.entry_date <= args.hi):
                        continue
                    # Entry is the daily close, i.e. the LAST hourly bar of that date.
                    d = pd.Timestamp(tr.entry_date).date()
                    hits = (hour_dates == d).nonzero()[0]
                    if len(hits) == 0:
                        continue
                    sig = int(hits[-1])
                    plan = _plan_from(tr, strategy, hk)
                    if not args.raw_trail:
                        plan.trail_atr_mult = _trail_scale(
                            daily_w, hourly_w, tr.entry_date, plan.trail_atr_mult)
                    hbars = HORIZONS[hk]["max_holding_days"] * 7   # 7 hourly bars/day
                    try:
                        hres = simulate_exit(hourly_w, sig, plan, scale_out=True,
                                             max_holding_days=hbars)
                    except Exception:
                        continue
                    if hres.outcome in ("no_trade", "not_triggered"):
                        continue
                    same = (hres.outcome == tr.outcome)
                    amb = _ambiguous(daily_w, tr)
                    total += 1
                    t_total += 1
                    agree += same
                    t_agree += same
                    amb_total += amb
                    amb_disagree += (amb and not same)
                    if not same:
                        flips[f"{tr.outcome}->{hres.outcome}"] = \
                            flips.get(f"{tr.outcome}->{hres.outcome}", 0) + 1
                    rows.append({"ticker": t, "strategy": strategy, "horizon": hk,
                                 "entry_date": tr.entry_date,
                                 "daily_outcome": tr.outcome, "hourly_outcome": hres.outcome,
                                 "daily_r": tr.r_multiple, "hourly_r": hres.r_total,
                                 "ambiguous_bar": amb})
        pct = (t_agree / t_total * 100) if t_total else float("nan")
        print(f"[{n}/{len(tickers)}] {t:<8} trades={t_total:<5} agree={pct:5.1f}%",
              flush=True)

    print("\n" + "=" * 70)
    print(f"DAILY vs HOURLY exit fidelity | {total} replayed trades")
    print("=" * 70)
    if not total:
        print("no trades in window -- nothing to compare")
        return
    print(f"  outcome agreement      {agree}/{total} = {agree/total*100:.1f}%")
    print(f"  DISAGREEMENT RATE      {(total-agree)/total*100:.1f}%   "
          "<- the error bar V52 must carry")
    if amb_total:
        print(f"\n  daily bars spanning BOTH barriers: {amb_total} trades "
              f"({amb_total/total*100:.1f}%)")
        print(f"    of those, hourly disagreed: {amb_disagree}/{amb_total} = "
              f"{amb_disagree/amb_total*100:.1f}%")
    else:
        print("\n  no trade had a daily bar spanning both barriers")
    if flips:
        print("\n  flips (daily -> hourly):")
        for k, v in sorted(flips.items(), key=lambda kv: -kv[1]):
            print(f"    {k:<28} {v}")
    if rows:
        dr = [r["daily_r"] for r in rows]
        hr = [r["hourly_r"] for r in rows]
        print(f"\n  mean R  daily {sum(dr)/len(dr):+.3f}   hourly {sum(hr)/len(hr):+.3f}   "
              f"delta {(sum(hr)-sum(dr))/len(dr):+.3f}R")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"window": [args.lo, args.hi], "horizons": horizons,
             "n_trades": total, "agreement": agree / total,
             "ambiguous": amb_total, "ambiguous_disagreed": amb_disagree,
             "flips": flips, "rows": rows}, indent=2))
        print(f"\nWrote {args.json}")


if __name__ == "__main__":
    main()
