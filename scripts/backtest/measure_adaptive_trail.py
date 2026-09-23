"""v92 Hypothesis 1 -- R-adaptive chandelier trail. TRAIN grid.

Run: python scripts/backtest/measure_adaptive_trail.py [n_tickers]

Purpose-built instrument, same shape as measure_avwap_confluence.py: toggles
config attributes directly and calls the simulator in-process, because
run_backtest_range.py's --json output is pooled per-strategy stats, not the
per-ticker per-trade rows acceptance_harvest's cluster bootstrap needs.

Baseline = ADAPTIVE_RUNNER_TRAIL_ENABLED off. Component = on, at each grid
cell. Grid: TIGHTEN_TRIGGER_R x {1.5, 2.0, 2.5}, TIGHTEN_ATR_MULT x
{1.5, 1.75, 2.0} (9 cells). exit_model=v2, scale_out=True throughout --
Hypothesis 1 lives entirely in that path.

PROGRESS: 10 passes (1 baseline + 9 grid cells) x ~77 tickers x 10 horizons x
11 strategies is very likely past the 15-minute mark
(docs/claude/working-conventions.md), so progress is doubly surfaced: a
flushed per-ticker print inside every pass (labelled with which pass), and a
plain-text percent-complete file rewritten (not appended) after every ticker
unit across all passes combined -- see PROGRESS_PATH below. Whoever runs this
script (the backtest-runner subagent) reads that file's last line to answer
"how far along" and deletes it on completion; this script never deletes it
itself.
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
TRIGGER_GRID = (1.5, 2.0, 2.5)
MULT_GRID = (1.5, 1.75, 2.0)

#: Percent-complete log for this run (OS temp dir -- outside the repo, so
#: Task 7 Step 4's `git add` of two named files never picks it up). Rewritten
#: after every ticker unit across all 10 passes; last line read is always
#: current. Not deleted by this script -- the runner (backtest-runner
#: subagent / controller) deletes it once the run finishes.
PROGRESS_PATH = os.path.join(tempfile.gettempdir(), "v92-adaptive-trail-progress.log")


def _write_progress(done, total):
    try:
        with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
            f.write(f"{done}/{total} units ({done / total * 100:.0f}%)\n")
    except OSError:
        pass


def _arm_trades(flag_on, trigger, mult, tickers, pass_label, counter, total):
    config.ADAPTIVE_RUNNER_TRAIL_ENABLED = flag_on
    config.TIGHTEN_TRIGGER_R = trigger
    config.TIGHTEN_ATR_MULT = mult
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

    total_units = 10 * len(tickers)   # 1 baseline + 9 grid cells, each len(tickers)
    counter = [0]                     # mutable running count, shared across all passes
    print(f"Progress file: {PROGRESS_PATH}", flush=True)

    print(f"Baseline (flag off), {len(tickers)} tickers...", flush=True)
    baseline = _arm_trades(False, 2.0, 1.75, tickers, "baseline", counter, total_units)
    print(f"  {len(baseline)} closed trades")

    mde = mde_expectancy_r(baseline, target_n=len(baseline))
    print(f"Stage 0 MDE (ExpR, target_n={len(baseline)}): {mde:+.4f}R" if mde else "Stage 0 MDE: n/a")

    print("\n" + "=" * 72)
    print(f"{'trigger_r':>10s} {'tighten_mult':>13s} {'n':>6s} {'dExpR':>9s} "
          f"{'lo95':>9s} {'expect':>7s} {'wr_floor':>9s} {'volume':>7s}")
    for trigger in TRIGGER_GRID:
        for mult in MULT_GRID:
            pass_label = f"trigger={trigger:.2f} mult={mult:.2f}"
            component = _arm_trades(True, trigger, mult, tickers, pass_label, counter, total_units)
            result = evaluate_harvest(baseline, component, stage="walkforward",
                                     structurally_immune_to_wr=True)
            eg = result.clause("expectancy_gain")
            wf = result.clause("win_rate_floor")
            vol = result.clause("volume")
            print(f"{trigger:10.2f} {mult:13.2f} {len(component):6d} "
                  f"{eg.value:+9.4f} {eg.detail.split('[')[1].split(',')[0]:>9s} "
                  f"{eg.verdict:>7s} {wf.verdict:>9s} {vol.verdict:>7s}")


if __name__ == "__main__":
    main()
