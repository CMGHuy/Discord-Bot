#!/usr/bin/env python3
"""v176 deploy gate, local half: each open runner's stop before and after the
first post-deploy tick, from the rows scripts/ops/partial_runner_rows.py
printed on production.

    python scripts/ops/giveback_deploy_gate.py --rows "$SCRATCH/v176-partial-rows.txt" --pct 5.0

Mirrors PlanManager's first tick (V176-2): the tick is folded into the
extreme first, then the give-back tightens the current stop (working_stop,
else the runner floor). The chandelier may tighten further on the same
tick; this table shows the give-back's move only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.planning.exit_sim import giveback_stop, runner_floor, tighter_stop  # noqa: E402

COLUMNS = ("plan", "ticker", "dir", "entry", "TP1", "floor", "current stop", "E stored",
           "E used", "give-back stop", "new stop", "last", "moves", "closes on tick 1")


def load_rows(text: str) -> list[dict]:
    """The JSON list on the last line that starts with '[' (log noise above is ignored)."""
    lines = [line for line in text.splitlines() if line.lstrip().startswith("[")]
    if not lines:
        raise ValueError("no JSON row list in the rows output")
    return json.loads(lines[-1])


def _extreme_used(stored, last, is_bull):
    if last is None:
        return stored
    if stored is None:
        return float(last)
    return max(stored, last) if is_bull else min(stored, last)


def _past(last, stop, is_bull):
    if last is None:
        return None
    return bool(last <= stop) if is_bull else bool(last >= stop)


def gate_row(row: dict, pct: float) -> dict:
    """``row`` plus floor, current_stop, extreme_used, giveback_stop, new_stop, moves, past."""
    is_bull = row["direction"] == "bullish"
    floor = runner_floor(float(row["entry_price"]), float(row["tp1"]))
    current = float(row["working_stop"]) if row["working_stop"] is not None else floor
    extreme = _extreme_used(row["runner_high_close"], row["last_price"], is_bull)
    giveback = giveback_stop(float(extreme), pct, row["direction"]) if extreme is not None else None
    new_stop = tighter_stop(current, giveback, is_bull)
    return {**row, "floor": floor, "current_stop": current, "extreme_used": extreme,
            "giveback_stop": giveback, "new_stop": new_stop,
            "moves": new_stop != current, "past": _past(row["last_price"], new_stop, is_bull)}


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return f"{value:.2f}"


def _cells(r: dict) -> list[str]:
    return [str(r["plan_id"])[:8], r["ticker"], "long" if r["direction"] == "bullish" else "short",
            *(_fmt(r[k]) for k in ("entry_price", "tp1", "floor", "current_stop",
                                   "runner_high_close", "extreme_used", "giveback_stop",
                                   "new_stop", "last_price", "moves")),
            "unknown" if r["past"] is None else _fmt(r["past"])]


def render_table(rows: list[dict]) -> str:
    if not rows:
        return "No open PARTIAL plans: the give-back moves no stop at deploy."
    out = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    out += ["| " + " | ".join(_cells(r)) + " |" for r in rows]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", required=True, type=Path)
    parser.add_argument("--pct", type=float, default=5.0)
    args = parser.parse_args(argv)
    rows = load_rows(args.rows.read_text(encoding="utf-8"))
    print(render_table([gate_row(row, args.pct) for row in rows]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
