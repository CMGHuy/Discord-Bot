"""v151: the Why panel's gate margins and holding-window calendar -- pure.

No I/O and no ``swingbot.config`` import: the admin layer builds
``GateThresholds`` from config per request and passes it in, so this package
keeps its no-config property and the tests pass thresholds directly.
Thresholds are TODAY's configuration, never the values in force when the plan
was issued -- the UI says so beside every margin.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from swingbot.core.market import opex

RS_LABEL = "Relative strength"
REGIME_LABEL = "Regime"
EARNINGS_LABEL = "Days to earnings"
EARNINGS_NOT_RECORDED = "not recorded on this plan"
OPEX_KIND = "opex_monthly"
OPEX_LABEL = "Monthly OPEX"


@dataclass(frozen=True)
class GateThresholds:
    """Today's gate configuration, as the admin layer read it."""

    rs_gate: bool
    rs_laggard_pct: float
    rs_leader_pct: float
    regime_gates: bool


def _row(key: str, label: str, value, *, applies: bool, threshold=None, margin=None,
         parts: list | None = None, note: str | None = None) -> dict:
    return {"key": key, "label": label, "value": value, "threshold": threshold,
            "margin": margin, "applies": applies, "parts": parts or [], "note": note}


def _rs_note(value, bearish: bool, t: GateThresholds) -> str | None:
    """Why the RS row does not apply, first reason wins; None when it does."""
    if value is None:
        return "exempt"
    if not t.rs_gate:
        return "RS gate off"
    if not bearish and t.rs_leader_pct <= 0:
        return "bullish arm disabled"
    return None


def _rs_row(direction, ctx: dict, risk: dict, cohort, t: GateThresholds) -> dict:
    value = ctx.get("rs_combined")
    if value is None:
        value = ctx.get("rs_pctile")
    bearish = direction == "bearish"
    threshold = t.rs_laggard_pct if bearish else t.rs_leader_pct
    note = _rs_note(value, bearish, t)
    applies = note is None
    margin = None
    if applies:
        margin = threshold - value if bearish else value - threshold
    parts = [{"label": "Ticker RS pctile", "value": ctx.get("rs_pctile")},
             {"label": "Sector RS pctile", "value": ctx.get("sector_pctile")}]
    return _row("rs", RS_LABEL, value, applies=applies, threshold=threshold,
                margin=margin, parts=parts, note=note)


def _regime_row(direction, ctx: dict, risk: dict, cohort, t: GateThresholds) -> dict:
    return _row("regime", REGIME_LABEL, ctx.get("regime2_state"),
                applies=bool(t.regime_gates), note=cohort)


def _earnings_row(direction, ctx: dict, risk: dict, cohort, t: GateThresholds) -> dict:
    value = risk.get("days_to_earnings")
    return _row("earnings", EARNINGS_LABEL, value, applies=value is not None,
                note=EARNINGS_NOT_RECORDED if value is None else None)


#: One builder per gate, in display order. Add a gate by adding a builder.
_BUILDERS = (_rs_row, _regime_row, _earnings_row)


def gate_rows(direction: str | None, entry_context: dict | None, risk_features: dict | None,
              cohort_label: str | None, thresholds: GateThresholds) -> list[dict]:
    """One row per gate, never hidden: a missing value is ``None`` and shows "—"."""
    ctx = entry_context or {}
    risk = risk_features or {}
    return [build(direction, ctx, risk, cohort_label, thresholds) for build in _BUILDERS]


def _months(start: dt.date, end: dt.date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def calendar_rows(start: dt.date, end: dt.date) -> list[dict]:
    """Monthly OPEX dates inside ``[start, end]``, within opex.py's coverage.

    Weekly OPEX is left out (every Friday -- noise). Earnings and macro dates
    are out of scope (they need I/O this module must not do).
    """
    rows = []
    for year, month in _months(start, end):
        if year > opex.LAST_YEAR_COVERED:
            break
        day = opex.monthly_expiration(year, month)
        if start <= day <= end:
            rows.append({"date": day.isoformat(), "kind": OPEX_KIND, "label": OPEX_LABEL})
    return rows
