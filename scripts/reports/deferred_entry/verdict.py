"""v229 frozen rule, forward window and verdict guard (spec section 3).

The forward rule is frozen before either read: every pair row carries
``rule_hash()``, and a verdict over a log written under another rule is
refused. The verdict is computed once, after the twelve complete ISO weeks
following T0 have passed their five-session mark, and never again once the
ledger holds ``LEDGER_ID``. The study words have no ledger tokens of their
own: UNCALIBRATED -> INCONCLUSIVE, UNDERPOWERED -> NO-LIFT (index Handoff 2).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

import pandas as pd

from swingbot.core.market.session import US_MARKET_TZ, nyse_calendar

FROZEN = {"defer_et": "15:30", "hold_sessions": 5, "window_weeks": 12, "floor_r": 0.10,
          "lower_pct": 2.5, "calibration_min": 0.80, "min_pairs": 300, "min_weeks": 10,
          "resamples": 10000, "seed": 42, "be_fraction": 0.5, "deferred_entry_bps_mult": 2}
LEDGER_ID = "v229-deferred-entry"
STUDY_TO_LEDGER = {"PASS": "PASS", "NO-LIFT": "NO-LIFT", "UNDERPOWERED": "NO-LIFT",
                   "UNCALIBRATED": "INCONCLUSIVE"}
ARMS = ("A", "B")


class VerdictRefused(RuntimeError):
    """The verdict cannot be computed now, or has been computed already."""


def rule_hash() -> str:
    return hashlib.sha256(json.dumps(FROZEN, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _t0_date(t0) -> dt.date:
    ts = pd.Timestamp(t0)
    if ts.tzinfo is None:
        raise ValueError("T0 must be a timezone-aware UTC timestamp")
    return ts.tz_convert(US_MARKET_TZ).date()


def forward_window(t0) -> tuple[dt.date, dt.date]:
    """Monday after T0's ET date through the Sunday twelve weeks later."""
    day = _t0_date(t0)
    start = day + dt.timedelta(days=7 - day.weekday())
    return start, start + dt.timedelta(days=7 * FROZEN["window_weeks"] - 1)


def phase(entry_date: dt.date, t0) -> str:
    start, end = forward_window(t0)
    if entry_date < _t0_date(t0):
        return "exploratory"
    return "forward" if start <= entry_date <= end else "after"


def verdict_open_date(t0) -> dt.date:
    calendar = nyse_calendar()
    last = calendar.session_after(forward_window(t0)[1], 0)
    fifth = calendar.session_after(last, FROZEN["hold_sessions"]) if last else None
    if fifth is None:
        raise ValueError("the forward window runs past the NYSE calendar")
    return fifth + dt.timedelta(days=1)


def assert_one_rule(pairs) -> None:
    other = sorted({str(p.get("rule_hash")) for p in pairs} - {rule_hash()})
    if other:
        raise VerdictRefused(f"pair log carries rows written under another rule ({other}); "
                             f"the frozen rule is {rule_hash()}")
    assert_same_frictions(pairs)


def assert_same_frictions(pairs, stamp=None) -> None:
    """Refuse a log whose stamped rows (plus ``stamp``) carry more than one cost setting."""
    stamps = [p.get("frictions") for p in pairs] + [stamp]
    distinct = {json.dumps(s, sort_keys=True) for s in stamps if s is not None}
    if len(distinct) > 1:
        raise VerdictRefused(f"pair log mixes cost settings (frictions): {sorted(distinct)}")


def guard(*, today: dt.date, t0, ledger_rows, pairs) -> None:
    if any(row.get("id") == LEDGER_ID for row in ledger_rows):
        raise VerdictRefused(f"the ledger already holds {LEDGER_ID}: the verdict is computed once")
    opens = verdict_open_date(t0)
    if today < opens:
        raise VerdictRefused(f"the verdict opens on {opens.isoformat()} (today {today.isoformat()})")
    assert_one_rule(pairs)


def arm_verdict(delta: dict, calibrated: bool) -> str:
    if not calibrated:
        return "UNCALIBRATED"
    mean, lower = delta.get("mean"), delta.get("lower")
    if mean is not None and lower is not None and mean >= FROZEN["floor_r"] and lower > 0:
        return "PASS"
    return "NO-LIFT"


def _study_word(arms: dict, calibrated: bool, n_pairs: int, weeks: int) -> str:
    if n_pairs < FROZEN["min_pairs"] or weeks < FROZEN["min_weeks"]:
        return "UNDERPOWERED"
    if not calibrated:
        return "UNCALIBRATED"
    return "PASS" if "PASS" in arms.values() else "NO-LIFT"


def _estimate(deltas: dict) -> tuple[float | None, float | None]:
    """(exp_r of the arm with the smaller p, min(1, 2 x that p))."""
    with_p = sorted((d["p"], arm) for arm, d in deltas.items() if d.get("p") is not None)
    if not with_p:
        return None, None
    p, arm = with_p[0]
    mean = deltas[arm].get("mean")
    return (None if mean is None else round(mean, 4)), round(min(1.0, 2 * p), 4)


def study_verdict(*, deltas: dict, calibration: dict, n_pairs: int, weeks: int) -> dict:
    arms = {arm: arm_verdict(deltas[arm], calibration["calibrated"]) for arm in ARMS}
    study = _study_word(arms, calibration["calibrated"], n_pairs, weeks)
    if study == "UNDERPOWERED":
        arms = {arm: "UNDERPOWERED" for arm in ARMS}
    exp_r, p = (None, None) if study == "UNCALIBRATED" else _estimate(deltas)
    return {"study": study, "arms": arms,
            "ledger": {"verdict": STUDY_TO_LEDGER[study], "n": n_pairs, "exp_r": exp_r, "p": p}}


def exploratory_close(calibration: dict, n_pairs: int) -> dict | None:
    """The study's close when the exploratory read is UNCALIBRATED; else None."""
    if calibration["calibrated"]:
        return None
    return {"study": "UNCALIBRATED", "arms": {arm: "UNCALIBRATED" for arm in ARMS},
            "ledger": {"verdict": "INCONCLUSIVE", "n": n_pairs, "exp_r": None, "p": None}}
