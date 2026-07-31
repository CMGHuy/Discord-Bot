"""WR-by-decile, frontier, tier-cut proposals — pure functions over
gate-annotated trade records ({gate_score, gate_tier, outcome,
r_multiple, ...})."""
from __future__ import annotations

from swingbot.core.gate.wr_math import wilson_lower_bound


def _closed(trades):
    return [t for t in trades if t.get("outcome") in ("win", "loss")
            and t.get("gate_score") is not None]


def _stats(rows) -> dict:
    wins = sum(1 for t in rows if t["outcome"] == "win")
    n = len(rows)
    return {
        "n": n,
        "wr": round(100.0 * wins / n, 1) if n else None,
        "wilson_lb": round(wilson_lower_bound(wins, n), 4) if n else 0.0,
        "expectancy_r": (round(sum(t.get("r_multiple", 0.0) for t in rows) / n, 3)
                         if n else None),
    }


def wr_by_decile(trades) -> list[dict]:
    closed = _closed(trades)
    if not closed:
        return []
    out = []
    for decile in range(10):
        lo, hi = decile * 10.0, (decile + 1) * 10.0
        rows = [t for t in closed
                if lo <= t["gate_score"] < hi or (decile == 9 and t["gate_score"] == 100.0)]
        out.append({"decile": decile, **_stats(rows)})
    return out
