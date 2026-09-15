"""Print v81 execution-feed wording end to end without Discord, network or data.

    python scripts/dev/preview_execution_feed.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.planning.plan_types import TradePlanV2
from swingbot.core.presentation.instructions import block_warnings, instruction_for, ticket_for

SIZING = {"shares": 2439.02, "risk_amount": 10000.0}


def plan(**updates) -> TradePlanV2:
    base = dict(plan_id="preview1", ticker="AAPL", created_at="2026-09-10", source="strategy",
                strategy="RSI Pullback", horizon_key="1m", direction="bullish",
                entry_type="stop_entry", trigger_price=102.5, entry_price=None, expiry_bars=5,
                stop_loss=98.4, tp1=106.0, tp1_fraction=0.5, tp2=110.0,
                breakeven_trigger_fraction=0.5, trail_atr_mult=3.0, quality_score=70,
                quality_breakdown=[], badge="VALIDATED", badge_stats={}, status="PENDING")
    base.update(updates)
    return TradePlanV2(**base)


def show(title, instruction):
    print(f"=== {title}")
    print(f"[{instruction.verb}] {instruction.ticker} ({instruction.direction}, tone={instruction.tone})")
    for line in (*instruction.warnings, instruction.headline, *instruction.lines):
        print(f"  {line}")
    print()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pending = plan()
    short = plan(direction="bearish", trigger_price=97.5, stop_loss=101.6, tp1=94.0, tp2=None)
    active = plan(status="ACTIVE", entry_price=102.61)
    partial = plan(status="PARTIAL", entry_price=102.61, working_stop=104.87,
                   legs_realized=[{"fraction": .5, "exit_price": 106., "r": .81, "reason": "tp1"}])
    closed = plan(status="CLOSED", entry_price=102.61, working_stop=107.3,
                  legs_realized=[{"fraction": .5, "exit_price": 106., "r": .81, "reason": "tp1"},
                                 {"fraction": .5, "exit_price": 107.3, "r": 1.11, "reason": "tp1_runner_trail"}])
    for title, ticket in [
        ("ticket: long stop entry", ticket_for(pending, logged=True, not_logged_reason=None, sizing=SIZING, currency="$", level=5)),
        ("ticket: short stop entry, unsized", ticket_for(short, logged=True, not_logged_reason=None, sizing=None, level=4)),
        ("ticket: market entry", ticket_for(plan(entry_type="market"), logged=True, not_logged_reason=None, sizing=SIZING, currency="$", level=4)),
        ("ticket: blocked", ticket_for(pending, logged=True, not_logged_reason=None, sizing=SIZING, currency="$", level=5, warnings=block_warnings(heat={"open_heat": 6.2, "cap": 6.0}, cluster=None, kill={"reason": "3 losses"}))),
        ("ticket: not logged", ticket_for(pending, logged=False, not_logged_reason="already open", sizing=SIZING)),
    ]:
        show(title, ticket)
    events = [
        ("filled", active, PlanEvent("preview1", "filled", {"entry_price": 102.61})),
        ("break-even armed", active, PlanEvent("preview1", "be_moved", {"working_stop": 102.61})),
        ("TP1 banked", partial, PlanEvent("preview1", "tp1_partial", {"fraction": .5, "exit_price": 106., "r": .81, "working_stop": 104.87})),
        ("trail moved", partial, PlanEvent("preview1", "stop_moved", {"old": 104.87, "new": 107.3, "r_moved": .58, "effective": "now"})),
        ("expired", pending, PlanEvent("preview1", "cancelled_expired", {"bars_waited": 6})),
        ("invalidated short", short, PlanEvent("preview1", "cancelled_invalidated", {"live_price": 101.7})),
        ("trail exit", closed, PlanEvent("preview1", "closed", {"reason": "tp1_runner_trail", "exit_price": 107.3, "session": "regular", "notified_stop": 106.9, "bot_stop": 107.3})),
        ("after-hours stop", plan(status="CLOSED", entry_price=102.61), PlanEvent("preview1", "closed", {"reason": "loss", "exit_price": 97.8, "session": "extended", "notified_stop": 98.4, "bot_stop": 98.4})),
    ]
    for title, event_plan, event in events:
        show(title, instruction_for(event_plan, event, sizing=SIZING))


if __name__ == "__main__":
    main()
