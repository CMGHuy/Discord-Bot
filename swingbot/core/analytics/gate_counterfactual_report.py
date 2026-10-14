"""v147: the gate-counterfactual report -- what blocked candidates would have done.

V147-13 holds the pre-registered statistics (spec § Pre-registered verdict):
distinct setups, the one population rule, the blocked - taken difference with a
paired week-cluster bootstrap, v146's two-sided p, BH over the five verdict
cells, and the EARNS / COSTS / INCONCLUSIVE / WAITING rule. V147-15 adds
`build_report`. The file itself is written and read by the light
`swingbot.core.infra.gate_counterfactual_store` (this module imports numpy).
"""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict, namedtuple

import numpy as np

from swingbot.core.backtesting.instrument import stats
from swingbot.core.market.session import nyse_calendar
from swingbot.core.planning.params import DEFAULT_EXPIRY_BARS

# Frozen by the spec before any row existed. Never tuned.
VERDICT_FLOOR = 30                       # distinct filled blocked setups per cell
Q_MAX = 0.10
BOOTSTRAP_RESAMPLES = 10_000             # read at call time
BOOTSTRAP_SEED = 42
NEAR_MISS_BANDS = {"rs": 5.0, "risk_cap": 0.5}   # absolute cut-offs; compression has no margin
CELLS = (("rs", "live"), ("risk_cap", "live"), ("compression", "live"),
         ("risk_cap", "train"), ("compression", "train"))

EARNS, COSTS, INCONCLUSIVE, WAITING = "GATE EARNS", "GATE COSTS", "INCONCLUSIVE", "WAITING"
VERDICTS = (EARNS, COSTS, INCONCLUSIVE, WAITING)
# cell key -> the `gate` field the cell's rows (blocked and taken) carry
CELL_GATE = {"rs": "rs", "risk_cap": "plan_rejected", "no_qualifying_target": "plan_rejected",
             "compression": "compression"}

_WeekSum = namedtuple("_WeekSum", "entry_date total n")


def two_sided_bootstrap_p(draws) -> float:
    """v146's two-sided, +1-corrected bootstrap p of a difference against 0."""
    values = np.asarray(draws, dtype=float)
    if values.size == 0:
        raise ValueError("two_sided_bootstrap_p needs at least one draw")
    tail = min(int((values <= 0).sum()), int((values >= 0).sum())) + 1
    return min(1.0, 2.0 * tail / (len(values) + 1))


def cell_key(row) -> str:
    """The report cell a row belongs to: rs, risk_cap, compression, no_qualifying_target or other.

    A taken confluence row (gate plan_rejected, reason None) is the risk_cap cell's taken arm.
    Any other plan_rejected reason (another plan's gate: v135 headroom, v139
    stop_beyond_confluence_ceiling / risk_sizing) is "other" -- in no verdict cell, never
    pooled into risk_cap."""
    gate = row["gate"]
    if gate != "plan_rejected":
        return gate
    return {"no_qualifying_target": "no_qualifying_target", "risk_cap": "risk_cap",
            None: "risk_cap"}.get(row.get("reason"), "other")


def _window(row) -> int:
    bars = row.get("expiry_bars")
    return int(bars) if bars is not None else DEFAULT_EXPIRY_BARS


def _sessions_apart(earlier: str, later: str) -> int:
    first, second = dt.date.fromisoformat(earlier[:10]), dt.date.fromisoformat(later[:10])
    span = nyse_calendar().sessions_between(first, second)
    return span if span is not None else (second - first).days


def _setup_key(row) -> tuple:
    return (row["population"], row["arm"], cell_key(row), row["ticker"], row["strategy"],
            row["horizon"], row["direction"])


def _collapse(members: list) -> list:
    """Members sorted by date; keep each anchor, drop rows inside the anchor's pending window."""
    kept, anchor = [], None
    for row in members:
        if anchor is None or _sessions_apart(anchor["signal_date"], row["signal_date"]) > _window(anchor):
            anchor = row
            kept.append(row)
    return kept


def distinct_setups(rows) -> list[dict]:
    """One row per distinct setup: the earliest row of each run of re-blocks (spec § Distinct setups)."""
    groups = defaultdict(list)
    for row in sorted(rows, key=lambda r: r["signal_date"]):
        groups[_setup_key(row)].append(row)
    kept = [row for members in groups.values() for row in _collapse(members)]
    return sorted(kept, key=lambda r: (r["signal_date"], r["ticker"]))


def _mean(values) -> float | None:
    values = [float(v) for v in values]
    return sum(values) / len(values) if values else None


def _filled(rows) -> list:
    return [row for row in rows if row["cf_status"] == "filled"]


def arm_stats(rows) -> dict:
    """Counts, fill rate and the filled-only ExpR / win rate of one arm (the one population rule)."""
    counts = Counter(row["cf_status"] for row in rows)
    filled = _filled(rows)
    tried = counts["filled"] + counts["no-fill"]
    return {"n": len(rows), "filled_n": len(filled), "no_fill_n": counts["no-fill"],
            "no_plan_n": counts["no-plan"], "no_data_n": counts["no-data"],
            "fill_rate": counts["filled"] / tried if tried else None,
            "exp_r": _mean(row["cf_r"] for row in filled),
            "win_rate": _mean(1.0 if row["win"] else 0.0 for row in filled)}


def _week_sums(rows) -> list:
    """One (Monday ISO date, sum of R, count) per ISO week of entry."""
    totals = defaultdict(lambda: [0.0, 0])
    for row in rows:
        year, week, _ = dt.date.fromisoformat(str(row["entry_date"])[:10]).isocalendar()
        bucket = totals[(year, week)]
        bucket[0] += float(row["cf_r"])
        bucket[1] += 1
    return [_WeekSum(dt.date.fromisocalendar(year, week, 1).isoformat(), total, n)
            for (year, week), (total, n) in totals.items()]


def _mean_gap(blocked_draw, taken_draw) -> float | None:
    blocked_n, taken_n = sum(o.n for o in blocked_draw), sum(o.n for o in taken_draw)
    if not blocked_n or not taken_n:
        return None
    return (sum(o.total for o in blocked_draw) / blocked_n
            - sum(o.total for o in taken_draw) / taken_n)


def difference_reading(blocked, taken, *, seed: int = BOOTSTRAP_SEED) -> dict | None:
    """Blocked ExpR - taken ExpR over filled rows, its 95% week-cluster interval and two-sided p.

    None when either arm has no filled row or no bootstrap draw is defined."""
    blocked_filled, taken_filled = _filled(blocked), _filled(taken)
    if not blocked_filled or not taken_filled:
        return None
    draws = stats.week_cluster_bootstrap(_week_sums(blocked_filled), _week_sums(taken_filled),
                                         _mean_gap, n_resamples=BOOTSTRAP_RESAMPLES, seed=seed)
    if draws.size == 0:
        return None
    low, high = np.percentile(draws, [2.5, 97.5])
    point = _mean(r["cf_r"] for r in blocked_filled) - _mean(r["cf_r"] for r in taken_filled)
    return {"difference": float(point), "ci_low": float(low), "ci_high": float(high),
            "p": two_sided_bootstrap_p(draws)}


def family_qvalues(pvalues) -> list[float]:
    """BH q over the fixed five-cell family; a cell without an eligible reading enters as p = 1.0."""
    values = list(pvalues)
    if len(values) != len(CELLS):
        raise ValueError(f"the BH family is the {len(CELLS)} verdict cells, got {len(values)} p-values")
    return stats.bh_qvalues([1.0 if p is None else float(p) for p in values])


def classify(reading, q, n) -> str:
    """The pre-registered three-way verdict, or WAITING below the floor / without a reading."""
    if n < VERDICT_FLOOR or reading is None:
        return WAITING
    if q is None or q >= Q_MAX:
        return INCONCLUSIVE
    if reading["ci_high"] < 0:
        return EARNS
    if reading["ci_low"] > 0:
        return COSTS
    return INCONCLUSIVE
