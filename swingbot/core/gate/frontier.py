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


def _days_between(a: str, b: str) -> int:
    import datetime as dt
    try:
        return (dt.date.fromisoformat(b[:10]) - dt.date.fromisoformat(a[:10])).days
    except ValueError:
        return 1


def frontier(trades, cuts=range(0, 101, 5)) -> list[dict]:
    """The honest tradeoff curve: WR gained vs signals lost vs expectancy,
    at every score cut."""
    closed = _closed(trades)
    total = len(closed)
    if total == 0:
        return []
    dates = sorted(str(t.get("entry_date", "")) for t in closed if t.get("entry_date"))
    months = 1.0
    if len(dates) >= 2 and dates[0] and dates[-1]:
        span_days = max((_days_between(dates[0], dates[-1])), 1)
        months = max(span_days / 30.44, 1.0)
    out = []
    for cut in cuts:
        kept = [t for t in closed if t["gate_score"] >= cut]
        stats = _stats(kept)
        out.append({"cut": cut,
                    "n_kept": stats["n"],
                    "pct_kept": round(100.0 * stats["n"] / total, 1),
                    "wr": stats["wr"], "wilson_lb": stats["wilson_lb"],
                    "expectancy_r": stats["expectancy_r"],
                    "trades_per_month": round(stats["n"] / months, 1)})
    return out


def best_cut(frontier_rows, min_n: int, max_signal_loss_pct: float) -> dict | None:
    """Highest-WR cut satisfying the G2 constraints; None when nothing
    qualifies (an allowed, reportable outcome -- never force a cut)."""
    eligible = [r for r in frontier_rows
                if r["n_kept"] >= min_n
                and (100.0 - r["pct_kept"]) <= max_signal_loss_pct
                and r["wr"] is not None]
    if not eligible:
        return None
    return max(eligible, key=lambda r: (r["wr"], r["cut"]))
