"""Attach gate results to plan records + blocked/shadow JSONL logs.
The shadow log is the evidence stream regardless of mode (G103)."""
from __future__ import annotations

import json
import os
import time

import swingbot.config as config
from swingbot.core.gate.types import GateResult

BLOCKED_PATH = os.path.join(config.DATA_DIR, "gate", "blocked.jsonl")
SHADOW_PATH = os.path.join(config.DATA_DIR, "gate", "shadow.jsonl")


def _append_jsonl(path: str, row: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def attach_to_plan(store, plan_id: str, result: GateResult) -> bool:
    """store = PlanStore (plan-engine-v2). Uses the additive set_extra hook
    added below -- plan_from_dict already filters to known TradePlanV2
    dataclass fields, so the extra 'gate' key on the record is a no-op for
    the legacy load path (verified in swingbot/core/plan_engine.py)."""
    return store.set_extra(plan_id, "gate", result.to_dict())


def blocked_log(result: GateResult, decision: str, reason: str) -> None:
    _append_jsonl(BLOCKED_PATH, {
        "ts": time.time(), "ticker": result.ticker, "strategy": result.strategy,
        "as_of": result.as_of, "tier": result.tier, "score": result.score,
        "decision": decision, "reason": reason,
        "hard_blocks": list(result.hard_blocks)})


def shadow_log(result: GateResult, plan_id: str | None = None) -> None:
    _append_jsonl(SHADOW_PATH, {
        "ts": time.time(), "plan_id": plan_id, "ticker": result.ticker,
        "strategy": result.strategy, "tier": result.tier, "score": result.score,
        "advisory_decision": result.advisory_decision,
        "fired_flags": [c.check_id for c in result.checks
                        if c.section == "redflag" and c.status == "fail"]})
