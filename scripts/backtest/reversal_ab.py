#!/usr/bin/env python3
"""A/B the reversal rule over one window, on ONE shared signal set.

    python scripts/backtest/reversal_ab.py --train
    python scripts/backtest/reversal_ab.py --from 2020-01-01 --to 2023-12-31 --json out.json

Signals are collected ONCE and replayed three ways, so the arms differ only in
the position rule -- not in the data, the window, the frictions, or the exit
model:

    A  current        several positions per ticker allowed (today's behaviour)
    B  one-per-ticker at most one position per ticker, opposite side blocked
    C  reversals      as B, but an opposite signal cuts the position short

C is the live feature. B isolates how much of any difference is the duplicate
guard alone rather than the flipping.

Fidelity gaps versus live, both of which make C flip MORE than production
would (see portfolio_replay's docstring): no confidence-margin guard, because
BacktestTrade carries no score; and guards in days rather than hours, because
signals are dated, not timestamped.
"""
import argparse
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
# Windows redirects stdout as cp1252; a single non-ASCII char in a header
# would otherwise kill a run AFTER the expensive collection step.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.backtest_wf import collect_portfolio_signals, portfolio_replay  # noqa: E402

TRAIN = ("2020-01-01", "2023-12-31")
VALIDATION = ("2024-01-01", "2025-12-31")


def _arm(name, signals, **kw):
    out = portfolio_replay(signals, **kw)
    rs = out["r_multiples_taken"]
    return {
        "arm": name,
        "taken": out["trades_taken"],
        "skipped": out["trades_skipped"],
        "final_multiple": round(out["final_multiple"], 4),
        "max_dd_pct": out["max_dd_pct"],
        "expectancy_r": round(sum(rs) / len(rs), 4) if rs else None,
        "trades_per_month": out["trades_per_month"],
        "reversals": out.get("reversals", 0),
        "reversals_r_delta": out.get("reversals_r_delta", 0.0),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--validation", action="store_true")
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--min-hold-days", type=float, default=1.0)
    ap.add_argument("--cooldown-days", type=float, default=2.0)
    ap.add_argument("--max-per-day", type=int, default=1)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--signals-cache",
                    help="reuse/save the collected signals; collection is the slow part")
    args = ap.parse_args()

    if args.train:
        start, end = TRAIN
    elif args.validation:
        start, end = VALIDATION
    elif args.date_from and args.date_to:
        start, end = args.date_from, args.date_to
    else:
        ap.error("need --train, --validation, or --from/--to")

    cache = Path(args.signals_cache) if args.signals_cache else None
    if cache and cache.exists():
        signals = json.loads(cache.read_text(encoding="utf-8"))
        print(f"Reusing {len(signals)} cached signals from {cache}", flush=True)
    else:
        print(f"Collecting signals {start} .. {end} (one pass, shared by all arms)", flush=True)
        signals = collect_portfolio_signals(start, end)
        if cache:
            cache.write_text(json.dumps(signals), encoding="utf-8")
    print(f"\n{len(signals)} signals collected\n", flush=True)
    if not signals:
        print("No signals -- is data/backtest_cache/ populated?")
        return 1

    arms = [
        _arm("A current", signals),
        _arm("B one-per-ticker", signals, one_per_ticker=True),
        _arm("C reversals", signals, reversals=True,
             rev_min_hold_days=args.min_hold_days,
             rev_cooldown_days=args.cooldown_days,
             rev_max_per_day=args.max_per_day),
    ]

    print(f"{'Arm':<18}{'Taken':>7}{'Skip':>7}{'ExpR':>9}{'FinalX':>9}"
          f"{'MaxDD%':>8}{'Trd/mo':>8}{'Flips':>7}{'FlipRd':>9}")
    for a in arms:
        er = f"{a['expectancy_r']:+.4f}" if a["expectancy_r"] is not None else "n/a"
        print(f"{a['arm']:<18}{a['taken']:>7}{a['skipped']:>7}{er:>9}"
              f"{a['final_multiple']:>9.4f}{a['max_dd_pct']:>8.1f}"
              f"{a['trades_per_month']:>8.1f}{a['reversals']:>7}"
              f"{a['reversals_r_delta']:>+9.2f}")

    base = arms[0]
    print("\nvs A (current):")
    for a in arms[1:]:
        d_exp = ((a["expectancy_r"] or 0) - (base["expectancy_r"] or 0))
        d_fin = a["final_multiple"] - base["final_multiple"]
        print(f"  {a['arm']:<18} expectancy {d_exp:+.4f}R   final multiple {d_fin:+.4f}"
              f"   maxDD {a['max_dd_pct'] - base['max_dd_pct']:+.1f}pp")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"window": [start, end], "n_signals": len(signals),
                        "guards": {"min_hold_days": args.min_hold_days,
                                   "cooldown_days": args.cooldown_days,
                                   "max_per_day": args.max_per_day},
                        "arms": arms}, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
