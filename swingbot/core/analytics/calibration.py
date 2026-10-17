"""Live-trade calibration checks: does the quality score actually predict
win rate (score_deciles), how does each confidence level's live win rate
compare (level_calibration), and has a VALIDATED strategy's live win rate
drifted below its out-of-sample number (badge_drift)? Pure functions, no
I/O -- callers supply `closed` and (for badge_drift) the already-loaded
registry list.

v32 Task 11: tier_calibration() (A/B/C tier, quality.py's own 0-100
quality_score bands) is retired in favour of level_calibration() (1-5
confidence level, the number that actually gates whether an alert fires).
Unlike tier, level has no design-band-vs-live-win-rate "ok" verdict here:
tier's EXPECTED_BAND came from quality.py's own pre-v32 design; there is no
equivalent measured expected-win-rate-per-level in this codebase (v32's own
VALIDATION run measured legacy vs unified gating, not a per-level band), so
inventing one would be exactly the kind of ungrounded number this repo's
TRAIN-derived-weights discipline exists to prevent. level_calibration()
reports n/win_rate/expectancy per level, same shape as score_deciles(),
without a pass/fail column.

v164: match_live_rows() buckets the live population of every registry row
(both ledgers, regular lane, entered on or after EXPR_WATCH_START) for the
pre-registered live loss watch; LW2's live_loss_watch() turns the buckets
into rows. Day boundaries are Berlin dates read from BERLIN_TZ directly:
this module must never import tracking.retrospective (it imports us).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict, namedtuple
from dataclasses import dataclass

import numpy as np

from swingbot.core.analytics import metrics
from swingbot.core.backtesting.instrument import stats
from swingbot.core.market.session import BERLIN_TZ
from swingbot.core.market.strategy_types import horizon_order
from swingbot.core.tracking import origin


def _decile_label(score: float) -> str:
    idx = min(int(score) // 10, 9)
    lo = idx * 10
    hi = 100 if idx == 9 else lo + 9
    return f"{lo}-{hi}"


def _decile_floor(label: str) -> int:
    return int(label.split("-")[0])


def score_deciles(closed: list[dict]) -> list[dict]:
    """Bucket closed trades with a known quality_score into 10-wide score
    deciles (0-9 .. 80-89, plus a combined 90-100) and report each
    bucket's win rate/expectancy -- the live counterpart to whatever
    offline backtest calibration produced the score in the first place.
    Trades without a quality_score (legacy rows, or any trade logged
    without a plan in hand) are silently excluded, not bucketed as
    "unknown" -- there is no decile for "no score"."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in closed:
        score = t.get("quality_score")
        if score is None:
            continue
        groups[_decile_label(score)].append(t)

    rows = [
        {"decile": label, "n": len(trades),
         "win_rate": metrics.win_rate(trades), "expectancy_r": metrics.expectancy_r(trades)}
        for label, trades in groups.items()
    ]
    rows.sort(key=lambda r: _decile_floor(r["decile"]))
    return rows


LEVELS = (1, 2, 3, 4, 5)


def level_calibration(closed: list[dict]) -> list[dict]:
    """One row per confidence level (1-5, always all five regardless of
    whether any trades exist yet) reporting live win rate and expectancy --
    the level-based successor to tier_calibration(), with no expected-band
    verdict (see this module's docstring for why)."""
    rows = []
    for level in LEVELS:
        trades = [t for t in closed if t.get("confidence_level") == level]
        n = len(trades)
        wr = metrics.win_rate(trades)
        er = metrics.expectancy_r(trades)
        rows.append({"level": level, "n": n, "win_rate": wr, "expectancy_r": er})
    return rows


DRIFT_LIVE_N_FLOOR = 20         # below this, live win rate is too noisy to judge decay from
DRIFT_THRESHOLD_POINTS = 10.0   # live WR must fall more than this many points below OOS WR


def badge_drift(closed: list[dict], registry_entries: list[dict]) -> list[dict]:
    """Compare each VALIDATED strategy's committed out-of-sample win rate
    against its live win rate so far, flagging real edge decay.

    The alert rule below is PRE-REGISTERED (Global Constraint / design
    decision #5 in the cockpit-v3 plan): live_n >= 20 and
    live_wr < oos_wr - 10.0. This threshold must never be loosened or
    tightened after actually observing live drift -- that would be
    tuning on the very data the rule exists to police. If it needs to
    change, that is a deliberate, documented design decision made BEFORE
    looking at what triggered it, not a reaction to it.

    One row per distinct strategy name across `registry_entries` that has
    at least one VALIDATED-status record -- WEAK-status rows are excluded
    entirely (there is no "decay" concept for a strategy that was never
    validated to begin with), and duplicate strategy names (e.g. one row
    per horizon) collapse to the first VALIDATED occurrence encountered.
    """
    from swingbot.core.market.levels import strategy_family

    rows = []
    seen: set[str] = set()
    for r in registry_entries:
        if r.get("status") != "VALIDATED":
            continue
        strat = r["strategy"]
        if strat in seen:
            continue
        seen.add(strat)

        oos_n = r.get("n", 0)
        oos_wr = r.get("win_rate", 0.0)

        # Match trades by strategy name, or by the canonical family of any
        # source that contributed to the trade's target/stop (e.g. "Fibonacci"
        # matches a trade with target_sources containing "Fib 61.8%").
        live = []
        for t in closed:
            if t.get("strategy") == strat:
                live.append(t)
                continue
            sources = (t.get("target_sources") or []) + (t.get("stop_sources") or [])
            if any(strategy_family(src) == strat for src in sources):
                live.append(t)

        live_n = len(live)
        live_wr = metrics.win_rate(live)
        delta = (live_wr - oos_wr) if live_wr is not None else None
        alert = bool(live_n >= DRIFT_LIVE_N_FLOOR and live_wr is not None
                     and live_wr < oos_wr - DRIFT_THRESHOLD_POINTS)

        rows.append({"strategy": strat, "oos_n": oos_n, "oos_wr": oos_wr,
                     "oos_run_date": r.get("run_date", ""),
                     "live_n": live_n, "live_wr": live_wr, "delta_wr": delta,
                     "drift_alert": alert})
    return rows


# ---------------------------------------------------------------------------
# v164 live loss watch, D1: population and matching (pre-registered)
# ---------------------------------------------------------------------------

EXPR_WATCH_START = dt.date(2026, 10, 16)   # Berlin date of opened_at, on or after
WATCH_STATUSES = ("win", "loss", "closed")
WATCH_COUNT_KEYS = ("no_source", "unknown_strategy", "no_r", "manual_close", "no_entry_date")

#: The bootstrap adapter: stats.group_by_week reads `entry_date` with getattr,
#: so a plain trade dict cannot be passed. entry_date is the Berlin-date ISO
#: string, never the UTC timestamp (iso_week_key slices [:10]).
LiveTrade = namedtuple("LiveTrade", "entry_date r status")

RowKey = tuple  # (source, strategy, horizon | None)


@dataclass(frozen=True)
class MatchResult:
    """One bucket per registry row key (empty when nothing matched) plus the
    per-reason counts of trades that were reported rather than bucketed."""
    buckets: dict
    counts: dict


def row_key(entry: dict) -> RowKey:
    """(source, strategy, horizon) of a registry row; horizon None = pooled."""
    return (entry.get("source"), entry.get("strategy"), entry.get("horizon"))


def berlin_entry_date(trade: dict) -> str | None:
    """Berlin date of `opened_at` as "YYYY-MM-DD"; naive reads as UTC (as
    retrospective._to_berlin does). None when missing or unparseable."""
    raw = trade.get("opened_at")
    if not raw:
        return None
    try:
        stamp = dt.datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(BERLIN_TZ).date().isoformat()


def _pooled_key(trade: dict) -> RowKey:
    source = trade.get("source")
    strategy = "ALL" if source == "confluence" else trade.get("strategy")
    return (source, strategy, None)


def _target_keys(trade: dict, buckets: dict) -> list:
    """The exact-horizon row when it exists, and always the pooled row."""
    pooled = _pooled_key(trade)
    exact = (pooled[0], pooled[1], trade.get("horizon_key"))
    if exact == pooled or exact not in buckets:
        return [pooled]
    return [exact, pooled]


def _in_population(trade: dict) -> bool:
    return trade.get("status") in WATCH_STATUSES and origin.is_regular(trade)


def _exclusion(trade: dict, buckets: dict, r: float | None) -> str | None:
    """The count key a population trade is reported under instead of being
    bucketed, first hit wins; None = keep it."""
    if not trade.get("source"):
        return "no_source"
    if _pooled_key(trade) not in buckets:
        return "unknown_strategy"
    if r is None:
        return "no_r"
    return None


def match_live_rows(trades: list[dict], registry_entries: list[dict]) -> MatchResult:
    """Bucket the pre-registered live population (spec D1) per registry row.

    A trade counts toward its exact-horizon row and the pooled row of its
    (source, strategy'); two aggregation levels, never two strategies.
    Status/origin/start-date filtering defines the population and is not
    counted; every other exclusion is counted by reason, never dropped."""
    buckets = {row_key(entry): [] for entry in registry_entries}
    counts = dict.fromkeys(WATCH_COUNT_KEYS, 0)
    for trade in trades:
        if not _in_population(trade):
            continue
        entry_date = berlin_entry_date(trade)
        if entry_date is None:
            counts["no_entry_date"] += 1
            continue
        if dt.date.fromisoformat(entry_date) < EXPR_WATCH_START:
            continue
        r = metrics.r_multiple(trade)
        reason = _exclusion(trade, buckets, r)
        if reason is not None:
            counts[reason] += 1
            continue
        if trade["status"] == "closed":
            counts["manual_close"] += 1
        live = LiveTrade(entry_date, r, trade["status"])
        for key in _target_keys(trade, buckets):
            buckets[key].append(live)
    return MatchResult(buckets=buckets, counts=counts)


# ---------------------------------------------------------------------------
# v164 live loss watch, D2: the loss rule (PRE-REGISTERED)
# ---------------------------------------------------------------------------
# Fixed in spec v164 before any trade it judges existed (EXPR_WATCH_START is
# the day after the spec's commit). Never loosened or tightened after seeing
# what it flags; a change is a new spec written before looking. The baseline
# is zero, not the registry: registry rows carry no exit-model, scale-out or
# friction provenance, so they are shown as labelled context only.

EXPR_WATCH_LIVE_N_FLOOR = 20
EXPR_WATCH_CONFIDENCE = 0.90      # one-sided
EXPR_WATCH_RESAMPLES = 10_000

LIVE_LOSS_MEANING = ('live ExpR for this row is below zero with ~90% one-sided '
                     'confidence — not "the edge decayed versus its backtest"')
LIVE_LOSS_LOOKS_CAVEAT = ("11 correlated looks per week; flags are prompts to "
                          "investigate, not verdicts")
REGISTRY_CONTEXT_LABEL = "backtest context — not comparable"

#: backtest-methodology.md windows, matched by exact string; never guessed.
_WINDOW_KINDS = {
    "2020-01-01..2023-12-31": "TRAIN",
    "2024-01-01..2025-12-31": "VALIDATION",
}
_BOUND_PERCENTILE = round(EXPR_WATCH_CONFIDENCE * 100, 6)   # 90.0, not 90.00000000000001


def registry_window_kind(window: str | None) -> str | None:
    """TRAIN / VALIDATION for the two methodology windows, else None."""
    return _WINDOW_KINDS.get(window) if window else None


def _canonical(live: list) -> list:
    """Input-order-free ordering, so float sums and the bootstrap are
    bit-identical however the trades arrive."""
    return sorted(live, key=lambda t: (t.entry_date, t.r, t.status))


def _mean_r(draw: list, _component=()) -> float | None:
    """Bootstrap statistic: mean R of one week draw; None (dropped) when empty."""
    if not draw:
        return None
    return sum(t.r for t in draw) / len(draw)


def live_expr_bound(live: list, *, n_resamples: int = EXPR_WATCH_RESAMPLES) -> float | None:
    """One-sided upper bound on live ExpR: the 90th percentile of the
    week-clustered bootstrap of mean R (stats.week_cluster_bootstrap, its
    named seed, a fresh generator per call). None when there is nothing to
    resample, and a row without a bound cannot trip."""
    if not live:
        return None
    draws = stats.week_cluster_bootstrap(_canonical(live), (), _mean_r,
                                         n_resamples=n_resamples,
                                         seed=stats.WEEK_BOOTSTRAP_SEED)
    if draws.size == 0:
        return None
    return float(np.percentile(draws, _BOUND_PERCENTILE))


def loss_rule_trips(live_n: int, bound_upper: float | None) -> bool:
    """The pre-registered rule: live_n >= 20 and bound_upper < 0."""
    return (bound_upper is not None and live_n >= EXPR_WATCH_LIVE_N_FLOOR
            and bound_upper < 0)


def _live_stats(live: list) -> tuple:
    """(live_n, live_wr, live_expr) of one bucket; WR over win/loss only."""
    live_n = len(live)
    live_wr = metrics.win_rate([{"status": t.status} for t in live])
    live_expr = (sum(t.r for t in _canonical(live)) / live_n) if live_n else None
    return live_n, live_wr, live_expr


def live_loss_row(entry: dict, live: list, *,
                  n_resamples: int = EXPR_WATCH_RESAMPLES) -> dict:
    """One output row (spec D2). The registry_* columns are backtest context
    (REGISTRY_CONTEXT_LABEL), never an input to `alert`."""
    live_n, live_wr, live_expr = _live_stats(live)
    bound = live_expr_bound(live, n_resamples=n_resamples)
    return {
        "source": entry.get("source"),
        "strategy": entry.get("strategy"),
        "horizon": entry.get("horizon"),
        "live_n": live_n,
        "live_wr": live_wr,
        "live_expr": live_expr,
        "bound_upper": bound,
        "alert": loss_rule_trips(live_n, bound),
        "registry_status": entry.get("status"),
        "registry_window_kind": registry_window_kind(entry.get("window")),
        "registry_run_date": entry.get("run_date"),
        "registry_expr": entry.get("expectancy_r"),
    }


def _row_rank(row: dict, horizons: list) -> tuple:
    first = 0 if row.get("alert") else 1
    if row.get("source") == "confluence":
        horizon = row.get("horizon")
        position = horizons.index(horizon) if horizon in horizons else len(horizons)
        return (first, 0, position, "")
    return (first, 1, 0, str(row.get("strategy")))


def order_live_loss_rows(rows: list[dict]) -> list[dict]:
    """Alert rows first; then confluence rows in HORIZONS order, pooled last;
    then strategy rows by name. The digest and the UI share this order."""
    horizons = list(horizon_order())
    return sorted(rows, key=lambda row: _row_rank(row, horizons))


def _unique_entries(registry_entries: list[dict]) -> list[dict]:
    """First registry row per (source, strategy, horizon) key."""
    seen: dict = {}
    for entry in registry_entries:
        seen.setdefault(row_key(entry), entry)
    return list(seen.values())


def live_loss_watch(trades: list[dict], registry_entries: list[dict], *,
                    n_resamples: int = EXPR_WATCH_RESAMPLES) -> dict:
    """D1 + D2: {"rows": ordered rows, one per registry row key, "counts":
    the matcher's exclusion counts}. Pure; report-only."""
    match = match_live_rows(trades, registry_entries)
    rows = [live_loss_row(entry, match.buckets[row_key(entry)], n_resamples=n_resamples)
            for entry in _unique_entries(registry_entries)]
    return {"rows": order_live_loss_rows(rows), "counts": dict(match.counts)}
