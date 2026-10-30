"""v191 ATR-band replay: every confluence signal replayed with the floor off
(baseline) and at each floor k for one target arm, from the same bars.

Unlike v139 arm S, the band changes WHICH plans exist: scenarios the percent
floor refused are admitted (newly_admitted), arm K drops plans under the
minimum reward:risk (band_rr_drop), arm R drops plans with no target
(band_no_target), and the per-direction cooldown can shift. So the baseline
and each cell are joined on the union of (signal index, direction) per ticker
and horizon, never zipped by position.

Two row shapes, both plain JSON types: census rows (Stage -1 -- plans only,
plus the spec's one outcome-adjacent disclosure, stop-then-reversal on the
BASELINE) and outcome rows (Stages 0-3).

Dollar view: each traded record is sized on REFERENCE_ACCOUNT at the fill
with both gap-sizing flags on (the coupled configuration a live floor
requires) and OPEX scaling pinned to 1.0, through gap_sizing -- the one
sizing function the alert and the engine use. R is never re-priced.
"""
from __future__ import annotations

import copy
import dataclasses
from contextlib import contextmanager
from typing import NamedTuple
from unittest import mock

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.backtesting.acceptance import arm_trade_from_plan
from swingbot.core.backtesting.acceptance_replay import UNTRIGGERED, _exit_mix, _gap_through
from swingbot.core.backtesting.arms.knobs import apply_knobs
from swingbot.core.market import atr_band, opex
from swingbot.core.planning import gap_sizing
from swingbot.core.planning.builders import STOP_GEOMETRY_TOL, band_no_plan_reason
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.stop_scope import band_sizing_verdict, plan_stop_ceiling
from swingbot.core.risk_limits import planned_loss_pct
from swingbot.scan_params import ScanParams

FLOOR_KNOB = "CONFLUENCE_ATR_STOP_FLOOR"
MODE_KNOB = "CONFLUENCE_ATR_TARGET_MODE"
#: PRE-REGISTERED (spec § Arm R / § Arm K): arm -> CONFLUENCE_ATR_TARGET_MODE.
ARMS = {"R": "rechoose", "K": "keep"}
#: PRE-REGISTERED floor grid (spec § Definitions). A new step is a new pre-registration.
K_STEPS = atr_band.FLOOR_GRID
REFERENCE_ACCOUNT = {"balance": 10000.0, "risk_pct": 1.0, "sizing_mode": "risk_pct",
                     "position_pct": 10.0, "max_position_pct": 100.0,
                     "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}
DOLLAR_VIEW_FLAGS = {"LONG_GAP_SIZING": True, "SHORT_GAP_SIZING": True}
#: A loss past the budget by more than this is an exceedance; less is the
#: rounding noise of 0.01-share sizing.
EXCEED_TOL_DOLLARS = 0.5
EARLY_STOP_SESSIONS = 2
ADV_BARS = 20
_BASELINE = (0.0, "rechoose")


def cell_key(k) -> str:
    """Stable JSON key for a floor: 'k0.75', 'k1', 'k1.5'."""
    return f"k{float(k):g}"


class Signal(NamedTuple):
    """One (signal index, direction) of one ticker and horizon, on every side."""
    i: int
    direction: str
    base: object        # baseline TradePlanV2 | None
    plans: dict         # cell_key -> TradePlanV2 | None
    blocked: dict       # cell_key -> (scenario, band reason | None) | None


# --- replay -------------------------------------------------------------------

def _check_knobs_off() -> None:
    if config.CONFLUENCE_STRUCTURAL_STOP_PCT or config.CONFLUENCE_STOP_DROP_PCT:
        raise RuntimeError(
            "CONFLUENCE_STRUCTURAL_STOP_PCT and CONFLUENCE_STOP_DROP_PCT must be 0 while "
            "measuring v191: a v139 knob is never set with a v191 knob.")


def _mode(arm) -> str:
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {sorted(ARMS)}, got {arm!r}")
    return ARMS[arm]


def _delta(k, mode) -> dict:
    return {FLOOR_KNOB: float(k), MODE_KNOB: mode}


def _replay(ticker, df, horizon_key, k, mode, gates, blocked=None) -> list:
    """replay_scenarios at floor k and target mode; apply_knobs reaches both
    ScanParams.from_config() call sites inside the replay."""
    with apply_knobs(_delta(k, mode)):
        return bs.replay_scenarios(ticker, df, horizon_key, gates=gates, blocked=blocked)


def _blocked_reasons(ticker, df, horizon_key, k, mode, gates, blocked) -> dict:
    """{(i, direction): (scenario, reason)} for the scenarios a cell's plan
    build refused, the reason named by builders.band_no_plan_reason with the
    bar's own level map and the build params the replay used. First per key."""
    out: dict = {}
    if not blocked:
        return out
    with apply_knobs(_delta(k, mode)):
        params, legacy = bs._replay_params(None, gates)
        scope = bs._ReplayScope(ticker, horizon_key, bs.HORIZONS[horizon_key], params, legacy, None)
        build_params = ScanParams.from_config() if legacy else params
        for i, sc in blocked:
            key = (int(i), sc.direction)
            if key not in out:
                cache = {}
                bs.levels_asof(ticker, df, bs.bucket_bar(int(i), horizon_key), horizon_key, cache)
                level_map = bs._bar_scenarios(scope, df, int(i), cache, None)[2]
                out[key] = (sc, band_no_plan_reason(sc, level_map, build_params))
    return out


def _by_key(plans) -> dict:
    return {(int(i), plan.direction): plan for i, plan in plans}


def _cell_side(ticker, df, horizon_key, k, mode, gates, with_blocked) -> tuple:
    blocked = [] if with_blocked else None
    plans = _by_key(_replay(ticker, df, horizon_key, k, mode, gates, blocked))
    reasons = _blocked_reasons(ticker, df, horizon_key, k, mode, gates, blocked) \
        if with_blocked else {}
    return plans, reasons


def signals(ticker, df, horizon_key, *, arm, cells=K_STEPS, gates=None,
            with_blocked=False) -> list[Signal]:
    """The union of the baseline's and every cell's (signal index, direction),
    sorted. `gates` is the replay_scenarios test seam (None = live ScanParams)."""
    _check_knobs_off()
    mode = _mode(arm)
    base = _by_key(_replay(ticker, df, horizon_key, *_BASELINE, gates))
    by_cell, blocked_by_cell = {}, {}
    for k in cells:
        by_cell[cell_key(k)], blocked_by_cell[cell_key(k)] = _cell_side(
            ticker, df, horizon_key, k, mode, gates, with_blocked)
    keys = set(base).union(*by_cell.values(), *blocked_by_cell.values())
    return [Signal(i, d, base.get((i, d)),
                   {key: plans.get((i, d)) for key, plans in by_cell.items()},
                   {key: reasons.get((i, d)) for key, reasons in blocked_by_cell.items()})
            for i, d in sorted(keys)]


# --- row context ----------------------------------------------------------------

def _anchor(sig) -> tuple:
    """(entry, level) of the signal: any plan's trigger and pre-clamp level,
    else the blocked scenario's entry and stop."""
    plan = sig.base or next((p for p in sig.plans.values() if p is not None), None)
    if plan is not None:
        return plan.trigger_price, plan.acceptance_level
    sc = next(b[0] for b in sig.blocked.values() if b is not None)
    return sc.entry, sc.stop_loss


def _adv(window) -> float | None:
    if window.empty or "Volume" not in window:
        return None
    tail = window.tail(ADV_BARS)
    return float((tail["Close"] * tail["Volume"]).mean())


def _context(df, sig) -> dict:
    entry, level = _anchor(sig)
    window = df.iloc[: sig.i + 1]
    return {"d": None if level is None else planned_loss_pct(entry, level),
            "atr_pct": atr_band.raw_atr14_pct(window, entry), "adv_dollars": _adv(window)}


def _identity(ticker, horizon_key, df, sig, arm) -> dict:
    return {"arm": arm, "ticker": ticker, "horizon_key": horizon_key,
            "entry_date": str(df.index[sig.i].date()), "signal_index": sig.i,
            "direction": sig.direction}


def _would_move(plan, atr_pct, k) -> str | None:
    """The band a baseline plan would have carried at floor k."""
    if plan is None or plan.acceptance_level is None:
        return None
    band = atr_band.band_stop(plan.trigger_price, plan.acceptance_level,
                              plan.direction == "bullish", atr_pct, k)
    return None if band is None else band.moved_by


def _moved_by(sig, atr_pct, cells) -> dict:
    out = {}
    for k in cells:
        plan = sig.plans[cell_key(k)]
        out[cell_key(k)] = plan.stop_moved_by if plan is not None \
            else _would_move(sig.base, atr_pct, k)
    return out


def _newly_admitted(sig, cells) -> dict:
    return {cell_key(k): sig.base is None and sig.plans[cell_key(k)] is not None for k in cells}


# --- dollar view ------------------------------------------------------------------

@contextmanager
def _dollar_env():
    with apply_knobs(DOLLAR_VIEW_FLAGS), mock.patch.object(opex, "size_mult", return_value=1.0):
        yield


def _account() -> dict:
    return dict(REFERENCE_ACCOUNT)


def _budget() -> float:
    return REFERENCE_ACCOUNT["balance"] * REFERENCE_ACCOUNT["risk_pct"] / 100.0


def _stamped(window, plan):
    sized = copy.copy(plan)
    gap_sizing.stamp_gap_sizing(sized, window)
    return sized


def _shares(window, plan, fill) -> float:
    with _dollar_env():
        result = gap_sizing.size_for_plan(_stamped(window, plan), entry=fill,
                                          account_cfg=_account())
    return float((result or {}).get("shares") or 0.0)


def _dollar_pnl(plan, res, shares) -> float:
    side = 1.0 if plan.direction == "bullish" else -1.0
    move = sum(float(leg["fraction"]) * (float(leg["exit_price"]) - res.entry_price)
               for leg in res.legs)
    return round(shares * side * move, 2)


def _size_zero(df, i, plan) -> bool:
    if plan is None or plan.stop_moved_by is None:
        return False
    with _dollar_env():
        verdict = band_sizing_verdict(
            _stamped(df.iloc[: i + 1], plan),
            sizing_fn=lambda p: gap_sizing.size_for_plan(p, account_cfg=_account()))
    return verdict == atr_band.REASON_SIZE_ZERO


# --- outcome records ----------------------------------------------------------------

def _early_stop(res) -> bool:
    return _exit_mix(res) == "stop" and res.exit_index - res.entry_index <= EARLY_STOP_SESSIONS


def _overshoot_r(df, plan, res) -> float:
    bar_open = float(df["Open"].values[res.exit_index])
    return abs(bar_open - plan.stop_loss) / abs(res.entry_price - plan.stop_loss)


def _record(df, i, plan, atr_pct) -> dict | None:
    """One side's exit as ArmTrade fields plus the disclosures, or None when
    the plan never became a trade. fill_beyond_ceiling: a fill live
    plan_manager would cancel (cancelled_risk_cap) that the replay keeps."""
    res = simulate_exit(df, i, plan, scale_out=True)
    if res.outcome in UNTRIGGERED:
        return None
    trade = arm_trade_from_plan(plan, entry_date=str(df.index[i].date()),
                                outcome=res.outcome, r_multiple=res.r_total)
    shares = _shares(df.iloc[: i + 1], plan, res.entry_price)
    pnl = _dollar_pnl(plan, res, shares)
    distance = planned_loss_pct(plan.trigger_price, plan.stop_loss)
    gap = _gap_through(df, plan, res)
    return {**dataclasses.asdict(trade), "exit_mix": _exit_mix(res), "gap_through": gap,
            "fill_beyond_ceiling": planned_loss_pct(res.entry_price, plan.stop_loss)
            > plan_stop_ceiling(plan) + STOP_GEOMETRY_TOL,
            "stop_moved_by": plan.stop_moved_by, "stop_distance_pct": distance,
            "stop_distance_atr": distance / atr_pct if atr_pct else None,
            "early_stop": _early_stop(res),
            "gap_overshoot_r": _overshoot_r(df, plan, res) if gap else None,
            "regime2_state": (plan.entry_context or {}).get("regime2_state"),
            "shares": shares, "dollar_pnl": pnl,
            "dollar_exceeds_budget": pnl < -(_budget() + EXCEED_TOL_DOLLARS)}


def _same_geometry(a, b) -> bool:
    return (a.trigger_price, a.stop_loss, a.tp1, a.tp2, a.entry_type) == \
        (b.trigger_price, b.stop_loss, b.tp1, b.tp2, b.entry_type)


def _cell_record(df, i, plan, base, baseline, atr_pct) -> dict | None:
    if plan is None:
        return None
    if base is not None and plan.stop_moved_by is None and _same_geometry(plan, base):
        return baseline          # no band on this plan (band_no_atr): today's trade
    return _record(df, i, plan, atr_pct)


def entry_row(ticker, horizon_key, df, sig, arm, cells) -> dict | None:
    """One signal under the baseline and every cell; None when nothing traded."""
    ctx = _context(df, sig)
    baseline = None if sig.base is None else _record(df, sig.i, sig.base, ctx["atr_pct"])
    records = {cell_key(k): _cell_record(df, sig.i, sig.plans[cell_key(k)], sig.base, baseline,
                                         ctx["atr_pct"]) for k in cells}
    if baseline is None and all(record is None for record in records.values()):
        return None
    return {**_identity(ticker, horizon_key, df, sig, arm), **ctx,
            "baseline": baseline, "cells": records,
            "moved_by": _moved_by(sig, ctx["atr_pct"], cells),
            "newly_admitted": _newly_admitted(sig, cells)}


# --- census -------------------------------------------------------------------------

def _crossed(bull, low, high, level, *, below) -> bool:
    if bull:
        return low <= level if below else high >= level
    return high >= level if below else low <= level


def _reached_tp1_first(df, start, end, plan, lo_pct) -> bool:
    bull = plan.direction == "bullish"
    line = plan.trigger_price * (1 - lo_pct / 100 if bull else 1 + lo_pct / 100)
    lows, highs = df["Low"].values, df["High"].values
    for j in range(start, end + 1):
        if _crossed(bull, lows[j], highs[j], line, below=True):
            return False
        if _crossed(bull, lows[j], highs[j], plan.tp1, below=False):
            return True
    return False


def _reversal(df, i, base, atr_pct, cells) -> dict | None:
    """Spec § Stage -1: a baseline stop exit whose price later reached TP1
    within the horizon without first breaching k x ATR. Outcome-adjacent,
    read once, never selects k. None unless the baseline stopped out."""
    if base is None or atr_pct is None:
        return None
    res = simulate_exit(df, i, base, scale_out=True)
    if res.outcome in UNTRIGGERED or _exit_mix(res) != "stop":
        return None
    end = min(res.entry_index + bs.HORIZONS[base.horizon_key]["max_holding_days"], len(df) - 1)
    return {cell_key(k): _reached_tp1_first(df, res.entry_index, end, base, atr_pct * float(k))
            for k in cells}


def _life_end(df, i, horizon_key) -> str:
    end = min(i + bs.HORIZONS[horizon_key]["max_holding_days"], len(df) - 1)
    return str(df.index[end].date())


def _dropped_reason(sig, key) -> str | None:
    if sig.plans[key] is not None or sig.blocked.get(key) is None:
        return None
    return sig.blocked[key][1]


def census_row(ticker, horizon_key, df, sig, arm, cells) -> dict:
    """Plans only; the baseline alone is simulated, for the reversal count."""
    ctx = _context(df, sig)
    keys = [cell_key(k) for k in cells]
    return {**_identity(ticker, horizon_key, df, sig, arm), **ctx,
            "in_baseline": sig.base is not None,
            "life_end_date": _life_end(df, sig.i, horizon_key),
            "in_cell": {key: sig.plans[key] is not None for key in keys},
            "moved_by": _moved_by(sig, ctx["atr_pct"], cells),
            "newly_admitted": _newly_admitted(sig, cells),
            "dropped": {key: _dropped_reason(sig, key) for key in keys},
            "size_zero": {key: _size_zero(df, sig.i, sig.plans[key]) for key in keys},
            "reversal": _reversal(df, sig.i, sig.base, ctx["atr_pct"], cells)}


# --- entry points -------------------------------------------------------------------

def _in_window(signal_date, start, end) -> bool:
    return not ((start and signal_date < start) or (end and signal_date > end))


def _rows(make, ticker, df, horizons, arm, window, cells, gates, with_blocked) -> list:
    start, end = window
    rows = []
    for horizon_key in horizons:
        for sig in signals(ticker, df, horizon_key, arm=arm, cells=cells, gates=gates,
                           with_blocked=with_blocked):
            if not _in_window(str(df.index[sig.i].date()), start, end):
                continue
            row = make(ticker, horizon_key, df, sig, arm, cells)
            if row is not None:
                rows.append(row)
    return rows


def replay_entries(ticker, df, horizons, *, arm, start=None, end=None, cells=K_STEPS,
                   gates=None) -> list[dict]:
    """Outcome rows for one ticker and arm. `start`/`end` (ISO or None)
    restrict the SIGNAL date; the exit walk may run past `end`. Stage 3 and
    the 2023 fold pass the one selected cell so no other cell is read."""
    return _rows(entry_row, ticker, df, horizons, arm, (start, end),
                 tuple(float(k) for k in cells), gates, False)


def census(ticker, df, horizons, *, arm, start=None, end=None, cells=K_STEPS,
           gates=None) -> list[dict]:
    """Plan-only rows for one ticker and arm (Stage -1)."""
    return _rows(census_row, ticker, df, horizons, arm, (start, end),
                 tuple(float(k) for k in cells), gates, True)
