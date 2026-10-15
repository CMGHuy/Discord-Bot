"""v147: the gate-counterfactual report's inputs.

TRAIN rows come from the `--record-blocked` JSONL files (V147-5/-6). Live
blocked rows come from the `gate_rejections` table once resolved (V147-11).
Live taken rows are the issued plans re-walked through `simulate_blocked` --
the same `simulate_exit(..., scale_out=True)` call the blocked arm uses -- on
the live `market_data/` cache, so both arms are read by one instrument. The
realised R of the closed trade rides along as context and is never compared.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
from pathlib import Path

from swingbot import config
from swingbot.core.analytics.metrics import r_multiple
from swingbot.core.backtesting.blocked_recorder import gate_row
from swingbot.core.backtesting.gate_counterfactual import BlockedCandidate, simulate_blocked
from swingbot.core.market import session
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.marketdata.spot_metals import SPOT_PAIRS
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.core.risk_limits import planned_loss_pct

log = logging.getLogger(__name__)

LIVE_SINCE = "2026-10-01"
TRAIN_GLOB = "v147-blocked-*.jsonl"
REPO_ROOT = Path(__file__).resolve().parents[3]
OUTLOOK_ORIGIN = "next_session"


# --- TRAIN -------------------------------------------------------------------

def default_train_paths() -> list[Path]:
    """Every TRAIN gate-row file present: the repo's logs/ and, on the VM, <DATA_DIR>/reports/inputs/."""
    folders = (REPO_ROOT / "logs", Path(config.DATA_DIR) / "reports" / "inputs")
    return [path for folder in folders if folder.is_dir() for path in sorted(folder.glob(TRAIN_GLOB))]


def _check_train(row: dict, path) -> dict:
    if row.get("population") != "train":
        raise ValueError(f"{path}: row population {row.get('population')!r} is not 'train'")
    if row.get("gate") == "rs":
        raise ValueError(f"{path}: a TRAIN rs row -- the RS gate is live-only (v34 closed)")
    return row


def load_train_rows(paths) -> list[dict]:
    """Every row of every TRAIN JSONL file, in file order (a missing file raises)."""
    rows = []
    for path in paths:
        with Path(path).open(encoding="utf-8") as handle:
            rows.extend(_check_train(json.loads(line), path) for line in handle if line.strip())
    return rows


# --- live blocked ----------------------------------------------------------------

def _finite(value) -> float | None:
    return float(value) if value is not None and math.isfinite(float(value)) else None


def _plan_fields(record: dict) -> dict:
    plan = record.get("plan") if isinstance(record.get("plan"), dict) else {}
    loss = None
    if record.get("reason") == "risk_cap" and plan:
        loss = _finite(planned_loss_pct(plan.get("trigger_price"), plan.get("stop_loss")))
    return {"planned_loss_pct": loss, "expiry_bars": plan.get("expiry_bars", record.get("expiry_bars"))}


def live_blocked_rows(records) -> list[dict]:
    """Resolved `gate_rejections` records as shared gate rows; `pending` records are skipped."""
    rows = []
    for record in records:
        if record.get("cf_status") == "pending":
            continue
        rows.append(gate_row(
            population="live", arm="blocked", source=record["source"], ticker=record["ticker"],
            strategy=record["strategy"], horizon=record["horizon"], direction=record["direction"],
            signal_date=record["signal_date"], gate=record["gate"], reason=record.get("reason"),
            margin=record.get("margin"), cf_status=record["cf_status"], cf_r=record.get("cf_r"),
            win=record.get("win"), in_sample=False, **_plan_fields(record)))
    return rows


# --- live taken --------------------------------------------------------------------

def _in_scope(plan) -> bool:
    return getattr(plan, "origin", None) != OUTLOOK_ORIGIN and plan.ticker not in SPOT_PAIRS


def _taken_gates(plan) -> tuple:
    """The gates this issued plan passed and could have been blocked by."""
    gates = ["rs"]
    if plan.source != "strategy":
        gates.append("plan_rejected")
    if plan.strategy == COMPRESSION_SHORT:
        gates.append("compression")
    return tuple(gates)


def _walk(plan, bars, last_session):
    candidate = BlockedCandidate(
        ticker=plan.ticker, gate="taken", reason=None, source=plan.source, strategy=plan.strategy,
        horizon=plan.horizon_key, direction=plan.direction, signal_date=str(plan.created_at)[:10],
        plan=plan_to_dict(plan))
    return simulate_blocked(candidate, bars, last_session=last_session)


def _taken_row(plan, result, gate: str, realised_r) -> dict:
    row = gate_row(
        population="live", arm="taken", source=plan.source, ticker=plan.ticker, strategy=plan.strategy,
        horizon=plan.horizon_key, direction=plan.direction, signal_date=str(plan.created_at)[:10],
        gate=gate, reason=None, margin=None, cf_status=result.cf_status, cf_r=result.cf_r,
        win=result.win, expiry_bars=plan.expiry_bars, in_sample=False)
    row["realised_r"] = realised_r
    return row


def _memo(load_bars):
    cache = {}

    def bars_of(ticker):
        if ticker not in cache:
            cache[ticker] = load_bars(ticker)
        return cache[ticker]
    return bars_of


def live_taken_rows(plans, load_bars, *, last_session: str | None = None,
                    realised: dict | None = None) -> list[dict]:
    """Issued plans re-walked from the stored plan; one row per gate the plan passed."""
    realised = realised or {}
    bars_of = _memo(load_bars)
    rows = []
    for plan in plans:
        if not _in_scope(plan):
            continue
        result = _walk(plan, bars_of(plan.ticker), last_session)
        if result.cf_status == "pending":
            continue
        rows.extend(_taken_row(plan, result, gate, realised.get(plan.plan_id)) for gate in _taken_gates(plan))
    return rows


def realised_r_by_plan(trades=None) -> dict[str, float]:
    """plan_id -> realised R of its closed paper trade (context beside the re-walk, never compared)."""
    if trades is None:
        from swingbot.core.tracking.performance import TradeLog
        trades = TradeLog().get_trades(status="all", limit=None)
    out = {}
    for trade in trades:
        r = r_multiple(trade) if trade.get("plan_id") and trade.get("status") != "open" else None
        if r is not None:
            out[trade["plan_id"]] = float(r)
    return out


def last_completed_session(now=None) -> str:
    """ISO date of the last NYSE session whose regular close has passed."""
    moment = session.now_et(now)
    today, calendar = moment.date(), session.nyse_calendar()
    closed_today = calendar.is_session(today) and moment.time() >= session.session_close(today)
    cutoff = today if closed_today else today - dt.timedelta(days=1)
    return calendar.sessions(cutoff - dt.timedelta(days=14), cutoff)[-1].isoformat()


def load_live(*, since: str = LIVE_SINCE, now=None) -> tuple[list[dict], list[dict]]:
    """(live blocked rows, live taken rows) for the live window starting `since`."""
    from swingbot.core.db.repositories.gate_rejections import gate_rejections_repo
    from swingbot.core.marketdata import data_store
    from swingbot.core.planning.plan_store import PlanStore
    blocked = live_blocked_rows(gate_rejections_repo().list_since(since))
    plans = [plan for plan in PlanStore().all() if str(plan.created_at)[:10] >= since]
    taken = live_taken_rows(plans, lambda ticker: data_store.load_normalized(ticker, "daily"),
                            last_session=last_completed_session(now), realised=realised_r_by_plan())
    log.info("gate counterfactual live inputs: %d blocked rows, %d taken rows", len(blocked), len(taken))
    return blocked, taken
