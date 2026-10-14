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

import numpy as np

from swingbot.core.analytics.aggregate import rs_quintile_label
from swingbot.core.edge.frictions import apply_frictions, commission_r
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
