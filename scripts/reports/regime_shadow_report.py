"""v244: the bear-regime shadow report (v239 spec § Evidence the shadow produces).

    python scripts/reports/regime_shadow_report.py [--trades trades.json]

Joins closed MAIN-ledger trades with their entry_context.regime_action and
prints N, WR, ExpR and sum R per action: would_veto / caution /
pullback_watch / none (LONG), aligned / none (SHORT). Below MIN_N a row prints
"too few". This is LIVE MONITORING, NOT A SCREEN: no figure from it licenses a
gate (the B9 screen does; pooled-numbers skill).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.tracking import ledger as _ledger  # noqa: E402
from swingbot.core.tracking.performance import closed_r_multiple  # noqa: E402

MIN_N = 30
ROWS = (("LONG", "would_veto"), ("LONG", "caution"), ("LONG", "pullback_watch"),
        ("LONG", "none"), ("SHORT", "aligned"), ("SHORT", "none"))
_SIDE = {"bullish": "LONG", "bearish": "SHORT"}
NO_STAMPS = "No stamped trades yet: no closed main-ledger trade carries regime_action."


def _key(trade: dict) -> tuple[str, str] | None:
    ctx = trade.get("entry_context") or {}
    key = (_SIDE.get(trade.get("direction")), ctx.get("regime_action"))
    return key if key in ROWS else None


def _stats(direction: str, action: str, rs: list[float]) -> dict:
    n = len(rs)
    return {"direction": direction, "action": action, "n": n,
            "win_rate": round(100.0 * sum(1 for r in rs if r > 0) / n, 2) if n else 0.0,
            "expectancy_r": round(sum(rs) / n, 4) if n else 0.0,
            "sum_r": round(sum(rs), 2), "too_few": n < MIN_N}


def summarise(trades: Iterable[dict]) -> list[dict]:
    buckets: dict[tuple[str, str], list[float]] = {key: [] for key in ROWS}
    for trade in trades:
        key = _key(trade)
        r = closed_r_multiple(trade) if key else None
        if r is not None:
            buckets[key].append(r)
    return [_stats(direction, action, buckets[(direction, action)]) for direction, action in ROWS]


def coverage(trades: Iterable[dict]) -> dict:
    trades = list(trades)
    stamped = [t for t in trades if _key(t)]
    return {"closed": len(trades), "stamped": len(stamped),
            "no_r": sum(1 for t in stamped if closed_r_multiple(t) is None)}


def _line(row: dict) -> str:
    head = f"{row['direction']:<6}{row['action']:<16}{row['n']:>5}"
    if row["too_few"]:
        return f"{head}  too few"
    return (f"{head}  WR {row['win_rate']:>6.2f}%  ExpR {row['expectancy_r']:+.2f}R"
            f"  sum {row['sum_r']:+.2f}R")


def _coverage_lines(cover: dict) -> list[str]:
    lines = [f"closed {cover['closed']} · stamped {cover['stamped']} · no R {cover['no_r']}"]
    if cover["stamped"] == 0:
        lines.append(NO_STAMPS)
    return lines + [""]


def render(rows: list[dict], cover: dict | None = None) -> str:
    lines = ["Bear-regime shadow report -- live monitoring, not a screen.",
             f"Rows below N = {MIN_N} show no figures. No figure here licenses a gate.", ""]
    if cover is not None:
        lines += _coverage_lines(cover)
    lines.append(f"{'side':<6}{'action':<16}{'N':>5}")
    lines += [_line(row) for row in rows]
    return "\n".join(lines) + "\n"


def _trades(path: str | None) -> list[dict]:
    """Closed main-ledger trades, from a JSON file when ``path`` is given."""
    from swingbot.core.analytics.scope import CLOSED_STATUSES, closed_only
    if path:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
        return [t for t in loaded
                if t.get("status", "closed") in CLOSED_STATUSES and _ledger.is_main(t)]
    from swingbot.core.tracking.performance import TradeLog
    return closed_only(TradeLog().get_trades(status=None, limit=None, ledger="main"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bear-regime shadow report (monitoring only).")
    parser.add_argument("--trades", help="JSON list of trade dicts instead of the trades table")
    args = parser.parse_args(argv)
    trades = _trades(args.trades)
    sys.stdout.write(render(summarise(trades), coverage(trades)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
