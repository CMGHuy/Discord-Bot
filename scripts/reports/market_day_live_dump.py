#!/usr/bin/env python3
"""v141: dump the live book and scan telemetry as ONE JSON line. Read-only.

Standalone on purpose: production does not carry the v141 branch, so this
file imports only modules production already runs and is piped over ssh::

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" \
        < scripts/reports/market_day_live_dump.py > data/market_day_live.json

It writes nothing on the box. Tickers are deliberately left out -- the report
buckets by day and direction and needs none.
"""
from __future__ import annotations

import json


def trade_record(trade: dict) -> dict:
    from swingbot.core.analytics.metrics import r_multiple
    from swingbot.core.tracking.performance import primary_strategy_label
    return {
        "opened_at": trade.get("opened_at"),
        "closed_at": trade.get("closed_at"),
        "direction": trade.get("direction"),
        "status": trade.get("status"),
        "r": r_multiple(trade),
        "strategy": primary_strategy_label(trade),
    }


def scan_record(row: dict) -> dict | None:
    """One scan row; None for the file's non-scan rows (deploy markers)."""
    if not isinstance(row.get("duration_s"), (int, float)):
        return None
    return {"at": row.get("at"), "signals": row.get("signals", 0),
            "alerts": row.get("alerts", 0), "funnel": row.get("short_funnel") or {}}


def build_dump(trades: list[dict], telemetry_rows: list[dict]) -> dict:
    from swingbot.core.analytics.scope import closed_only
    scans = [scan for row in telemetry_rows if (scan := scan_record(row)) is not None]
    return {"trades": [trade_record(t) for t in closed_only(trades)], "scans": scans}


def _telemetry_rows() -> list[dict]:
    from swingbot.core.scanning.telemetry import TELEMETRY_PATH
    rows = []
    try:
        with open(TELEMETRY_PATH, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
    except OSError:
        pass
    return rows


def main() -> None:
    from swingbot.core.tracking.performance import TradeLog
    trades = TradeLog().get_trades(status=None, limit=None)
    print(json.dumps(build_dump(trades, _telemetry_rows())))


if __name__ == "__main__":
    main()
