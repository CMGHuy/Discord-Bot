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


def _read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _load_closed_trades() -> list[dict]:
    """Real closed-trade source for join_shadow_outcomes()'s default path.
    The plan's own audit note flagged `performance.load_closed_trades()` as
    unverified -- no such function exists in this codebase. TradeLog is the
    real trade-history store (status "win"/"loss" on a closed record, with
    a v2 `plan_id` when one exists) and
    swingbot.core.analytics.metrics.r_multiple is THE shared R-multiple
    computation, so this adapts both to the {plan_id, outcome, r_multiple}
    shape join_shadow_outcomes expects. Trades without a plan_id (legacy/
    v1) are dropped here too -- join_shadow_outcomes can only match on
    plan_id anyway."""
    from swingbot.core.analytics.metrics import r_multiple as _r_multiple
    from swingbot.core.performance import TradeLog

    trades = TradeLog().get_trades(status="all", limit=None)
    out = []
    for t in trades:
        if not t.get("plan_id") or t.get("status") not in ("win", "loss"):
            continue
        out.append({"plan_id": t["plan_id"], "outcome": t["status"],
                    "r_multiple": _r_multiple(t) or 0.0})
    return out


def join_shadow_outcomes(shadow_rows=None, trades=None) -> list[dict]:
    """Join shadow.jsonl rows to closed-trade outcomes by plan_id."""
    rows = shadow_rows if shadow_rows is not None else _read_jsonl(SHADOW_PATH)
    if trades is None:
        trades = _load_closed_trades()
    by_plan = {t.get("plan_id"): t for t in trades if t.get("plan_id")}
    joined = []
    for row in rows:
        trade = by_plan.get(row.get("plan_id"))
        if trade and trade.get("outcome") in ("win", "loss"):
            joined.append({**row, "outcome": trade["outcome"],
                           "r_multiple": trade.get("r_multiple", 0.0)})
    return joined


def shadow_cohorts(joined: list[dict]) -> dict:
    """{n, wr, expectancy_r} for the would-have-blocked cohort vs. the
    passed cohort (everything else) -- the shadow-vs-outcome comparison
    G104 exists to answer: would enforce's blocks have actually helped?"""
    def _stats(rows):
        n = len(rows)
        wins = sum(r["outcome"] == "win" for r in rows)
        return {"n": n, "wr": round(100.0 * wins / n, 1) if n else None,
                "expectancy_r": (round(sum(r["r_multiple"] for r in rows) / n, 3)
                                 if n else None)}
    return {"would_block": _stats([r for r in joined
                                   if r["advisory_decision"] == "block"]),
            "passed": _stats([r for r in joined
                              if r["advisory_decision"] != "block"])}
