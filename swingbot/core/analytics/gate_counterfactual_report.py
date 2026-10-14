"""v147: the gate-counterfactual report -- what blocked candidates would have done.

V147-13 holds the pre-registered statistics (spec § Pre-registered verdict):
distinct setups, the one population rule, the blocked - taken difference with a
paired week-cluster bootstrap, v146's two-sided p, BH over the five verdict
cells, and the EARNS / COSTS / INCONCLUSIVE / WAITING rule. V147-15 adds
`build_report`. `build_report` writes through the light `swingbot.core.infra.gate_counterfactual_store` (atomic `os.replace` lives there); `load_report` is that module's, re-exported.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict, namedtuple

import numpy as np

from swingbot.core.analytics import gate_counterfactual_inputs as inputs
from swingbot.core.backtesting.instrument import stats
from swingbot.core.infra import gate_counterfactual_store as store
from swingbot.core.infra.gate_counterfactual_store import load_report  # noqa: F401  -- re-export for v150
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
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


# --- V147-15: the report -------------------------------------------------------------

NOTE_NO_TRAIN_RS = "no TRAIN population"
NOTE_NO_PLAN = "no verdict — no-plan"
NOTE_CELLS = (("rs", "train", NOTE_NO_TRAIN_RS), ("no_qualifying_target", "live", NOTE_NO_PLAN),
              ("no_qualifying_target", "train", NOTE_NO_PLAN))
EMPTY_TAKEN_NOTES = {("compression", "train"): "no TRAIN taken arm — no as-of earnings archive"}
IN_SAMPLE_CELLS = frozenset({("compression", "train")})
ROW_GATES = ("rs", "risk_cap", "no_qualifying_target", "compression")
SOURCE_FAMILY = {"strategy": "strategy", "confluence": "confluence", "short_lane": "confluence"}
LIMITATIONS = (
    "Portfolio state: every blocked candidate is simulated as a lone trade; the portfolio heat and "
    "correlated-cluster caps are ignored, and heat at block time is not stored (null).",
    "Gap floor: simulate_exit books a stop at the stop price, so a gap through the stop reads -1.0R; "
    "counterfactual losses on gaps are understated, so the blocked arm's losses are understated.",
    "R is per-trade risk-normalised (every trade sized to 1R). risk_cap rows add dollar_risk -- the "
    "outcome in units of the 2% dollar cap -- and are over-cap: never a tradable alternative.",
    "TRAIN compression is in-sample (v119 fitted the gate on TRAIN); TRAIN has no as-of earnings "
    "archive, so its taken arm is expected to be empty and the cell carries a note, not a verdict.",
    "Live rows from 2026-10 sit inside the 2026 holdout; a follow-on screen built on a live verdict "
    "must name a holdout this report has not seen.",
    "Short-lane blocked rows are scoped against confluence taken plans (issued plans carry no lane "
    "marker); live taken plans store no signal-day close, so their re-walk is never re-anchored.",
    "A verdict changes nothing: GATE COSTS licenses one Stage -2 screen under a new idea name (for "
    "risk_cap, with the partner); no closed pre-registration is reopened.",
)


def _blocked_rows(rows, key: str, population: str) -> list:
    return [r for r in rows
            if r["population"] == population and r["arm"] == "blocked" and cell_key(r) == key]


def _taken_match(row, key: str, population: str, scope: set) -> bool:
    if row["population"] != population or row["arm"] != "taken" or row["gate"] != CELL_GATE[key]:
        return False
    if key == "compression" and row["strategy"] != COMPRESSION_SHORT:
        return False
    return (SOURCE_FAMILY[row["source"]], row["direction"]) in scope


def _arms(rows, key: str, population: str) -> tuple[list, list]:
    """(blocked, taken) distinct setups of one cell, the taken arm in the blocked arm's scope."""
    blocked = distinct_setups(_blocked_rows(rows, key, population))
    scope = {(SOURCE_FAMILY[r["source"]], r["direction"]) for r in blocked}
    taken = distinct_setups([r for r in rows if _taken_match(r, key, population, scope)])
    return blocked, taken


def _note_for(key: str, population: str, n: int, taken_n: int) -> str | None:
    if n < VERDICT_FLOOR:
        return None
    if taken_n == 0:
        return EMPTY_TAKEN_NOTES.get((key, population), f"no {population.upper()} taken arm")
    if taken_n < VERDICT_FLOOR:
        return f"taken arm below the floor ({taken_n} distinct filled setups < {VERDICT_FLOOR})"
    return None


def _evaluate(rows, key: str, population: str) -> dict:
    blocked, taken = _arms(rows, key, population)
    n, taken_n = len(_filled(blocked)), len(_filled(taken))
    note = _note_for(key, population, n, taken_n)
    eligible = note is None and n >= VERDICT_FLOOR
    return {"gate": key, "population": population, "n": n, "taken_n": taken_n, "note": note,
            "reading": difference_reading(blocked, taken) if eligible else None}


def _cell(state: dict, q, today: str) -> dict:
    """One verdict cell (v150 shape); the record is seeded here and frozen by the store."""
    reading = state["reading"]
    verdict = WAITING if state["note"] else classify(reading, q, state["n"])
    latest = None if reading is None else {"difference": reading["difference"], "ci_low": reading["ci_low"],
                                           "ci_high": reading["ci_high"], "q": q, "p": reading["p"]}
    record = None if verdict == WAITING else {"verdict": verdict, "date": today, "n": state["n"]}
    return {"gate": state["gate"], "population": state["population"], "verdict": verdict, "n": state["n"],
            "taken_n": state["taken_n"], "verdict_of_record": record, "latest": latest,
            "in_sample": (state["gate"], state["population"]) in IN_SAMPLE_CELLS, "note": state["note"]}


def _note_cell(key: str, population: str, note: str) -> dict:
    return {"gate": key, "population": population, "verdict": WAITING, "n": 0, "taken_n": 0,
            "verdict_of_record": None, "latest": None, "in_sample": False, "note": note}


def _cells(rows, today: str) -> list[dict]:
    states = [_evaluate(rows, key, population) for key, population in CELLS]
    qvalues = family_qvalues([s["reading"]["p"] if s["reading"] else None for s in states])
    cells = [_cell(state, q, today) for state, q in zip(states, qvalues)]
    return cells + [_note_cell(key, population, note) for key, population, note in NOTE_CELLS]


def _near_miss(key: str, blocked) -> dict:
    band = NEAR_MISS_BANDS.get(key)
    if band is None:
        return {"near_miss_n": None, "near_miss_exp_r": None, "rest_n": None, "rest_exp_r": None}
    inside = [r["margin"] is not None and abs(r["margin"]) <= band for r in blocked]
    near = [r for r, flag in zip(blocked, inside) if flag]
    rest = [r for r, flag in zip(blocked, inside) if not flag]
    return {"near_miss_n": len(near), "near_miss_exp_r": arm_stats(near)["exp_r"],
            "rest_n": len(rest), "rest_exp_r": arm_stats(rest)["exp_r"]}


def _dollar_risk(key: str, blocked) -> float | None:
    if key != "risk_cap":
        return None
    return _mean(r["dollar_risk"] for r in _filled(blocked) if r.get("dollar_risk") is not None)


def _row(key: str, reason, population: str, blocked, taken) -> dict:
    """One detail row: gate x reason x population (v150 shape)."""
    b, t = arm_stats(blocked), arm_stats(taken)
    return {"gate": key, "reason": reason, "population": population,
            "blocked_n": b["n"], "no_plan_n": b["no_plan_n"], "fill_rate": b["fill_rate"],
            "blocked_exp_r": b["exp_r"], "blocked_win_rate": b["win_rate"],
            "taken_n": t["filled_n"], "taken_exp_r": t["exp_r"], "taken_win_rate": t["win_rate"],
            "taken_realised_exp_r": _mean(r["realised_r"] for r in taken if r.get("realised_r") is not None),
            **_near_miss(key, blocked), "dollar_risk": _dollar_risk(key, blocked),
            "over_cap": key == "risk_cap", "in_sample": (key, population) in IN_SAMPLE_CELLS}


def _rows_for(rows, key: str, population: str) -> list[dict]:
    blocked, taken = _arms(rows, key, population)
    by_reason = defaultdict(list)
    for row in blocked:
        by_reason[row["reason"]].append(row)
    return [_row(key, reason, population, members, taken)
            for reason, members in sorted(by_reason.items(), key=lambda item: str(item[0]))]


def _report_rows(rows) -> list[dict]:
    return [row for population in ("live", "train") for key in ROW_GATES
            for row in _rows_for(rows, key, population)]


def _live_window(rows) -> str | None:
    dates = sorted(r["signal_date"] for r in rows if r["population"] == "live")
    return f"{dates[0]}..{dates[-1]}" if dates else None


def build_report(*, train_rows=None, live_blocked=None, live_taken=None, today=None, write=True,
                 path=None) -> dict:
    """The gate-counterfactual report (v150 shape); written through the light store unless write=False."""
    if train_rows is None:
        train_rows = inputs.load_train_rows(inputs.default_train_paths())
    if live_blocked is None or live_taken is None:
        live_blocked, live_taken = inputs.load_live()
    rows = [*train_rows, *live_blocked, *live_taken]
    now = dt.datetime.now(dt.timezone.utc)
    today = today or now.date().isoformat()
    result = {"generated_at": now.isoformat(timespec="seconds"), "live_window": _live_window(rows),
              "bh_family": len(CELLS), "seed": BOOTSTRAP_SEED, "limitations": list(LIMITATIONS),
              "cells": _cells(rows, today), "rows": _report_rows(rows)}
    return store.write_report(result, path) if write else result
