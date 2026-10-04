#!/usr/bin/env python3
"""v123 Task 0: baseline runner capture (runner R vs runner MFE) on TRAIN replay."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

TRAIN = ("2020-01-01", "2023-12-31")
STOP_CAPTURE = 0.75          # spec v123 frozen stop rule


def cache_universe() -> list[str]:
    """Sorted tickers with daily CSV in the local backtest cache.
    Derives from swingbot.core.marketdata.backtest_cache; does not touch DB."""
    from swingbot.core.marketdata.backtest_cache import CACHE_DIR
    csvs = CACHE_DIR.glob("*.csv")
    # Stems are the sanitised cache names (e.g., GC_F for GC=F, _GSPC for ^GSPC)
    tickers = [p.stem for p in csvs]
    return sorted(tickers)


def _tp1_index(df, result, plan) -> int:
    high, low = df["High"].values, df["Low"].values
    for j in range(result.entry_index + 1, result.exit_index + 1):
        if (high[j] >= plan.tp1) if plan.direction == "bullish" else (low[j] <= plan.tp1):
            return j
    return result.exit_index


def runner_metrics(df, result, plan) -> dict | None:
    if result.outcome != "win" or len(result.legs) != 2:
        return None
    sign = 1 if plan.direction == "bullish" else -1
    risk = abs(result.entry_price - plan.stop_loss)
    closes = df["Close"].values[_tp1_index(df, result, plan):result.exit_index]
    runner_r = float(result.legs[1]["r"])
    best = max(((float(c) - result.entry_price) * sign / risk for c in closes), default=runner_r)
    mfe_r = max(best, runner_r)
    return {"horizon_key": plan.horizon_key, "source": plan.source, "runner_r": runner_r,
            "mfe_r": mfe_r, "capture": runner_r / mfe_r if mfe_r > 0 else None,
            "reason": result.legs[1]["reason"]}


def _compute_reason_pct(reasons, n) -> dict:
    return {k: v / n * 100 for k, v in sorted(reasons.items())}


def _compute_sum_capture(rows) -> float | None:
    sum_runner = sum(r["runner_r"] for r in rows)
    sum_mfe = sum(r["mfe_r"] for r in rows)
    if sum_mfe > 0:
        return sum_runner / sum_mfe
    return None


def _block(rows) -> dict:
    captured = [r["capture"] for r in rows if r["capture"] is not None]
    reasons = Counter(r["reason"] for r in rows)
    n = len(rows)
    mean_runner = sum(r["runner_r"] for r in rows) / n if n else None
    mean_mfe = sum(r["mfe_r"] for r in rows) / n if n else None
    mean_capture = sum(captured) / len(captured) if captured else None
    sum_capture = _compute_sum_capture(rows)
    reason_pct = _compute_reason_pct(reasons, n) if n else {}
    return {"n": n, "mean_runner_r": mean_runner, "mean_mfe_r": mean_mfe,
            "mean_capture": mean_capture, "sum_capture": sum_capture,
            "reasons_pct": reason_pct}


def summarise(rows) -> dict:
    by_h = defaultdict(list)
    for row in rows:
        by_h[row["horizon_key"]].append(row)
    return {"pooled": _block(rows), "per_horizon": {h: _block(v) for h, v in sorted(by_h.items())}}


def stop_rule(summary) -> str:
    mean = summary["pooled"]["mean_capture"]
    return "NO_HEADROOM" if mean is not None and mean >= STOP_CAPTURE else "HEADROOM"


def _ticker_rows(task) -> list:
    from measure_arms import load_frame
    from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    from swingbot.core.planning.plan_engine import simulate_exit
    from swingbot.scan_params import ScanParams
    ticker, horizons = task
    df, params, out = load_frame(ticker), ScanParams.from_config(), []
    if df is None:
        return []
    engine = StrategyEngine()
    for hk in horizons:
        for strategy in engine.strategies:
            for _date, plan, result in engine.iter_trades(ticker, df, strategy, hk, TRAIN, params):
                out.append(runner_metrics(df, result, plan))
        for index, plan in replay_scenarios(ticker, df.loc[:TRAIN[1]], hk, params=params):
            if str(df.index[index].date()) >= TRAIN[0]:
                out.append(runner_metrics(df, simulate_exit(df, index, plan, scale_out=True), plan))
    return [row for row in out if row is not None]


def main(argv=None) -> int:
    from measure_arms import _write_progress
    from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
    from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args(argv)
    universe = cache_universe()
    if not universe:
        print("error: backtest cache is empty; no tickers to process", file=sys.stderr)
        return 2
    progress = ROOT / "logs" / f"runner_headroom.{uuid.uuid4().hex[:8]}.progress"
    rows, done = [], 0
    with ProcessPoolExecutor(max_workers=_resolve_replay_workers(args.workers)) as pool:
        for future in as_completed([pool.submit(_ticker_rows, (t, ALL_HORIZONS)) for t in universe]):
            rows.extend(future.result())
            done += 1
            print(f"  {done}/{len(universe)} tickers", flush=True)
            _write_progress(progress, done, len(universe))
    progress.unlink(missing_ok=True)
    summary = summarise(rows)
    summary["verdict"] = stop_rule(summary)
    args.out_json.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary["pooled"], indent=1), "\nverdict:", summary["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
