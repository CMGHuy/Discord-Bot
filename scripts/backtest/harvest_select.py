#!/usr/bin/env python3
"""v123 Stage 1: harvest selection over a grid of stamped selection-stage arms."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "backtest")]

from swingbot.core.backtesting.acceptance import ArmTrade, bootstrap_delta, delta_expectancy_r  # noqa: E402
from swingbot.core.backtesting.backtest_wf import plateau_report  # noqa: E402


def _row(value, baseline, component, refused, cluster="ticker"):
    res = bootstrap_delta(baseline, component, delta_expectancy_r, cluster=cluster)
    eligible = value not in refused and res.lo is not None and res.lo > 0
    return {"value": value, "n": len(component), "delta_r": res.point, "lo95": res.lo, "eligible": eligible}


def _qualifies(rows, i, param, grid, deltas):
    if not rows[i]["eligible"]:
        return False
    neighbours = [j for j in (i - 1, i + 1) if 0 <= j < len(rows)]
    plateau = plateau_report(param, grid, deltas, grid[i])["is_plateau"]
    return plateau and any(rows[j]["eligible"] for j in neighbours)


def _pick(pool, less_aggressive):
    best = max(round(r["delta_r"], 4) for r in pool)
    tied = [r["value"] for r in pool if round(r["delta_r"], 4) == best]
    return max(tied) if less_aggressive == "larger" else min(tied)


def select(cells, *, param, less_aggressive, refused=(), cluster="ticker") -> dict:
    rows = [_row(v, b, c, set(refused), cluster) for v, b, c in cells]
    grid, deltas = [r["value"] for r in rows], [r["delta_r"] or 0.0 for r in rows]
    for i, row in enumerate(rows):
        row["plateau"] = _qualifies(rows, i, param, grid, deltas)
    if not any(r["eligible"] for r in rows):
        return {"verdict": "NO_ELIGIBLE_CELL", "selected": None, "rows": rows}
    pool = [r for r in rows if r["plateau"]]
    if not pool:
        return {"verdict": "NO_PLATEAU", "selected": None, "rows": rows}
    pick = _pick(pool, less_aggressive)
    return {"verdict": "SELECTED", "selected": pick, "rows": rows}


def _load(path):
    from swingbot.core.backtesting.arms.provenance import check_stamp
    from measure_arms import cached_universe
    blob = json.loads(Path(path).read_text())
    token = check_stamp(blob, funnel_stage="mde", full_universe=cached_universe())
    if token:
        raise SystemExit(f"{token} -- {path}. Budget intact.")
    return [ArmTrade(**r) for r in blob["baseline"]], [ArmTrade(**r) for r in blob["component"]]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--param", required=True)
    p.add_argument("--cell", action="append", required=True)
    p.add_argument("--less-aggressive", choices=("larger", "smaller"), required=True)
    p.add_argument("--mde-refused", action="append", type=float, default=[])
    p.add_argument("--out-json", type=Path, required=True)
    args = p.parse_args(argv)
    cells = [(float(v), *_load(path)) for v, _, path in (c.partition("=") for c in args.cell)]
    out = select(cells, param=args.param, less_aggressive=args.less_aggressive, refused=args.mde_refused)
    args.out_json.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0 if out["verdict"] == "SELECTED" else 1


if __name__ == "__main__":
    sys.exit(main())
