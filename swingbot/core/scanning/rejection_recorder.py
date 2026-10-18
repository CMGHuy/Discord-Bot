"""v147: fail-open recording of live gate rejections into `gate_rejections`.

Called once at each live block point -- the strategy pass loop
(`strategy_pass._emit_signal`), `_sync_run_scan`'s serial merge and
`short_run._qualified_items` -- never from a `map_tickers` worker and never
from `qualify.py` (shared with the outlook and the replays). Every entry point
catches `Exception`, logs at most one warning per WARN_INTERVAL_S and returns
False: the gate's own decision never depends on the write, and a swallowed
database error must never reach `write_failure.is_store_write_failure`, which
would halt issuance.

Price basis (spec § Price basis). `signal_date` is the last bar of the frame
the gate saw -- the live constructor's own `created_at`. Its close is stored as
`signal_close` only when that bar is completed; an intraday scan's forming bar
stores `basis_date`/`basis_close` (the last completed bar) instead, which the
resolver (`backtesting/gate_resolver.py`) turns into the implied write-basis
close.

Heat at block time is stored as None (`heat_before`, `heat_cap`): heat is
computed in `analyze.build_decision_context` after a plan exists, which no
reject site reaches.
"""
from __future__ import annotations

import datetime as dt
import logging
import time

from swingbot.core.edge.rs_gate import rs_margin
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata.spot_metals import is_spot_metal

log = logging.getLogger(__name__)

WARN_INTERVAL_S = 600.0
NO_PLAN_REASONS = frozenset({"no_qualifying_target"})
_SHORT_GATES = {"rs": "rs", "plan": "plan_rejected"}   # qualify.Rejected.stage -> gate
_last_warning: float | None = None


def _repo():
    """The live store; tests monkeypatch this factory."""
    from swingbot.core.db.repositories.gate_rejections import gate_rejections_repo
    return gate_rejections_repo()


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _warn(what: str) -> None:
    """One warning per WARN_INTERVAL_S, the rest at DEBUG: a down database must not flood the log."""
    global _last_warning
    now = time.monotonic()
    if _last_warning is None or now - _last_warning >= WARN_INTERVAL_S:
        _last_warning = now
        log.warning("gate rejection not recorded (%s) -- scan unaffected", what, exc_info=True)
        return
    log.debug("gate rejection not recorded (%s)", what, exc_info=True)


def _bar_date(frame) -> str:
    return frame.index[-1].date().isoformat()


def _basis(frame, now: dt.datetime) -> dict:
    """`signal_close` when the signal bar is completed; else the last completed bar as the basis."""
    from swingbot.core.scanning.strategy_pass import completed_frame
    done = completed_frame(frame, now)
    if len(done) == len(frame):
        return {"signal_close": float(frame["Close"].iloc[-1])}
    if len(done) == 0:
        return {"signal_close": None, "basis_date": None, "basis_close": None}
    return {"signal_close": None, "basis_date": _bar_date(done),
            "basis_close": float(done["Close"].iloc[-1])}


def _as_dict(value, to_dict):
    if value is None or isinstance(value, dict):
        return value
    return to_dict(value)


def _snapshot(fields: dict, frame, now: dt.datetime) -> dict:
    """The flat `gate_rejections` record; the repository splits promoted columns from `doc`."""
    from swingbot.core.backtesting.gate_counterfactual import scenario_to_dict
    from swingbot.core.planning.plan_types import plan_to_dict
    no_plan = fields["reason"] in NO_PLAN_REASONS
    margin = fields["margin"]
    return {**fields,
            "margin": None if margin is None else float(margin),
            "plan": _as_dict(fields["plan"], plan_to_dict),
            "scenario": _as_dict(fields["scenario"], scenario_to_dict),
            "entry_context": dict(fields["entry_context"] or {}),
            "cf_status": "no-plan" if no_plan else "pending",
            "created_at": now,
            "resolved_at": now if no_plan else None,
            "heat_before": None, "heat_cap": None,
            **_basis(frame, now)}


def record_rejection(*, ticker, gate, reason, source, strategy, horizon, direction, signal_date,
                     frame, margin=None, plan=None, scenario=None, scan_params=None,
                     entry_context=None) -> bool:
    """Insert one blocked candidate. True when a new row was written; never raises."""
    if is_spot_metal(ticker):
        return False
    fields = {"ticker": ticker, "gate": gate, "reason": reason, "source": source,
              "strategy": strategy, "horizon": horizon, "direction": direction,
              "signal_date": signal_date, "margin": margin, "plan": plan, "scenario": scenario,
              "scan_params": scan_params, "entry_context": entry_context}
    try:
        return bool(_repo().insert_ignore(_snapshot(fields, frame, _utc_now())))
    except Exception as exc:   # noqa: BLE001 -- fail-open: a recording failure never touches the scan
        swallowed(log, "scan.record_rejection", exc, level=logging.DEBUG)
        _warn(f"{ticker} {gate} {strategy} {horizon}")
        return False


def _record_built(label: str, build) -> bool:
    """record_rejection(**build()), with a failure while building the arguments swallowed too."""
    try:
        kwargs = build()
    except Exception as exc:   # noqa: BLE001 -- fail-open
        swallowed(log, "scan.record_built", exc, level=logging.DEBUG)
        _warn(label)
        return False
    return record_rejection(**kwargs)


def _scan_params(strategy: str, plan: dict | None) -> dict:
    """The pinned overrides and ScanParams as they stood at the block (V147-3)."""
    from swingbot.core.backtesting.gate_counterfactual import pinned_scan_params
    from swingbot.core.planning.plan_types import plan_from_dict
    from swingbot.scan_params import ScanParams
    return pinned_scan_params(strategy, plan=plan_from_dict(plan) if plan else None,
                              params=ScanParams.from_config())


def _strategy_margin(deps, ticker: str, gate: str) -> float | None:
    if gate != "rs":
        return None
    value = deps.rs_combined_of(ticker)
    return None if value is None else rs_margin(float(value))


def record_strategy_block(deps, frame, *, ticker, strategy, horizon, direction, gate, reason,
                          entry_context=None) -> bool:
    """L1 (rs) / L2 (compression) in `strategy_pass._emit_signal`; `frame` is the completed frame."""
    def build() -> dict:
        return dict(ticker=ticker, gate=gate, reason=reason, source="strategy", strategy=strategy,
                    horizon=horizon, direction=direction, signal_date=_bar_date(frame),
                    frame=frame, margin=_strategy_margin(deps, ticker, gate),
                    scan_params=_scan_params(strategy, None), entry_context=entry_context)
    return _record_built(f"{ticker} {gate} {strategy} {horizon}", build)


def _item_margin(item, gate: str) -> float | None:
    if gate == "rs":
        value = getattr(item, "rs_combined", None)
        return None if value is None else rs_margin(float(value))
    return getattr(item, "plan_v2_rejected_margin", None)


def _item_fields(item, frames, gate: str, reason: str, source: str) -> dict:
    from swingbot.core.planning.builders import primary_strategy_for
    result, scenario = item.result, item.plan
    frame = frames.get(result.ticker)
    strategy = primary_strategy_for(scenario)
    plan = getattr(item, "plan_v2_rejected_plan", None) if gate == "plan_rejected" else None
    return dict(ticker=result.ticker, gate=gate, reason=reason, source=source, strategy=strategy,
                horizon=result.horizon_key, direction=result.trend, signal_date=_bar_date(frame),
                frame=frame, margin=_item_margin(item, gate), plan=plan, scenario=scenario,
                scan_params=_scan_params(strategy, plan))


def record_item_block(item, frames: dict, gate: str, reason: str, *, source: str) -> bool:
    """L3/L4 (`_sync_run_scan` merge, source "confluence") and L5/L6 (source "short_lane")."""
    ticker = getattr(getattr(item, "result", None), "ticker", "?")
    return _record_built(f"{ticker} {gate} {reason}",
                         lambda: _item_fields(item, frames, gate, reason, source))


def record_short_verdict(verdict, frames: dict) -> bool:
    """One `qualify_short_item` verdict from the live short lane: rs and plan stages only."""
    gate = _SHORT_GATES.get(getattr(verdict, "stage", None))
    if gate is None:
        return False
    return record_item_block(verdict.item, frames, gate, verdict.reason, source="short_lane")
