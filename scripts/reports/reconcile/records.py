"""Export records, populations and plan rehydration (v232 spec, ### Populations).

Reads the JSONL export of the live book: plan/trade/journal records, gate
rejections, the watchlist and deploy entries. Empty rejection or deploy sets
are measured zeros, never missing data.
"""
from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import json
from pathlib import Path

from autopsy.eras import ERA_BOUNDARY_UTC
from autopsy.rows import read_input
from swingbot.core.analytics.metrics import close_reason_text
from swingbot.core.analytics.override_fidelity import MANUAL_REASONS
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_from_dict

from . import sessions

KINDS = ("plan", "rejection", "watchlist", "deploy")
CLASSES = ("closed", "manual", "still_open", "unfilled")
_REJECTION_FIELDS = ("ticker", "gate", "strategy", "horizon", "signal_date")


@dataclasses.dataclass(frozen=True)
class LiveRecord:
    plan_id: str
    ticker: str
    direction: str
    plan: dict
    trade: dict | None
    journal: dict | None

    @property
    def side(self) -> str:
        return "short" if self.direction in ("bearish", "short") else "long"


@dataclasses.dataclass(frozen=True)
class Export:
    records: tuple[LiveRecord, ...]
    rejections: tuple[dict, ...]
    watchlist: tuple[str, ...]
    deploys: tuple[dict, ...]


def _plan_record(obj: dict) -> LiveRecord:
    plan = obj["plan"]
    return LiveRecord(plan["plan_id"], plan["ticker"], plan["direction"], plan,
                      obj.get("trade"), obj.get("journal"))


def _rejection(obj: dict) -> dict:
    return {k: obj.get(k) for k in _REJECTION_FIELDS}


_HANDLERS = {
    "plan": _plan_record,
    "rejection": _rejection,
    "watchlist": lambda obj: obj["ticker"],
    "deploy": lambda obj: dict(obj["entry"]),
}


def _parse_lines(text: str) -> dict[str, list]:
    buckets: dict[str, list] = {k: [] for k in KINDS}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        obj = json.loads(line)
        kind = obj.get("kind")
        if kind not in _HANDLERS:
            raise ValueError(f"line {number}: unknown kind {kind!r}")
        buckets[kind].append(_HANDLERS[kind](obj))
    return buckets


def _plan_session(rec: LiveRecord) -> dt.date:
    return sessions.issue_session(sessions.stamp_source(rec.plan)[0])


def load_export(path, *, input_fingerprints: dict | None = None,
                until: dt.date | None = None) -> Export:
    buckets = _parse_lines(read_input(Path(path), input_fingerprints))
    recs, rejections = buckets["plan"], buckets["rejection"]
    if until is not None:
        recs = [r for r in recs if _plan_session(r) <= until]
        rejections = [r for r in rejections if (r["signal_date"] or "") <= until.isoformat()]
    return Export(tuple(recs), tuple(rejections), tuple(sorted(set(buckets["watchlist"]))),
                  tuple(buckets["deploy"]))


def _last_reason(rec: LiveRecord) -> str:
    history = rec.plan.get("status_history") or []
    return (history[-1].get("reason") or "") if history else ""


def class_of(rec: LiveRecord) -> str:
    if rec.trade is None:
        return "unfilled"
    if not rec.trade.get("closed_at"):
        return "still_open"
    if _last_reason(rec) in MANUAL_REASONS or close_reason_text(rec.trade) in MANUAL_REASONS:
        return "manual"
    return "closed"


def era_of(rec: LiveRecord, boundary: dt.datetime = ERA_BOUNDARY_UTC) -> str:
    stamp = rec.trade["opened_at"] if rec.trade else sessions.stamp_source(rec.plan)[0]
    return "headline" if sessions.to_utc(stamp) >= boundary else "earlier"


def ledger_of(rec: LiveRecord) -> str:
    return (rec.trade or {}).get("ledger") or rec.plan.get("ledger") or "main"


def unfilled_reason(rec: LiveRecord) -> str:
    for entry in reversed(rec.plan.get("status_history") or []):
        if entry.get("status") == "CANCELLED":
            return entry.get("reason") or "cancelled"
    return "pending" if rec.plan.get("status") == "PENDING" else "unknown"


def rehydrate(plan_doc: dict) -> tuple[TradePlanV2, bool]:
    plan = plan_from_dict(copy.deepcopy(plan_doc))
    plan.working_stop = None
    plan.legs_realized = []
    plan.status_history = []
    plan.status = PlanStatus.PENDING
    plan.runner_high_close = None
    plan.be_armed_session = None
    plan.runner_floor_session = None
    if plan.entry_type != "market" or plan.waits_next_open is True:
        plan.entry_price = None
    return plan, plan.tp1_fraction < 1.0


def deploys_between(export: Export, start: dt.date, end: dt.date) -> list[dict]:
    kept = [d for d in export.deploys
            if d.get("ts") and start <= sessions.ny_time(d["ts"]).date() <= end]
    return sorted(kept, key=lambda d: d["ts"])
