#!/usr/bin/env python3
"""v176 live book: each live give-back exit against its flag-off counterfactual exit.

A closed plan counts when its runner leg carries stop_source == "giveback".
The flag-off stop at that exit is approximated from daily bars as the tighter
of the runner floor and the chandelier on the leg's giveback_extreme with the
ATR(14) of the bar before the exit day; from the exit day on, each bar checks
the stop (gap-aware fill), then TP2, then takes the close into E and
ratchets the chandelier. No exit by the last bar: "open" at the last close.
No conclusion below 30 give-back exits (spec § Live book); changing the 5%
or the flag is the partner's call.

Run where the live book is, read-only:
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" \
        < scripts/reports/giveback_live_counterfactual.py
or locally after /replicate-prod-db: python scripts/reports/giveback_live_counterfactual.py [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.market.indicators import atr  # noqa: E402
from swingbot.core.planning.exit_sim import chandelier_stop, runner_floor, tighter_stop  # noqa: E402
from swingbot.core.backtesting.instrument.fills import gap_stop_fill  # noqa: E402  (pure; same formula as plan_manager.py:39)

MIN_N = 30
NY = "America/New_York"


def _runner_leg(plan: dict) -> dict | None:
    legs = plan.get("legs_realized") or []
    leg = legs[-1] if legs else None
    return leg if leg and leg.get("stop_source") == "giveback" else None


def giveback_plans(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("status") == "CLOSED" and _runner_leg(r)]


def _session_date(stamp) -> str:
    ts = pd.Timestamp(stamp)
    return str((ts.tz_convert(NY) if ts.tzinfo is not None else ts).date())


def _trail(extreme, atr_value, plan) -> float | None:
    if atr_value is None or not math.isfinite(float(atr_value)):
        return None
    return chandelier_stop(extreme, float(atr_value), float(plan["trail_atr_mult"]), plan["direction"])


def _hit(bar, stop, tp2, is_bull):
    """(fill, kind) when the bar reaches the stop, else TP2, else None."""
    if (bar.Low <= stop) if is_bull else (bar.High >= stop):
        return gap_stop_fill(float(bar.Open), stop, "bullish" if is_bull else "bearish"), "stop"
    if tp2 is not None and ((bar.High >= tp2) if is_bull else (bar.Low <= tp2)):
        return float(tp2), "tp2"
    return None


def _walk(bars, atr_series, start, stop, extreme, plan, floor):
    is_bull = plan["direction"] == "bullish"
    for i in range(start, len(bars)):
        bar = bars.iloc[i]
        hit = _hit(bar, stop, plan.get("tp2"), is_bull)
        if hit:
            kind = "tp2" if hit[1] == "tp2" else ("floor" if stop == floor else "trail")
            return hit[0], str(bars.index[i].date()), kind
        extreme = max(extreme, float(bar.Close)) if is_bull else min(extreme, float(bar.Close))
        stop = tighter_stop(stop, _trail(extreme, atr_series.iloc[i], plan), is_bull)
    return float(bars["Close"].iloc[-1]), str(bars.index[-1].date()), "open"


def counterfactual_exit(plan: dict, bars) -> dict:
    leg = _runner_leg(plan)
    is_bull = plan["direction"] == "bullish"
    entry, sign = float(plan["entry_price"]), (1 if is_bull else -1)
    risk = abs(entry - float(plan["stop_loss"]))
    floor = runner_floor(entry, float(plan["tp1"]))
    day = _session_date(leg["closed_at"])
    dates = [str(ts.date()) for ts in bars.index]
    start = next((i for i, d in enumerate(dates) if d >= day), None)
    out = {"plan_id": plan["plan_id"], "ticker": plan["ticker"], "direction": plan["direction"],
           "exit_date": day, "live_exit": float(leg["exit_price"]), "live_r": float(leg["r"]),
           "giveback_stop": leg.get("giveback_stop")}
    if start is None:
        return {**out, "cf_start_stop": None, "cf_exit": None, "cf_date": None,
                "cf_reason": "no_bars", "cf_r": None, "delta_r": None}
    atr_series = atr(bars, 14)
    extreme = float(leg["giveback_extreme"])
    stop0 = tighter_stop(floor, _trail(extreme, atr_series.iloc[max(start - 1, 0)], plan), is_bull)
    cf_exit, cf_date, reason = _walk(bars, atr_series, start, stop0, extreme, plan, floor)
    cf_r = (cf_exit - entry) * sign / risk
    return {**out, "cf_start_stop": stop0, "cf_exit": cf_exit, "cf_date": cf_date,
            "cf_reason": reason, "cf_r": cf_r, "delta_r": out["live_r"] - cf_r}


def _records() -> list[dict]:
    from swingbot.core.planning.plan_store import PlanStore
    return PlanStore().records()


def _bars(ticker):
    from swingbot.core.marketdata.data import get_daily_data
    return get_daily_data(ticker, period="5y")


def _summary(results) -> str:
    decided = [r["delta_r"] for r in results if r["delta_r"] is not None]
    if len(decided) < MIN_N:
        return f"n={len(decided)}: no conclusion below {MIN_N} give-back exits"
    s = pd.Series(decided)
    return (f"n={len(decided)}: mean delta_r {s.mean():+.3f}R, median {s.median():+.3f}R "
            "(descriptive; the 5% and the flag are the partner's call)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    results = [counterfactual_exit(p, _bars(p["ticker"])) for p in giveback_plans(_records())]
    for r in results:
        print(f"{r['ticker']:<6} {str(r['plan_id'])[:8]} exit {r['exit_date']} live {r['live_r']:+.2f}R "
              f"cf {r['cf_reason']} {r['cf_r'] if r['cf_r'] is None else round(r['cf_r'], 2)}R")
    print(_summary(results))
    if args.json:
        args.json.write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
