"""Expectancy attribution (v146): does today's confidence score, or any factor
inside it, rank trades by realised R?

Measurement only -- nothing here changes an alert, a gate, a level, a size or
an exit. Two populations, NEVER pooled: the live book (closed trades) and the
TRAIN confluence replay. Each becomes a list of *attribution rows* (ROW_KEYS)
and is bucketed, tested and reported on its own.

Pure apart from one loader (``load_live_rows``) and one writer
(``write_latest``, in ``swingbot.core.infra.expectancy_attribution_store``).
Numbers are stored unrounded; the results document rounds for display, so the
pre-registered verdict always compares exact values.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np

from swingbot import config
from swingbot.core.analytics import metrics
from swingbot.core.analytics.aggregate import rs_quintile_label
from swingbot.core.analytics.scope import closed_only
from swingbot.core.backtesting.instrument import stats
from swingbot.core.edge.frictions import apply_frictions, commission_r
from swingbot.core.infra.expectancy_attribution_store import load_latest, write_latest  # noqa: F401  (load_latest is re-exported for v150)
from swingbot.core.market import earnings_calendar
from swingbot.core.market.earnings_calendar import EARNINGS_CSV_DIR
from swingbot.core.market.strategy_types import HORIZONS

#: Spec: a bucket with N < 30 is shown greyed (``thin``) and enters no verdict.
#: This is the methodology's TRAIN floor; ``aggregate.MIN_CELL_N`` is untouched.
THIN_N = 30
DECILES = 10
#: Spec: sessions to the next earnings reaction session, in this order.
EARNINGS_BUCKETS = ("0-5", "6-10", "11-20", ">20", "none", "unknown")
_EARNINGS_EDGES = ((5, "0-5"), (10, "6-10"), (20, "11-20"))

#: One attribution row. ``r`` is net of frictions, ``r_gross`` is not; ``week``
#: is the Monday (ISO date) of the entry week; ``earnings_status`` is one of
#: "known" (``earnings_sessions`` is an int), "none", "unknown".
ROW_KEYS = ("r", "r_gross", "week", "confidence_score", "confidence_level",
            "confidence_points", "confidence_unevaluated", "confluence_count",
            "regime2_state", "rs_pctile", "direction", "horizon",
            "earnings_sessions", "earnings_status", "risk_reward_ratio")

#: Labels with a fixed display order; digits sort numerically after them,
#: other labels alphabetically, "unknown" last.
_ORDER = ("Q1", "Q2", "Q3", "Q4", "Q5", "0-5", "6-10", "11-20", ">20", "none",
          "yes", "no")


def quantile_bins(values: list[float], k: int) -> list[int]:
    """Bin index (0..k-1) per value, aligned with the input.

    Tied values are never split: a tied block goes wholly to the bin that
    contains its median rank. Deterministic -- no randomness, no jitter. With
    0-based sorted ranks ``a..b`` for a block of ``n`` values, the bin is
    ``floor(((a + b) / 2) * k / n)``, in integer arithmetic."""
    n = len(values)
    bins = [0] * n
    order = sorted(range(n), key=lambda index: values[index])
    start = 0
    while start < n:
        end = start
        while end + 1 < n and values[order[end + 1]] == values[order[start]]:
            end += 1
        block = min(k - 1, ((start + end) * k) // (2 * n))
        for position in range(start, end + 1):
            bins[order[position]] = block
        start = end + 1
    return bins


def earnings_bucket(row: dict) -> str:
    """One of EARNINGS_BUCKETS for a row's sessions-to-earnings reading."""
    status, sessions = row.get("earnings_status"), row.get("earnings_sessions")
    if status == "none":
        return "none"
    if status != "known" or sessions is None or sessions < 0:
        return "unknown"
    for edge, label in _EARNINGS_EDGES:
        if sessions <= edge:
            return label
    return ">20"


def earnings_in_hold(row: dict) -> str:
    """"yes" when the next earnings reaction falls inside the horizon's
    ``max_holding_days`` (sessions <= max_holding_days), "no" when it does not
    or there is provably none, "unknown" when either input is missing."""
    bucket = earnings_bucket(row)
    if bucket == "unknown":
        return "unknown"
    if bucket == "none":
        return "no"
    hold = (HORIZONS.get(row.get("horizon")) or {}).get("max_holding_days")
    if hold is None:
        return "unknown"
    return "yes" if row["earnings_sessions"] <= hold else "no"


def net_r(entry: float, stop_loss: float, direction: str, legs: list[dict]) -> float:
    """R net of frictions, recomputed from the fills leg by leg with the
    named-strategy backtest's model (``backtest.py:688-743``): the entry fill
    is worsened by slippage and re-bases the risk, every exit fill is worsened
    on the opposite side, and one round-trip commission comes off in R.

    ``legs`` is ``[{"fraction", "exit_price", ...}]``; a recorded leg ``r`` is
    ignored. Raises ValueError without legs or with a zero stop distance."""
    bullish = direction == "bullish"
    sign = 1.0 if bullish else -1.0
    entry_fill = apply_frictions(float(entry), "buy" if bullish else "sell")
    risk = abs(entry_fill - float(stop_loss))
    if not legs or risk == 0:
        raise ValueError("net_r needs at least one leg and a non-zero stop distance")
    total = 0.0
    for leg in legs:
        exit_fill = apply_frictions(float(leg["exit_price"]), "sell" if bullish else "buy")
        total += float(leg.get("fraction", 0)) * (exit_fill - entry_fill) * sign / risk
    return total - commission_r()


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def bucket_stats(rows: list[dict]) -> dict:
    """N / win rate (percent; a win is net ``r > 0``) / net and gross ExpR."""
    n = len(rows)
    return {
        "n": n,
        "win_rate": 100.0 * sum(1 for row in rows if row["r"] > 0) / n if n else None,
        "exp_r": _mean([row["r"] for row in rows]),
        "exp_r_gross": _mean([row["r_gross"] for row in rows]),
        "thin": n < THIN_N,
    }


def _scored(rows: list[dict]) -> list[dict]:
    """The confidence analyses' rows: those with a non-null score."""
    return [row for row in rows if row.get("confidence_score") is not None]


def _label(value) -> str:
    return "unknown" if value is None or value == "" else str(value)


def _sort_key(label: str) -> tuple:
    if label in _ORDER:
        return (0, _ORDER.index(label), "")
    if label.isdigit():
        return (1, int(label), "")
    return (3, 0, "") if label == "unknown" else (2, 0, label)


#: (grouping name, row -> label, confidence analysis (scored rows only)?)
_PLAIN_GROUPINGS = (
    ("confidence_level", lambda row: _label(row.get("confidence_level")), True),
    ("confluence", lambda row: _label(row.get("confluence_count")), False),
    ("regime2_state", lambda row: _label(row.get("regime2_state")), False),
    ("rs_quintile", lambda row: rs_quintile_label(row.get("rs_pctile")), False),
    ("direction", lambda row: _label(row.get("direction")), False),
    ("horizon", lambda row: _label(row.get("horizon")), False),
    ("earnings", earnings_bucket, False),
    ("earnings_in_hold", earnings_in_hold, False),
)


def _decile_groups(rows: list[dict]) -> dict[str, list[dict]]:
    """Population-quantile deciles of ``confidence_score``; a decile emptied
    by ties is simply absent. Label: ``D<k> (<lowest>-<highest> score)``."""
    scored = _scored(rows)
    bins = quantile_bins([row["confidence_score"] for row in scored], DECILES)
    groups: dict[int, list[dict]] = {}
    for row, index in zip(scored, bins):
        groups.setdefault(index, []).append(row)
    out = {}
    for index in sorted(groups):
        scores = [row["confidence_score"] for row in groups[index]]
        out[f"D{index + 1} ({min(scores):g}-{max(scores):g})"] = groups[index]
    return out


def _grouped_rows(rows: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """grouping -> label -> member rows, in display order. The one place
    membership is decided: buckets and their looks both read it."""
    out = {"confidence_decile": _decile_groups(rows)}
    for name, label_of, scored_only in _PLAIN_GROUPINGS:
        groups: dict[str, list[dict]] = {}
        for row in (_scored(rows) if scored_only else rows):
            groups.setdefault(label_of(row), []).append(row)
        out[name] = {label: groups[label] for label in sorted(groups, key=_sort_key)}
    return out


def _quartiles(values) -> dict:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return {"p25": None, "median": None, "p75": None}
    p25, median, p75 = (float(x) for x in np.percentile(clean, [25, 50, 75]))
    return {"p25": p25, "median": median, "p75": p75}


def _decile_extras(rows: list[dict]) -> dict:
    return {
        "unevaluated_n": sum(1 for row in rows if row.get("confidence_unevaluated")),
        "rr": _quartiles([row.get("risk_reward_ratio") for row in rows]),
    }


def population_buckets(rows: list[dict]) -> dict[str, list[dict]]:
    """One N / WR / ExpR bucket list per grouping of ONE population.

    Groupings: confidence_decile, confidence_level (both on scored rows only),
    confluence, regime2_state, rs_quintile, direction, horizon, earnings,
    earnings_in_hold (every row). ``q`` is None until ``assign_qvalues``."""
    out: dict[str, list[dict]] = {}
    for name, groups in _grouped_rows(rows).items():
        out[name] = [{"label": label, **bucket_stats(members), "q": None}
                     for label, members in groups.items()]
        if name == "confidence_decile":
            for bucket, members in zip(out[name], groups.values()):
                bucket.update(_decile_extras(members))
    return out


# --------------------------------------------------------------------------
# Statistics: week-clustered looks, monotonicity, factor deltas, BH, verdict.
# --------------------------------------------------------------------------

#: Bootstrap replicates per look (pre-registered default, 10,000).
N_RESAMPLES = stats.WEEK_BOOTSTRAP_RESAMPLES
TERCILES = 3
#: Spec, "The verdict": point estimate >= +0.10R (and CI lower bound > 0).
MIN_SPREAD_R = 0.10
VERDICTS = ("PREDICTIVE", "WEAK", "NOT PREDICTIVE")
#: Factor keys that exist on a row only when they fired: their absence is a
#: reading of 0. Any other key absent from a row means another scorer wrote
#: that row, and the row is left out of that factor's look. These are the
#: scorers in ``swingbot.core.scanning.factors`` that return None when they do
#: not fire (``factor_tight_stop``, ``factor_gap``), not only on missing data.
ABSENT_IS_ZERO = frozenset({"Tight stop penalty", "Gap penalty"})


class _Obs(NamedTuple):
    """One arm's rows of one entry week, summed. ``entry_date`` is the week's
    Monday, which is what ``stats.group_by_week`` keys on."""
    entry_date: str
    total: float
    n: int


def _week_sums(rows: list[dict]) -> list[_Obs]:
    sums: dict[str, tuple[float, int]] = {}
    for row in rows:
        total, n = sums.get(row["week"], (0.0, 0))
        sums[row["week"]] = (total + row["r"], n + 1)
    return [_Obs(week, total, n) for week, (total, n) in sorted(sums.items())]


def _mean_gap(base: list[_Obs], comp: list[_Obs]) -> float | None:
    """ExpR(comp) - ExpR(base) for one resample; None when an arm is empty
    (the bootstrap drops that draw, it never zero-fills it)."""
    base_n, comp_n = sum(obs.n for obs in base), sum(obs.n for obs in comp)
    if not base_n or not comp_n:
        return None
    return sum(obs.total for obs in comp) / comp_n - sum(obs.total for obs in base) / base_n


def _look(base_rows: list[dict], comp_rows: list[dict], seed: int) -> dict:
    """One look: ExpR(comp) - ExpR(base), its 95% week-clustered bootstrap CI
    and a two-sided bootstrap p. An arm under THIN_N rows gets the point
    estimate only -- no interval, no p, so it never enters the BH family."""
    out = {"delta": None, "ci_low": None, "ci_high": None, "p": None}
    if base_rows and comp_rows:
        out["delta"] = _mean([row["r"] for row in comp_rows]) - _mean([row["r"] for row in base_rows])
    if min(len(base_rows), len(comp_rows)) < THIN_N:
        return out
    draws = stats.week_cluster_bootstrap(_week_sums(base_rows), _week_sums(comp_rows),
                                         _mean_gap, n_resamples=N_RESAMPLES, seed=seed)
    if not len(draws):
        return out
    low, high = np.percentile(draws, [2.5, 97.5])
    tail = min(int((draws <= 0).sum()), int((draws >= 0).sum())) + 1
    out.update(ci_low=float(low), ci_high=float(high),
               p=min(1.0, 2.0 * tail / (len(draws) + 1)))
    return out


def _ranks(values: list[float]) -> list[float]:
    """1-based ranks, ties sharing their mean rank."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for position in range(start, end + 1):
            ranks[order[position]] = (start + end) / 2.0 + 1.0
        start = end + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rho (Pearson on mean ranks); None under 3 points or when one
    side is constant. numpy only: scipy is not a dependency."""
    if len(xs) < 3:
        return None
    rank_x, rank_y = np.asarray(_ranks(xs)), np.asarray(_ranks(ys))
    if rank_x.std() == 0 or rank_y.std() == 0:
        return None
    return float(np.corrcoef(rank_x, rank_y)[0, 1])


def _terciles(scored: list[dict]) -> list[list[dict]]:
    """[bottom, middle, top] by ``confidence_score``; ties never split."""
    bins = quantile_bins([row["confidence_score"] for row in scored], TERCILES)
    return [[row for row, index in zip(scored, bins) if index == third]
            for third in range(TERCILES)]


def monotonicity(rows: list[dict], *, seed: int) -> dict:
    """Does ``confidence_score`` rank R? Spearman rho and the top-minus-bottom
    tercile ExpR with its week-clustered CI, on the scored rows.

    The tercile of every row is fixed ONCE here, on the full sample; the
    bootstrap resamples weeks of rows that keep their tercile."""
    scored = _scored(rows)
    thirds = _terciles(scored)
    look = _look(thirds[0], thirds[-1], seed)
    return {
        "n": len(scored),
        "spearman_rho": _spearman([row["confidence_score"] for row in scored],
                                  [row["r"] for row in scored]),
        "tercile_spread": look["delta"],
        "ci_low": look["ci_low"],
        "ci_high": look["ci_high"],
        "p": look["p"],
        "inverted": look["ci_high"] is not None and look["ci_high"] < 0,
        "tercile_n": [len(third) for third in thirds],
        "rr_by_tercile": [_quartiles([row.get("risk_reward_ratio") for row in third])
                          for third in thirds],
    }


def _factor_arms(rows: list[dict], key: str) -> tuple[list[dict], list[dict]]:
    """(rows where the factor scored, rows where it scored 0). A row that
    lists the factor in ``confidence_unevaluated`` is in neither arm: "no
    data" is never a positive reading."""
    scored_rows, zero_rows = [], []
    for row in rows:
        points = row.get("confidence_points")
        if not isinstance(points, dict) or key in (row.get("confidence_unevaluated") or ()):
            continue
        if key not in points and key not in ABSENT_IS_ZERO:
            continue
        (scored_rows if points.get(key, 0) != 0 else zero_rows).append(row)
    return scored_rows, zero_rows


def factor_deltas(rows: list[dict], *, seed: int) -> list[dict]:
    """Per factor key: ExpR where it scored minus ExpR where it scored 0."""
    keys = sorted({key for row in rows for key in (row.get("confidence_points") or {})})
    out = []
    for key in keys:
        scored_rows, zero_rows = _factor_arms(rows, key)
        look = _look(zero_rows, scored_rows, seed)
        out.append({"key": key, "n": len(scored_rows) + len(zero_rows),
                    "n_pos": len(scored_rows), "n_zero": len(zero_rows),
                    "delta": look["delta"], "ci_low": look["ci_low"],
                    "ci_high": look["ci_high"], "p": look["p"], "q": None})
    return out


def bucket_looks(rows: list[dict], buckets: dict[str, list[dict]], *, seed: int) -> None:
    """Fill ``delta, ci_low, ci_high, p`` on every bucket, in place: the
    bucket's ExpR minus the ExpR of the rest of its own grouping. A thin
    bucket (or a thin rest) keeps None for the interval and the p."""
    for name, groups in _grouped_rows(rows).items():
        for bucket in buckets.get(name, ()):
            inside = groups.get(bucket["label"], [])
            members = {id(row) for row in inside}
            rest = [row for group in groups.values() for row in group
                    if id(row) not in members]
            bucket.update(_look(rest, inside, seed))


def _look_holders(population: dict | None) -> list[tuple[dict, bool]]:
    """Every dict of one population that carries a ``p``, with whether it
    takes a ``q`` (buckets and factors do; monotonicity keeps its shape)."""
    if not population:
        return []
    holders = [(population["monotonicity"], False)]
    for split in (population.get("splits") or {}).values():
        holders.extend((mono, False) for mono in split.values())
    holders.extend((factor, True) for factor in population.get("factors") or ())
    for grouping in (population.get("buckets") or {}).values():
        holders.extend((bucket, True) for bucket in grouping)
    return holders


def assign_qvalues(populations: dict) -> int:
    """Benjamini-Hochberg over EVERY look of both populations (one family).
    Writes ``q`` on buckets and factors and returns ``looks``, the family
    size (the number of non-null p-values)."""
    holders = [holder for name in ("live", "train")
               for holder in _look_holders(populations.get(name))]
    qvalues = stats.bh_qvalues([holder.get("p") for holder, _ in holders])
    for (holder, takes_q), q in zip(holders, qvalues):
        if takes_q:
            holder["q"] = q
    return sum(1 for q in qvalues if q is not None)


def population_passes(mono: dict) -> bool:
    """One population's clause of the pre-registered verdict: CI lower bound
    > 0 AND point estimate >= +0.10R; any tercile with N < 30 fails it."""
    if not mono or min(mono.get("tercile_n") or [0]) < THIN_N:
        return False
    low, spread = mono.get("ci_low"), mono.get("tercile_spread")
    return low is not None and spread is not None and low > 0 and spread >= MIN_SPREAD_R


def verdict(live_mono: dict | None, train_mono: dict | None) -> str:
    """PREDICTIVE when the clause holds in both populations, WEAK in exactly
    one, NOT PREDICTIVE otherwise. An inverted CI is reported through the
    monotonicity dict's ``inverted`` flag, inside NOT PREDICTIVE or WEAK."""
    passed = sum(1 for mono in (live_mono, train_mono) if population_passes(mono))
    return VERDICTS[2 - passed]


# --------------------------------------------------------------------------
# Populations, the report and the run. Only ``load_live_rows`` touches the
# database and only ``run`` writes (through ``write_latest``).
# --------------------------------------------------------------------------

log = logging.getLogger(__name__)

#: Handoff 5, verified in V146-12 Step 1: live fills are booked at the exact
#: trigger / stop / target price (no slippage, no commission), so the study
#: nets live rows with the same model as TRAIN rows. True would mean "use
#: metrics.r_multiple as it is".
LIVE_FILLS_INCLUDE_FRICTIONS = False
WEEK_BOOTSTRAP_SEED = stats.WEEK_BOOTSTRAP_SEED
#: Spec: a TRAIN signal later than the last CSV report plus this margin has
#: unknown earnings (the CSV has gone stale), in calendar days.
TRAIN_EARNINGS_MARGIN_DAYS = 100

_NOTES = {
    "live": (
        "Closed trades from the trades table, both ledgers. Confidence analyses "
        "use rows with a non-null confidence_score.",
        "Range-restricted: only trades at or above MIN_ALERT_CONFIDENCE_LEVEL were "
        "ever paper-traded, which attenuates any score-R slope; a weaker live slope "
        "is the expected shape, not by itself a contradiction.",
        "confidence_score is level-major (the quality score is repositioned inside "
        "the final level's band), so deciles read close to level, then quality.",
        "Earnings: risk_features.days_to_earnings, a provider point-in-time estimate "
        "in NYSE sessions; unknown for every trade opened before v146 I2 shipped.",
    ),
    "train": (
        "TRAIN confluence replay (--scenarios --train --exit-model v2 --scale-out), "
        "not level-gated; VALIDATION is never read.",
        "The TRAIN score is computed with the expectancy level adjustment "
        "neutralised; the R:R distribution per tercile shows any residual effect.",
        "R net: the replay's exit_sim applies no frictions, so slippage and "
        "commission are re-applied here; exp_r_gross is the replay's own r_total.",
        "Earnings: actual report dates (CsvSource). Buckets >20 and none are "
        "ex-post, 11-20 partly; report timing is ex-post and can move a row across "
        "the 0-5 edge. Never merged with the live estimate.",
        "Backtest and live differ in their gap-fill model (exit_sim.py:541-548).",
    ),
}


def _progress(message: str) -> None:
    print(f"[expectancy-attribution] {message}", file=sys.stderr, flush=True)


def _week_of(value) -> str | None:
    """The Monday (ISO date) of the week holding an ISO date or timestamp."""
    try:
        day = dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
    return (day - dt.timedelta(days=day.weekday())).isoformat()


def _live_net(trade: dict, gross: float) -> float | None:
    if LIVE_FILLS_INCLUDE_FRICTIONS:
        return gross
    legs = trade.get("legs") or [{"fraction": 1.0, "exit_price": trade.get("exit_price")}]
    if any(leg.get("exit_price") is None for leg in legs):
        return None
    try:
        return net_r(trade["entry"], trade["stop_loss"], trade["direction"], legs)
    except (KeyError, TypeError, ValueError):
        return None          # a malformed fill drops the row, never the report (as _train_row)


def live_row(trade: dict) -> dict | None:
    """One closed live trade as an attribution row, or None when it has no
    R (``metrics.r_multiple`` is None), no entry week, or a leg with no fill
    price to net."""
    gross = metrics.r_multiple(trade)
    week = _week_of(trade.get("opened_at"))
    if gross is None or week is None:
        return None
    net = _live_net(trade, gross)
    if net is None:
        return None
    features = trade.get("risk_features") or {}
    context = trade.get("entry_context") or {}
    sessions = features.get("days_to_earnings")
    known = isinstance(sessions, int) and not isinstance(sessions, bool)
    return {
        "r": net, "r_gross": gross, "week": week,
        "confidence_score": trade.get("confidence_score"),
        "confidence_level": trade.get("confidence_level"),
        "confidence_points": trade.get("confidence_points"),
        "confidence_unevaluated": trade.get("confidence_unevaluated") or [],
        # The count_confirming_strategies count, the definition TRAIN records;
        # never len(target_sources).
        "confluence_count": features.get("confluence_count"),
        "regime2_state": context.get("regime2_state") or features.get("regime2_state"),
        "rs_pctile": context.get("rs_pctile"),
        "direction": trade.get("direction"),
        "horizon": trade.get("horizon_key"),
        "earnings_sessions": sessions if known else None,
        "earnings_status": "known" if known else "unknown",
        "risk_reward_ratio": trade.get("risk_reward_ratio"),
    }


def load_live_rows() -> list[dict]:
    """Every closed trade of both ledgers, as attribution rows. The database
    is whatever ``swingbot.config.DATABASE_URL`` names when this is CALLED:
    nothing is captured at import."""
    from swingbot.core.tracking.performance import TradeLog
    closed = closed_only(TradeLog().get_trades(status=None, limit=None, ledger=None) or [])
    rows = [row for row in map(live_row, closed) if row is not None]
    if len(rows) != len(closed):
        log.warning("expectancy attribution: %d of %d closed live trades have no "
                    "usable R and are left out", len(closed) - len(rows), len(closed))
    return rows


def train_earnings(ticker: str, signal_date: dt.date, source, *,
                   margin_days: int = 100) -> tuple[int | None, str]:
    """(sessions to the next earnings reaction, status) as of a TRAIN signal.

    "unknown": no earnings CSV rows for the ticker, or the signal is later
    than the last CSV report plus ``margin_days``. "none": coverage reaches
    the signal and holds no report at or after it. Otherwise "known"."""
    reports = source.reports(ticker)
    if not reports:
        return None, "unknown"
    last = max(report.date for report in reports)
    if signal_date > last + dt.timedelta(days=margin_days):
        return None, "unknown"
    sessions = earnings_calendar.sessions_to_reaction(ticker, signal_date, source=source)
    return (None, "none") if sessions is None else (int(sessions), "known")


def _train_row(raw: dict, source) -> dict | None:
    legs = raw.get("legs") or []
    week = _week_of(raw.get("signal_date"))
    entry = raw.get("entry_price") if raw.get("entry_price") is not None else raw.get("entry")
    if not legs or week is None or entry is None or raw.get("r_total") is None:
        return None
    try:
        net = net_r(entry, raw["stop_loss"], raw["direction"], legs)
    except (KeyError, TypeError, ValueError):
        return None
    context = raw.get("entry_context") or {}
    sessions, status = train_earnings(
        raw["ticker"], dt.date.fromisoformat(str(raw["signal_date"])[:10]), source,
        margin_days=TRAIN_EARNINGS_MARGIN_DAYS)
    return {
        "r": net, "r_gross": float(raw["r_total"]), "week": week,
        "confidence_score": raw.get("confidence_score"),
        "confidence_level": raw.get("confidence_level"),
        "confidence_points": raw.get("confidence_points"),
        "confidence_unevaluated": raw.get("confidence_unevaluated") or [],
        "confluence_count": raw.get("confluence_count"),
        "regime2_state": context.get("regime2_state"),
        "rs_pctile": context.get("rs_pctile"),
        "direction": raw.get("direction"),
        "horizon": raw.get("horizon_key"),
        "earnings_sessions": sessions, "earnings_status": status,
        "risk_reward_ratio": raw.get("risk_reward_ratio"),
    }


def load_train_rows(path, *, source=None) -> list[dict]:
    """The TRAIN replay's ``--trades-jsonl`` rows as attribution rows.
    ``source`` defaults to ``CsvSource()`` on the code-relative
    ``market_data/earnings/`` directory (actual report dates)."""
    source = source if source is not None else earnings_calendar.CsvSource()
    rows = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = _train_row(json.loads(line), source)
                if row is not None:
                    rows.append(row)
    return rows


def earnings_provenance(directory=EARNINGS_CSV_DIR) -> dict:
    """What the TRAIN earnings buckets were read from: the file set's count,
    one sha256 over every (file name, bytes) in name order, and the newest
    ``report_date`` in it."""
    folder = Path(directory)
    paths = sorted(folder.glob("*.csv")) if folder.is_dir() else []
    digest, dates = hashlib.sha256(), []
    for path in paths:
        data = path.read_bytes()
        digest.update(path.name.encode("utf-8"))
        digest.update(data)
        dates.extend(line.split(",")[0] for line in data.decode("utf-8").splitlines()[1:]
                     if line.strip())
    return {"directory": str(folder), "files": len(paths),
            "sha256": digest.hexdigest() if paths else None,
            "newest_report_date": max(dates, default=None),
            "calendar": "v82 earnings_calendar.sessions_to_reaction (NYSE sessions "
                        "to the next earnings reaction session)"}


def _splits(rows: list[dict], seed: int) -> dict:
    """The verdict table again per direction and per horizon, so a lift that
    concentrates in one is visible."""
    out = {}
    for name in ("direction", "horizon"):
        labels = sorted({_label(row.get(name)) for row in _scored(rows)}, key=_sort_key)
        out[name] = {label: monotonicity([row for row in rows if _label(row.get(name)) == label],
                                         seed=seed)
                     for label in labels}
    return out


def _population(name: str, rows: list[dict], seed: int) -> dict | None:
    if not rows:
        return None
    _progress(f"{name}: {len(rows)} rows -- buckets and bucket looks")
    buckets = population_buckets(rows)
    bucket_looks(rows, buckets, seed=seed)
    _progress(f"{name}: monotonicity, splits and factor deltas")
    weeks = sorted(row["week"] for row in rows)
    return {
        "window": {"first_week": weeks[0], "last_week": weeks[-1]},
        "n": len(rows),
        "monotonicity": monotonicity(rows, seed=seed),
        "factors": factor_deltas(rows, seed=seed),
        "buckets": buckets,
        "splits": _splits(rows, seed),
        "notes": list(_NOTES[name]),
    }


def build_report(live_rows: list[dict], train_rows: list[dict], *, seed: int,
                 generated_at: str | None = None) -> dict:
    """The whole report, pure: the two populations side by side (never
    pooled), q-values over every look, and the verdict. ``provenance`` is
    filled by ``run``."""
    populations = {"live": _population("live", live_rows, seed),
                   "train": _population("train", train_rows, seed)}
    looks = assign_qvalues(populations)
    monos = [(populations[name] or {}).get("monotonicity") for name in ("live", "train")]
    outcome = verdict(*monos)
    stamp = generated_at or dt.datetime.now(dt.timezone.utc).isoformat()
    return {
        "generated_at": stamp,
        "verdict": outcome,
        # Handoff 9: n is the rows that entered the verdict, live + TRAIN.
        # write_latest keeps an earlier record on disk in place of this one.
        "verdict_of_record": {"verdict": outcome, "date": stamp[:10],
                              "n": sum((mono or {}).get("n", 0) for mono in monos)},
        "looks": looks,
        "seed": seed,
        "provenance": {},
        "populations": populations,
    }


def _file_sha256(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(train_jsonl, *, seed: int = WEEK_BOOTSTRAP_SEED, write: bool = True) -> dict:
    """Load both populations, build the report, persist it (unless
    ``write=False``) and return what was written."""
    train_rows = load_train_rows(train_jsonl)
    live_rows = load_live_rows()
    report = build_report(live_rows, train_rows, seed=seed)
    report["provenance"] = {
        "earnings": earnings_provenance(),
        "train_rows": {"path": str(train_jsonl), "rows": len(train_rows),
                       "sha256": _file_sha256(train_jsonl)},
        "live_fills_include_frictions": LIVE_FILLS_INCLUDE_FRICTIONS,
        "frictions": {"slippage_bps": getattr(config, "SLIPPAGE_BPS", 5.0),
                      "commission_r": commission_r()},
        "n_resamples": N_RESAMPLES,
    }
    return write_latest(report) if write else report
