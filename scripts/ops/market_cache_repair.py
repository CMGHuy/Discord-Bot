"""Audit and repair the on-disk market_data cache against fresh data (v116 follow-up).

Why it exists: `data_refresh._merge_save` never overwrites bars already on disk, and a warm refresh only
fetches bars newer than the last cached one. A single bad full fetch (around 2026-08-05) therefore left
another instrument's older history under 16 daily and 5 hourly files for two months, with correct recent
bars appended on top. See docs/claude/known-traps.md ("The market_data cache never self-heals").

Run INSIDE the bot container (the provider path uses a process pool, so it must be a real file, not
`python -c` or stdin):

    docker compose cp scripts/ops/market_cache_repair.py bot:/tmp/market_cache_repair.py
    docker compose exec -T -w /app -e PYTHONPATH=/app bot python /tmp/market_cache_repair.py plan
    docker compose exec -T -w /app -e PYTHONPATH=/app bot python /tmp/market_cache_repair.py apply

`plan` (the default) only reads and prints a verdict per symbol/timeframe. `apply` replaces only files
whose fresh full-history frame (a) disagrees with the cache (median ratio off by >2%, >10% of the last 500
bars off by >1%, or the cache starts >30 days before the fresh frame) and (b) agrees with Alpaca's 2y
daily frame to within 0.5%. Each replaced file is first MOVED to market_data/_quarantine/<UTC stamp>/<tf>/
and restored if the cold refetch fails; the persistent coverage state is updated through data_refresh.
Daily and hourly only: weekly/monthly differ from yfinance by a small uniform adjustment offset.
"""
import json
import logging
import os
import shutil
import statistics
import sys
import time

SKIP = {"GC", "GC_F", "SI", "SI_F", "XAUUSD", "XAGUSD"}   # spot/futures names are handled elsewhere
MEDIAN_TOLERANCE = 0.02       # whole-history median close ratio
RECENT_BARS = 500
RECENT_DEV = 0.01             # a recent bar "deviates" beyond 1%
RECENT_DEV_FRACTION = 0.10    # flagged when more than 10% of the recent bars deviate
EARLY_DAYS = 30               # cache starting this much before the fresh frame = another instrument's history
ALPACA_TOLERANCE = 0.005
MIN_OVERLAP = 20


def close_ratios(cache, fresh):
    """(fresh Close / cache Close) per overlapping bar, oldest first, with both indexes made tz-naive."""
    def naive(frame):
        out = frame.copy()
        if getattr(out.index, "tz", None) is not None:
            out.index = out.index.tz_localize(None)
        return out
    c, f = naive(cache), naive(fresh)
    overlap = c.index.intersection(f.index)
    return c, f, [float(f.loc[i, "Close"]) / float(c.loc[i, "Close"])
                  for i in overlap if float(c.loc[i, "Close"]) > 0]


def summarise(cache, fresh, timeframe):
    """Numbers the verdict is based on, or None when the overlap is too short to judge."""
    import pandas as pd
    c, f, ratios = close_ratios(cache, fresh)
    if len(ratios) < MIN_OVERLAP:
        return None
    recent = ratios[-RECENT_BARS:]
    early = (timeframe in ("daily", "weekly")
             and c.index[0] < f.index[0] - pd.Timedelta(days=EARLY_DAYS))
    return {"median": statistics.median(ratios),
            "recent_dev_frac": sum(1 for v in recent if abs(v - 1) > RECENT_DEV) / len(recent),
            "early": early, "cache_first": str(c.index[0])[:10], "fresh_first": str(f.index[0])[:10],
            "cache_rows": len(c), "fresh_rows": len(f)}


def is_flagged(stats):
    return (abs(stats["median"] - 1) > MEDIAN_TOLERANCE
            or stats["recent_dev_frac"] > RECENT_DEV_FRACTION or stats["early"])


def public_info(stats):
    return {"median": round(stats["median"], 3), "recent_dev_frac": round(stats["recent_dev_frac"], 2),
            "cache_first": stats["cache_first"], "fresh_first": stats["fresh_first"],
            "cache_rows": stats["cache_rows"], "fresh_rows": stats["fresh_rows"]}


def alpaca_verdict(fresh, live):
    """('ok'|'no-alpaca'|'disagrees', median ratio or None) for a fresh daily frame vs the Alpaca 2y frame."""
    if live is None or live.attrs.get("source") != "alpaca":
        return "no-alpaca", None
    _, _, ratios = close_ratios(fresh, live)
    if len(ratios) < MIN_OVERLAP:
        return "disagrees", None
    median = statistics.median(ratios)
    return ("ok" if abs(median - 1) <= ALPACA_TOLERANCE else "disagrees"), median


def judge(sym, tf, data_store, data):
    cache = data_store.load_normalized(sym, tf)
    fresh = data_store.fetch_interval_data(sym, tf)
    if cache is None or fresh is None or len(fresh) == 0:
        return "SKIP-NODATA", {}
    stats = summarise(cache, fresh, tf)
    if stats is None:
        return "SKIP-NOOVERLAP", {}
    info = public_info(stats)
    if not is_flagged(stats):
        return "OK", info
    if tf != "daily":
        return "REPLACE", info
    status, median = alpaca_verdict(fresh, data.get_daily_data_batch([sym], "2y").get(sym))
    info["fresh_vs_alpaca"] = None if median is None else round(median, 4)
    if status == "no-alpaca":
        return "FLAGGED-UNVERIFIED", info
    return ("REPLACE" if status == "ok" else "FLAGGED-FRESH-DISAGREES-WITH-ALPACA"), info


def candidate_symbols(base):
    names = set()
    for tf in ("daily", "hourly"):
        names |= {f[:-4] for f in os.listdir(os.path.join(base, tf)) if f.endswith(".csv")}
    return sorted(names - SKIP)


def build_plan(base, data_store, data):
    plan, counts = [], {}
    for sym in candidate_symbols(base):
        for tf in ("daily", "hourly"):
            if not os.path.exists(os.path.join(base, tf, sym + ".csv")):
                continue
            try:
                verdict, info = judge(sym, tf, data_store, data)
            except Exception as exc:                      # one bad symbol never aborts the audit
                verdict, info = "ERR", {"error": type(exc).__name__ + ":" + str(exc)[:80]}
            counts[verdict] = counts.get(verdict, 0) + 1
            if verdict != "OK":
                plan.append((sym, tf, verdict, info))
    return plan, counts


def replace_one(sym, tf, base, qdir, data_refresh, state):
    """Quarantine the cache file, cold-refetch it, and put the old file back if that fails."""
    src = os.path.join(base, tf, sym + ".csv")
    dst_dir = os.path.join(qdir, tf)
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, sym + ".csv")
    shutil.move(src, dst)                                  # force=True merges, so the old file must go first
    result = data_refresh.refresh_symbol(sym, tf, base_dir=base, force=True, state=state)
    if result.get("status") in ("full", "incremental") and os.path.exists(src):
        data_refresh._record(state, sym, tf, result, base)
        return (sym, tf, result["status"], result["rows"])
    shutil.move(dst, src)
    return (sym, tf, "RESTORED-OLD(" + str(result.get("status")) + ")", None)


def apply_plan(plan, base, data_refresh, data_store):
    qdir = os.path.join(base, "_quarantine", time.strftime("%Y%m%d-%H%M%S", time.gmtime()))
    state = data_refresh.load_state()
    done = [replace_one(sym, tf, base, qdir, data_refresh, state)
            for sym, tf, verdict, _ in plan if verdict == "REPLACE"]
    data_refresh.save_state(state)
    data_store.clear_normalized_frame_cache()
    return done, qdir


def main(argv):
    logging.disable(logging.CRITICAL)
    mode = argv[1] if len(argv) > 1 else "plan"
    from swingbot.core.marketdata import data, data_refresh, data_store
    base = data_store.DATA_DIR
    plan, counts = build_plan(base, data_store, data)
    print("MODE", mode, "| verdict counts:", counts)
    for sym, tf, verdict, info in plan:
        print("  %-6s %-6s %-36s %s" % (sym, tf, verdict, json.dumps(info)))
    if mode != "apply":
        return 0
    done, qdir = apply_plan(plan, base, data_refresh, data_store)
    print("APPLIED:", json.dumps(done))
    print("quarantine dir:", qdir)
    return 0


if __name__ == "__main__":      # guard: the fetch path starts a process pool
    sys.exit(main(sys.argv))
