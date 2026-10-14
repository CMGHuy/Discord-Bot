#!/usr/bin/env python3
"""v147: how far is each live gate-counterfactual cell from its verdict floor?

Read-only. Counts `gate_rejections` rows per cell x cf_status and the distinct
filled setups of each live verdict cell against the floor (30). Installed
weekly on the VM by install_gate_counterfactual_cron.sh; it decides nothing,
resolves nothing and removes nothing. When every live cell is past the floor,
the next Claude session runs scripts/reports/gate_counterfactual_report.py
and records the reading.

    docker compose exec -T bot python scripts/ops/gate_counterfactual_progress.py
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from swingbot.core.analytics.gate_counterfactual_inputs import live_blocked_rows  # noqa: E402
from swingbot.core.analytics.gate_counterfactual_report import (  # noqa: E402
    VERDICT_FLOOR, cell_key, distinct_setups)

LIVE_CELLS = ("rs", "risk_cap", "compression")
STATUSES = ("pending", "filled", "no-fill", "no-plan", "no-data")


def _span(records) -> str:
    dates = sorted(str(r.get("signal_date")) for r in records if r.get("signal_date"))
    return f", signal dates {dates[0]}..{dates[-1]}" if dates else ""


def _cell_line(key: str, counts: Counter, filled: int | None) -> str:
    statuses = " ".join(f"{status}={counts[status]}" for status in STATUSES)
    if filled is None:
        return f"  {key:<22}{statuses}  (no-plan: no verdict)"
    ready = " READY" if filled >= VERDICT_FLOOR else ""
    return f"  {key:<22}{statuses}  distinct filled {filled}/{VERDICT_FLOOR}{ready}"


def progress_lines(records) -> list[str]:
    """Plain-text progress of every cell toward its verdict floor."""
    records = list(records)
    counts = defaultdict(Counter)
    for record in records:
        counts[cell_key(record)][record.get("cf_status")] += 1
    filled = Counter(cell_key(row) for row in distinct_setups(live_blocked_rows(records))
                     if row["cf_status"] == "filled")
    lines = [f"gate_rejections: {len(records)} rows{_span(records)}"]
    lines += [_cell_line(key, counts[key], filled[key]) for key in LIVE_CELLS]
    lines.append(_cell_line("no_qualifying_target", counts["no_qualifying_target"], None))
    ready = all(filled[key] >= VERDICT_FLOOR for key in LIVE_CELLS)
    lines.append("ALL LIVE VERDICT CELLS PAST THE FLOOR: "
                 + ("yes -- run scripts/reports/gate_counterfactual_report.py and record it" if ready else "no"))
    return lines


def main() -> int:
    from swingbot.core.db.repositories.gate_rejections import gate_rejections_repo
    try:
        records = gate_rejections_repo().list_since(None)
    except Exception as exc:  # a read-only check reports and exits non-zero; it never retries or repairs
        print(f"gate_rejections unreadable: {exc!r}")
        return 1
    for line in progress_lines(records):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
