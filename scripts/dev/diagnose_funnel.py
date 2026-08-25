"""Read-only funnel autopsy for the scan's FIRST stage.

The live "Signal funnel" log line collapses the biggest drop into one
bucket -- "had no qualifying entry point (no real support/resistance, or
didn't meet min reward/stop/risk-reward requirements)" -- because
levels.build_scenarios() never *builds* a scenario that fails one of the
four hard constraints, so stats["failed_counts"]["min_reward"] and friends
can only ever count scenarios that already passed (scanning/engine.py:1462).
That makes the one funnel stage that eliminates ~99.9% of combos completely
opaque.

This script re-runs exactly that stage (same crawl, same level map, same
effective_min_reward / effective_max_stop derivation as
scanning/engine.py) and tallies, per ticker/horizon/direction, WHICH
constraint failed -- plus a sensitivity table showing how many extra
scenarios each individual threshold relaxation would admit.

Read-only: fetches data and computes: never writes state, never posts,
never touches trade_log.
"""
import argparse
import sys
from collections import Counter

from swingbot import config
from swingbot.core.market import levels, trendlines
from swingbot.core.market.strategy import HORIZONS, MIN_BARS
from swingbot.core.marketdata import watchlist as watchlist_mod
from swingbot.core.scanning import engine
from swingbot.core.marketdata import universe

CONSTRAINTS = ("min_reward", "min_stop_distance", "max_stop_distance", "min_risk_reward")


def constraint_check(dist1, stop_dist, rr, min_reward, min_stop, max_stop, min_rr):
    return {
        "min_reward": dist1 >= min_reward,
        "min_stop_distance": stop_dist >= min_stop,
        "max_stop_distance": max_stop <= 0 or stop_dist <= max_stop,
        "min_risk_reward": min_rr <= 0 or rr >= min_rr,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only first N tickers")
    args = ap.parse_args()

    tickers = watchlist_mod.load_watchlist()
    if args.limit:
        tickers = tickers[:args.limit]
    print(f"watchlist: {len(tickers)} ticker(s)", flush=True)
    print(f"config: MIN_REWARD_PCT={config.MIN_REWARD_PCT} MIN_STOP_DISTANCE_PCT={config.MIN_STOP_DISTANCE_PCT} "
          f"MAX_STOP_LOSS_PCT={config.MAX_STOP_LOSS_PCT} MIN_RISK_REWARD_RATIO={config.MIN_RISK_REWARD_RATIO}",
          flush=True)

    frames = engine._crawl_latest_data(tickers)
    print(f"crawl: {len(frames)} frame(s) resolved", flush=True)

    checked = 0
    skipped_ticker = 0
    no_levels = 0            # one or both sides had no genuine level at all
    both_levels = 0
    passed = 0
    fail_exact = Counter()   # frozenset of failing constraint names -> count
    fail_any = Counter()     # constraint name -> count of directions it failed
    sole_blocker = Counter() # constraint that was the ONLY failure
    relax = Counter()        # how many extra directions each single relaxation admits
    samples = []

    for ticker in tickers:
        df = frames.get(ticker)
        if df is None or df.empty:
            skipped_ticker += 1
            continue
        if universe.liquidity_reason(df) is not None or universe.data_quality_issues(df, ticker):
            skipped_ticker += 1
            continue
        current_price = float(df["Close"].iloc[-1])
        tl = trendlines.custom_scanner_levels(df, current_price)
        for hk, h in HORIZONS.items():
            if len(df) < MIN_BARS[hk]:
                continue
            checked += 1
            cands = levels.collect_candidate_levels(df, h, current_price, trendline_candidates=tl)
            supports, resistances = levels.build_level_map(df, h, current_price, candidates=cands)
            if not (supports and resistances):
                no_levels += 1
                continue
            both_levels += 1
            min_reward = max(config.MIN_REWARD_PCT, h.get("sr_target_min_pct", config.MIN_REWARD_PCT) * 0.15)
            max_stop = max(config.MAX_STOP_LOSS_PCT, h.get("max_risk_pct", config.MAX_STOP_LOSS_PCT))
            min_stop = config.MIN_STOP_DISTANCE_PCT
            min_rr = config.MIN_RISK_REWARD_RATIO

            up = (resistances[0].price - current_price) / current_price * 100
            dn = (current_price - supports[0].price) / current_price * 100
            for direction, dist1, stop_dist in (("bullish", up, dn), ("bearish", dn, up)):
                rr = (dist1 / stop_dist) if stop_dist > 0 else 0.0
                c = constraint_check(dist1, stop_dist, rr, min_reward, min_stop, max_stop, min_rr)
                failing = frozenset(k for k, ok in c.items() if not ok)
                if not failing:
                    passed += 1
                    continue
                fail_exact[failing] += 1
                for k in failing:
                    fail_any[k] += 1
                if len(failing) == 1:
                    sole_blocker[next(iter(failing))] += 1
                if len(samples) < 25:
                    samples.append((ticker, hk, direction, dist1, stop_dist, rr, sorted(failing)))

                # single-lever sensitivity: would relaxing ONE threshold alone admit it?
                for name, alt in (
                    ("min_risk_reward -> 1.2", constraint_check(dist1, stop_dist, rr, min_reward, min_stop, max_stop, 1.2)),
                    ("min_risk_reward -> 1.0", constraint_check(dist1, stop_dist, rr, min_reward, min_stop, max_stop, 1.0)),
                    ("min_stop_distance -> 1.0", constraint_check(dist1, stop_dist, rr, min_reward, 1.0, max_stop, min_rr)),
                    ("min_stop_distance -> 0.5", constraint_check(dist1, stop_dist, rr, min_reward, 0.5, max_stop, min_rr)),
                    ("max_stop_distance -> 12", constraint_check(dist1, stop_dist, rr, min_reward, min_stop, max(12.0, max_stop), min_rr)),
                    ("min_reward -> 1.0", constraint_check(dist1, stop_dist, rr, 1.0, min_stop, max_stop, min_rr)),
                ):
                    if all(alt.values()):
                        relax[name] += 1
        print(f"  {ticker}: done (checked={checked}, passed={passed})", flush=True)

    print("\n================ FUNNEL AUTOPSY ================", flush=True)
    print(f"ticker/horizon combos checked : {checked}", flush=True)
    print(f"  tickers skipped (data/liq)  : {skipped_ticker}", flush=True)
    print(f"  missing support or resistance: {no_levels}", flush=True)
    print(f"  had levels on BOTH sides     : {both_levels}", flush=True)
    print(f"directions evaluated           : {both_levels * 2}", flush=True)
    print(f"  PASSED all 4 constraints     : {passed}", flush=True)
    print("\n-- failed at least this constraint (directions) --", flush=True)
    for k, n in fail_any.most_common():
        print(f"  {k:22s} {n:6d}", flush=True)
    print("\n-- SOLE blocker (relaxing just this one would admit the trade) --", flush=True)
    for k, n in sole_blocker.most_common():
        print(f"  {k:22s} {n:6d}", flush=True)
    print("\n-- exact failing combinations --", flush=True)
    for combo, n in fail_exact.most_common(10):
        print(f"  {n:6d}  {'+'.join(sorted(combo))}", flush=True)
    print("\n-- single-lever sensitivity: extra directions admitted --", flush=True)
    for k, n in relax.most_common():
        print(f"  {k:28s} +{n}", flush=True)
    print("\n-- sample rejections --", flush=True)
    for s in samples:
        print(f"  {s[0]:6s} {s[1]:3s} {s[2]:8s} target={s[3]:6.2f}% stop={s[4]:6.2f}% rr={s[5]:5.2f}  fails={s[6]}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
