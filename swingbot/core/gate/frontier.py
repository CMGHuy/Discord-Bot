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


def propose_tier_cuts(frontier_rows) -> dict | None:
    """Mechanical, pre-registered: A+ = lowest cut whose wilson_lb >= 0.80
    with n >= 59 (the G1 math: where ~95% observed WR PROVES > 90% is
    N >= 59); A = lowest cut with wr >= baseline + 5 pts and n >= 30;
    B stays at the configured default (baseline behavior). Returns a
    PROPOSAL -- never applied to config by code."""
    if not frontier_rows:
        return None
    baseline = next((r for r in frontier_rows if r["cut"] == 0), frontier_rows[0])
    if baseline["wr"] is None:
        return None
    aplus = next((r for r in frontier_rows
                  if r["wilson_lb"] >= 0.80 and r["n_kept"] >= 59), None)
    a_row = next((r for r in frontier_rows
                  if r["wr"] is not None and r["wr"] >= baseline["wr"] + 5.0
                  and r["n_kept"] >= 30), None)
    if aplus is None and a_row is None:
        return None
    return {"aplus_cut": aplus["cut"] if aplus else None,
            "a_cut": a_row["cut"] if a_row else None,
            "baseline_wr": baseline["wr"],
            "evidence": {"aplus": aplus, "a": a_row},
            "note": "b stays at the configured default (baseline tier); "
                    "cuts are proposals — apply via the settings page only"}


def plateau_report(frontier_rows, chosen_cut: int,
                   wr_tol: float = 2.0, exp_tol: float = 0.03,
                   span: int = 10) -> dict:
    """A trustworthy cut sits on a plateau: neighbors within +/-span score
    points hold WR within wr_tol pts and expectancy within exp_tol R.
    A spiky choice gets redirected to the widest plateau's center."""
    by_cut = {r["cut"]: r for r in frontier_rows if r["wr"] is not None}
    chosen = by_cut.get(chosen_cut)
    if chosen is None:
        return {"on_plateau": False, "recommend": None, "reason": "cut has no data"}
    neighbors = [r for c, r in by_cut.items()
                 if c != chosen_cut and abs(c - chosen_cut) <= span]
    stable = [r for r in neighbors
              if abs(r["wr"] - chosen["wr"]) <= wr_tol
              and abs((r["expectancy_r"] or 0) - (chosen["expectancy_r"] or 0)) <= exp_tol]
    on_plateau = neighbors and len(stable) == len(neighbors)
    if on_plateau:
        return {"on_plateau": True, "recommend": chosen_cut, "reason": None}
    # widest run of mutually-stable consecutive cuts -> its center
    cuts = sorted(by_cut)
    best_run, run = [], []
    for cut in cuts:
        if run and not (abs(by_cut[cut]["wr"] - by_cut[run[0]]["wr"]) <= wr_tol):
            run = []
        run = run + [cut]
        if len(run) > len(best_run):
            best_run = run
    recommend = best_run[len(best_run) // 2] if best_run else None
    return {"on_plateau": False, "recommend": recommend,
            "reason": f"cut {chosen_cut} is a spike; widest plateau centers at {recommend}"}


def write_proposal(proposal: dict, kind: str = "gate-tiers") -> str:
    """data/tuning_proposals/{ts}-{kind}.json (cockpit C36 shape)."""
    import os
    import time

    import swingbot.config as config
    from swingbot.core.jsonio import atomic_write_json
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(config.DATA_DIR, "tuning_proposals", f"{ts}-{kind}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write_json(path, {"kind": kind, "created_at": ts, "payload": proposal})
    return path
