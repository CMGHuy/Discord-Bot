"""Counterfactual half of the funnel autopsy (see diagnose_funnel.py).

diagnose_funnel.py established that build_scenarios() rejects ~99.9% of
directions on min_reward / min_stop_distance. This asks the follow-up
question those numbers cannot answer: is that because the market has no
qualifying structure right now, or because build_scenarios() only ever
looks at supports[0] / resistances[0] -- the single NEAREST clustered
level on each side (levels.py:701,716) -- and never walks further out?

For each ticker/horizon it reports:
  A. the nearest-level pair (what the scanner actually uses today), and
  B. the best pair found by WALKING both level lists, which is what
     levels.target_candidates() + plan_engine.select_structural_target
     already do downstream for targets.
Read-only.
"""
import sys
from collections import Counter

from swingbot import config
from swingbot.core.market import levels, trendlines
from swingbot.core.market.strategy import HORIZONS, MIN_BARS
from swingbot.core.marketdata import universe, watchlist as watchlist_mod
from swingbot.core.scanning import engine


def ok(dist1, stop_dist, min_reward, min_stop, max_stop, min_rr):
    rr = (dist1 / stop_dist) if stop_dist > 0 else 0.0
    return (dist1 >= min_reward and stop_dist >= min_stop
            and (max_stop <= 0 or stop_dist <= max_stop)
            and (min_rr <= 0 or rr >= min_rr))


def main():
    tickers = watchlist_mod.load_watchlist()
    frames = engine._crawl_latest_data(tickers)
    print(f"crawl: {len(frames)}/{len(tickers)} frames", flush=True)

    n_combo = 0
    nearest_pass = 0
    walked_pass = 0
    target_only_pass = 0
    level_counts = Counter()
    unlocked = []

    for ticker in tickers:
        df = frames.get(ticker)
        if df is None or df.empty:
            continue
        if universe.liquidity_reason(df) is not None or universe.data_quality_issues(df, ticker):
            continue
        cp = float(df["Close"].iloc[-1])
        tl = trendlines.custom_scanner_levels(df, cp)
        for hk, h in HORIZONS.items():
            if len(df) < MIN_BARS[hk]:
                continue
            n_combo += 1
            cands = levels.collect_candidate_levels(df, h, cp, trendline_candidates=tl)
            sups, ress = levels.build_level_map(df, h, cp, candidates=cands)
            if not (sups and ress):
                continue
            level_counts[(min(len(sups), 6), min(len(ress), 6))] += 1
            mr = max(config.MIN_REWARD_PCT, h.get("sr_target_min_pct", config.MIN_REWARD_PCT) * 0.15)
            ms = max(config.MAX_STOP_LOSS_PCT, h.get("max_risk_pct", config.MAX_STOP_LOSS_PCT))
            mn, rr_min = config.MIN_STOP_DISTANCE_PCT, config.MIN_RISK_REWARD_RATIO

            ups = [(r.price - cp) / cp * 100 for r in ress]
            dns = [(cp - s.price) / cp * 100 for s in sups]

            near = ok(ups[0], dns[0], mr, mn, ms, rr_min) or ok(dns[0], ups[0], mr, mn, ms, rr_min)
            if near:
                nearest_pass += 1

            # variant (b): stop stays the NEAREST level (unchanged invalidation
            # point); only the TARGET walks outward -- the same rule
            # plan_engine.select_structural_target already applies downstream.
            tgt_only = (any(ok(u, dns[0], mr, mn, ms, rr_min) for u in ups)
                        or any(ok(d, ups[0], mr, mn, ms, rr_min) for d in dns))
            if tgt_only:
                target_only_pass += 1

            # variant (c): any (target level, stop level) pair on the real lists
            best = None
            for i, u in enumerate(ups):
                for j, d in enumerate(dns):
                    if ok(u, d, mr, mn, ms, rr_min):
                        best = ("bullish", i, j, u, d, u / d)
                        break
                if best:
                    break
            if not best:
                for j, d in enumerate(dns):
                    for i, u in enumerate(ups):
                        if ok(d, u, mr, mn, ms, rr_min):
                            best = ("bearish", j, i, d, u, d / u)
                            break
                    if best:
                        break
            if best:
                walked_pass += 1
                if not near and len(unlocked) < 30:
                    unlocked.append((ticker, hk, best, len(ress), len(sups)))
        print(f"  {ticker}: n={n_combo} near={nearest_pass} tgt={target_only_pass} both={walked_pass}", flush=True)

    print("\n============ NEAREST-LEVEL vs WALKED-LEVEL ============", flush=True)
    print(f"ticker/horizon combos            : {n_combo}", flush=True)
    print(f"qualify using NEAREST level only : {nearest_pass}   <- what the scanner does today", flush=True)
    print(f"qualify walking TARGET only      : {target_only_pass}   <- stop stays nearest level", flush=True)
    print(f"qualify walking BOTH lists       : {walked_pass}", flush=True)
    print("\n-- (n_supports, n_resistances) distribution, capped at 6 --", flush=True)
    for k, v in sorted(level_counts.items(), key=lambda x: -x[1])[:12]:
        print(f"  supports={k[0]} resistances={k[1]}  : {v}", flush=True)
    print("\n-- combos unlocked ONLY by walking (target_idx/stop_idx are list positions) --", flush=True)
    for t, hk, b, nr, ns in unlocked:
        print(f"  {t:6s} {hk:3s} {b[0]:8s} target_idx={b[1]} stop_idx={b[2]} "
              f"target={b[3]:6.2f}% stop={b[4]:6.2f}% rr={b[5]:5.2f}  (levels: {nr}R/{ns}S)", flush=True)


if __name__ == "__main__":
    sys.exit(main())
