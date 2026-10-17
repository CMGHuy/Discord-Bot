"""v170 alert-surface gate: render every execution-feed message kind from
fixed fixtures, against whichever tree --root points at.

    python scripts/dev/render_feed_samples.py --root <tree> --json <out.json>
    python scripts/dev/render_feed_samples.py --merge <before.json> <after.json> --out <note.md>

build_ticket_embed(item, plan) and build_instruction_embed(plan, event) keep
their signatures across v170, so one script renders both trees. Sizing is a
fixed snapshot; after v170 the linked paper record is fixed too (before v170
that seam does not exist and is skipped). No Discord, network or database."""
import argparse
import asyncio
import json
import subprocess
import sys
import types
from pathlib import Path

PID = "0f8fad5b-d9cb-469f-a165-70867728950e"
SIZING = {"shares": 54.35, "risk_amount": 250.0}
TP1_LEG = {"fraction": 0.5, "exit_price": 189.10, "r": 1.4565, "reason": "tp1"}
SHORT = dict(direction="bearish", trigger_price=50.0, stop_loss=52.0, tp1=46.0, tp2=43.0)
FILLED = dict(status="ACTIVE", entry_price=182.40)
PARTIAL = dict(status="PARTIAL", entry_price=182.40, working_stop=182.40, legs_realized=[TP1_LEG])
CLOSED_LOSS = dict(status="CLOSED", entry_price=182.40)
CLOSED_WIN = dict(status="CLOSED", entry_price=182.40, legs_realized=[
    TP1_LEG, {"fraction": 0.5, "exit_price": 191.20, "r": 1.913, "reason": "tp1_runner_tp2"}])
STALL = dict(status="CLOSED", entry_price=182.40, legs_realized=[
    TP1_LEG, {"fraction": 0.5, "exit_price": 187.00, "r": 1.0, "reason": "tp1_runner_progress_stall"}])
DUE = {"cover_fraction": 1.0, "auction_time": "2026-10-16T16:00:00-04:00", "late": False,
       "notice_id": f"{PID}:time_exit_due:2026-10-16"}


def _closed(reason: str, exit_price: float, stop: float) -> tuple:
    return ("closed", {"reason": reason, "exit_price": exit_price, "session": "regular",
                       "notified_stop": stop, "bot_stop": stop})


#: (name, plan overrides, event (transition, detail) or None for a ticket,
#:  ticket logged?, the linked record's realized_pnl_amount)
SAMPLES = [
    ("ticket place long", {}, None, True, None),
    ("ticket place short", SHORT, None, True, None),
    ("ticket do-not-place", {}, None, False, None),
    ("filled", FILLED, ("filled", {"entry_price": 182.40}), None, None),
    ("be_moved", {**FILLED, "working_stop": 182.40}, ("be_moved", {"working_stop": 182.40}), None, None),
    ("tp1_partial", PARTIAL, ("tp1_partial", {**TP1_LEG, "working_stop": 182.40}), None, None),
    ("stop_moved", {**PARTIAL, "working_stop": 186.0},
     ("stop_moved", {"new": 186.0, "r_moved": 0.78}), None, None),
    ("closed win", CLOSED_WIN, _closed("tp1_runner_tp2", 191.20, 186.0), None, 421.21),
    ("closed loss", CLOSED_LOSS, _closed("loss", 177.80, 177.80), None, -250.01),
    ("closed unsettled", CLOSED_LOSS, _closed("loss", 177.80, 177.80), None, None),
    ("close at market", STALL, _closed("tp1_runner_progress_stall", 187.00, 186.0), None, 307.08),
    ("cancel expired", {"status": "CANCELLED"}, ("cancelled_expired", {"bars_waited": 5}), None, None),
    ("cancel invalidated", {"status": "CANCELLED"}, ("cancelled_invalidated", {}), None, None),
    ("time exit due", {**SHORT, "status": "ACTIVE", "entry_price": 50.0},
     ("time_exit_due", DUE), None, None),
]


def _plan(**kw):
    from swingbot.core.planning.plan_types import TradePlanV2
    base = dict(plan_id=PID, ticker="AAPL", created_at="2026-10-14", source="strategy",
                strategy="Fibonacci", horizon_key="2w", direction="bullish",
                entry_type="stop_entry", trigger_price=182.40, entry_price=None, expiry_bars=5,
                stop_loss=177.80, tp1=189.10, tp1_fraction=0.5, tp2=195.00,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.0, quality_score=70,
                quality_breakdown=[], badge="VALIDATED", badge_stats={}, status="PENDING",
                status_history=[])
    base.update(kw)
    return TradePlanV2(**base)


def _item(logged: bool):
    return types.SimpleNamespace(
        paper_logged=logged, not_logged_reason=None if logged else "portfolio heat cap reached",
        heat_blocked=None, cluster_blocked=None, kill_switch_blocked=None,
        conf=types.SimpleNamespace(level=4))


def _render(plan_kw: dict, event, logged, realized) -> str:
    from swingbot.core.planning.plan_manager import PlanEvent
    from swingbot.core.scanning import execution_embeds as ee
    plan = _plan(**plan_kw)
    ee._sizing_snapshot = lambda entry, p: dict(SIZING)
    if hasattr(ee, "_linked_trade"):
        record = {"plan_id": PID, "shares": SIZING["shares"], "status": "open",
                  "entry": plan.entry_price or plan.trigger_price, "realized_pnl_amount": realized}
        ee._linked_trade = lambda plan_id: record
    embed = (ee.build_ticket_embed(_item(logged), plan) if event is None
             else ee.build_instruction_embed(plan, PlanEvent(PID, *event)))
    return "\n".join([f"content: {getattr(embed, 'push_text', None) or '-'}",
                      f"title: {embed.title}", embed.description or ""])


def _buttons() -> str | None:
    """The feed panel's labels after v170; None before (no feed_view)."""
    from swingbot.commands import views
    if not hasattr(views, "feed_view"):
        return None

    async def build():
        return [type(item).LABEL for item in views.feed_view(PID).children]
    return " · ".join(asyncio.run(build()))


def _snapshot(root: Path) -> dict:
    sys.path.insert(0, str(root))
    from swingbot import config
    if not Path(config.__file__).resolve().is_relative_to(root):
        sys.exit(f"imported swingbot from {config.__file__}, not from {root}")
    config.CURRENCY_SYMBOL = "$"
    samples = {}
    for name, plan_kw, event, logged, realized in SAMPLES:
        try:
            samples[name] = _render(plan_kw, event, logged, realized)
        except Exception as exc:          # one broken kind must not hide the others
            samples[name] = f"RENDER ERROR: {type(exc).__name__}: {exc}"
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    return {"root": str(root), "head": head, "samples": samples, "buttons": _buttons()}


def _merge(before_path: str, after_path: str, out_path: str) -> None:
    before, after = (json.loads(Path(p).read_text(encoding="utf-8")) for p in (before_path, after_path))
    lines = ["# v170 execution feed: before/after render", "",
             f"Before: `{before['head']}` (main). After: `{after['head']}` (v170 branch). "
             "Same fixtures both sides (`scripts/dev/render_feed_samples.py`): sizing 54.35 sh, "
             "risk $250; after v170 also a linked paper record of 54.35 sh.", "",
             f"Buttons on every plan-backed feed message after v170: {after['buttons'] or 'none'}. "
             "Before: none.", ""]
    for name, text in after["samples"].items():
        lines += [f"## {name}", "", "Before:", "", "~~~", before["samples"].get(name, "(absent)"),
                  "~~~", "", "After:", "", "~~~", text, "~~~", ""]
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path)
    parser.add_argument("--json")
    parser.add_argument("--merge", nargs=2, metavar=("BEFORE", "AFTER"))
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.merge:
        _merge(*args.merge, args.out)
        return
    snapshot = _snapshot(args.root.resolve())
    Path(args.json).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
