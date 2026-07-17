"""Shadow-mode plan log: one JSONL line per scan item comparing the v2 plan
against the legacy scenario numbers it would replace. Read by
scripts/shadow_parity_report.py; the cutover decision (Task 88) is made on
this file's evidence."""
import json
import os
from datetime import datetime, timezone

from swingbot import config
from swingbot.core.plan_engine import plan_to_dict

MAX_BYTES = 50 * 1024 * 1024


def _default_path() -> str:
    return os.path.join(config.DATA_DIR, "shadow_plans.jsonl")


def append(plan, legacy_scenario_summary: dict, path: str | None = None) -> None:
    path = path or _default_path()
    if os.path.exists(path) and os.path.getsize(path) >= MAX_BYTES:
        os.replace(path, path + ".1")            # single rotation slot
    record = {
        "ts_scan": datetime.now(timezone.utc).isoformat(),
        "ticker": plan.ticker,
        "horizon": plan.horizon_key,
        "plan": plan_to_dict(plan),
        "legacy": legacy_scenario_summary,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")       # one write() call per line
