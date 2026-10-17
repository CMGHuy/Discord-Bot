# v170 Simple alerts: money beside R, symbol labels, plan buttons. Part 4: render gate and full suite

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: `grep -n "^### Task V170-14" -A 300 <this file>`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v170-simple-alerts-money-symbols-buttons-design.md`](../specs/2026-10-16-v170-simple-alerts-money-symbols-buttons-design.md)
**Index:** [`2026-10-16-v170-simple-alerts-money-symbols-buttons_0-index.md`](2026-10-16-v170-simple-alerts-money-symbols-buttons_0-index.md): `## Where to work` (worktree `$WT`, main tree `$R`, test database), `## Global Constraints`, `## Decisions taken while planning`, `## Parallelisation` and the `## Task ledger` all apply. Read them before starting.
**Bump:** minor
**Edge:** none (integrity)

This part holds only the plan's final task, V170-14. It was split from part 3 (`..._3-buttons-render.md`, V170-10..V170-13) because the two together pass the 1500-line cap. It runs after **every** other task (V170-1..V170-13).

# Phase 6 (continued): render gate and full suite

### Task V170-14: Radon sweep, before/after render results note, full suite once

**Model:** sonnet — a dev render script against two trees, a written review of the rendered surface, and dispatching the one full-suite run; judgement on the render, no production code.

**Files:**
- Create: `scripts/dev/render_feed_samples.py`
- Create: `docs/superpowers/results/2026-10-16-v170-feed-before-after.md`

**Interfaces:**
- Consumes: the public builders, unchanged in signature before and after v170: `execution_embeds.build_ticket_embed(item, plan)`, `execution_embeds.build_instruction_embed(plan, event)`; the seams `execution_embeds._sizing_snapshot(entry, plan)` (both trees) and `execution_embeds._linked_trade(plan_id)` (after only, V170-4); `views.feed_view(plan_id)` (after only, V170-11); `plan_types.TradePlanV2`, `plan_manager.PlanEvent(plan_id, transition, detail)`.
- Produces: the committed results note (the alert-surface gate, spec § Testing) and the green full-suite run that closes the plan. Nothing later consumes code from it.

Rules (spec § Testing, Global Constraints, index Decision 9): a rendered before/after for **every** feed message kind (ticket place long and short, ticket do-not-place, filled, be_moved, tp1_partial, stop_moved, closed win, closed loss, closed unsettled, close at market, cancel, time exit due) is committed as a results note; **a green suite alone does not pass this gate**. The script touches no Discord, network or database: sizing and the linked record are monkeypatched. `radon cc` over every file the plan touched shows no function the plan wrote or changed at 15 or above. One full suite, dispatched to the `test-runner` subagent; a failure is fixed and re-run alone, never by re-running the suite.

- [ ] **Step 0: Everything landed, test database up**

```bash
git -C $WT log --oneline main..HEAD
git -C $WT grep -n "def feed_view\|def reply_for\|def quote_trade\|def pnl_line\|def trade_for_plan\|def push_kwargs(embed, view=None)\|feed_legend()" -- swingbot
```

Expected: one or more commits per task V170-1..V170-13, and every symbol found (`feed_legend()` in both `tokens.py` and `info.py`). Anything missing: stop, `BLOCKED: V170-<n> not landed`.

Run the index's DB check (`docker compose -f E:/Documents/Private/Projects/Discord-Bot/docker-compose.yml --profile test up -d db-test`, then `docker ps --filter name=swing-db-test`). The full suite needs it: DB-backed tests skip without it, and a skip there is not green.

- [ ] **Step 1: Write the render script**

Create `$WT/scripts/dev/render_feed_samples.py`:

```python
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
```

- [ ] **Step 2: Render both trees and merge**

`$TMP` is your session scratchpad directory (outside both trees). Each run is a fresh process, so the `--root` tree's `swingbot` is the one imported:

```bash
python $WT/scripts/dev/render_feed_samples.py --root E:/Documents/Private/Projects/Discord-Bot --json $TMP/v170-before.json
python $WT/scripts/dev/render_feed_samples.py --root $WT --json $TMP/v170-after.json
python $WT/scripts/dev/render_feed_samples.py --merge $TMP/v170-before.json $TMP/v170-after.json --out $WT/docs/superpowers/results/2026-10-16-v170-feed-before-after.md
grep -c "RENDER ERROR" $TMP/v170-before.json $TMP/v170-after.json
```

Expected: the last command prints `0` for both files. A `RENDER ERROR` in the **after** file is a bug in the task that owns that builder: fix it there (with its test), re-run that task's narrow test file, then re-render. One in the **before** file means a fixture the old code cannot take: adjust the fixture, never the old code.

- [ ] **Step 3: Review the after column and record the checks**

Invoke the `alert-surface` skill, then read every `After:` block against spec §1-§2 (with §4 A3/A9) and append to the results note:

```markdown
## Checks (alert-surface gate)

- [ ] Ticket long: `▶ BUY STOP 182.40 · 54 sh`; stop line `🛑 SELL STOP 177.80 · if hit -$248.40 · −1.0R` (54 × −4.60); TP1 `💰 SELL LIMIT 189.10 · 27 sh · if hit +$180.90` (27 × 6.70); runner line `🏃 27 sh: 🎯 SELL LIMIT 195.00 · if hit +$340.20 · +2.7R · 〜 trail 2×ATR, stop moves pinged here` (27 × 12.60; the trail has no $); `⚖` and `⏳ CANCEL` / `⛔ CANCEL` lines present.
- [ ] Ticket short flips every verb (`SELL STOP` entry, `BUY STOP` stop, `BUY LIMIT` targets) and the comparison glyphs (`⛔ CANCEL if ≥`, `⚖ … ≤`).
- [ ] Do-not-place ticket keeps its wording and shows no "if hit" $.
- [ ] Filled leads `▶ FILLED`; be_moved and stop_moved say `MOVE SELL STOP` and carry `🔒 if it fills: … total`; never "locked".
- [ ] TP1 partial: `💰 TP1 FILLED 27 sh @ 189.10 · 🧾 +$182.07 · +1.5R` (record arithmetic 54.35 × 0.5 × 6.70), then `🛑 MOVE SELL STOP on the runner → 182.40 now (runner floor)`.
- [ ] Closed win / loss: headlines `✅ EXITED @ 191.20 · 🎯 TP2` / `❌ EXITED @ 177.80 · 🛑 stop`, then `🧾 +$421.21 · … (paper, gross)` / `🧾 -$250.01 · −1.0R (paper, gross)` (the record's settled amount, not a recomputation).
- [ ] Closed unsettled: `🧾 −1.0R (paper, gross)`, no $.
- [ ] Close at market and time exit due: broker verb words on every order line; wording otherwise unchanged from Before.
- [ ] Cancels: `CANCEL` on every cancel line; `⏳` leads the expiry cancel, `⛔` the invalidation cancel.
- [ ] The `content:` (push-preview) line of every kind is identical Before and After (`kinds.py` untouched).
- [ ] `⚠` appears only in warnings; no glyph is used for two meanings.
```

Tick each box only after reading it in the After block. A box that fails is a defect in its owning task (V170-3 ticket, V170-4 lifecycle, V170-5 close): fix it there with a test, re-run that test file, re-render (Step 2), re-check. The note is committed with every box ticked; the figures in the boxes are the fixtures' expected values, so a different figure is a failure, not a note.

- [ ] **Step 4: Radon sweep over every file the plan touched**

```bash
python -m radon cc -s -n C $WT/swingbot/core/presentation/tokens.py $WT/swingbot/core/scanning/plan_table.py $WT/swingbot/core/tracking/performance.py $WT/swingbot/core/presentation/instructions.py $WT/swingbot/core/scanning/execution_embeds.py $WT/swingbot/core/presentation/components.py $WT/swingbot/core/scanning/scan_run.py $WT/swingbot/commands/pnl_now.py $WT/swingbot/commands/views.py $WT/swingbot/commands/scanning/alerts.py $WT/swingbot/core/scanning/lifecycle_embeds.py $WT/swingbot/commands/info.py $WT/scripts/dev/render_feed_samples.py
```

Expected: only legacy functions no v170 task changed, at their pre-v170 grades: `TradeLog.update_open_trades` (E 31), `TradeLog.check_near_tp_timeout` (F 42), `_sync_run_scan` (F 100), `build_closed_trade_embed` (C 17), `breakdown_embed` (C 12), plus any other function `git -C $WT diff main -- <file>` shows untouched. `instruction_for` and `notify_plan_events` do not appear at C 13 or above (both were C 13 before v170). Any function a v170 commit wrote or changed at 15 or above: split it into named helpers in its owning task's file (behaviour unchanged, `code-complexity.md`), re-run that task's test file, re-run this step.

Record the sweep's output (the lines it printed) under a `## Complexity` heading at the end of the results note.

- [ ] **Step 5: The one full-suite run**

Dispatch the `test-runner` subagent with: run `python $WT/scripts/dev/testrun.py full` (with `TEST_DATABASE_URL` exported if the test DB is not on port `55432`); report `passed`, `failed`, `xfailed`, `skipped` and the skip reasons for any file under `tests/tracking/`, `tests/planning/` or `tests/scanning/`.

Expected: `0 failed`, `0 xfailed`, and no skip whose reason is an unreachable database. A changed pass count is not a failure (`testing-cost.md`). A failure: fix it in its owning task's files and re-run **that test alone** (`python $WT/scripts/dev/testrun.py file <test>`), never the suite again. Record the result line (counts and duration) under `## Full suite` at the end of the results note.

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/dev/render_feed_samples.py docs/superpowers/results/2026-10-16-v170-feed-before-after.md
git -C $WT commit -m "docs(v170): feed before/after render, radon sweep, full suite

Every execution-feed message kind rendered on main and on the branch
from the same fixtures, read against the spec layouts; complexity and
the one full-suite run recorded.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command shows the main tree unchanged.

- [ ] **Step 7: Hand back**

Report to the controller: the results note path, the full-suite counts, and that the plan is ready for `/panel veteran-trader,financial-advisor,senior-engineer` over the branch diff (the spec's `Panel:` line, run before close-out) and then `/close-out` (bot minor bump; no task edited `VERSION.json`). Do not merge, bump or close out from this task.
