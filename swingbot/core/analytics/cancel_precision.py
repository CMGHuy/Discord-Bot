"""v188: cancelled-plan precision -- figures, intervals, baseline and payload (pure).

Spec: docs/superpowers/specs/2026-10-23-v188-cancelled-plan-precision-design.md.
Precision = right / (right + wrong); R avoided = right x 1.0R; R missed = the
wrong rows' full target R; net R = avoided - missed. Unresolved rows are marked
to market into `unresolved_r` and never enter precision or net R. Intervals are
the 95% percentile band of `week_cluster_bootstrap` over ISO-week sums, so a
draw costs about one item per week.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from swingbot.core.analytics.cancel_replay import OUTCOMES, last_bar_day
from swingbot.core.analytics.cancel_rows import (ENTRY_MODELS, OTHER, REASONS, CancelRow,
                                                 Loader, cancel_rows, filled_rows,
                                                 manual_count)
from swingbot.core.backtesting.instrument.stats import iso_week_key, week_cluster_bootstrap
from swingbot.core.market.strategy_types import LEGACY_HORIZONS

SMALL_N = 10
CI_PCT = (2.5, 97.5)
CAPTION = "Hypothetical replay, before commissions, slippage and tax"
RISK_CAP_LABEL = "Outcome of the skipped setup, unaffordable at the cap"
TP1_NOTE = ("A TP1 hit counts the full target R with no partial exit; "
            "the bot does not bank winners in full.")
RULE_CHANGES: tuple[tuple[str, str], ...] = (
    ("2026-09-28", "v104 structural stops and stop-ceiling scope"),
    ("2026-10-14", "v139 stored stop ceiling"),
    ("2026-10-23", "v183 gap-aware short sizing"),
)
_ORIGINS = ("regular", "next_session")
_DIRECTIONS = ("long", "short")


@dataclass(frozen=True)
class _Week:
    entry_date: str
    right: int
    wrong: int
    net: float


def _r(value: float | None) -> float | None:
    return None if value is None else round(float(value), 2)


def _scored(rows: list[CancelRow]) -> list[CancelRow]:
    return [r for r in rows if r.excluded is None and r.replay is not None]


def _weeks(scored: list[CancelRow]) -> list[_Week]:
    by = defaultdict(list)
    for row in scored:
        if row.replay.outcome in ("right", "wrong"):
            by[iso_week_key(row.entry_date)].append(row)
    out = []
    for members in by.values():
        right = sum(1 for m in members if m.replay.outcome == "right")
        missed = sum(m.replay.r for m in members if m.replay.outcome == "wrong")
        out.append(_Week(members[0].entry_date, right, len(members) - right, right - missed))
    return out


def _precision_stat(_baseline, draw):
    decided = sum(w.right + w.wrong for w in draw)
    return sum(w.right for w in draw) / decided if decided else None


def _net_stat(_baseline, draw):
    return sum(w.net for w in draw)


def _interval(weeks: list[_Week], statistic, digits: int) -> list[float] | None:
    if not weeks:
        return None
    draws = week_cluster_bootstrap([], weeks, statistic)
    if draws.size == 0:
        return None
    lo, hi = np.percentile(draws, CI_PCT)
    return [round(float(lo), digits), round(float(hi), digits)]


def _tally(scored: list[CancelRow]) -> tuple[dict, float, float, int]:
    """(outcome counts, R missed, unresolved mark-to-market R, ties)."""
    counts = {o: sum(1 for r in scored if r.replay.outcome == o) for o in OUTCOMES}
    missed = sum(r.replay.r for r in scored if r.replay.outcome == "wrong")
    drift = sum(r.replay.r for r in scored
                if r.replay.outcome == "unresolved" and r.replay.r is not None)
    return counts, missed, drift, sum(1 for r in scored if r.replay.tie)


def figure(rows: list[CancelRow], *, with_interval: bool = True) -> dict:
    scored = _scored(rows)
    counts, missed, drift, ties = _tally(scored)
    n = counts["right"] + counts["wrong"]
    weeks = _weeks(scored) if with_interval and n else []
    return {
        "n": n, "total": len(rows), "excluded": len(rows) - len(scored),
        "precision": round(counts["right"] / n, 4) if n else None,
        "precision_ci": _interval(weeks, _precision_stat, 4),
        "r_avoided": _r(counts["right"]), "r_missed": _r(missed),
        "net_r": _r(counts["right"] - missed),
        "net_r_ci": _interval(weeks, _net_stat, 2),
        "counts": counts, "unresolved_r": _r(drift), "ties": ties,
        "small_n": n < SMALL_N,
    }


def baseline_population(filled: list[CancelRow], scored: list[CancelRow]) -> list[CancelRow]:
    """Filled rows whose fill day lies in the scored cancels' window and whose
    (strategy, horizon) pair occurs among them."""
    if not scored:
        return []
    first = min(r.cancel_day for r in scored)
    last = max(r.cancel_day for r in scored)
    pairs = {(r.strategy, r.horizon_key) for r in scored}
    return [r for r in filled
            if first <= r.cancel_day <= last and (r.strategy, r.horizon_key) in pairs]


# -- payload -------------------------------------------------------------------

def _cached(loader: Loader):
    """A loader that reads each ticker once, and the frames it returned."""
    frames: dict = {}

    def load(ticker: str):
        if ticker not in frames:
            frames[ticker] = loader(ticker)
        return frames[ticker]

    return load, frames


def _data_as_of(frames: dict) -> str | None:
    days = [d for d in (last_bar_day(f) for f in frames.values()) if d is not None]
    return max(days).isoformat() if days else None


def _window(scored: list[CancelRow]) -> dict:
    if not scored:
        return {"first": None, "last": None}
    days = [r.cancel_day for r in scored]
    return {"first": min(days).isoformat(), "last": max(days).isoformat()}


def _rule_changes(window: dict) -> list[dict]:
    first, last = window["first"], window["last"]
    if first is None:
        return []
    return [{"date": day, "label": label} for day, label in RULE_CHANGES
            if first <= day <= last]


def _cards(trigger: list[CancelRow], rows: list[CancelRow]) -> dict:
    def by_reason(reason: str) -> dict:
        return figure([r for r in trigger if r.reason == reason])

    return {
        "risk_cap": by_reason("risk_cap"),
        "risk_cap_fill": figure([r for r in rows if r.entry_model == "cancel_fill"]),
        "invalidated": by_reason("invalidated"),
        "expired": by_reason("expired"),
        OTHER: by_reason(OTHER),
    }


def _split(rows: list[CancelRow], attr: str, order: tuple[str, ...]) -> dict:
    present = {getattr(r, attr) for r in rows}
    keys = [k for k in order if k in present]
    keys += sorted(k for k in present if k not in order)
    return {k: figure([r for r in rows if getattr(r, attr) == k]) for k in keys}


def _splits(pooled: list[CancelRow]) -> dict:
    return {"origin": _split(pooled, "origin", _ORIGINS),
            "direction": _split(pooled, "direction", _DIRECTIONS),
            "horizon": _split(pooled, "horizon_key", LEGACY_HORIZONS)}


def _replay_json(row: CancelRow) -> dict:
    rep = row.replay
    if row.excluded is not None or rep is None:
        return {"outcome": None, "r": None, "tie": False, "exit_date": None}
    return {"outcome": rep.outcome, "r": _r(rep.r), "tie": rep.tie,
            "exit_date": rep.exit_day.isoformat() if rep.exit_day else None}


def _row_json(row: CancelRow) -> dict:
    return {
        "plan_id": row.plan_id, "ticker": row.ticker, "strategy": row.strategy,
        "horizon_key": row.horizon_key, "direction": row.direction, "origin": row.origin,
        "reason": row.reason, "raw_reason": row.raw_reason,
        "cancel_date": row.cancel_day.isoformat(), "entry_model": row.entry_model,
        "entry_source": row.entry_source, "entry": row.entry, "stop": row.stop,
        "tp1": row.tp1, "badge": row.badge, "stop_ceiling_pct": row.stop_ceiling_pct,
        "cap_size_pct": row.cap_size_pct, **_replay_json(row), "excluded": row.excluded,
    }


def _newest_first(rows: list[CancelRow]) -> list[CancelRow]:
    return sorted(rows, key=lambda r: (-r.cancel_day.toordinal(), r.plan_id,
                                       ENTRY_MODELS.index(r.entry_model)))


def precision_payload(plans: list, loader: Loader, *, generated_at: str) -> dict:
    load, frames = _cached(loader)
    rows = cancel_rows(plans, load)
    trigger = [r for r in rows if r.entry_model == "trigger"]
    pooled = [r for r in trigger if r.reason in REASONS]
    scored = _scored(pooled)
    baseline = baseline_population(filled_rows(plans, load), scored)
    window = _window(scored)
    return {
        "generated_at": generated_at, "data_as_of": _data_as_of(frames),
        "caption": CAPTION, "risk_cap_label": RISK_CAP_LABEL, "tp1_note": TP1_NOTE,
        "small_n_threshold": SMALL_N, "window": window,
        "rule_changes": _rule_changes(window),
        "out_of_scope": {"manual": manual_count(plans)},
        "headline": {"all": figure(pooled),
                     "without_risk_cap": figure([r for r in pooled if r.reason != "risk_cap"])},
        "baseline": figure(baseline),
        "cards": _cards(trigger, rows),
        "splits": _splits(pooled),
        "rows": [_row_json(r) for r in _newest_first(rows)],
    }
