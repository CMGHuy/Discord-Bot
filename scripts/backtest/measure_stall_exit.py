"""v92 Hypothesis 2 -- MAE/time stall-exit. TRAIN comparison (no grid --
stall_exit_day is journal-derived, not tuned).

Purpose-built instrument, same shape as measure_adaptive_trail.py: toggles
config attributes directly and calls the simulator in-process, because
run_backtest_range.py's --json output is pooled per-strategy stats, not the
per-ticker per-trade rows acceptance_harvest's cluster bootstrap needs.

Baseline = STALL_EXIT_ENABLED off. Component = on. Unlike Hypothesis 1, there
is no grid here -- stall_exit_day resolves from the journal's
optimal_time_stop_days, not a tuned constant -- so this is a single
flag-off-vs-flag-on comparison (2 passes instead of Task 7's 10).
exit_model=v2, scale_out=True throughout -- the stall-exit resolver only
applies in that path.

PROGRESS: 2 passes (baseline + component) x ~77 tickers x 10 horizons x 11
strategies is likely past the 15-minute mark
(docs/claude/working-conventions.md), so progress is doubly surfaced: a
flushed per-ticker print inside every pass (labelled with which pass), and a
plain-text percent-complete file rewritten (not appended) after every ticker
unit across both passes combined -- see PROGRESS_PATH below. Whoever runs
this script (the backtest-runner subagent) reads that file's last line to
answer "how far along" and deletes it on completion; this script never
deletes it itself.

Run: python scripts/backtest/measure_stall_exit.py [n_tickers]
"""
import os
import sys
import tempfile
import warnings

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts", "data"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "backtest"))

from fetch_backtest_data import load_cached
from run_backtest_range import _tickers_for_run, window_trades, ALL_STRATEGIES
from swingbot import config
from swingbot.core.backtesting.backtest import run_backtest
from swingbot.core.backtesting.acceptance import arm_trade_from_backtest
from swingbot.core.backtesting.acceptance_harvest import mde_expectancy_r, evaluate_harvest
from swingbot.core.market.strategy_types import HORIZONS

TRAIN_FROM, TRAIN_TO = "2020-01-01", "2023-12-31"

#: Percent-complete log for this run (OS temp dir -- outside the repo, so
#: Task 14 Step 4's `git add` of two named files never picks it up). Rewritten
#: after every ticker unit across both passes; last line read is always
#: current. Not deleted by this script -- the runner (backtest-runner
#: subagent / controller) deletes it once the run finishes.
PROGRESS_PATH = os.path.join(tempfile.gettempdir(), "v92-stall-exit-progress.log")


def _write_progress(done, total):
    try:
        with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
            f.write(f"{done}/{total} units ({done / total * 100:.0f}%)\n")
    except OSError:
        pass


def _arm_trades(flag_on, tickers, pass_label, counter, total):
    config.STALL_EXIT_ENABLED = flag_on
    out = []
    for ti, ticker in enumerate(tickers, 1):
        print(f"    [{pass_label}] [{ti}/{len(tickers)}] {ticker}", flush=True)
        counter[0] += 1
        _write_progress(counter[0], total)
        df = load_cached(ticker)
        if df is None:
            continue
        for hk in HORIZONS:
            for strat in ALL_STRATEGIES:
                try:
                    s = run_backtest(ticker, df, strat, hk, one_at_a_time=True,
                                      exit_model="v2", scale_out=True,
                                      tp2_mode="levels", frictions=True)
                except Exception:
                    continue
                for tr in window_trades(s, TRAIN_FROM, TRAIN_TO):
                    out.append(arm_trade_from_backtest(tr, ticker=ticker, strategy=strat,
                                                        horizon_key=hk))
    return out


def main():
    tickers = _tickers_for_run(None)
    if len(sys.argv) > 1:
        tickers = tickers[:int(sys.argv[1])]

    total_units = 2 * len(tickers)   # baseline + component, each len(tickers)
    counter = [0]                     # mutable running count, shared across both passes
    print(f"Progress file: {PROGRESS_PATH}", flush=True)

    print(f"Baseline (flag off), {len(tickers)} tickers...", flush=True)
    baseline = _arm_trades(False, tickers, "baseline", counter, total_units)
    print(f"  {len(baseline)} closed trades")
    mde = mde_expectancy_r(baseline, target_n=len(baseline))
    print(f"Stage 0 MDE (ExpR, target_n={len(baseline)}): {mde:+.4f}R" if mde else "Stage 0 MDE: n/a")

    print(f"Component (flag on), {len(tickers)} tickers...", flush=True)
    component = _arm_trades(True, tickers, "component", counter, total_units)
    print(f"  {len(component)} closed trades")

    result = evaluate_harvest(baseline, component, stage="walkforward",
                             structurally_immune_to_wr=False)
    for c in result.clauses:
        print(f"  {c.name}: {c.verdict} -- {c.detail}")
    print(f"OVERALL: {result.verdict}")


if __name__ == "__main__":
    main()
