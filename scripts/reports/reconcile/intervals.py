"""v232 statistics (spec ### Statistics): one-arm week-cluster intervals and the cells around them.

Intervals come only from instrument/stats.week_cluster_bootstrap (clarification 7: an empty
baseline arm and a statistic over the drawn rows), clustered by entry week. Tag means and
distributions carry no interval.
"""
from __future__ import annotations

import dataclasses
from collections import Counter, defaultdict

import numpy as np

from autopsy import cells as autopsy_cells
from swingbot.core.backtesting.instrument import stats

from . import layer1, layer1_run, raw_bars, records, tags

INTERVAL_LABEL = "descriptive; under-covers below 20 clusters"
_GAP_KEYS = ("gap_r", "gap_pct", "exit_vs_open_r", "exit_vs_stop_r")


@dataclasses.dataclass(frozen=True)
class WeekItem:
    entry_date: str
    value: float


def _r4(value):
    return None if value is None else round(float(value), 4)


def _draw_mean(_baseline, draw) -> float | None:
    return float(np.mean([item.value for item in draw])) if draw else None


def _week_totals(items) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for item in items:
        totals[stats.iso_week_key(item.entry_date)] += item.value
    return dict(totals)


def one_arm_interval(items, *, n_resamples: int, seed: int) -> tuple[float, float] | None:
    """2.5/97.5 percentiles of the week-resampled mean; None below two entry weeks."""
    items = list(items)
    if len(_week_totals(items)) < 2:
        return None
    draws = stats.week_cluster_bootstrap([], items, _draw_mean,
                                         n_resamples=n_resamples, seed=seed)
    if draws.size == 0:
        return None
    low, high = np.percentile(draws, [2.5, 97.5])
    return float(low), float(high)


@dataclasses.dataclass(frozen=True)
class CellStats:
    n: int
    weeks: int
    total: float
    mean: float | None
    largest_week_share: float | None
    interval: tuple[float, float] | None
    thin: bool

    def to_dict(self) -> dict:
        return {"n": self.n, "weeks": self.weeks, "total": _r4(self.total),
                "mean": _r4(self.mean), "largest_week_share": _r4(self.largest_week_share),
                "interval": None if self.interval is None else [_r4(v) for v in self.interval],
                "thin": self.thin}


def _largest_share(week_totals: dict) -> float | None:
    spread = sum(abs(v) for v in week_totals.values())
    return max(abs(v) for v in week_totals.values()) / spread if spread else None


def cell_stats(items, *, n_resamples: int, seed: int, with_interval: bool = True) -> CellStats:
    """N, entry weeks, total, mean, the largest week's share, the interval and the thin flag."""
    items = list(items)
    weeks = _week_totals(items)
    total = float(sum(item.value for item in items))
    interval = (one_arm_interval(items, n_resamples=n_resamples, seed=seed)
                if with_interval else None)
    return CellStats(n=len(items), weeks=len(weeks), total=total,
                     mean=total / len(items) if items else None,
                     largest_week_share=_largest_share(weeks), interval=interval,
                     thin=autopsy_cells.is_thin(len(items), len(weeks)))


def _scored(rows, fill_model: str) -> list:
    return [r for r in rows if r.scored and fill_model in r.values]


def confusion(rows, fill_model: str) -> dict[str, dict[str, int]]:
    """Live outcome class (rows) against the exit-only class (columns), zeros kept."""
    grid = {live: dict.fromkeys(layer1.OUTCOME_CLASSES, 0) for live in layer1.OUTCOME_CLASSES}
    for row in _scored(rows, fill_model):
        grid[row.live_class][row.values[fill_model]["exit_only_class"]] += 1
    return grid


def distribution(values) -> dict:
    """Median and 90th percentile of the non-None values."""
    kept = [float(v) for v in values if v is not None]
    if not kept:
        return {"n": 0, "median": None, "p90": None}
    return {"n": len(kept), "median": _r4(np.median(kept)), "p90": _r4(np.percentile(kept, 90))}


def tag_means(rows, fill_model: str) -> dict[str, dict]:
    """Per tag: how many scored rows carry it and their mean exit effect (no interval)."""
    scored = _scored(rows, fill_model)
    out = {}
    for tag in tags.TAGS:
        exits = [r.effects[fill_model]["exit"] for r in scored if tag in r.tags]
        out[tag] = {"n": len(exits), "mean_exit_effect": _r4(np.mean(exits)) if exits else None}
    return out


def _yes_no(rows, fill_model: str) -> dict:
    got = [r.would_fill.get(fill_model) for r in rows]
    return {"yes": sum(g is True for g in got), "no": sum(g is False for g in got),
            "unknown": sum(g is None for g in got)}


def _refusal_counts(rows) -> dict:
    return {"refusals": {k: sum(r.refusal == k for r in rows) for k in layer1_run.REFUSALS},
            "refused_tickers": {k: sorted({r.ticker for r in rows if r.refusal == k})
                                for k in raw_bars.REFUSALS}}


def _source_counts(rows) -> dict:
    """Where each row's live R came from (layer1.R_SOURCES), zeros kept."""
    return {k: sum(r.r_source == k for r in rows) for k in layer1.R_SOURCES}


def population(rows) -> dict:
    """Class counts, refusals (refused tickers listed), unfilled reasons, live R sources
    and would-fill."""
    unfilled = [r for r in rows if r.klass == "unfilled"]
    reasons = Counter(r.unfilled_reason or "unknown" for r in unfilled)
    return {"classes": {k: sum(r.klass == k for r in rows) for k in records.CLASSES},
            "scored": sum(r.scored for r in rows), **_refusal_counts(rows),
            "unfilled_reasons": dict(sorted(reasons.items())),
            "r_source": _source_counts(rows),
            "would_fill": {m: _yes_no(unfilled, m) for m in layer1.FILL_MODELS}}


def _parts(rows, attr: str, i: int) -> dict:
    return distribution([getattr(r, attr)[i] for r in rows if getattr(r, attr) is not None])


def slip(rows) -> dict:
    """entry_slip and poll_fill (bps, R) and the gap detail, as distributions over scored rows."""
    scored = [r for r in rows if r.scored]
    out = {f"{attr}_{unit}": _parts(scored, attr, i)
           for attr in ("entry_slip", "poll_fill") for i, unit in enumerate(("bps", "r"))}
    out.update({k: distribution([r.gap[k] for r in scored if r.gap]) for k in _GAP_KEYS})
    return out


def ledger_cells(rows, *, n_resamples: int, seed: int) -> dict:
    """Live net R per ledger over closed and manual rows (live figures only, no interval)."""
    book = [r for r in rows if r.klass in ("closed", "manual") and r.r_live_net is not None]
    return {name: cell_stats([WeekItem(r.entry_date, r.r_live_net) for r in book
                              if r.ledger == name],
                             n_resamples=n_resamples, seed=seed, with_interval=False).to_dict()
            for name in sorted({r.ledger for r in book})}


def cell_count(report: dict) -> int:
    """Means shown: effect cells and tag means per block, plus layer 2 sub-reasons."""
    n = 0
    for by_era in report.get("layer1", {}).values():
        for by_model in by_era.values():
            for block in by_model.values():
                n += len(block.get("effects", {})) + len(block.get("tags", {}))
    for by_era in report.get("selection", {}).values():
        for cell in by_era.values():
            n += len(cell["live_only"]["by_bucket"]) + len(cell["replay_only"]["by_reason"])
    return n
