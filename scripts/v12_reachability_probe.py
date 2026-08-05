"""V12 instrumented scan: why does the V11 reachability screen never fire?

Live telemetry over 143 clean scans (1,730 verdicts, floor enforced) returned
`wall=0, clear=1730, no_levels=0` -- survival 1.0000. Two readings fit that,
and a reject *count* cannot separate them (the same trap V12 Step 1 called
out, one level up):

  1. genuinely non-binding -- the nearest clustered level ahead really is
     >= MIN_TARGET_PCT away for every scenario, and the screen is correct to
     pass everything;
  2. effectively a no-op -- a near level exists in the price structure but
     never reaches `target_is_reachable`, because clustering merged it into
     the entry or `build_scenarios` only emits scenarios whose target already
     clears the floor.

So this dumps the *distance*, not the verdict: for every scenario it records
how far the nearest level ahead sits, in percent, against the floor the screen
tests. If reading 1 is right the distribution has real mass just above the
floor and simply never crosses it. If reading 2 is right there is a visible
gap -- nothing anywhere near the floor, because near levels were removed
before the screen ran.

Replicates `engine.py:900-946` exactly (`build_level_map` -> `atr_floor_pct`
-> `effective_min_reward`/`effective_max_stop` -> `build_scenarios`), so the
level map and scenarios are the ones the live screen judges.

**Caveat, stated up front:** this runs on the cached *daily* bars, whereas the
live scanner builds its map from the intraday frame it just fetched. Structure
at these horizons is daily-driven so the shape should hold, but an exact
tie to a specific live scan row is not claimed.
"""
import argparse
import json
import os
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_backtest_data import load_cached                       # noqa: E402
from swingbot import config                                       # noqa: E402
from swingbot.core import levels                                  # noqa: E402
from swingbot.core.plan_engine import (target_floor_price,        # noqa: E402
                                       target_is_reachable)
from swingbot.core.strategy import MIN_BARS                       # noqa: E402
from swingbot.core.strategy_types import HORIZONS                 # noqa: E402


def probe_ticker(ticker, df, horizons):
    rows = []
    current_price = float(df["Close"].iloc[-1])
    bars = len(df)
    for hk in horizons:
        h = HORIZONS[hk]
        if bars < MIN_BARS[hk]:
            continue
        supports, resistances = levels.build_level_map(df, h, current_price)
        floor_pct = levels.atr_floor_pct(df, current_price, h)
        eff_min_reward = max(config.MIN_REWARD_PCT,
                             h.get("sr_target_min_pct", config.MIN_REWARD_PCT) * 0.15)
        eff_max_stop = max(config.MAX_STOP_LOSS_PCT,
                           h.get("max_risk_pct", config.MAX_STOP_LOSS_PCT))
        scenarios = levels.build_scenarios(
            current_price, supports, resistances, eff_min_reward,
            atr_floor=floor_pct,
            min_stop_distance_pct=config.MIN_STOP_DISTANCE_PCT,
            max_stop_distance_pct=eff_max_stop,
            min_risk_reward=config.MIN_RISK_REWARD_RATIO)

        sup_p = [lv.price for lv in supports]
        res_p = [lv.price for lv in resistances]
        for sc in scenarios:
            entry = float(sc.entry)
            reachable, reason = target_is_reachable(res_p, sup_p, sc.direction, entry)
            cands = res_p if sc.direction == "bullish" else sup_p
            ahead = [p for p in cands
                     if (p > entry if sc.direction == "bullish" else p < entry)]
            nearest = (min(ahead) if sc.direction == "bullish" else max(ahead)) if ahead else None
            floor_price = target_floor_price(entry, sc.direction)
            rows.append({
                "ticker": ticker, "horizon": hk, "direction": sc.direction,
                "entry": entry, "reason": reason, "reachable": bool(reachable),
                "n_levels_ahead": len(ahead),
                # the number this probe exists for
                "nearest_ahead_pct": (abs(nearest - entry) / entry * 100.0
                                      if nearest is not None else None),
                "floor_pct_required": abs(floor_price - entry) / entry * 100.0,
                "target_pct": abs(float(sc.take_profit) - entry) / entry * 100.0,
                "min_reward_required": eff_min_reward,
                # how close the entry sits to structure on the OTHER side --
                # if clustering swallowed a near level, this is where it went
                "nearest_behind_pct": _behind(entry, sup_p, res_p, sc.direction),
            })
    return rows


def _behind(entry, sup_p, res_p, direction):
    cands = sup_p if direction == "bullish" else res_p
    behind = [p for p in cands
              if (p < entry if direction == "bullish" else p > entry)]
    if not behind:
        return None
    nearest = max(behind) if direction == "bullish" else min(behind)
    return abs(nearest - entry) / entry * 100.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--horizons", default=None, help="comma-separated; default all")
    args = ap.parse_args()

    horizons = ([h.strip() for h in args.horizons.split(",")]
                if args.horizons else list(HORIZONS))
    wl_path = os.path.join(config.DATA_DIR, "watchlist.json")
    with open(wl_path, encoding="utf-8") as f:
        watchlist = json.load(f)
    tickers = sorted(watchlist)[:args.limit]

    print(f"V12 reachability probe | {len(tickers)} tickers x {len(horizons)} "
          f"horizons | MIN_TARGET_PCT={config.MIN_TARGET_PCT} "
          f"TARGET_FLOOR_ENABLED={config.TARGET_FLOOR_ENABLED}", flush=True)

    rows = []
    for i, t in enumerate(tickers, 1):
        df = load_cached(t)
        if df is None or df.empty:
            print(f"[{i}/{len(tickers)}] {t}: no cached data", flush=True)
            continue
        try:
            r = probe_ticker(t, df, horizons)
        except Exception as e:                                    # noqa: BLE001
            print(f"[{i}/{len(tickers)}] {t}: ERROR {e}", flush=True)
            continue
        rows.extend(r)
        print(f"[{i}/{len(tickers)}] {t}: +{len(r)} scenarios", flush=True)

    if not rows:
        print("\nNo scenarios produced -- nothing to conclude.", flush=True)
        return

    print(f"\n{'=' * 68}\nscenarios: {len(rows)}", flush=True)
    print("reasons:", dict(Counter(r["reason"] for r in rows)), flush=True)

    near = [r["nearest_ahead_pct"] for r in rows if r["nearest_ahead_pct"] is not None]
    floors = [r["floor_pct_required"] for r in rows]
    print(f"\nfloor required (%): min={min(floors):.3f} max={max(floors):.3f}", flush=True)

    if near:
        near_sorted = sorted(near)
        def pct(p):
            return near_sorted[min(len(near_sorted) - 1, int(len(near_sorted) * p))]
        print("\nnearest level AHEAD, distance from entry (%) -- the quantity "
              "the screen tests:", flush=True)
        print(f"  n={len(near)} min={near_sorted[0]:.3f} p05={pct(0.05):.3f} "
              f"p10={pct(0.10):.3f} p25={pct(0.25):.3f} median={statistics.median(near):.3f} "
              f"p75={pct(0.75):.3f} max={near_sorted[-1]:.3f}", flush=True)
        floor = config.MIN_TARGET_PCT
        below = [x for x in near if x < floor]
        print(f"  below the {floor}% floor: {len(below)} "
              f"({len(below) / len(near) * 100:.2f}%)  <-- these are the walls",
              flush=True)
        # The discriminating histogram: is there mass approaching the floor?
        print("\n  distribution near the floor:", flush=True)
        edges = [0, 0.5, 1.0, 1.5, 2.0, floor, 3.0, 4.0, 5.0, 10.0, 1e9]
        for lo, hi in zip(edges, edges[1:]):
            c = sum(1 for x in near if lo <= x < hi)
            bar = "#" * min(50, c * 50 // max(1, len(near)))
            hi_s = "inf" if hi > 1e8 else f"{hi}"
            print(f"    [{lo:>5}, {hi_s:>5}) {c:6d} {bar}", flush=True)

    behind = [r["nearest_behind_pct"] for r in rows if r["nearest_behind_pct"] is not None]
    if behind:
        print(f"\nnearest level BEHIND entry (%): n={len(behind)} "
              f"min={min(behind):.3f} median={statistics.median(behind):.3f}",
              flush=True)
    print(f"\nscenarios with NO level ahead: "
          f"{sum(1 for r in rows if r['n_levels_ahead'] == 0)}", flush=True)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, default=str)
        print(f"\nwrote {args.json_out}", flush=True)


if __name__ == "__main__":
    main()
