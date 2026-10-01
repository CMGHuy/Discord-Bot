#!/usr/bin/env python3
"""v116 Phase 3 soak: the nightly check, and the gate that reads its log.

    check  inside the bot container, from v116_parity_check.sh (cron, 22:15 UTC Mon-Fri):
           python scripts/ops/v116_soak.py check --error-lines N [--day YYYY-MM-DD]
    gate   on a copy of logs/v116_parity.log (stdlib only):
           python scripts/ops/v116_soak.py gate --log FILE --group ops --stage dual [--need 5]

A group's day is CLEAN when every store of it at `dual` with a parity spec
compares clean and no database error line was logged in the last 24 h.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

GROUPS: dict[str, tuple[str, ...]] = {
    "ops": ("flags", "heartbeat", "jobs", "scheduled_jobs", "killswitch",
            "notify_queue", "scan_progress", "market_data_state"),
    "reference": ("watchlist", "state", "ticker_directory", "preferences",
                  "settings_audit", "tuning"),
    "trading": ("plans", "starred_plans", "trades", "account", "journal"),
}
VERDICT_RE = re.compile(r"^VERDICT day=(?P<day>\S+) trading_day=(?P<trading>yes|no) "
                        r"group=(?P<group>\S+) stage=(?P<stage>\S+) result=(?P<result>CLEAN|DIRTY)")


def group_stage(stage_by_store: dict, group: str) -> str:
    found = {stage_by_store.get(store, "json") for store in GROUPS[group]}
    return found.pop() if len(found) == 1 else "mixed"


def _store_lines(group: str, stage_by_store: dict, parity_ok) -> tuple[list[str], bool]:
    from scripts.db.parity_report import STAGE_STORES
    lines, clean = [], True
    for store in GROUPS[group]:
        stage = stage_by_store.get(store, "json")
        names = STAGE_STORES.get(store, ())
        if stage != "dual" or not names:
            why = "no parity spec (ephemeral)" if not names else f"parity not applicable at {stage}"
            lines.append(f"  {store:<18} {stage:<5} n/a -- {why}")
            continue
        for name in names:
            ok = parity_ok(name)
            clean = clean and ok
            lines.append(f"  {store:<18} {stage:<5} parity[{name}] {'clean' if ok else 'DIRTY'}")
    return lines, clean


def check_lines(day: str, trading_day: bool, error_lines: int, stage_by_store: dict,
                parity_ok) -> list[str]:
    out = []
    for group in GROUPS:
        stage = group_stage(stage_by_store, group)
        if stage == "json":
            continue
        lines, clean = _store_lines(group, stage_by_store, parity_ok)
        result = "CLEAN" if clean and error_lines == 0 and stage != "mixed" else "DIRTY"
        out.extend([f"--- group {group} ({stage}) ---", *lines,
                    f"VERDICT day={day} trading_day={'yes' if trading_day else 'no'} "
                    f"group={group} stage={stage} result={result} errors={error_lines}"])
    return out


def _weekday_lines(lines: list[str], group: str) -> dict[str, re.Match]:
    by_day = {}
    for line in lines:
        match = VERDICT_RE.match(line.strip())
        if match and match["group"] == group:
            by_day[match["day"]] = match          # a re-run the same day wins
    return by_day


def gate(lines: list[str], group: str, stage: str, need: int = 5) -> tuple[str, int]:
    """PASS after `need` consecutive clean trading days at `stage`; DIRTY if
    the latest trading day was dirty; else WAIT. A weekday with no line at
    all (the cron did not run) breaks the streak; a logged holiday does not."""
    by_day = _weekday_lines(lines, group)
    if not by_day:
        return "WAIT", 0
    day = dt.date.fromisoformat(min(by_day))
    last = dt.date.fromisoformat(max(by_day))
    streak, latest = 0, None
    while day <= last:
        match = by_day.get(day.isoformat())
        if match is None and day.weekday() < 5:
            streak = 0
        elif match is not None and match["trading"] == "yes":
            ok = match["stage"] == stage and match["result"] == "CLEAN"
            streak, latest = (streak + 1 if ok else 0), ok
        day += dt.timedelta(days=1)
    if streak >= need:
        return "PASS", streak
    return ("DIRTY" if latest is False else "WAIT"), streak


def _is_trading_day(day: dt.date) -> bool:
    from swingbot.core.market.session import NYSE_HOLIDAYS
    return day.weekday() < 5 and day not in NYSE_HOLIDAYS


def _parity_ok(name: str) -> bool:
    from scripts.db.parity_report import parity
    try:
        report = parity(name)
    except Exception as exc:  # noqa: BLE001 -- an erroring compare is not clean
        print(f"  parity[{name}] raised {type(exc).__name__}: {exc}")
        return False
    return report.ok


def _cmd_check(args) -> int:
    from swingbot import config
    from swingbot.core.db import stages
    day = dt.date.fromisoformat(args.day) if args.day else dt.datetime.now(dt.timezone.utc).date()
    print(f"DB_STORES={config.DB_STORES}")
    for line in check_lines(day.isoformat(), _is_trading_day(day), args.error_lines,
                            stages.parse(config.DB_STORES), _parity_ok):
        print(line)
    return 0


def _cmd_gate(args) -> int:
    with open(args.log, encoding="utf-8") as handle:
        verdict, streak = gate(handle.read().splitlines(), args.group, args.stage, args.need)
    print(f"GATE group={args.group} stage={args.stage} streak={streak} need={args.need} {verdict}")
    return {"PASS": 0, "WAIT": 3, "DIRTY": 1}[verdict]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.add_argument("--error-lines", type=int, required=True)
    check.add_argument("--day")
    gate_cmd = sub.add_parser("gate")
    gate_cmd.add_argument("--log", required=True)
    gate_cmd.add_argument("--group", required=True, choices=sorted(GROUPS))
    gate_cmd.add_argument("--stage", required=True, choices=("dual", "db"))
    gate_cmd.add_argument("--need", type=int, default=5)
    args = parser.parse_args(argv)
    return _cmd_check(args) if args.command == "check" else _cmd_gate(args)


if __name__ == "__main__":
    sys.exit(main())
