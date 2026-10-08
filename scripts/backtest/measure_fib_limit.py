#!/usr/bin/env python3
"""v131 measurement: Fibonacci Limit -- a resting buy limit inside the retracement zone.

Stages (spec "The measurement"): collect (TRAIN rows, one horizon per call) ->
stage0 (the loosest cell's fill count) -> reproduce (the reference arm's
2010-2023 slice against v103) -> evaluate (Stages 1-2) -> holdout (Stage 3, one
shot) -> emit-registry. Every command refuses to run until the pre-registration
is committed. Reads the EXTENDED cache only:
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_limit.py <command> ...
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import gzip
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

import funnel  # noqa: E402
from funnel import BOOTSTRAP_SEED, MIN_N_TRAIN, MIN_N_VALIDATION  # noqa: E402
from measure_fib_confluence import Progress, _load_frames, _write, require_ext_cache  # noqa: E402
from measure_fib_v103 import require_committed  # noqa: E402
from run_backtest_range import _build_asof_map, merge_registry  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES  # noqa: E402
from swingbot.core.backtesting.backtest import run_backtest  # noqa: E402
from swingbot.core.market.entry_filters import DEFAULT_PARAMS, gate_override  # noqa: E402
from swingbot.core.market.indicators import atr  # noqa: E402
from swingbot.core.market.strategy_types import FIB_LIMIT, LEGACY_HORIZONS  # noqa: E402
from swingbot.core.planning.params import PLAN_SHAPES  # noqa: E402
from swingbot.core.planning.stop_scope import in_scope, stop_ceiling  # noqa: E402

# --- pre-registered constants (spec "The measurement") ---
TRAIN = ("2010-01-01", "2025-12-31")
REPRO_WINDOW = ("2010-01-01", "2023-12-31")
V103_REFERENCE = {"n": 815, "win_rate": 36.81, "expectancy_r": 0.2219, "universe_n": 73}
HOLDOUT_START = "2026-01-01"
THIN_REOPEN = "2026-12-31"
FOLD_YEARS = tuple(range(2013, 2026))
ALL_HZ = tuple(LEGACY_HORIZONS)          # the ten legacy horizons, 2w..9m
L_GRID = (0.5, 0.618)
N_GRID = (3, 5, 10)
LOOSEST = (0.5, 10)
STAGE0_MIN_FILLS = 30
FILLS_SHARE = 0.5                           # profit clause (b)
WR_SLACK_PP = 2.0                           # profit clause (c)
MIN_HOLDOUT_FILLS = 15
EARLY_STOP_BARS = 3
CAP_TOLERANCE_PCT = 0.001
TOP2_LINE = 0.8
RR_BAND = (1.5, 2.5)
REFERENCE_STRATEGY = "Fibonacci"
UNMASKED = {"directions": ("bullish",)}
RESULTS = ROOT / "docs" / "superpowers" / "results"


def cell_key(ratio, life) -> str:
    return f"L{float(ratio):g}|N{int(life)}"


CELLS = tuple(cell_key(ratio, life) for ratio in L_GRID for life in N_GRID)
LOOSEST_KEY = cell_key(*LOOSEST)


def parse_cell(key: str) -> tuple[float, int]:
    ratio, life = key.split("|")
    return float(ratio[1:]), int(life[1:])


# --- guards -------------------------------------------------------------------

def require_preregistration(path) -> None:
    """Every command refuses to run before the pre-registration is committed."""
    if not Path(path).name.endswith("-v131-preregistration.md"):
        raise SystemExit(f"--preregistration must be the v131 pre-registration, got {path}")
    require_committed(path)


def require_frozen_config() -> None:
    """The plan arithmetic the pre-registration froze: the 1.5-2.5R band, and
    Fibonacci Limit outside STRUCTURAL_STOP_SCOPE (2% cap, not drop)."""
    band = (float(config.MIN_RISK_REWARD_RATIO), float(config.MAX_RISK_REWARD_RATIO))
    if band != RR_BAND:
        raise SystemExit(f"R:R band is {band}, the pre-registration froze {RR_BAND}")
    if in_scope(FIB_LIMIT, "bullish"):
        raise SystemExit("Fibonacci Limit is in STRUCTURAL_STOP_SCOPE; the pre-registration froze the 2% cap")


@contextlib.contextmanager
def cell(key: str):
    """Set one grid cell: L and N on the setup, N as the order's expiry_bars."""
    ratio, life = parse_cell(key)
    params, shape = DEFAULT_PARAMS[FIB_LIMIT], PLAN_SHAPES[FIB_LIMIT]
    saved = (dict(params), shape["expiry_bars"])
    params.update(L=ratio, N=life)
    shape["expiry_bars"] = life
    try:
        with gate_override(FIB_LIMIT, UNMASKED):
            yield
    finally:
        params.clear()
        params.update(saved[0])
        shape["expiry_bars"] = saved[1]


# --- rows -------------------------------------------------------------------------

def _positions(frame, *dates):
    import pandas as pd
    return [int(frame.index.get_indexer([pd.Timestamp(date)])[0]) for date in dates]


def _geometry(entry, stop, target, atr_value, ceiling) -> dict:
    """Plan geometry measured from `entry` (the limit for a cell, the close for
    the reference): risk %, cap binding, and the three context keys v131
    recomputes from the limit (spec "Features recorded for B")."""
    risk = abs(entry - stop)
    risk_pct = risk / entry * 100
    return {"risk_pct": round(risk_pct, 4),
            "cap_bound": risk_pct >= ceiling - CAP_TOLERANCE_PCT,
            "stop_pct": round(risk_pct, 6),
            "planned_rr": round(abs(target - entry) / risk, 6) if risk else None,
            "stop_atr": round(risk / atr_value, 6) if atr_value else None}


def _base_row(ticker, horizon, trade) -> dict:
    return {"ticker": ticker, "horizon_key": horizon, "direction": trade.direction,
            "entry_date": trade.entry_date, "exit_date": trade.exit_date,
            "outcome": trade.outcome, "r_multiple": trade.r_multiple,
            "stop_loss": trade.stop_loss, "take_profit": trade.take_profit}


def _early_stop(trade, fill_pos, exit_pos) -> bool:
    return trade.outcome == "loss" and exit_pos - fill_pos <= EARLY_STOP_BARS


def limit_row(ticker, horizon, trade, order, frame, atr_series) -> dict:
    """One filled Fibonacci Limit order: outcome, fill, disclosures, and the
    arming-bar entry_context with its geometry re-priced from the limit."""
    signal_pos, fill_pos, exit_pos = _positions(frame, trade.entry_date, order["fill_date"],
                                                trade.exit_date)
    ceiling = stop_ceiling(FIB_LIMIT, "bullish", horizon)[0]
    geometry = _geometry(trade.entry, trade.stop_loss, trade.take_profit,
                         float(atr_series.iloc[signal_pos]), ceiling)
    context = dict(trade.context or {})
    context.update({key: geometry[key] for key in ("stop_pct", "planned_rr", "stop_atr")})
    return {**_base_row(ticker, horizon, trade), "limit_price": trade.entry,
            "fill_date": order["fill_date"], "fill_price": order["fill_price"],
            "fill_index": fill_pos, "signal_index": signal_pos,
            "risk_pct": geometry["risk_pct"], "cap_bound": geometry["cap_bound"],
            "early_stop": _early_stop(trade, fill_pos, exit_pos),
            "same_bar_new_high": order["same_bar_new_high"], "context": context}


def reference_row(ticker, horizon, trade, frame) -> dict:
    """One reference-arm trade (market entry on the bounce bar's close)."""
    entry_pos, exit_pos = _positions(frame, trade.entry_date, trade.exit_date)
    ceiling = stop_ceiling(REFERENCE_STRATEGY, "bullish", horizon)[0]
    risk_pct = abs(trade.entry - trade.stop_loss) / trade.entry * 100
    return {**_base_row(ticker, horizon, trade), "risk_pct": round(risk_pct, 4),
            "cap_bound": risk_pct >= ceiling - CAP_TOLERANCE_PCT,
            "early_stop": _early_stop(trade, entry_pos, exit_pos)}


def _in_window(date, window) -> bool:
    return window[0] <= date <= window[1]


def _run(run_fn, ticker, frame, strategy, horizon, asof):
    return run_fn(ticker, frame, strategy, horizon, one_at_a_time=True, exit_model="v2",
                  scale_out=True, tp2_mode="levels", frictions=True, asof=asof)


def _count_orders(counts, orders, window) -> None:
    for order in orders:
        if not _in_window(order["signal_date"], window):
            continue
        counts["placed"] += 1
        counts[order["status"]] += 1
        counts["same_bar_new_high"] += int(bool(order["same_bar_new_high"]))


def cell_rows(key, frames, asof_map, horizon, window, *, run_fn=None, progress=None) -> dict:
    """Every bullish fill of one cell on one horizon inside `window`, plus the
    order counts behind the fill rate."""
    run_fn = run_fn or run_backtest
    rows, counts = [], collections.Counter()
    with cell(key):
        for ticker, frame in sorted(frames.items()):
            if progress is not None:
                progress.tick(f"{horizon} {key} {ticker}")
            summary = _run(run_fn, ticker, frame, FIB_LIMIT, horizon, asof_map.get(ticker))
            filled = {order["signal_date"]: order for order in summary.limit_orders
                      if order["status"] == "filled"}
            atr_series = atr(frame, 14)
            rows.extend(limit_row(ticker, horizon, trade, filled[trade.entry_date], frame, atr_series)
                        for trade in summary.trades
                        if trade.direction == "bullish" and _in_window(trade.entry_date, window))
            _count_orders(counts, summary.limit_orders, window)
    return {"rows": rows, "orders": {name: counts[name] for name in
                                     ("placed", "filled", "expired", "cancelled", "same_bar_new_high")}}


def reference_rows(frames, asof_map, horizon, window, *, run_fn=None, progress=None) -> list:
    """Today's Fibonacci, as it ships (bullish, live gates), on the same window."""
    run_fn = run_fn or run_backtest
    rows = []
    for ticker, frame in sorted(frames.items()):
        if progress is not None:
            progress.tick(f"{horizon} reference {ticker}")
        summary = _run(run_fn, ticker, frame, REFERENCE_STRATEGY, horizon, asof_map.get(ticker))
        rows.extend(reference_row(ticker, horizon, trade, frame) for trade in summary.trades
                    if trade.direction == "bullish" and _in_window(trade.entry_date, window))
    return rows


def collect_horizon(frames, asof_map, horizon, window, *, cells=CELLS, run_fn=None,
                    progress=None) -> dict:
    out = {"cells": {key: cell_rows(key, frames, asof_map, horizon, window,
                                    run_fn=run_fn, progress=progress) for key in cells},
           "reference": {"rows": reference_rows(frames, asof_map, horizon, window,
                                                run_fn=run_fn, progress=progress)}}
    return out


# --- loading the per-horizon collects ----------------------------------------------

def load_collects(paths) -> dict:
    """Merge the ten per-horizon TRAIN collects into one {cells, reference, universe_n}."""
    payloads = [json.loads(Path(path).read_text(encoding="utf-8")) for path in paths]
    horizons = sorted(payload["horizon"] for payload in payloads)
    if horizons != sorted(ALL_HZ):
        raise SystemExit(f"need exactly one collect per horizon {list(ALL_HZ)}, got {horizons}")
    if len({payload["universe_n"] for payload in payloads}) != 1:
        raise SystemExit("collects disagree on universe_n")
    merged = {"universe_n": payloads[0]["universe_n"], "reference": [],
              "cells": {key: {"rows": [], "orders": collections.Counter()} for key in CELLS}}
    for payload in payloads:
        merged["reference"].extend(payload["reference"]["rows"])
        for key in CELLS:
            merged["cells"][key]["rows"].extend(payload["cells"][key]["rows"])
            merged["cells"][key]["orders"].update(payload["cells"][key]["orders"])
    for key in CELLS:
        merged["cells"][key]["orders"] = dict(merged["cells"][key]["orders"])
    return merged


# --- Stage 0 and the reference reproduction -----------------------------------------

def stage0_verdict(merged) -> dict:
    """Free volume check: the loosest cell needs STAGE0_MIN_FILLS fills. Reads
    that one cell's fill count and nothing else."""
    fills = len(merged["cells"][LOOSEST_KEY]["rows"])
    return {"cell": LOOSEST_KEY, "fills": fills, "min_fills": STAGE0_MIN_FILLS,
            "passes": fills >= STAGE0_MIN_FILLS}


def reproduction(merged) -> dict:
    """The reference arm's 2010-2023 slice against v103's reference."""
    rows = [row for row in merged["reference"] if _in_window(row["entry_date"], REPRO_WINDOW)]
    stats = funnel.pooled(rows)
    got = {"n": stats["n"], "universe_n": merged["universe_n"],
           "win_rate": None if stats["win_rate"] is None else round(stats["win_rate"], 2),
           "expectancy_r": None if stats["expectancy_r"] is None else round(stats["expectancy_r"], 4)}
    by_ticker = collections.Counter(row["ticker"] for row in rows)
    return {"window": list(REPRO_WINDOW), "expected": V103_REFERENCE, "got": got,
            "matches": got == V103_REFERENCE, "by_ticker": dict(sorted(by_ticker.items()))}


# --- disclosures (reported, never selecting) ------------------------------------------

def _share(rows, flag):
    return sum(1 for row in rows if row[flag]) / len(rows) if rows else None


def horizon_concentration(rows) -> dict:
    counts = collections.Counter(row["horizon_key"] for row in rows)
    top2 = sum(n for _, n in counts.most_common(2))
    share = top2 / len(rows) if rows else None
    return {"by_horizon": dict(sorted(counts.items())), "top2_share": share,
            "over_line": share is not None and share >= TOP2_LINE}


def total_r(rows) -> float:
    return round(sum(row["r_multiple"] for row in rows if row["r_multiple"] is not None), 4)


def disclosures(rows, orders=None) -> dict:
    out = {"fills": len(rows), "early_stop_share": _share(rows, "early_stop"),
           "cap_bind_share": _share(rows, "cap_bound"),
           "horizon_concentration": horizon_concentration(rows), "total_r": total_r(rows)}
    if orders is not None:
        placed = orders.get("placed", 0)
        out.update(orders=orders, fill_rate=orders.get("filled", 0) / placed if placed else None)
    return out


# --- commands (collect, stage0, reproduce) -------------------------------------------

def _frames(args):
    require_ext_cache()
    require_frozen_config()
    frames = _load_frames(args.universe, args.tickers)
    return frames, _build_asof_map(list(frames), frames, args.universe)


def _cmd_collect(args):
    require_preregistration(args.preregistration)
    if args.horizon not in ALL_HZ:
        raise SystemExit(f"--horizon must be one of {list(ALL_HZ)}")
    started = time.monotonic()
    frames, asof_map = _frames(args)
    progress = Progress((len(CELLS) + 1) * len(frames))
    collected = collect_horizon(frames, asof_map, args.horizon, TRAIN, progress=progress)
    for arm in [*collected["cells"].values(), collected["reference"]]:
        funnel.assert_rows_before(arm["rows"], TRAIN[1])
    _write(args.out, {"horizon": args.horizon, "window": list(TRAIN), "universe_n": len(frames),
                      **collected, "elapsed_s": round(time.monotonic() - started, 1)})


def _cmd_stage0(args):
    require_preregistration(args.preregistration)
    _write(args.out, stage0_verdict(load_collects(args.rows)))


def _cmd_reproduce(args):
    require_preregistration(args.preregistration)
    _write(args.out, reproduction(load_collects(args.rows)))


# --- Stage 1: selection on TRAIN ------------------------------------------------------

def neighbours(key: str) -> list[str]:
    """Adjacent values on one axis of the L x N grid."""
    ratio, life = parse_cell(key)
    i, j = L_GRID.index(ratio), N_GRID.index(life)
    out = [cell_key(L_GRID[a], life) for a in (i - 1, i + 1) if 0 <= a < len(L_GRID)]
    return out + [cell_key(ratio, N_GRID[b]) for b in (j - 1, j + 1) if 0 <= b < len(N_GRID)]


def plateau(passes: dict) -> list[str]:
    """Cells that clear a tier together with every grid neighbour."""
    return [key for key in CELLS if passes[key] and all(passes[n] for n in neighbours(key))]


def profit_clauses(cell_stats, cell_fills, ref_stats, ref_trades) -> dict:
    """Stage 1's profit clauses, all required of the winner: (a) ExpR above the
    reference arm's, (b) fills at least half the reference's trade count,
    (c) WR no more than 2.0pp below the reference's."""
    exp, ref_exp = cell_stats.get("expectancy_r"), ref_stats.get("expectancy_r")
    wr, ref_wr = cell_stats.get("win_rate"), ref_stats.get("win_rate")
    return {"a_expr_beats_reference": exp is not None and ref_exp is not None and exp > ref_exp,
            "b_fills_half_of_reference": cell_fills >= FILLS_SHARE * ref_trades,
            "c_wr_within_2pp": wr is not None and ref_wr is not None and wr >= ref_wr - WR_SLACK_PP}


def stage1(merged, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED) -> dict:
    cells = {key: funnel.score_cell(merged["cells"][key]["rows"], MIN_N_TRAIN,
                                    n_resamples=n_resamples, seed=seed) for key in CELLS}
    plateau1 = plateau({key: cells[key]["tier1"]["clears"] for key in CELLS})
    plateau2 = plateau({key: cells[key]["tier2"]["clears"] for key in CELLS})
    winner, tier = funnel._pick_winner(cells, plateau1, plateau2)
    reference = merged["reference"]
    clauses = None if winner is None else profit_clauses(
        cells[winner]["stats"], len(merged["cells"][winner]["rows"]),
        funnel.pooled(reference), len(reference))
    return {"cells": cells, "plateau_tier1": plateau1, "plateau_tier2": plateau2,
            "winner": winner, "winner_tier": tier, "profit_clauses": clauses,
            "passes": clauses is not None and all(clauses.values())}


# --- Stage 2: anchored folds ------------------------------------------------------------

def fold_pick(merged, year):
    """Re-select on 2010..year-1: the highest-ExpR cell with N >= 30 there."""
    best = None
    for key in CELLS:
        stats = funnel.pooled(funnel.year_rows(merged["cells"][key]["rows"],
                                               funnel.TRAIN_START_YEAR, year - 1))
        if stats["n"] < MIN_N_TRAIN or stats["expectancy_r"] is None:
            continue
        if best is None or stats["expectancy_r"] > best[1]:
            best = (key, stats["expectancy_r"])
    return None if best is None else best[0]


def stage2(merged) -> dict:
    folds = []
    for year in FOLD_YEARS:
        key = fold_pick(merged, year)
        stats = None if key is None else funnel.pooled(
            funnel.year_rows(merged["cells"][key]["rows"], year, year))
        folds.append({"test_year": year, "tol": key, "stats": stats})
    return {"folds": folds, "verdict": funnel.fold_verdict(folds)}


def evaluate(merged, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED) -> dict:
    """Stages 1-2. Stage 2 runs only behind a Stage 1 winner that met every
    profit clause; disclosures are reported for every cell either way."""
    first = stage1(merged, n_resamples=n_resamples, seed=seed)
    second = stage2(merged) if first["passes"] else None
    proceed = second is not None and second["verdict"]["clears"]
    closed_at = None if proceed else ("stage1" if second is None else "stage2")
    reference = merged["reference"]
    return {"universe_n": merged["universe_n"], "stage1": first, "stage2": second,
            "proceed_to_holdout": proceed, "closed_at": closed_at,
            "winner": first["winner"] if proceed else None,
            "tier": first["winner_tier"] if proceed else None,
            "reference": {"stats": funnel.pooled(reference), "trades": len(reference),
                          **disclosures(reference)},
            "disclosures": {key: disclosures(merged["cells"][key]["rows"], merged["cells"][key]["orders"])
                            for key in CELLS}}


# --- Stage 3: the holdout (one shot) ----------------------------------------------------

def holdout_window(frames) -> tuple:
    """2026-01-01 to the cache end at the time of the shot."""
    return HOLDOUT_START, max(str(frame.index[-1].date()) for frame in frames.values())


def check_shot_allowed(out_path, cache_end=None) -> None:
    """One shot, ever: the results directory is the ledger. A single
    sealed-thin shot may be retried once, when the cache reaches THIN_REOPEN."""
    out = Path(out_path)
    if out.parent.resolve() != Path(RESULTS).resolve() or not out.name.endswith("-v131-holdout.json"):
        raise SystemExit(f"--out must be {RESULTS}/<date>-v131-holdout.json so the one-shot rule sees it")
    if out.exists():
        raise SystemExit(f"holdout output already exists: {out}")
    prior = sorted(Path(RESULTS).glob("*-v131-holdout.json"))
    if not prior:
        return
    statuses = [json.loads(path.read_text(encoding="utf-8")).get("status") for path in prior]
    if statuses != ["sealed-thin"]:
        raise SystemExit(f"the v131 holdout shot is spent ({prior[-1].name})")
    if cache_end is not None and cache_end < THIN_REOPEN:
        raise SystemExit(f"sealed-thin; the one retry waits for the cache to reach {THIN_REOPEN}")


def holdout_verdict(rows, reference, tier, *, n_resamples=BOOTSTRAP_RESAMPLES,
                    seed=BOOTSTRAP_SEED) -> dict:
    """Fewer than 15 fills is sealed-thin (shot unspent). Otherwise the winner
    is scored at the tier it held on TRAIN, plus profit clause (a) against the
    reference arm on the same holdout. The badge is computed, never gating:
    VALIDATED only for a Tier 1 winner that passes, WEAK for a Tier 2 pass."""
    fills = len(rows)
    if fills < MIN_HOLDOUT_FILLS:
        return {"status": "sealed-thin", "fills": fills}
    scored = funnel.score_cell(rows, MIN_N_VALIDATION, n_resamples=n_resamples, seed=seed)
    reference_stats = funnel.pooled(reference)
    clauses = dict(scored["tier1" if tier == 1 else "tier2"]["clauses"])
    clauses["a_expr_beats_reference"] = profit_clauses(
        scored["stats"], fills, reference_stats, len(reference))["a_expr_beats_reference"]
    passes = all(clauses.values())
    return {"status": "scored", "tier": tier, "fills": fills, "stats": scored["stats"],
            "lower_bound": scored["lower_bound"], "reference": reference_stats,
            "clauses": clauses, "passes": passes,
            "badge": ("VALIDATED" if tier == 1 else "WEAK") if passes else None}


def holdout_rows(winner, frames, asof_map, window, progress=None) -> tuple:
    rows, orders, reference = [], collections.Counter(), []
    for horizon in ALL_HZ:
        one = cell_rows(winner, frames, asof_map, horizon, window, progress=progress)
        rows.extend(one["rows"])
        orders.update(one["orders"])
        reference.extend(reference_rows(frames, asof_map, horizon, window, progress=progress))
    return rows, dict(orders), reference


def registry_row(payload, run_date) -> dict:
    stats = payload["stats"]
    return {"source": "strategy", "strategy": FIB_LIMIT, "horizon": None, "status": payload["badge"],
            "n": stats["n"],
            "win_rate": None if stats["win_rate"] is None else round(stats["win_rate"], 1),
            "expectancy_r": None if stats["expectancy_r"] is None else round(stats["expectancy_r"], 3),
            "window": f"{payload['window'][0]}..{payload['window'][1]}", "run_date": run_date}


# --- commands (evaluate, holdout, emit-registry) -----------------------------------------

def _require_reproduction(path, note) -> None:
    """No cell is read until the reference reproduces v103, or a committed
    note explains the difference."""
    require_committed(path)
    if json.loads(Path(path).read_text(encoding="utf-8")).get("matches"):
        return
    if note is None:
        raise SystemExit("the reference does not reproduce v103: commit a --reproduction-note first")
    require_committed(note)


def _cmd_evaluate(args):
    require_preregistration(args.preregistration)
    require_committed(args.stage0)
    if not json.loads(Path(args.stage0).read_text(encoding="utf-8")).get("passes"):
        raise SystemExit("Stage 0 closed the mechanism (volume-dead); nothing to evaluate")
    _require_reproduction(args.reproduction, args.reproduction_note)
    _write(args.out, evaluate(load_collects(args.rows)))


def _holdout_target(args) -> dict:
    require_preregistration(args.preregistration)
    require_committed(args.evaluate)
    evaluated = json.loads(Path(args.evaluate).read_text(encoding="utf-8"))
    if not evaluated.get("proceed_to_holdout"):
        raise SystemExit("the mechanism did not proceed to the holdout")
    return evaluated


def _cmd_holdout(args):
    evaluated = _holdout_target(args)
    check_shot_allowed(args.out)
    frames, asof_map = _frames(args)
    window = holdout_window(frames)
    check_shot_allowed(args.out, cache_end=window[1])
    progress = Progress(2 * len(ALL_HZ) * len(frames))
    rows, orders, reference = holdout_rows(evaluated["winner"], frames, asof_map, window, progress)
    result = holdout_verdict(rows, reference, evaluated["tier"])
    payload = {"candidate": evaluated["winner"], "window": list(window), "universe_n": len(frames),
               "evaluate": str(args.evaluate), "preregistration": str(args.preregistration), **result}
    if result["status"] == "scored":
        payload.update(rows=rows, reference_rows=reference, disclosures=disclosures(rows, orders),
                       reference_disclosures=disclosures(reference))
    _write(args.out, payload)


FEATURE_ROW_KEYS = ("ticker", "horizon_key", "entry_date", "signal_index", "fill_index", "fill_date",
                    "fill_price", "limit_price", "stop_loss", "take_profit", "outcome", "r_multiple",
                    "context")


def feature_rows(merged) -> dict:
    """Every TRAIN fill per cell with its arming-bar entry_context, for the
    queued meta-label spec (B). Recorded only: nothing here is split, scored
    or read by any stage."""
    return {key: [{name: row[name] for name in FEATURE_ROW_KEYS} for row in merged["cells"][key]["rows"]]
            for key in CELLS}


def _cmd_features(args):
    require_preregistration(args.preregistration)
    merged = load_collects(args.rows)
    payload = {"window": list(TRAIN), "universe_n": merged["universe_n"], "cells": feature_rows(merged)}
    with gzip.open(args.out, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, default=str)


def _cmd_emit(args):
    require_committed(args.holdout_json)
    payload = json.loads(Path(args.holdout_json).read_text(encoding="utf-8"))
    if payload.get("status") != "scored" or not payload.get("passes"):
        raise SystemExit("refusing to emit a failing or sealed-thin holdout")
    require_preregistration(payload["preregistration"])
    merge_registry(args.registry, [registry_row(payload, args.run_date)])


def _parser():
    parser = argparse.ArgumentParser(description="v131 Fibonacci Limit funnel")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("collect", "stage0", "reproduce", "evaluate", "features", "holdout"):
        command = sub.add_parser(name)
        command.add_argument("--out", required=True)
        command.add_argument("--preregistration", required=True)
    for name in ("collect", "holdout"):
        sub.choices[name].add_argument("--universe")
        sub.choices[name].add_argument("--tickers", help="comma-separated subset, smoke runs only")
    sub.choices["collect"].add_argument("--horizon", required=True)
    for name in ("stage0", "reproduce", "evaluate", "features"):
        sub.choices[name].add_argument("--rows", nargs="+", required=True)
    evaluate_parser = sub.choices["evaluate"]
    evaluate_parser.add_argument("--stage0", required=True)
    evaluate_parser.add_argument("--reproduction", required=True)
    evaluate_parser.add_argument("--reproduction-note")
    sub.choices["holdout"].add_argument("--evaluate", required=True)
    emit = sub.add_parser("emit-registry")
    emit.add_argument("--holdout-json", required=True)
    emit.add_argument("--registry", required=True)
    emit.add_argument("--run-date", required=True)
    return parser


COMMANDS = {"collect": _cmd_collect, "stage0": _cmd_stage0, "reproduce": _cmd_reproduce,
            "evaluate": _cmd_evaluate, "features": _cmd_features, "holdout": _cmd_holdout,
            "emit-registry": _cmd_emit}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    COMMANDS[args.cmd](args)
    print(f"v131 {args.cmd} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
