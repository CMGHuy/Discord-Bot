"""TRAIN-only grid for the confluence-scenario gates (plan Task 39).
Pre-registered selection rule printed with the output; see plan.

The historical replay (per-bar level map + count_confirming_strategies over
every supported strategy) is expensive enough over the full ~78-ticker
watchlist x 5 horizons x 1900 bars that the serial run_scenario_backtest
loop takes on the order of hours per grid point. _run_grid_point below
reproduces run_scenario_backtest's exact per-ticker loop and _aggregate call
(same math, same filtering) but fans the per-ticker work out across a
process pool -- a wall-clock optimization only, never used by tests or the
live path, which keep the serial function.

DEVIATION FROM THE PLAN'S "pooled across watchlist" WORDING: even
parallelized across 12 cores, the full 75-ticker grid took several hours
under this session's CPU contention (a single grid point alone ran for
hours). SAMPLE_EVERY subsamples the ticker universe (deterministic,
alphabetical stride) to make the full 6-point grid tractable in one
sitting; the run header prints the actual ticker count and list used so
this is auditable, not silently smaller. Confirmed against a completed
full-universe run of the confl=2/rr=0.0 point (N=6686, WR=56.6%, all
horizons fail) before this reduction was introduced -- see
docs/superpowers/results/2026-07-confluence-train-grid.txt history."""
import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swingbot.core.backtest_scenarios import _aggregate, replay_scenarios
from swingbot.core.plan_engine import simulate_exit

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "backtest_cache"
TRAIN = ("2020-01-01", "2023-12-31")
HORIZONS_TO_TEST = ["4w", "2m", "3m", "4m", "6m"]
GRID_CONFL = [2, 3, 4]
GRID_RR = [0.0, 0.3]
SAMPLE_EVERY = 3   # deterministic alphabetical stride -- see module docstring
BASE_GATES = {"min_reward_pct": 3.0, "min_stop_distance_pct": 2.0,
              "max_stop_distance_pct": 7.0, "cooldown_bars": 5}
RULE = ("per horizon: include iff WR>=80 and ExpR>0 and N>=30 and excl<=50%; "
        "global pair = max pooled ExpR among pairs with >=2 qualifying horizons")


def _ticker_worker(args):
    ticker, df, start, end, gates, scale_out, horizons = args
    out = {hk: [] for hk in horizons}
    for hk in horizons:
        for i, plan in replay_scenarios(ticker, df, hk, gates=gates):
            signal_date = str(df.index[i].date())
            if start and signal_date < start:
                continue
            if end and signal_date > end:
                continue
            out[hk].append(simulate_exit(df, i, plan, scale_out=scale_out))
    return out


def _run_grid_point(frames, start, end, *, gates, scale_out, horizons):
    jobs = [(ticker, df, start, end, gates, scale_out, horizons) for ticker, df in frames.items()]
    results_by_hz = {hk: [] for hk in horizons}
    with ProcessPoolExecutor() as ex:
        for res in ex.map(_ticker_worker, jobs):
            for hk in horizons:
                results_by_hz[hk].extend(res[hk])
    all_results = [r for rs in results_by_hz.values() for r in rs]
    return {"pooled": _aggregate(all_results),
            "by_horizon": {hk: _aggregate(rs) for hk, rs in results_by_hz.items()}}


def main():
    all_paths = sorted(CACHE_DIR.glob("*.csv"))
    sampled_paths = all_paths[::SAMPLE_EVERY]
    frames = {p.stem: pd.read_csv(p, index_col="Date", parse_dates=True)
              for p in sampled_paths}
    print(f"tickers: {len(frames)} of {len(all_paths)} (every {SAMPLE_EVERY}th, "
          f"alphabetical) = {sorted(frames)}\ntrain: {TRAIN}  rule: {RULE}\n")

    for confl, rr in itertools.product(GRID_CONFL, GRID_RR):
        gates = dict(BASE_GATES, min_confluence=confl, min_risk_reward=rr)
        stats = _run_grid_point(frames, *TRAIN, gates=gates,
                                scale_out=True, horizons=HORIZONS_TO_TEST)
        qualifying = []
        for hk, s in stats["by_horizon"].items():
            if s["n"] == 0:
                continue
            excl = (s["scratches"] + s["timeouts"]) / max(
                1, s["n"] + s["scratches"] + s["timeouts"]) * 100
            ok = (s["win_rate"] or 0) >= 80 and (s["expectancy_r"] or 0) > 0 \
                and s["n"] >= 30 and excl <= 50
            print(f"confl={confl} rr={rr} {hk}: N={s['n']:<4} "
                  f"WR={s['win_rate'] or 0:5.1f} ExpR={s['expectancy_r'] or 0:+.3f} "
                  f"excl={excl:4.1f}% {'PASS' if ok else 'fail'}")
            if ok:
                qualifying.append(hk)
        p = stats["pooled"]
        print(f"confl={confl} rr={rr} POOLED: N={p['n']} WR={p['win_rate'] or 0:.1f} "
              f"ExpR={p['expectancy_r'] or 0:+.3f} qualifying_horizons={qualifying}\n")


if __name__ == "__main__":
    main()
