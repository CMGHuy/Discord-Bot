"""v229 statistics: per-alert ExpR, week-clustered paired deltas, calibration.

Spec sections "Statistic" and "Calibration clause". ExpR is per alert: a
skipped arm-B plan scores 0R. Deltas are bootstrapped by ISO week of the
ET entry date (trades are held up to five sessions, so neighbouring dates
share bars). Calibration compares path classes, never R: the simulator races
to TP1 only and cannot reproduce the live scale-out's R.
"""
from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace

import numpy as np
import pandas as pd

from swingbot.core.backtesting.instrument.stats import (
    WEEK_BOOTSTRAP_RESAMPLES,
    WEEK_BOOTSTRAP_SEED,
    iso_week_key,
    week_cluster_bootstrap,
)

LOWER_PCT = 2.5           # one-sided 97.5% bound: Bonferroni split of the gate's 95% over two arms
CALIBRATION_MIN = 0.80
CLASSES = ("loss", "scratch", "win")
_SIM_CLASS = {"win": "win", "loss": "loss", "scratch": "scratch"}
_LIVE_EXACT = {"win": "win", "scratch": "scratch", "loss": "loss", "stop": "loss"}
_SPLITS = (("fill_above", "fill_above_entry", True), ("fill_below", "fill_above_entry", False),
           ("with_events", "event_day", True), ("without_events", "event_day", False))


def live_class(reason) -> str | None:
    """Path class of a live close reason; None when it is not a stop/scratch/TP1 path."""
    text = (reason or "").strip().lower()
    if text.startswith("tp1"):
        return "win"
    return _LIVE_EXACT.get(text)


def sim_class(outcome) -> str | None:
    """Path class of a simulated outcome; timeout, no_bars and skipped have none."""
    return _SIM_CLASS.get(outcome or "")


def arm_r(pair: dict, arm: str, field: str = "r_net") -> float:
    """The arm's R for this plan; a leg not taken scores 0R."""
    leg = pair["arms"][arm]
    return float(leg[field]) if leg["taken"] else 0.0


def _mean(values) -> float | None:
    values = list(values)
    return float(np.mean(values)) if values else None


def _deltas(pairs, arm: str) -> list[float]:
    return [arm_r(p, arm) - arm_r(p, "C") for p in pairs]


def week_count(pairs) -> int:
    return len({iso_week_key(p["entry_date"]) for p in pairs})


def arm_summary(pairs, arm: str) -> dict:
    pairs = list(pairs)
    taken = [p["arms"][arm] for p in pairs if p["arms"][arm]["taken"]]
    wins = sum(1 for leg in taken if leg["outcome"] == "win")
    rs = [arm_r(p, arm) for p in pairs]
    return {"n": len(pairs), "taken": len(taken), "wins": wins,
            "win_rate": wins / len(taken) if taken else None,
            "exp_r": _mean(rs), "total_r": float(sum(rs)),
            "exp_r_gross": _mean(arm_r(p, arm, "r_gross") for p in pairs)}


def _items(pairs, arm: str) -> list[SimpleNamespace]:
    return [SimpleNamespace(entry_date=p["entry_date"], r=arm_r(p, arm)) for p in pairs]


def _mean_difference(baseline, component) -> float | None:
    if not baseline:
        return None
    return float(np.mean([c.r for c in component]) - np.mean([b.r for b in baseline]))


def delta_stats(pairs, arm: str, *, n_resamples: int = WEEK_BOOTSTRAP_RESAMPLES,
                seed: int = WEEK_BOOTSTRAP_SEED) -> dict:
    """Mean per-plan delta of ``arm`` over C, with the week-clustered bound and p."""
    pairs = list(pairs)
    weeks = week_count(pairs)
    out = {"arm": arm, "n": len(pairs), "weeks": weeks,
           "mean": _mean(_deltas(pairs, arm)), "lower": None, "p": None}
    if weeks < 2:              # the bootstrap would return a zero-width interval
        return out
    draws = week_cluster_bootstrap(_items(pairs, "C"), _items(pairs, arm), _mean_difference,
                                   n_resamples=n_resamples, seed=seed)
    if draws.size:
        out["lower"] = float(np.percentile(draws, LOWER_PCT))
        out["p"] = float((draws <= 0).mean())
    return out


def delta_over_taken(pairs, arm: str) -> dict:
    taken = [p for p in pairs if p["arms"][arm]["taken"]]
    return {"n": len(taken), "mean": _mean(_deltas(taken, arm))}


def _live_r(pair: dict) -> float | None:
    value = pair["live"].get("r_realized")
    return None if value is None else float(value)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Pearson on average ranks; None under 3 points or with a constant side."""
    if len(xs) < 3:
        return None
    rx = pd.Series(xs, dtype=float).rank().to_numpy()
    ry = pd.Series(ys, dtype=float).rank().to_numpy()
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def _information(pairs: list[dict]) -> dict:
    both = [(arm_r(p, "C"), _live_r(p)) for p in pairs if _live_r(p) is not None]
    return {"mean_r_c": _mean(arm_r(p, "C") for p in pairs),
            "mean_live_r": _mean(live for _, live in both),
            "spearman": _spearman([sim for sim, _ in both], [live for _, live in both])}


def calibration(pairs) -> dict:
    """3x3 path-class table of simulated control (outer) against live (inner)."""
    pairs = list(pairs)
    table = {sim: {live: 0 for live in CLASSES} for sim in CLASSES}
    excluded = 0
    for pair in pairs:
        sim, live = sim_class(pair["arms"]["C"]["outcome"]), live_class(pair["live"].get("reason"))
        if sim is None or live is None:
            excluded += 1
            continue
        table[sim][live] += 1
    n = sum(sum(row.values()) for row in table.values())
    agreement = sum(table[c][c] for c in CLASSES) / n if n else None
    return {"table": table, "n": n, "agreement": agreement,
            "calibrated": agreement is not None and agreement >= CALIBRATION_MIN,
            "excluded": excluded, **_information(pairs)}


def _cell(group: list[dict]) -> dict:
    return {"n": len(group), "d_a": _mean(_deltas(group, "A")), "d_b": _mean(_deltas(group, "B"))}


def weekly_deltas(pairs) -> list[dict]:
    by_week: dict[str, list[dict]] = defaultdict(list)
    for pair in pairs:
        by_week[iso_week_key(pair["entry_date"])].append(pair)
    return [{"week": week, **_cell(group)} for week, group in sorted(by_week.items())]


def split_deltas(pairs) -> dict:
    """d_A and d_B by fill side of the plan's entry and by event day (None in neither)."""
    pairs = list(pairs)
    return {name: _cell([p for p in pairs if p["tradeability"].get(key) is value])
            for name, key, value in _SPLITS}


def skip_summary(pairs) -> dict:
    skipped = [p for p in pairs if not p["arms"]["B"]["taken"]]
    return {"skipped": len(skipped), "control_r_of_skipped": _mean(arm_r(p, "C") for p in skipped)}
