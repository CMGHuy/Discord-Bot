#!/usr/bin/env python3
"""v176: TRAIN-only paired measurement of the runner give-back (flag off vs on at 5%).

Frozen before TRAIN is read (spec § Measurement), v123's instrument:
  window     TRAIN 2020-01-01..2023-12-31 only. Every frame is cut at TRAIN's
             end, so no VALIDATION bar is run or read.
  data       the 75-ticker local backtest cache (training_data "yfinance")
  engines    StrategyEngine.iter_trades + replay_scenarios, all ten horizons
  exits      simulate_exit(scale_out=True), instrument v1
  frictions  net_r: SLIPPAGE_BPS on both fills + commission_r(), both arms;
             zero frictions are refused
  arms       entries from ONE flag-off pass; each re-simulated off, then on at 5%
  basis      close (the spec's rule, the primary reading) | high_low (the
             tick/close sensitivity, descriptive)

One look: refuses to overwrite <out-dir>/train-<basis>.json. Reported, not a
gate; it never changes RUNNER_GIVEBACK_ENABLED.
PROGRESS: a flushed line per ticker plus logs/measure_runner_giveback.<basis>.progress.

Run: python scripts/backtest/measure_runner_giveback.py --out-dir docs/superpowers/results/v176 --basis close
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import sys
from collections import Counter, defaultdict, namedtuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot import config  # noqa: E402
from swingbot.core.analytics.expectancy_attribution import net_r  # noqa: E402
from swingbot.core.backtesting.acceptance import (BOOTSTRAP_RESAMPLES,  # noqa: E402
                                                  bootstrap_delta, mde_paired)
from swingbot.core.backtesting.instrument import cli as instrument_cli  # noqa: E402
from swingbot.core.backtesting.instrument import contract  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402
from swingbot.core.planning import exit_sim  # noqa: E402
from swingbot.core.planning.plan_engine import simulate_exit  # noqa: E402

#: v136 rule 2: the window comes from the instrument contract, never a literal.
#: This measurement is frozen on instrument v1 (spec § Measurement); main()
#: refuses any other --instrument.
TRAIN = instrument_cli.window_for(contract.resolve("v1"), "train")
PCT = 5.0
DATA_SOURCE = "yfinance"
BASES = ("close", "high_low")
ARMS = ("off", "on")
CLOSED = ("win", "loss", "scratch")
SHAKEOUT_BARS = 10
POOLED_DESCRIPTIVE_CELLS = 8   # runner R, floor share, exit mix, capture, days, gaps, shake-outs, book
RESULTS = ROOT / "docs" / "superpowers" / "results" / "v176"
LOG_DIR = ROOT / "logs"
_Arm = namedtuple("_Arm", "ticker r")


@contextlib.contextmanager
def giveback(enabled: bool):
    """The give-back flag (at 5%) for one simulation; the previous values come back after."""
    saved = (config.RUNNER_GIVEBACK_ENABLED, config.RUNNER_GIVEBACK_PCT)
    config.RUNNER_GIVEBACK_ENABLED, config.RUNNER_GIVEBACK_PCT = enabled, PCT
    try:
        yield
    finally:
        config.RUNNER_GIVEBACK_ENABLED, config.RUNNER_GIVEBACK_PCT = saved


def _entries(ticker, df) -> list:
    """(source, horizon_key, signal_index, plan) for every TRAIN entry of the
    flag-OFF pass: the off arm decides the entry set for both arms."""
    from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
    from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    from swingbot.scan_params import ScanParams
    params, engine, out = ScanParams.from_config(), StrategyEngine(), []
    position = {str(ts.date()): i for i, ts in enumerate(df.index)}
    with giveback(False):
        for hk in ALL_HORIZONS:
            for strategy in engine.strategies:
                for date, plan, _result in engine.iter_trades(ticker, df, strategy, hk, TRAIN, params):
                    out.append(("strategy", hk, position[date], plan))
            for index, plan in replay_scenarios(ticker, df, hk, params=params):
                if str(df.index[index].date()) >= TRAIN[0]:
                    out.append(("scenario", hk, index, plan))
    return out


def _arm(df, index, plan, enabled) -> dict | None:
    with giveback(enabled):
        result = simulate_exit(df, index, copy.deepcopy(plan), scale_out=True)
    if result.outcome not in CLOSED or not result.legs:
        return None
    runner = result.outcome == "win" and len(result.legs) == 2
    return {"r_net": net_r(result.entry_price, plan.stop_loss, plan.direction, result.legs),
            "runner_r": float(result.legs[1]["r"]) if runner else None,
            "entry_index": int(result.entry_index), "entry_price": float(result.entry_price),
            "exit_index": int(result.exit_index),
            "exit_date": str(df.index[result.exit_index].date()),
            "exit_price": float(result.legs[-1]["exit_price"]),
            "reason": result.runner_outcome or result.outcome,
            "stop_source": result.runner_stop_source}


def _tp1_index(df, start, stop, plan) -> int:
    high, low = df["High"].values, df["Low"].values
    for j in range(start, stop + 1):
        if (high[j] >= plan.tp1) if plan.direction == "bullish" else (low[j] <= plan.tp1):
            return j
    return stop


def _best_close(closes, lo, hi, is_bull) -> float:
    window = closes[lo:max(hi, lo + 1)]
    return float(window.max() if is_bull else window.min())


def _giveback_extras(df, on, best_on, sign, risk, fraction) -> dict:
    """Shake-out and gap-through-level for an on-arm give-back exit."""
    if on["stop_source"] != "giveback":
        return {"shakeout": None, "gap_worse_r": None}
    j = on["exit_index"]
    later = df["Close"].values[j + 1:j + 1 + SHAKEOUT_BARS]
    gap = (float(df["Open"].values[j]) - on["exit_price"]) * sign / risk
    return {"shakeout": bool(any((float(c) - best_on) * sign > 0 for c in later)),
            "gap_worse_r": min(0.0, gap) * fraction}


def _runner_context(df, off, on, plan, risk) -> dict:
    """Fixed-window (OFF arm) MFE and best close, 5% of price in R, days from TP1."""
    is_bull, closes = plan.direction == "bullish", df["Close"].values
    sign = 1 if is_bull else -1
    tp1 = _tp1_index(df, off["entry_index"], off["exit_index"], plan)
    best_off = _best_close(closes, tp1, off["exit_index"], is_bull)
    best_on = _best_close(closes, tp1, on["exit_index"], is_bull)
    mfe = max((best_off - off["entry_price"]) * sign / risk, off["runner_r"])
    return {"tp1_index": tp1, "mfe_off_r": mfe, "gb_r": PCT / 100.0 * best_off / risk,
            "days_off": off["exit_index"] - tp1, "days_on": on["exit_index"] - tp1,
            **_giveback_extras(df, on, best_on, sign, risk, 1.0 - plan.tp1_fraction)}


def pair_row(ticker, df, source, hk, index, plan) -> dict | None:
    off, on = _arm(df, index, plan, False), _arm(df, index, plan, True)
    if off is None or on is None:
        return None
    risk = abs(off["entry_price"] - plan.stop_loss)
    row = {"ticker": ticker, "source": source, "horizon_key": hk, "direction": plan.direction,
           "signal_date": str(df.index[index].date()), "risk": risk, "off": off, "on": on,
           "changed": (off["exit_index"], off["exit_price"]) != (on["exit_index"], on["exit_price"])}
    if off["runner_r"] is not None and on["runner_r"] is not None:
        row.update(_runner_context(df, off, on, plan, risk))
    return row


def paired_trades(ticker: str, df, *, basis: str) -> list[dict]:
    """Every TRAIN entry of ``ticker``, simulated off and on, on a frame cut at TRAIN's end."""
    if basis not in BASES:
        raise ValueError(f"basis must be one of {BASES}, got {basis!r}")
    exit_sim.GIVEBACK_EXTREME_BASIS = basis
    df = df.loc[:TRAIN[1]]
    rows = (pair_row(ticker, df, *entry) for entry in _entries(ticker, df))
    return [row for row in rows if row is not None]


# --- summary -----------------------------------------------------------------

def _mean(values):
    xs = [v for v in values if v is not None]
    return sum(xs) / len(xs) if xs else None


def _delta_mean(baseline, component):
    """Paired statistic: mean R on minus mean R off over one ticker draw."""
    if not baseline or not component:
        return None
    return _mean(t.r for t in component) - _mean(t.r for t in baseline)


def verdict(lo, hi) -> str:
    """Descriptive only (controller rule, 2026-10-19); never flips the flag."""
    if lo is None or hi is None:
        return "UNMEASURABLE"
    if lo > 0:
        return "PASS"
    if hi < 0:
        return "FAIL"
    return "NO-LIFT"


def _primary(rows, n_resamples) -> dict:
    base = [_Arm(r["ticker"], r["off"]["r_net"]) for r in rows]
    comp = [_Arm(r["ticker"], r["on"]["r_net"]) for r in rows]
    boot = bootstrap_delta(base, comp, _delta_mean, n_resamples=n_resamples)
    mde = mde_paired(base, comp, _delta_mean, observed_n=len(rows), target_n=len(rows),
                     n_resamples=n_resamples) if rows else None
    return {"n": len(rows), "exp_r_off": _mean(a.r for a in base),
            "exp_r_on": _mean(a.r for a in comp), "delta_exp_r": boot.point,
            "ci_lo": boot.lo, "ci_hi": boot.hi, "p_le_zero": boot.p_greater_than_zero,
            "mde_paired": mde, "n_resamples": n_resamples, "verdict": verdict(boot.lo, boot.hi)}


def _quantiles(values) -> dict | None:
    xs = np.array([v for v in values if v is not None], dtype=float)
    if xs.size == 0:
        return None
    p10, p25, p50, p75, p90 = (float(q) for q in np.percentile(xs, [10, 25, 50, 75, 90]))
    return {"n": int(xs.size), "mean": float(xs.mean()), "p10": p10, "p25": p25,
            "p50": p50, "p75": p75, "p90": p90}


def _per_horizon(rows) -> dict:
    by = defaultdict(list)
    for row in rows:
        by[row["horizon_key"]].append(row)
    return {hk: {"n": len(v), "changed": sum(r["changed"] for r in v),
                 "delta_r": _mean(r["on"]["r_net"] - r["off"]["r_net"] for r in v),
                 "giveback_pct_in_r": _quantiles(r.get("gb_r") for r in v)}
            for hk, v in sorted(by.items())}


def _runner_arm(runners, arm, mfe_total) -> dict:
    n = len(runners)
    mix = Counter(r[arm]["stop_source"] or r[arm]["reason"] for r in runners)
    return {"runner_r": _quantiles(r[arm]["runner_r"] for r in runners),
            "floor_share": sum(r[arm]["stop_source"] == "floor" for r in runners) / n if n else None,
            "exit_mix": dict(sorted(mix.items())),
            "capture_fixed_window": (sum(r[arm]["runner_r"] for r in runners) / mfe_total
                                     if mfe_total > 0 else None),
            "days_tp1_to_exit": _quantiles(r[f"days_{arm}"] for r in runners)}


def _giveback_block(runners) -> dict:
    gb = [r for r in runners if r["on"]["stop_source"] == "giveback"]
    gapped = [r["gap_worse_r"] for r in gb if r["gap_worse_r"] < 0]
    return {"n": len(gb), "fill_worse_than_level": len(gapped), "mean_gap_cost_r": _mean(gapped),
            "shakeouts_within_10_bars": sum(1 for r in gb if r["shakeout"])}


def _book(rows, arm) -> dict:
    """Fixed risk per trade (COMMISSION_RISK_BASIS dollars), ordered by exit date."""
    ordered = sorted(rows, key=lambda r: (r[arm]["exit_date"], r["ticker"], r["signal_date"]))
    rs = np.array([r[arm]["r_net"] for r in ordered], dtype=float)
    cum = np.cumsum(rs)
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    dd = float(np.max(peak - cum)) if rs.size else 0.0
    basis = float(config.COMMISSION_RISK_BASIS)
    return {"total_r": float(rs.sum()), "dollars": float(rs.sum()) * basis,
            "max_drawdown_r": dd, "max_drawdown_dollars": dd * basis,
            "risk_per_trade_dollars": basis}


def summarise(rows: list[dict], *, n_resamples: int = BOOTSTRAP_RESAMPLES) -> dict:
    runners = [r for r in rows if "mfe_off_r" in r]
    mfe_total = sum(r["mfe_off_r"] for r in runners)
    per_horizon = _per_horizon(rows)
    return {"primary": _primary(rows, n_resamples),
            "changed": sum(r["changed"] for r in rows),
            "per_horizon": per_horizon,
            "runner": {"n": len(runners),
                       "mean_delta_r": _mean(r["on"]["r_net"] - r["off"]["r_net"] for r in runners),
                       **{arm: _runner_arm(runners, arm, mfe_total) for arm in ARMS}},
            "giveback_exits": _giveback_block(runners),
            "book": {arm: _book(rows, arm) for arm in ARMS},
            "cells_looked_at": 2 * len(per_horizon) + POOLED_DESCRIPTIVE_CELLS}


# --- run ---------------------------------------------------------------------

def _init_worker(basis) -> None:
    training_data.select(DATA_SOURCE)
    exit_sim.GIVEBACK_EXTREME_BASIS = basis


def _ticker_rows(task):
    ticker, basis = task
    df = training_data.load_daily(ticker)
    return ticker, ([] if df is None else paired_trades(ticker, df, basis=basis))


def build_rows(basis, *, tickers=None, workers=None) -> list[dict]:
    """Every cached ticker's rows, in ticker order whatever order the pool finishes in."""
    from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers
    universe = list(tickers) if tickers else training_data.available_tickers()
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"measure_runner_giveback.{basis}.progress"
    by_ticker = {}

    def record(ticker, rows):
        by_ticker[ticker] = rows
        done = len(by_ticker)
        print(f"  [{basis}] {done}/{len(universe)} {ticker}: {len(rows)} paired", flush=True)
        progress.write_text(f"{done}/{len(universe)} tickers ({done / len(universe) * 100:.0f}%)\n",
                            encoding="utf-8")

    n_workers = _resolve_replay_workers(workers)
    if n_workers <= 1 or len(universe) <= 1:
        _init_worker(basis)
        for ticker in universe:
            record(*_ticker_rows((ticker, basis)))
    else:
        with ProcessPoolExecutor(max_workers=n_workers, initializer=_init_worker,
                                 initargs=(basis,)) as pool:
            for future in as_completed([pool.submit(_ticker_rows, (t, basis)) for t in universe]):
                record(*future.result())
    progress.unlink(missing_ok=True)
    return [row for ticker in sorted(by_ticker) for row in by_ticker[ticker]]


def _frozen(basis) -> dict:
    from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
    return {"window": list(TRAIN), "data_source": DATA_SOURCE, "pct": PCT, "basis": basis,
            "arms": "flag off vs on, same entries (flag-off pass)", "scale_out": True,
            "instrument": "v1", "engines": ["StrategyEngine.iter_trades", "replay_scenarios"],
            "horizons": list(ALL_HORIZONS), "slippage_bps": float(config.SLIPPAGE_BPS),
            "commission_per_side": float(config.COMMISSION_PER_TRADE),
            "commission_risk_basis": float(config.COMMISSION_RISK_BASIS)}


def _refusal(args, target) -> str | None:
    if float(config.SLIPPAGE_BPS) <= 0 or float(config.COMMISSION_PER_TRADE) <= 0:
        return "refused:zero-frictions -- the spec needs non-zero frictions in both arms"
    if args.tickers and args.out_dir.resolve() == RESULTS.resolve():
        return "refused:smoke-run -- --tickers needs a scratch --out-dir"
    if target.exists():
        return f"refused:one-look -- {target} exists; this measurement is one look"
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    parser.add_argument("--basis", choices=BASES, default="close")
    parser.add_argument("--tickers", nargs="+", default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    instrument_cli.add_instrument_arg(parser)
    args = parser.parse_args(argv)
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "measure_runner_giveback.py",
                              "a later spec (v176 is frozen on instrument v1)")
    target = args.out_dir / f"train-{args.basis}.json"
    refusal = _refusal(args, target)
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    training_data.select(DATA_SOURCE)
    rows = build_rows(args.basis, tickers=args.tickers, workers=args.workers)
    blob = {"frozen": _frozen(args.basis), "summary": summarise(rows, n_resamples=args.resamples)}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(blob, indent=1), encoding="utf-8")
    training_data.write_provenance(target)
    print(json.dumps(blob["summary"]["primary"], indent=1), f"\n-> {target}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
