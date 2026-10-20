#!/usr/bin/env python3
"""v176 deploy gate, production half: list every open PARTIAL plan as JSON.

READ-ONLY. Piped into the running (pre-v176) bot container:

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" \
        < scripts/ops/partial_runner_rows.py > "$SCRATCH/v176-partial-rows.txt"

It imports nothing v176 adds (the old image has none of it), writes no row
and moves no stop. The last stdout line is the JSON list that
scripts/ops/giveback_deploy_gate.py reads.
"""
from __future__ import annotations

import json

FIELDS = ("plan_id", "ticker", "direction", "entry_price", "stop_loss", "tp1",
          "working_stop", "runner_high_close")


def _price(price_fn, ticker):
    try:
        value = price_fn(ticker)
    except Exception:          # a dead feed leaves the price unknown, never stops the list
        return None
    return float(value) if value is not None else None


def partial_rows(plans, price_fn) -> list[dict]:
    """One dict per PARTIAL plan, in the store's order, with its last price."""
    rows = []
    for plan in plans:
        if str(plan.status) != "PARTIAL":
            continue
        row = {name: getattr(plan, name) for name in FIELDS}
        row["plan_id"] = str(row["plan_id"])
        row["last_price"] = _price(price_fn, plan.ticker)
        rows.append(row)
    return rows


def main() -> int:
    from swingbot.core.marketdata.data import get_current_price
    from swingbot.core.planning.plan_store import PlanStore
    plans = PlanStore().open_plans()
    rows = partial_rows(plans, lambda t: get_current_price(t, allow_stale=False))
    print(json.dumps(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
