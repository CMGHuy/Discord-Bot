#!/usr/bin/env python3
"""v128 Stage 0 effect printer and Stage 1 judge under BOTH gates (script layer).

Stage 1 scores each candidate's pooled fold-train arms (selection blob top level,
2018-06-01..2022-12-31) with acceptance.evaluate(stage="walkforward") -- clause 6
replaced by the frozen v128 baseline reading -- and
acceptance_harvest.evaluate_harvest(stage="walkforward"). Permutation is
validation-only and SKIPPED there. Frozen in
docs/superpowers/results/2026-10-02-v128-fvg-preregistration.md.

Run: python scripts/backtest/fvg_select.py select --arm off=logs/v128/selection-off.json ... --mechanism off=logs/v128/mechanism-selection-off.json ...
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "backtest")]

from fvg_attribution import CANDIDATES  # noqa: E402
from validate_component import load_arms, load_clause, with_mechanism_clause  # noqa: E402
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES, delta_expectancy_r, delta_standardised_win_rate, evaluate  # noqa: E402
from swingbot.core.backtesting.acceptance_harvest import evaluate_harvest  # noqa: E402
from swingbot.core.backtesting.backtest_wf import plateau_report  # noqa: E402

ELIGIBILITY_V72 = ("win_rate", "profit_floor", "geometry", "volume", "mechanism")
ELIGIBILITY_V92 = ("expectancy_gain", "win_rate_floor", "volume")
K_GRID = (1.0, 1.5, 2.0)
K_CELL = {1.0: "disp-1.0", 1.5: "disp-1.5", 2.0: "disp-2.0"}
SELECTED, NO_ELIGIBLE, SPIKE = "selected", "no-eligible-cell", "spike"


@dataclass(frozen=True)
class Cell:
    cid: str
    eligible: bool
    delta_expectancy_r: float | None
    delta_win_rate_pp: float | None
    alert_cut_pct: float | None
    failed: tuple


def _failed(result, names, prefix) -> tuple:
    return tuple(f"{prefix}:{name}" for name in names if result.clause(name).verdict != "PASS")


def evaluate_cell(cid, baseline, component, mechanism, *, refused, n_resamples, seed) -> Cell:
    v72 = with_mechanism_clause(evaluate(baseline, component, stage="walkforward",
                                         n_resamples=n_resamples, seed=seed), mechanism)
    v92 = evaluate_harvest(baseline, component, stage="walkforward", n_resamples=n_resamples, seed=seed)
    failed = (("refused",) if refused else ()) + _failed(v72, ELIGIBILITY_V72, "v72") + _failed(v92, ELIGIBILITY_V92, "v92")
    return Cell(cid, not failed, delta_expectancy_r(baseline, component),
                delta_standardised_win_rate(baseline, component), v72.clause("volume").value, failed)


def _neighbours(k) -> list:
    i = K_GRID.index(k)
    return [K_GRID[j] for j in (i - 1, i + 1) if 0 <= j < len(K_GRID)]


def k_plateau(cells, k) -> dict:
    """plateau_report on pooled fold-train dExpR AND at least one eligible grid neighbour."""
    values = [cells[K_CELL[v]].delta_expectancy_r for v in K_GRID]
    needed = [values[K_GRID.index(v)] for v in [k, *_neighbours(k)]]
    if any(value is None for value in needed):
        return {"param": "FVG_DISPLACEMENT_ATR_K", "adopted": k, "is_plateau": False,
                "eligible_neighbour": False, "passes": False, "note": "missing dExpR"}
    report = plateau_report("FVG_DISPLACEMENT_ATR_K", list(K_GRID),
                            [0.0 if v is None else v for v in values], k)
    report["eligible_neighbour"] = any(cells[K_CELL[v]].eligible for v in _neighbours(k))
    report["passes"] = bool(report["is_plateau"] and report["eligible_neighbour"])
    return report


def _rank_key(cell) -> tuple:
    k = math.inf if cell.cid == "off" else CANDIDATES[cell.cid][1]
    return (-round(cell.delta_expectancy_r, 4), round(cell.alert_cut_pct, 2), cell.cid == "off", k)


def select(cells) -> dict:
    plateaus = {K_CELL[k]: k_plateau(cells, k) for k in K_GRID if cells[K_CELL[k]].eligible}
    pool = [cells["off"]] if cells["off"].eligible else []
    pool += [cells[cid] for cid, report in plateaus.items() if report["passes"]]
    if pool:
        verdict, winner = SELECTED, min(pool, key=_rank_key).cid
    else:
        verdict, winner = (SPIKE if any(c.eligible for c in cells.values()) else NO_ELIGIBLE), None
    return {"verdict": verdict, "winner": winner, "plateaus": plateaus,
            "cells": {cid: asdict(cell) for cid, cell in cells.items()}}


def _pairs(values) -> dict:
    out = {}
    for item in values:
        cid, _, path = item.partition("=")
        if cid not in CANDIDATES or not path:
            raise SystemExit(f"expected CID=PATH with CID in {sorted(CANDIDATES)}, got {item!r}")
        out[cid] = path
    if set(out) != set(CANDIDATES):
        raise SystemExit(f"need all four candidates {sorted(CANDIDATES)}, got {sorted(out)}")
    return out


def _render(result) -> str:
    lines = [f"### Stage 1 selection -- verdict **{result['verdict']}**, winner `{result['winner']}`", "",
             "| Cell | Eligible | dExpR | dWR (pp) | Alert cut % | Failed |", "|---|---|---|---|---|---|"]
    for cid, cell in result["cells"].items():
        dexp = "n/a" if cell["delta_expectancy_r"] is None else f"{cell['delta_expectancy_r']:+.4f}"
        dwr = "n/a" if cell["delta_win_rate_pp"] is None else f"{cell['delta_win_rate_pp']:+.2f}"
        lines.append(f"| {cid} | {cell['eligible']} | {dexp} | {dwr} | {cell['alert_cut_pct']} | "
                     f"{', '.join(cell['failed']) or '-'} |")
    lines += ["", "Plateau (k only; `off` is eligible on clauses alone):", ""]
    lines += [f"- `{cid}`: is_plateau={r['is_plateau']}, eligible_neighbour={r['eligible_neighbour']}, "
              f"passes={r['passes']}" for cid, r in result["plateaus"].items()]
    return "\n".join(lines) + "\n"


def cmd_select(args) -> int:
    arms, mechanisms = _pairs(args.arm), _pairs(args.mechanism)
    loaded = {cid: load_arms(path) for cid, path in arms.items()}
    baselines = {json.dumps([asdict(t) for t in base]) for base, _ in loaded.values()}
    if len(baselines) != 1:
        print("refused:baseline-drift -- the four candidate arms carry different baselines.", file=sys.stderr)
        return 1
    cells = {cid: evaluate_cell(cid, base, comp, load_clause(mechanisms[cid]), refused=cid in (args.refused or []),
                                n_resamples=args.resamples, seed=args.seed)
             for cid, (base, comp) in loaded.items()}
    result = select(cells)
    text = _render(result)
    print(text)
    for path, body in ((args.out_md, text), (args.out_json, json.dumps(result, indent=1))):
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(body, encoding="utf-8")
    return 0 if result["verdict"] == SELECTED else 1


def cmd_effects(args) -> int:
    baseline, component = load_arms(args.arms)
    print(json.dumps({"delta_win_rate_pp": delta_standardised_win_rate(baseline, component),
                      "delta_expectancy_r": delta_expectancy_r(baseline, component),
                      "baseline_n": len(baseline), "component_n": len(component)}))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    effects = sub.add_parser("effects"); effects.add_argument("--arms", required=True)
    sel = sub.add_parser("select")
    sel.add_argument("--arm", action="append", required=True); sel.add_argument("--mechanism", action="append", required=True)
    sel.add_argument("--refused", action="append", choices=sorted(CANDIDATES), default=None)
    sel.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES); sel.add_argument("--seed", type=int, default=42)
    sel.add_argument("--out-json", default=None); sel.add_argument("--out-md", default=None)
    args = parser.parse_args(argv)
    return {"effects": cmd_effects, "select": cmd_select}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
