#!/usr/bin/env python3
"""v178: pre-registered paired test of runner give-back levels (range-multiple and profit-share arms).

Frozen before any window is read (spec 2026-10-19-v178, § The test):
  arms       A = live 5% of the best close; B = give-back off;
             R k in {0.75, 1.0, 1.25}: best -/+ k x ATR14;
             S f in {0.25, 0.33, 0.50}: best -/+ max(f x profit, 1.0 x ATR14)
  entries    ONE control-A pass per ticker; each entry re-simulated under every arm
  windows    arms.windows.STAGES: pilot; train = selection start .. walkforward end
             (every frame cut at the walkforward end, so no VALIDATION bar is run);
             validation = the one shot, for the single stage-3 arm
  data       the 75-ticker yfinance cache; StrategyEngine.iter_trades +
             replay_scenarios, all ten horizons; simulate_exit(scale_out=True), v1
  frictions  net_r: SLIPPAGE_BPS on both fills + commission_r(); zero refused

One look: every output is refused if it exists. Read through the funnel in
giveback_levels_funnel; it never changes the live rule.
PROGRESS: a flushed line per ticker plus logs/measure_giveback_levels.<stage>-<basis>.progress.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import gzip
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot import config  # noqa: E402
from swingbot.core.analytics.expectancy_attribution import net_r  # noqa: E402
from swingbot.core.backtesting import giveback_levels_blocks as blocks  # noqa: E402
from swingbot.core.backtesting import giveback_levels_funnel as funnel  # noqa: E402
from swingbot.core.backtesting.acceptance import (BOOTSTRAP_RESAMPLES, CLOSED,  # noqa: E402
                                                  planned_rr)
from swingbot.core.backtesting.arms.windows import STAGES, universe_for  # noqa: E402
from swingbot.core.backtesting.instrument import cli as instrument_cli  # noqa: E402
from swingbot.core.market import indicators  # noqa: E402
from swingbot.core.market.earnings_calendar import (EARNINGS_CSV_DIR, CsvSource,  # noqa: E402
                                                    reaction_session)
from swingbot.core.market.session import SessionCalendar  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402
from swingbot.core.planning import exit_sim  # noqa: E402
from swingbot.core.planning.plan_engine import simulate_exit  # noqa: E402

DATA_SOURCE = "yfinance"
BASES = ("close", "high_low")
STAGE_NAMES = ("pilot", "train", "report", "validation")
ROW_STAGES = ("pilot", "train", "validation")
ARM_IDS = tuple(funnel.ARMS)
RESULTS = ROOT / "docs" / "superpowers" / "results" / "v178"
ROWS_DIR = ROOT / "logs" / "v178"
LOG_DIR = ROOT / "logs"
_MODULE_KNOBS = ("GIVEBACK_MODE", "GIVEBACK_K", "GIVEBACK_F")
_RUNNER_KEYS = ("tp1_index", "best", "best_index", "allowance_pct", "floor_bound",
                "stop_moves", "gap_r", "new_best_within_10", "shock")


@contextlib.contextmanager
def arm_settings(arm: str):
    """One arm's give-back for the simulations inside the block; every value comes back after."""
    spec = funnel.ARMS[arm]
    saved_cfg = (config.RUNNER_GIVEBACK_ENABLED, config.RUNNER_GIVEBACK_PCT)
    saved_mod = {name: getattr(exit_sim, name) for name in _MODULE_KNOBS}
    config.RUNNER_GIVEBACK_ENABLED, config.RUNNER_GIVEBACK_PCT = spec["enabled"], funnel.PCT
    exit_sim.GIVEBACK_MODE = spec["mode"]
    exit_sim.GIVEBACK_K = spec.get("k", saved_mod["GIVEBACK_K"])
    exit_sim.GIVEBACK_F = spec.get("f", saved_mod["GIVEBACK_F"])
    try:
        yield spec
    finally:
        config.RUNNER_GIVEBACK_ENABLED, config.RUNNER_GIVEBACK_PCT = saved_cfg
        for name, value in saved_mod.items():
            setattr(exit_sim, name, value)


def stage_window(stage: str) -> tuple[str, str]:
    """Signal window of a row stage, from arms.windows.STAGES (never a literal)."""
    if stage == "train":
        return STAGES["selection"].signal_window[0], STAGES["walkforward"].signal_window[1]
    if stage in ("pilot", "validation"):
        return tuple(STAGES[stage].signal_window)
    raise ValueError(f"no signal window for stage {stage!r}; expected one of {ROW_STAGES}")


def frame_end(stage: str) -> str:
    """Last bar any simulation of ``stage`` may read."""
    stage_window(stage)
    return STAGES["validation" if stage == "validation" else "walkforward"].signal_window[1]


def _entries(ticker, df, window) -> list:
    """(source, horizon_key, signal_index, plan) for every entry of the control-A
    pass whose signal date falls inside ``window``."""
    from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
    from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    from swingbot.scan_params import ScanParams
    params, engine, out = ScanParams.from_config(), StrategyEngine(), []
    position = {str(ts.date()): i for i, ts in enumerate(df.index)}
    with arm_settings("A"):
        for hk in ALL_HORIZONS:
            for strategy in engine.strategies:
                for date, plan, _result in engine.iter_trades(ticker, df, strategy, hk, window, params):
                    out.append(("strategy", hk, position[date], plan))
            for index, plan in replay_scenarios(ticker, df, hk, params=params):
                if window[0] <= str(df.index[index].date()) <= window[1]:
                    out.append(("scenario", hk, index, plan))
    return out


# --- per-ticker series -------------------------------------------------------

def reaction_indices(ticker, df, earnings_dir) -> list[int]:
    """Frame positions of earnings reaction sessions (ETFs have none)."""
    from swingbot.core.marketdata.universe import is_etf
    if is_etf(ticker):
        return []
    calendar = SessionCalendar.from_bar_index(df.index)
    out = set()
    for report in CsvSource(earnings_dir).reports(ticker):
        session = reaction_session(report, calendar)
        position = None if session is None else calendar.position_on_or_after(session)
        if position is not None:
            out.add(position)
    return sorted(out)


def ticker_series(ticker, df, earnings_dir) -> dict:
    """ATR(14), ADX(14), true range and earnings reaction bars of one frame."""
    prev = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()],
                   axis=1).max(axis=1)
    return {"atr": indicators.atr(df, 14).to_numpy(dtype=float),
            "adx": indicators.adx(df, 14).to_numpy(dtype=float),
            "tr": tr.to_numpy(dtype=float),
            "reactions": reaction_indices(ticker, df, earnings_dir)}


def regime(series, index) -> str | None:
    value = float(series["adx"][index])
    if not np.isfinite(value):
        return None
    return "trend" if value >= blocks.ADX_TREND_MIN else "chop"


def shock(series, lo, hi) -> bool:
    """An earnings reaction bar, or true range above TR_SHOCK_ATR x the previous bar's
    ATR(14), anywhere in [lo, hi]."""
    if any(lo <= p <= hi for p in series["reactions"]):
        return True
    atr, tr = series["atr"], series["tr"]
    return bool(any(j >= 1 and np.isfinite(atr[j - 1]) and tr[j] > blocks.TR_SHOCK_ATR * atr[j - 1]
                    for j in range(lo, hi + 1)))


# --- one entry under every arm ---------------------------------------------

def _is_runner(result) -> bool:
    return result.outcome == "win" and len(result.legs) == 2


def _stop_moves(df, plan, result) -> int | None:
    """Changes of the runner stop, from the v1 walk's trace; None when the traced
    walk does not reproduce the result (an entry form the plain walk does not take)."""
    hold = exit_sim._hold_cap_bars(plan, exit_sim.HORIZONS[plan.horizon_key]["max_holding_days"])
    trace = []
    again = exit_sim._scale_out_exit_walk(df, result.entry_index, result.entry_price,
                                          copy.deepcopy(plan), hold, trace=trace)
    if (again.exit_index, again.legs) != (result.exit_index, result.legs):
        return None
    stops = [exit_sim.runner_floor(result.entry_price, plan.tp1)] + [stop for _, stop in trace]
    return sum(1 for a, b in zip(stops, stops[1:]) if a != b)


def _simulate(df, index, plan, arm):
    with arm_settings(arm):
        result = simulate_exit(df, index, copy.deepcopy(plan), scale_out=True)
        moves = _stop_moves(df, plan, result) if _is_runner(result) else None
    return result, moves


def _base_result(df, plan, result) -> dict:
    return {"outcome": result.outcome,
            "r_net": net_r(result.entry_price, plan.stop_loss, plan.direction, result.legs),
            "runner_r": float(result.legs[1]["r"]) if _is_runner(result) else None,
            "entry_index": int(result.entry_index), "exit_index": int(result.exit_index),
            "exit_date": str(df.index[result.exit_index].date()),
            "exit_price": float(result.legs[-1]["exit_price"]),
            "reason": result.runner_outcome or result.outcome,
            "stop_source": result.runner_stop_source}


def tp1_bar(df, plan, entry_index, exit_index) -> int:
    high, low = df["High"].values, df["Low"].values
    for j in range(entry_index + 1, exit_index + 1):
        if (high[j] >= plan.tp1) if plan.direction == "bullish" else (low[j] <= plan.tp1):
            return j
    return exit_index


def best_close(df, lo, hi, is_bull) -> tuple[float, int]:
    """Best close over [lo, hi - 1] (just bar lo when hi <= lo) and its bar."""
    closes = df["Close"].values[lo:max(hi, lo + 1)]
    k = int(np.argmax(closes) if is_bull else np.argmin(closes))
    return float(closes[k]), lo + k


def allowance_share(arm, best, entry, atr) -> tuple[float | None, bool | None]:
    """(allowance / best, floor binds) at the bar before the exit."""
    spec = funnel.ARMS[arm]
    if not spec["enabled"]:
        return None, None
    if spec["mode"] == "pct":
        return funnel.PCT / 100.0, None
    allowance = exit_sim.giveback_allowance(spec["mode"], best, entry, atr,
                                            k=spec.get("k", exit_sim.GIVEBACK_K),
                                            f=spec.get("f", exit_sim.GIVEBACK_F))
    if allowance is None or best == 0:
        return None, None
    floor = None
    if spec["mode"] == "profit_share":
        floor = bool(spec["f"] * abs(best - entry) < exit_sim.GIVEBACK_FLOOR_ATR * atr)
    return allowance / best, floor


def _gap_r(df, base, sign, risk, fraction) -> float | None:
    if base["stop_source"] is None:
        return None
    gap = (float(df["Open"].values[base["exit_index"]]) - base["exit_price"]) * sign / risk
    return min(0.0, gap) * fraction


def _new_best_after(df, base, best, sign) -> bool | None:
    if base["stop_source"] is None:
        return None
    j = base["exit_index"]
    later = df["Close"].values[j + 1:j + 1 + blocks.SHAKEOUT_BARS]
    return bool(any((float(c) - best) * sign > 0 for c in later))


def runner_fields(df, plan, base, moves, arm, series, risk, entry) -> dict:
    if base["runner_r"] is None:
        return dict.fromkeys(_RUNNER_KEYS)
    is_bull = plan.direction == "bullish"
    sign = 1 if is_bull else -1
    tp1 = tp1_bar(df, plan, base["entry_index"], base["exit_index"])
    best, best_index = best_close(df, tp1, base["exit_index"], is_bull)
    share, floor = allowance_share(arm, best, entry,
                                   float(series["atr"][max(base["exit_index"] - 1, tp1)]))
    return {"tp1_index": tp1, "best": best, "best_index": best_index,
            "allowance_pct": share, "floor_bound": floor, "stop_moves": moves,
            "gap_r": _gap_r(df, base, sign, risk, 1.0 - plan.tp1_fraction),
            "new_best_within_10": _new_best_after(df, base, best, sign),
            "shock": shock(series, tp1, base["exit_index"])}


def _closed(result) -> bool:
    return result.outcome in CLOSED and bool(result.legs)


def entry_row(ticker, df, entry, *, arms, series) -> dict | None:
    """One entry simulated under every arm; None unless control A (and every arm) closed it."""
    source, hk, index, plan = entry
    results = {arm: _simulate(df, index, plan, arm) for arm in arms}
    if not all(_closed(result) for result, _ in results.values()):
        return None
    control = results["A"][0]
    risk = abs(control.entry_price - plan.stop_loss)
    row = {"ticker": ticker, "source": source, "strategy": plan.strategy, "horizon_key": hk,
           "direction": plan.direction, "signal_date": str(df.index[index].date()),
           "planned_rr": planned_rr(control.entry_price, plan.stop_loss, plan.tp1),
           "risk": risk, "runner_fraction": 1.0 - plan.tp1_fraction,
           "regime": regime(series, index), "arms": {}}
    for arm, (result, moves) in results.items():
        base = _base_result(df, plan, result)
        base.update(runner_fields(df, plan, base, moves, arm, series, risk,
                                  float(result.entry_price)))
        row["arms"][arm] = base
    return row


def _unique_keys(rows) -> list[dict]:
    """Suffix repeated (ticker, strategy, horizon, date, source, direction) keys."""
    seen = Counter()
    for row in rows:
        key = (row["ticker"], row["strategy"], row["horizon_key"], row["signal_date"],
               row["source"], row["direction"])
        seen[key] += 1
        if seen[key] > 1:
            row["strategy"] = f"{row['strategy']}#{seen[key]}"
    return rows


def rows_for(ticker, df, *, stage, basis, arms=ARM_IDS, earnings_dir=EARNINGS_CSV_DIR) -> list[dict]:
    """Every ``stage`` entry of ``ticker`` under ``arms``, on a frame cut at frame_end(stage)."""
    if basis not in BASES:
        raise ValueError(f"basis must be one of {BASES}, got {basis!r}")
    if "A" not in arms:
        raise ValueError("arms must include control A (the pairing baseline)")
    exit_sim.GIVEBACK_EXTREME_BASIS = basis
    df = df.loc[:frame_end(stage)]
    series = ticker_series(ticker, df, earnings_dir)
    rows = (entry_row(ticker, df, entry, arms=arms, series=series)
            for entry in _entries(ticker, df, stage_window(stage)))
    return _unique_keys([row for row in rows if row is not None])


# --- run ---------------------------------------------------------------------

def _init_worker(basis) -> None:
    training_data.select(DATA_SOURCE)
    exit_sim.GIVEBACK_EXTREME_BASIS = basis


def _ticker_rows(task):
    ticker, stage, basis, arms, earnings_dir = task
    df = training_data.load_daily(ticker)
    return ticker, ([] if df is None else rows_for(ticker, df, stage=stage, basis=basis,
                                                     arms=arms, earnings_dir=Path(earnings_dir)))


def _universe(stage, tickers) -> list[str]:
    if tickers:
        return list(tickers)
    return universe_for("pilot" if stage == "pilot" else "validation",
                        training_data.available_tickers())


def build_rows(stage, basis, *, arms=ARM_IDS, tickers=None, workers=None,
               earnings_dir=EARNINGS_CSV_DIR) -> list[dict]:
    """Every universe ticker's rows, in ticker order whatever order the pool finishes in."""
    from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers
    universe = _universe(stage, tickers)
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"measure_giveback_levels.{stage}-{basis}.progress"
    by_ticker = {}

    def record(ticker, rows):
        by_ticker[ticker] = rows
        done = len(by_ticker)
        print(f"  [{stage}/{basis}] {done}/{len(universe)} {ticker}: {len(rows)} rows", flush=True)
        progress.write_text(f"{done}/{len(universe)} tickers ({done / len(universe) * 100:.0f}%)\n",
                            encoding="utf-8")

    tasks = [(t, stage, basis, tuple(arms), str(earnings_dir)) for t in universe]
    n_workers = _resolve_replay_workers(workers)
    if n_workers <= 1 or len(universe) <= 1:
        _init_worker(basis)
        for task in tasks:
            record(*_ticker_rows(task))
    else:
        with ProcessPoolExecutor(max_workers=n_workers, initializer=_init_worker,
                                 initargs=(basis,)) as pool:
            for future in as_completed([pool.submit(_ticker_rows, task) for task in tasks]):
                record(*future.result())
    progress.unlink(missing_ok=True)
    return [row for ticker in sorted(by_ticker) for row in by_ticker[ticker]]


def write_rows(path, rows) -> Path:
    """Gzipped JSON, written to a temporary file then renamed (no half-written rows file)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        json.dump(rows, handle)
    temporary.replace(path)
    return path


def read_rows(path) -> list[dict]:
    with gzip.open(Path(path), "rt", encoding="utf-8") as handle:
        return json.load(handle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", required=True, choices=STAGE_NAMES)
    parser.add_argument("--basis", choices=BASES, default="close")
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    parser.add_argument("--rows-dir", type=Path, default=ROWS_DIR)
    parser.add_argument("--tickers", nargs="+", default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    parser.add_argument("--earnings-dir", type=Path, default=EARNINGS_CSV_DIR)
    parser.add_argument("--arm", choices=funnel.CANDIDATES, default=None)
    parser.add_argument("--preregistration", type=Path, default=None)
    instrument_cli.add_instrument_arg(parser)
    return parser


def parse_args(argv=None) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "measure_giveback_levels.py",
                              "a later spec (v178 is frozen on instrument v1)")
    return args
